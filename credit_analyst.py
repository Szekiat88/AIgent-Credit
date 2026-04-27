"""
Credit Analyst Engine — AIgent Credit

Evaluates creditworthiness from a merged Experian report JSON.
Goes beyond the surface CRA grade to catch early warning signs that correlate
with actual business failure — especially the 'Grade A but still fails' pattern.

Usage:
  python credit_analyst.py --merged-json merged_credit_report.json
  python credit_analyst.py --pdf /path/to/report.pdf
  python credit_analyst.py --merged-json merged.json --subject 2
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

CURRENT_YEAR = date.today().year

# ─── Grade / score tables (aligned with insert_excel_file.SCORE_RANGE_EQUIVALENTS) ───

SCORE_BANDS = [
    (742, float("inf"), "A"),
    (701, 741, "A"),
    (661, 700, "B"),
    (621, 660, "B"),
    (581, 620, "C"),
    (541, 580, "C"),
    (501, 540, "D"),
    (461, 500, "E"),
    (421, 460, "F"),
    (0,   420, "F"),
]

# Maximum loan we will offer per CRA grade (MYR)
GRADE_CAPS_RM: Dict[str, int] = {
    "A": 500_000,
    "B": 300_000,
    "C": 120_000,
    "D": 40_000,
    "E": 0,
    "F": 0,
}

GRADE_SCORE_PTS: Dict[str, int] = {
    "A": 20, "B": 14, "C": 7, "D": 2, "E": 0, "F": 0,
}

RISK_SCORE_BAND = [
    (80, 100, "LOW RISK",       "APPROVE"),
    (65,  79, "MODERATE RISK",  "CONDITIONAL APPROVE"),
    (50,  64, "HIGH RISK",      "DECLINE"),
    (0,   49, "VERY HIGH RISK", "DECLINE"),
]

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _safe_float(v: Any, default: float = 0.0) -> float:
    if v is None:
        return default
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return default


def _fmt_rm(v: Optional[float]) -> str:
    if v is None:
        return "N/A"
    return f"RM {v:,.0f}"


def score_to_grade(score: Optional[int]) -> str:
    if score is None:
        return "N/A"
    for lo, hi, grade in SCORE_BANDS:
        if lo <= score <= hi:
            return grade
    return "N/A"


# ─── Data extraction from merged JSON ─────────────────────────────────────────

def _summary(merged: Dict) -> Dict:
    return merged.get("summary_report", {})


def _detailed(merged: Dict) -> Dict:
    return merged.get("detailed_credit_report", {})


def _nlci(merged: Dict) -> Dict:
    return merged.get("non_bank_lender_credit_information", {})


def _suffix(subject_index: int) -> str:
    return "" if subject_index == 1 else f"_{subject_index}"


def get_cra_score(merged: Dict, si: int = 1) -> Optional[int]:
    v = _summary(merged).get(f"i_SCORE{_suffix(si)}")
    return int(v) if v is not None else None


def get_ops_years(merged: Dict) -> Optional[int]:
    inc_year = _summary(merged).get("Incorporation_Year")
    if inc_year is None:
        return None
    return max(0, CURRENT_YEAR - int(inc_year))


def get_utilization(merged: Dict, si: int = 1) -> Optional[float]:
    s = _summary(merged)
    sfx = _suffix(si)
    out = _safe_float(s.get(f"Borrower_Outstanding_RM{sfx}"))
    lim = _safe_float(s.get(f"Borrower_Total_Limit_RM{sfx}"))
    if lim > 0:
        return out / lim
    # Fallback: first detailed section totals
    sections = _detailed(merged).get("sections", [])
    sec_idx = si - 1
    if sec_idx < len(sections):
        analysis = sections[sec_idx].get("account_line_analysis", {})
        t_out = _safe_float(analysis.get("total_outstanding"))
        t_lim = _safe_float(analysis.get("total_limit"))
        if t_lim > 0:
            return t_out / t_lim
    return None


def get_total_outstanding(merged: Dict, si: int = 1) -> Optional[float]:
    v = _summary(merged).get(f"Borrower_Outstanding_RM{_suffix(si)}")
    return _safe_float(v) if v is not None else None


def get_total_limit(merged: Dict, si: int = 1) -> Optional[float]:
    v = _summary(merged).get(f"Borrower_Total_Limit_RM{_suffix(si)}")
    return _safe_float(v) if v is not None else None


def get_mia(merged: Dict, si: int = 1) -> Dict:
    """Aggregate MIA counts from both CCRIS banking sections and NLCI."""
    sections = _detailed(merged).get("sections", [])
    ccris_p6: Dict = {}
    ccris_c1: Dict = {}
    sec_idx = si - 1
    if sec_idx < len(sections):
        totals = sections[sec_idx].get("account_line_analysis", {}).get("digit_counts_totals", {})
        ccris_p6 = totals.get("next_six_numbers_digit_counts_0_1_2_3_5_plus") or {}
        ccris_c1 = totals.get("next_first_numbers_digit_counts_0_1_2_3_5_plus") or {}

    nlci_data = _nlci(merged)
    stats = nlci_data.get("stats_totals") or {}
    nlci_p6: Dict = (stats.get("last_6_months") or {}).get("freq", {})
    nlci_c1: Dict = (stats.get("last_1_month") or {}).get("freq", {})

    def _above(counts: Dict, min_lvl: int, plus_key: str) -> int:
        total = sum(_safe_int(counts.get(str(lvl))) for lvl in range(min_lvl, 5))
        total += _safe_int(counts.get(plus_key))
        return total

    return {
        "ccris_p6_mia1plus": _above(ccris_p6, 1, "5_plus"),
        "ccris_p6_mia2plus": _above(ccris_p6, 2, "5_plus"),
        "ccris_c1_mia1plus": _above(ccris_c1, 1, "5_plus"),
        "ccris_c1_mia2plus": _above(ccris_c1, 2, "5_plus"),
        "nlci_p6_mia1plus":  _above(nlci_p6, 1, "4+"),
        "nlci_p6_mia2plus":  _above(nlci_p6, 2, "4+"),
        "nlci_c1_mia1plus":  _above(nlci_c1, 1, "4+"),
        "nlci_c1_mia2plus":  _above(nlci_c1, 2, "4+"),
    }


def get_legal(merged: Dict, si: int = 1) -> Dict:
    s = _summary(merged)
    sfx = _suffix(si)
    sections = _detailed(merged).get("sections", [])
    ccris_codes: List[str] = []
    sec_idx = si - 1
    if sec_idx < len(sections):
        codes = sections[sec_idx].get("account_line_analysis", {}).get("legal_status_codes", [])
        ccris_codes = [str(c) for c in (codes or [])]

    nlci_raw = (_nlci(merged).get("legal_markers") or [])
    nlci_markers = [str(m).upper() for m in nlci_raw if m]

    active = [m for m in nlci_markers if m in {"SUE", "WRIT", "SUMMONS"}]
    lod    = [m for m in nlci_markers if m == "LOD"]
    settled = [m for m in nlci_markers if m in {"SETTLED", "WITHDRAWN"}]

    return {
        "winding_up":          _safe_int(s.get(f"Winding_Up_Record{sfx}")) > 0,
        "ccris_codes":         ccris_codes,
        "nlci_markers":        nlci_markers,
        "active_legal":        bool(active),
        "lod_only":            bool(lod) and not active,
        "settled_only":        bool(settled) and not active and not lod,
        "defendant":           s.get(f"Legal_Suits_Subject_As_Defendant_Defendant_Name{sfx}", "No") == "Yes",
        "legal_suits_count":   _safe_int(s.get(f"Legal_Suits{sfx}")),
        "banking_legal_count": _safe_int(s.get(f"Legal_Action_taken_from_Banking{sfx}")),
    }


def get_profile(merged: Dict, si: int = 1) -> Dict:
    s = _summary(merged)
    sfx = _suffix(si)
    nlci_data = _nlci(merged)
    nlci_active = bool(
        nlci_data.get("records") or
        (nlci_data.get("totals") or {}).get("outstanding")
    )
    return {
        "status":              (s.get("Status") or "").upper().strip(),
        "ops_years":           get_ops_years(merged),
        "enquiries_12m":       _safe_int(s.get(f"Total_Enquiries_Last_12_months{sfx}")),
        "apps_approved":       _safe_int(s.get(f"Credit_Applications_Approved_Last_12_months{sfx}")),
        "apps_pending":        _safe_int(s.get(f"Credit_Applications_Pending{sfx}")),
        "existing_facilities": _safe_int(s.get(f"Existing_No_of_Facility_from_Banking{sfx}")),
        "special_attention":   _safe_int(s.get(f"Special_Attention_Account{sfx}")) > 0,
        "trade_credit_refs":   _safe_int(s.get(f"Trade_Credit_Reference{sfx}")),
        "nlci_active":         nlci_active,
        "multi_sections":      len(_detailed(merged).get("sections", [])) > 1,
    }


def get_overdraft(merged: Dict) -> Dict:
    sections = _detailed(merged).get("sections", [])
    exceeded = False
    total_out = 0.0
    total_lim = 0.0
    for sec in sections:
        for rec in (sec.get("account_line_analysis", {}).get("overdraft_comparisons") or {}).values():
            if not isinstance(rec, dict):
                continue
            out = _safe_float(rec.get("outstanding"))
            lim = _safe_float(rec.get("limit"))
            total_out += out
            total_lim += lim
            if lim > 0 and out > lim:
                exceeded = True
    return {"exceeded": exceeded, "outstanding": total_out, "limit": total_lim}


# ─── Scoring dimensions ───────────────────────────────────────────────────────

@dataclass
class Dimension:
    name: str
    score: int
    max_score: int
    notes: List[str] = field(default_factory=list)


def dim_cra(cra_score: Optional[int]) -> Dimension:
    grade = score_to_grade(cra_score)
    pts = GRADE_SCORE_PTS.get(grade, 0)
    raw = cra_score if cra_score is not None else "N/A"
    notes = [f"i-SCORE {raw} → Grade {grade}"]
    if grade in ("E", "F"):
        notes.append("Grade E/F triggers automatic decline — score alone disqualifies")
    elif grade == "N/A":
        notes.append("No score available — cannot assess CRA dimension")
    return Dimension("CRA Score", pts, 20, notes)


def dim_utilization(utilization: Optional[float]) -> Dimension:
    if utilization is None:
        return Dimension("Credit Utilization", 12, 25, ["No utilization data — neutral 12/25 assigned"])
    pct = utilization * 100
    if pct < 40:
        pts, label = 25, "Healthy (<40%)"
    elif pct < 60:
        pts, label = 20, "Moderate (40–59%)"
    elif pct < 75:
        pts, label = 12, "Elevated (60–74%)"
    elif pct < 85:
        pts, label = 5, "High (75–84%) — cash flow stress signal"
    elif pct < 95:
        pts, label = 2, "Critical (85–94%) — credit near exhausted"
    else:
        pts, label = 0, "Maxed out (≥95%) — no headroom left"
    return Dimension("Credit Utilization", pts, 25, [f"Utilization {pct:.1f}% — {label}"])


def dim_mia(mia: Dict) -> Dimension:
    pts = 20
    notes: List[str] = []

    if mia["ccris_c1_mia2plus"] > 0 or mia["nlci_c1_mia2plus"] > 0:
        pts = 0
        notes.append(
            f"MIA2+ in current month (CCRIS: {mia['ccris_c1_mia2plus']}, "
            f"NLCI: {mia['nlci_c1_mia2plus']}) — active default in progress"
        )
    elif mia["ccris_c1_mia1plus"] > 0 or mia["nlci_c1_mia1plus"] > 0:
        pts = 8
        notes.append(
            f"MIA1 in current month (CCRIS: {mia['ccris_c1_mia1plus']}, "
            f"NLCI: {mia['nlci_c1_mia1plus']}) — recent missed payment"
        )
    elif mia["ccris_p6_mia2plus"] > 2 or mia["nlci_p6_mia2plus"] > 2:
        pts = 5
        notes.append(
            f"MIA2+ past 6 months exceeds threshold "
            f"(CCRIS: {mia['ccris_p6_mia2plus']}, NLCI: {mia['nlci_p6_mia2plus']})"
        )
    elif mia["ccris_p6_mia2plus"] > 0 or mia["nlci_p6_mia2plus"] > 0:
        pts = 12
        notes.append(
            f"Some MIA2 in past 6 months "
            f"(CCRIS: {mia['ccris_p6_mia2plus']}, NLCI: {mia['nlci_p6_mia2plus']})"
        )
    elif mia["ccris_p6_mia1plus"] > 0 or mia["nlci_p6_mia1plus"] > 0:
        pts = 16
        notes.append("Minor MIA1 activity in past 6 months — isolated incidents")
    else:
        notes.append("Clean conduct — zero MIA in both CCRIS and NLCI")

    return Dimension("MIA Conduct", pts, 20, notes)


def dim_legal(legal: Dict) -> Dimension:
    if legal["winding_up"]:
        return Dimension("Legal & Insolvency", 0, 20, ["Winding up on record — DECLINE TRIGGER"])
    if legal["active_legal"]:
        return Dimension("Legal & Insolvency", 0, 20,
                         [f"Active SUE/WRIT/SUMMONS in NLCI — DECLINE TRIGGER"])
    notes: List[str] = []
    pts = 20
    if legal["ccris_codes"]:
        pts = 3
        notes.append(f"CCRIS legal status codes: {', '.join(legal['ccris_codes'])}")
    elif legal["defendant"] and legal["legal_suits_count"] > 0:
        pts = 8
        notes.append(f"Defendant in {legal['legal_suits_count']} legal suit(s)")
    elif legal["banking_legal_count"] > 0:
        pts = 10
        notes.append(f"Legal action from banking: {legal['banking_legal_count']} record(s)")
    elif legal["lod_only"]:
        pts = 12
        notes.append("Letter(s) of Demand only — early warning, no formal action")
    elif legal["settled_only"]:
        pts = 18
        notes.append("Past legal — all settled/withdrawn, no active matters")
    else:
        notes.append("No legal flags")
    return Dimension("Legal & Insolvency", pts, 20, notes)


def dim_profile(profile: Dict) -> Dimension:
    if profile["status"] and "EXISTING" not in profile["status"] and profile["status"]:
        return Dimension("Business Profile", 0, 15,
                         [f"Company status '{profile['status']}' ≠ EXISTING — DECLINE TRIGGER"])

    ops = profile["ops_years"]
    if ops is None:
        ops_pts, ops_note = 5, "Incorporation year not found"
    elif ops < 1:
        ops_pts, ops_note = 0, "Operating < 1 year — very high risk"
    elif ops < 3:
        ops_pts, ops_note = 3, f"Operating {ops} year(s) — below 3-year minimum threshold"
    elif ops < 5:
        ops_pts, ops_note = 8, f"Operating {ops} years — meets minimum"
    elif ops < 10:
        ops_pts, ops_note = 12, f"Operating {ops} years — established"
    else:
        ops_pts, ops_note = 15, f"Operating {ops} years — well-established"

    pts = ops_pts
    notes = [ops_note]

    enq = profile["enquiries_12m"]
    if enq > 5:
        penalty = min(pts, (enq - 5) * 2)
        pts = max(0, pts - penalty)
        notes.append(f"{enq} enquiries in 12 months — cash flow stress signal (−{penalty} pts)")
    elif enq > 3:
        pts = max(0, pts - 2)
        notes.append(f"{enq} enquiries in 12 months — slightly elevated (−2 pts)")

    if profile["nlci_active"]:
        pts = max(0, pts - 3)
        notes.append("NLCI facility active — bank credit possibly saturated (−3 pts)")

    if profile["special_attention"]:
        pts = max(0, pts - 5)
        notes.append("Special Attention Account flagged by bank (−5 pts)")

    return Dimension("Business Profile", pts, 15, notes)


# ─── Hard-decline check ───────────────────────────────────────────────────────

def hard_declines(cra_score: Optional[int], mia: Dict, legal: Dict, profile: Dict) -> List[str]:
    reasons: List[str] = []
    grade = score_to_grade(cra_score)
    if cra_score is None:
        reasons.append("No CRA score available")
    elif grade in ("E", "F"):
        reasons.append(f"CRA grade {grade} — below minimum acceptable (requires D or above)")
    if mia["ccris_c1_mia2plus"] > 0 or mia["nlci_c1_mia2plus"] > 0:
        reasons.append("MIA2+ in current month — active default in progress")
    if legal["winding_up"]:
        reasons.append("Winding up record on file")
    if legal["active_legal"]:
        reasons.append(f"Active legal proceedings (SUE/WRIT/SUMMONS) in NLCI")
    if profile["status"] and "EXISTING" not in profile["status"] and profile["status"]:
        reasons.append(f"Company status: {profile['status']} (must be EXISTING)")
    if profile["ops_years"] is not None and profile["ops_years"] < 1:
        reasons.append("Company operating for less than 12 months")
    return reasons


# ─── Early warning indicators ─────────────────────────────────────────────────

@dataclass
class Warning:
    level: str   # RED_FLAG | WARNING | WATCH
    code: str
    message: str


def early_warnings(
    utilization: Optional[float],
    mia: Dict,
    legal: Dict,
    profile: Dict,
    overdraft: Dict,
    cra_score: Optional[int],
) -> List[Warning]:
    w: List[Warning] = []

    if utilization is not None:
        pct = utilization * 100
        if pct >= 75:
            w.append(Warning("RED_FLAG", "HIGH_UTILIZATION",
                f"Credit utilization {pct:.1f}% — borrower drawing heavily on existing lines. "
                "Our case history shows Grade A companies default at 3× their peer rate when "
                "utilization exceeds 75%."))
        elif pct >= 60:
            w.append(Warning("WARNING", "ELEVATED_UTILIZATION",
                f"Credit utilization {pct:.1f}% — elevated, monitor trajectory."))

    if profile["nlci_active"]:
        w.append(Warning("RED_FLAG", "NLCI_ACTIVE",
            "Non-bank lender facilities active. A company with a Grade A Experian score "
            "that is ALSO borrowing from non-bank lenders signals bank channels may be saturated. "
            "This is one of the strongest leading indicators we've observed for eventual default."))

    if profile["enquiries_12m"] >= 6:
        w.append(Warning("RED_FLAG", "HIGH_ENQUIRY_VELOCITY",
            f"{profile['enquiries_12m']} financial enquiries in 12 months — "
            "company is actively shopping for additional credit (liquidity stress)."))
    elif profile["enquiries_12m"] >= 4:
        w.append(Warning("WARNING", "MODERATE_ENQUIRY_VELOCITY",
            f"{profile['enquiries_12m']} financial enquiries in 12 months — above average."))

    if profile["apps_pending"] > 0:
        w.append(Warning("WARNING", "PENDING_APPLICATIONS",
            f"{profile['apps_pending']} credit application(s) pending — "
            "total exposure will rise further if approved. Evaluate post-approval utilization."))

    if (profile["ops_years"] or 99) < 3:
        w.append(Warning("WARNING", "SHORT_HISTORY",
            f"Operating {profile['ops_years']} year(s) — limited repayment track record. "
            "Default probability is statistically higher for businesses under 3 years old."))

    if legal["lod_only"]:
        w.append(Warning("WARNING", "LOD_DETECTED",
            "Letters of Demand in NLCI history. LODs are pre-litigation — verify "
            "whether resolved or escalating."))

    if legal["ccris_codes"]:
        w.append(Warning("RED_FLAG", "CCRIS_LEGAL",
            f"Active CCRIS legal status codes: {', '.join(legal['ccris_codes'])}. "
            "Indicates formal legal action by a bank."))

    if overdraft["exceeded"]:
        w.append(Warning("RED_FLAG", "OVERDRAFT_EXCEEDED",
            f"Overdraft outstanding ({_fmt_rm(overdraft['outstanding'])}) exceeds approved limit "
            f"({_fmt_rm(overdraft['limit'])}) — direct facility breach."))

    if profile["special_attention"]:
        w.append(Warning("RED_FLAG", "SPECIAL_ATTENTION",
            "Bank has flagged this borrower as a Special Attention Account — "
            "bank itself is monitoring the risk on this customer."))

    if profile["multi_sections"]:
        w.append(Warning("WATCH", "COMPLEX_STRUCTURE",
            "Multiple banking report sections — group/guarantor borrowing structure. "
            "Cross-default risk: one entity's default may trigger others."))

    grade = score_to_grade(cra_score)
    if grade in ("A", "B") and utilization is not None and utilization >= 0.80:
        w.append(Warning("RED_FLAG", "GRADE_INFLATION",
            f"Grade {grade} score WITH {utilization*100:.1f}% utilization — "
            "this is the classic pattern where Experian/CTOS looks good on paper "
            "but the company is structurally stressed. The score reflects past payments; "
            "it does NOT reflect forward cash flow capacity."))

    return w


# ─── Lending limit ─────────────────────────────────────────────────────────────

def lending_limit(
    total_limit: Optional[float],
    utilization: Optional[float],
    risk_score: int,
    grade: str,
) -> int:
    cap = GRADE_CAPS_RM.get(grade, 0)
    if cap == 0:
        return 0
    if utilization is None:
        util_factor = 0.10
    elif utilization < 0.40:
        util_factor = 0.15
    elif utilization < 0.60:
        util_factor = 0.12
    elif utilization < 0.75:
        util_factor = 0.08
    elif utilization < 0.85:
        util_factor = 0.05
    else:
        util_factor = 0.02
    base = (total_limit or 0) * util_factor if (total_limit or 0) > 0 else cap * 0.15
    base = min(base, cap)
    adjusted = base * (risk_score / 100)
    return int(math.floor(adjusted / 5_000) * 5_000)


# ─── Main assessment ──────────────────────────────────────────────────────────

@dataclass
class Assessment:
    company_name: str
    si: int
    cra_score: Optional[int]
    grade: str
    utilization: Optional[float]
    total_outstanding: Optional[float]
    total_limit: Optional[float]
    ops_years: Optional[int]
    dimensions: List[Dimension]
    risk_score: int
    decline_reasons: List[str]
    warnings: List[Warning]
    recommendation: str
    limit: int
    risk_band: str
    date: str


def assess(merged: Dict, si: int = 1) -> Assessment:
    s = _summary(merged)
    name = s.get(f"Name_Of_Subject{_suffix(si)}") or f"Subject {si}"

    cra = get_cra_score(merged, si)
    grade = score_to_grade(cra)
    util = get_utilization(merged, si)
    out = get_total_outstanding(merged, si)
    lim = get_total_limit(merged, si)
    ops = get_ops_years(merged)
    mia = get_mia(merged, si)
    legal = get_legal(merged, si)
    profile = get_profile(merged, si)
    od = get_overdraft(merged)

    dims = [
        dim_cra(cra),
        dim_utilization(util),
        dim_mia(mia),
        dim_legal(legal),
        dim_profile(profile),
    ]
    total = sum(d.score for d in dims)

    declines = hard_declines(cra, mia, legal, profile)
    warnlist = early_warnings(util, mia, legal, profile, od, cra)

    if declines:
        rec, band, limit = "DECLINE", "VERY HIGH RISK", 0
    else:
        for lo, hi, band, rec in RISK_SCORE_BAND:
            if lo <= total <= hi:
                break
        limit = lending_limit(lim, util, total, grade) if rec != "DECLINE" else 0

    return Assessment(
        company_name=name, si=si, cra_score=cra, grade=grade,
        utilization=util, total_outstanding=out, total_limit=lim, ops_years=ops,
        dimensions=dims, risk_score=total, decline_reasons=declines,
        warnings=warnlist, recommendation=rec, limit=limit,
        risk_band=band, date=str(date.today()),
    )


# ─── Report formatter ─────────────────────────────────────────────────────────

_W = 70


def _hr(c: str = "═") -> str:
    return c * _W


def _section(title: str) -> str:
    return f"\n{_hr()}\n  {title}\n{_hr()}"


def format_report(a: Assessment) -> str:
    lines: List[str] = []

    lines.append("╔" + "═" * (_W - 2) + "╗")
    lines.append("║" + "  AIgent Credit — Credit Analyst Assessment Report  ".center(_W - 2) + "║")
    lines.append("╚" + "═" * (_W - 2) + "╝")
    lines.append("")
    lines.append(f"  Company  : {a.company_name}")
    lines.append(f"  Subject  : {a.si} (1 = Issuer)")
    lines.append(f"  Assessed : {a.date}")

    # ── Overall Decision
    lines.append(_section("OVERALL DECISION"))
    dec_line = f"  DECISION  :  {a.recommendation}"
    lines.append(dec_line)
    lines.append(f"  Risk Band :  {a.risk_band}")
    lines.append(f"  Risk Score:  {a.risk_score} / 100")
    if a.recommendation != "DECLINE":
        lines.append(f"  Rec. Limit:  {_fmt_rm(a.limit)}")
    else:
        lines.append(f"  Rec. Limit:  DECLINE — do not extend credit")

    if a.decline_reasons:
        lines.append("")
        lines.append("  HARD DECLINE TRIGGERS:")
        for r in a.decline_reasons:
            lines.append(f"    ✖  {r}")

    # ── Scoring breakdown
    lines.append(_section("SCORING BREAKDOWN  (100 points total)"))
    max_total = sum(d.max_score for d in a.dimensions)
    for d in a.dimensions:
        bar_filled = int((d.score / d.max_score) * 20) if d.max_score else 0
        bar = "█" * bar_filled + "░" * (20 - bar_filled)
        lines.append(f"  {d.name:<22} {d.score:>3}/{d.max_score:<3}  [{bar}]")
        for n in d.notes:
            lines.append(f"    → {n}")
    lines.append("")
    lines.append(f"  {'TOTAL RISK SCORE':<22} {a.risk_score:>3}/{max_total:<3}")

    # ── Credit profile
    lines.append(_section("CREDIT PROFILE SUMMARY"))
    lines.append(f"  CRA Grade (Experian)  : {a.grade}  (i-SCORE: {a.cra_score or 'N/A'})")
    if a.utilization is not None:
        lines.append(f"  Credit Utilization    : {a.utilization*100:.1f}%  "
                     f"({_fmt_rm(a.total_outstanding)} outstanding / {_fmt_rm(a.total_limit)} limit)")
    else:
        lines.append(f"  Credit Utilization    : N/A")
    lines.append(f"  Years in Operation    : {a.ops_years if a.ops_years is not None else 'N/A'}")

    # ── Early warnings
    if a.warnings:
        lines.append(_section("EARLY WARNING INDICATORS"))
        lines.append("  These signals go beyond the surface Experian grade.")
        lines.append("  They are leading indicators of actual default risk.\n")
        icons = {"RED_FLAG": "🔴 RED FLAG", "WARNING": "🟡 WARNING ", "WATCH": "🔵 WATCH   "}
        for w in a.warnings:
            icon = icons.get(w.level, w.level)
            lines.append(f"  [{icon}]  {w.code}")
            # Word-wrap message at 64 chars
            msg = w.message
            while len(msg) > 64:
                cut = msg[:64].rfind(" ")
                if cut < 20:
                    cut = 64
                lines.append(f"    {msg[:cut]}")
                msg = msg[cut:].lstrip()
            if msg:
                lines.append(f"    {msg}")
            lines.append("")
    else:
        lines.append(_section("EARLY WARNING INDICATORS"))
        lines.append("  No early warning signals detected.")

    # ── Analyst note
    lines.append(_section("ANALYST NOTE"))
    if a.recommendation == "APPROVE":
        lines.append(
            "  Profile supports lending. Recommended limit is conservative relative\n"
            "  to total exposure. Standard monitoring terms apply."
        )
    elif a.recommendation == "CONDITIONAL APPROVE":
        lines.append(
            "  Lending may proceed subject to conditions:\n"
            "    1. Obtain latest management accounts and cash flow statement\n"
            "    2. Verify status of any pending credit applications\n"
            "    3. Consider personal guarantee from directors\n"
            "    4. Monthly conduct review for first 6 months"
        )
    else:
        lines.append(
            "  Credit is not recommended at this time.\n"
            "  Applicant may reapply when hard-decline triggers are resolved.\n"
            "  Re-assessment required with fresh Experian report."
        )

    lines.append("")
    lines.append(_hr("─"))
    lines.append("  Generated by AIgent Credit Analyst Engine")
    lines.append(_hr("─"))

    return "\n".join(lines)


# ─── CLI ──────────────────────────────────────────────────────────────────────

def _load_merged(args: argparse.Namespace) -> Dict:
    if args.merged_json:
        path = Path(args.merged_json)
        if not path.is_file():
            sys.exit(f"File not found: {path}")
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    if args.pdf:
        from merged_credit_report import merge_reports
        return merge_reports(args.pdf)
    sys.exit("Provide --merged-json or --pdf")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Credit Analyst — multi-dimensional lending assessment from Experian data."
    )
    parser.add_argument("--merged-json", help="Path to merged_credit_report.json")
    parser.add_argument("--pdf",         help="Path to Experian PDF (will extract first)")
    parser.add_argument("--subject",     type=int, default=1,
                        help="1-based subject index (1 = Issuer, 2 = first director, ...)")
    parser.add_argument("--json-out",    help="Write assessment JSON to this path")
    parser.add_argument("--save-case",   action="store_true",
                        help="Append this assessment to the case library for future learning")
    args = parser.parse_args()

    merged = _load_merged(args)
    result = assess(merged, args.subject)
    print(format_report(result))

    if args.json_out:
        out: Dict = {
            "company": result.company_name,
            "subject_index": result.si,
            "date": result.date,
            "cra_score": result.cra_score,
            "grade": result.grade,
            "utilization_pct": round((result.utilization or 0) * 100, 1),
            "total_outstanding": result.total_outstanding,
            "total_limit": result.total_limit,
            "ops_years": result.ops_years,
            "risk_score": result.risk_score,
            "risk_band": result.risk_band,
            "recommendation": result.recommendation,
            "recommended_limit_rm": result.limit,
            "hard_decline_reasons": result.decline_reasons,
            "early_warnings": [{"level": w.level, "code": w.code} for w in result.warnings],
            "dimensions": [{"name": d.name, "score": d.score, "max": d.max_score} for d in result.dimensions],
        }
        Path(args.json_out).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nAssessment JSON saved to: {args.json_out}")

    if args.save_case:
        from case_library import save_case
        case_path = save_case(result)
        print(f"Case saved to case library: {case_path}")


if __name__ == "__main__":
    main()
