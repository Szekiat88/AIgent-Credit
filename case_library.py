"""
Case Library — AIgent Credit

Records credit assessments with their actual loan outcomes.
Over time this builds empirical evidence of which signals actually predict
default in YOUR portfolio — not just what Experian scores claim.

Usage:
  python case_library.py list
  python case_library.py outcome <CASE_ID> --outcome GOOD
  python case_library.py insights
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

CASES_DIR = Path(__file__).parent / "cases"
OUTCOMES = ("GOOD", "DEFAULT", "PARTIAL_DEFAULT", "EARLY_SETTLEMENT")


def _cases_dir() -> Path:
    CASES_DIR.mkdir(exist_ok=True)
    return CASES_DIR


def save_case(result: Any) -> str:
    """Save an Assessment from credit_analyst.py to the case library. Returns file path."""
    case_id = str(uuid.uuid4())[:8]
    record = {
        "case_id": case_id,
        "date_assessed": result.date,
        "company_name": result.company_name,
        "subject_index": result.si,
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
        "early_warning_codes": [w.code for w in result.warnings],
        "dimensions": {d.name: {"score": d.score, "max": d.max_score} for d in result.dimensions},
        "actual_outcome": None,
        "outcome_date": None,
        "outcome_notes": "",
        "loan_amount_approved_rm": None,
    }
    path = _cases_dir() / f"case_{case_id}.json"
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(path)


def load_all_cases() -> List[Dict]:
    cases = []
    for f in sorted(_cases_dir().glob("case_*.json")):
        try:
            cases.append(json.loads(f.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            pass
    return cases


def record_outcome(
    case_id: str,
    outcome: str,
    notes: str = "",
    loan_amount: Optional[float] = None,
    outcome_date: Optional[str] = None,
) -> Optional[str]:
    """Update a case's actual outcome. Returns path or None if not found."""
    if outcome not in OUTCOMES:
        raise ValueError(f"outcome must be one of: {OUTCOMES}")
    for f in _cases_dir().glob(f"case_{case_id}*.json"):
        data = json.loads(f.read_text(encoding="utf-8"))
        data["actual_outcome"] = outcome
        data["outcome_date"] = outcome_date or str(date.today())
        data["outcome_notes"] = notes
        if loan_amount is not None:
            data["loan_amount_approved_rm"] = loan_amount
        f.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return str(f)
    return None


# ─── Insights ─────────────────────────────────────────────────────────────────

def _pct(n: int, d: int) -> str:
    if d == 0:
        return "N/A"
    return f"{100*n/d:.0f}%"


def compute_insights(cases: List[Dict]) -> str:
    resolved = [c for c in cases if c.get("actual_outcome") in ("GOOD", "DEFAULT", "PARTIAL_DEFAULT")]
    if not resolved:
        return "No resolved cases yet. Record actual loan outcomes to unlock insights."

    lines: List[str] = []
    W = 70

    lines.append("═" * W)
    lines.append("  CASE LIBRARY INSIGHTS — Empirical Default Patterns".center(W))
    lines.append(f"  Based on {len(resolved)} resolved cases out of {len(cases)} total".center(W))
    lines.append("═" * W)

    def defaults(subset: List[Dict]) -> int:
        return sum(1 for c in subset if c["actual_outcome"] in ("DEFAULT", "PARTIAL_DEFAULT"))

    # Default rate by CRA grade
    lines.append("\n  Default Rate by CRA Grade (what Experian claims vs what we observe):")
    lines.append(f"  {'Grade':<8}  {'Cases':>6}  {'Defaults':>9}  {'Default Rate':>13}  Note")
    lines.append("  " + "─" * 65)
    for grade in ("A", "B", "C", "D", "E", "F"):
        subset = [c for c in resolved if c.get("grade") == grade]
        if not subset:
            continue
        n = len(subset)
        d = defaults(subset)
        note = " ← grade inflation?" if grade in ("A", "B") and d/n > 0.20 else ""
        lines.append(f"  {grade:<8}  {n:>6}  {d:>9}  {_pct(d,n):>13}{note}")

    # Default rate by utilization band
    lines.append("\n  Default Rate by Credit Utilization at Time of Assessment:")
    bands = [("<40%", 0, 40), ("40–59%", 40, 60), ("60–74%", 60, 75),
             ("75–84%", 75, 85), ("≥85%", 85, 101)]
    for label, lo, hi in bands:
        subset = [c for c in resolved if lo <= (c.get("utilization_pct") or 0) < hi]
        if not subset:
            continue
        n = len(subset)
        d = defaults(subset)
        lines.append(f"  {label:<12}  {n:>6} cases  {d:>4} defaults  {_pct(d,n):>8}")

    # Default rate by NLCI presence
    lines.append("\n  Default Rate by Non-Bank Lender (NLCI) Presence:")
    for nlci_flag, label in [(True, "NLCI active"), (False, "NLCI absent")]:
        subset = [c for c in resolved if ("NLCI_ACTIVE" in (c.get("early_warning_codes") or [])) == nlci_flag]
        if not subset:
            continue
        n = len(subset)
        d = defaults(subset)
        lines.append(f"  {label:<20}  {n:>6} cases  {d:>4} defaults  {_pct(d,n):>8}")

    # Default rate by ops years band
    lines.append("\n  Default Rate by Years in Operation:")
    age_bands = [("<3 yrs", 0, 3), ("3–5 yrs", 3, 5), ("5–10 yrs", 5, 10), ("≥10 yrs", 10, 999)]
    for label, lo, hi in age_bands:
        subset = [c for c in resolved if c.get("ops_years") is not None and lo <= c["ops_years"] < hi]
        if not subset:
            continue
        n = len(subset)
        d = defaults(subset)
        lines.append(f"  {label:<20}  {n:>6} cases  {d:>4} defaults  {_pct(d,n):>8}")

    # Default rate by enquiry warning flag
    lines.append("\n  Default Rate by Enquiry Velocity Signal:")
    for flag, label in [
        ("HIGH_ENQUIRY_VELOCITY",     "High enquiry (6+/yr)   "),
        ("MODERATE_ENQUIRY_VELOCITY", "Moderate enquiry (4–5) "),
    ]:
        subset = [c for c in resolved if flag in (c.get("early_warning_codes") or [])]
        clean  = [c for c in resolved if flag not in (c.get("early_warning_codes") or [])
                  and "HIGH_ENQUIRY_VELOCITY" not in (c.get("early_warning_codes") or [])
                  and "MODERATE_ENQUIRY_VELOCITY" not in (c.get("early_warning_codes") or [])]
        if not subset:
            continue
        n = len(subset)
        d = defaults(subset)
        nc = len(clean)
        dc = defaults(clean)
        lines.append(f"  {label}  {n:>5} cases  {d:>4} defaults  {_pct(d,n):>8}"
                     f"   vs clean {_pct(dc,nc):>8}")

    lines.append("\n  Default Rate by Our Model Risk Score at Assessment:")
    score_bands = [("80–100 LOW",  80, 101), ("65–79 MOD", 65, 80),
                   ("50–64 HIGH",  50, 65),  ("<50 V.HIGH", 0, 50)]
    for label, lo, hi in score_bands:
        subset = [c for c in resolved if lo <= (c.get("risk_score") or 0) < hi]
        if not subset:
            continue
        n = len(subset)
        d = defaults(subset)
        lines.append(f"  {label:<20}  {n:>6} cases  {d:>4} defaults  {_pct(d,n):>8}")

    lines.append("\n" + "─" * W)
    lines.append("  To add more cases: python credit_analyst.py --merged-json X --save-case")
    lines.append("  To record outcomes: python case_library.py --record-outcome CASE_ID --outcome GOOD")
    lines.append("─" * W)
    return "\n".join(lines)


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Case Library — manage credit assessment history.")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("list", help="List all cases")
    sub.add_parser("insights", help="Show empirical default patterns from resolved cases")

    p_out = sub.add_parser("outcome", help="Record actual outcome for a case")
    p_out.add_argument("case_id", help="Case ID (from save output)")
    p_out.add_argument("--outcome", required=True, choices=OUTCOMES)
    p_out.add_argument("--notes",  default="", help="Optional notes")
    p_out.add_argument("--loan-amount", type=float, help="Actual loan amount approved (RM)")
    p_out.add_argument("--date", dest="outcome_date", help="Outcome date (YYYY-MM-DD)")

    args = parser.parse_args()

    if args.cmd == "list":
        cases = load_all_cases()
        if not cases:
            print("No cases in library yet.")
            return
        print(f"{'ID':<10}  {'Date':<12}  {'Company':<30}  {'Grade':<6}  {'Score':>5}  {'Rec':<22}  Outcome")
        print("─" * 110)
        for c in cases:
            print(
                f"{c['case_id']:<10}  {c['date_assessed']:<12}  "
                f"{(c['company_name'] or '')[:29]:<30}  {c['grade']:<6}  "
                f"{c['risk_score']:>5}  {c['recommendation']:<22}  "
                f"{c['actual_outcome'] or 'pending'}"
            )

    elif args.cmd == "insights":
        print(compute_insights(load_all_cases()))

    elif args.cmd == "outcome":
        path = record_outcome(
            args.case_id, args.outcome, args.notes, args.loan_amount, args.outcome_date
        )
        if path:
            print(f"Outcome recorded: {path}")
        else:
            sys.exit(f"Case ID '{args.case_id}' not found in {_cases_dir()}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
