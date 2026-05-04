"""
accuracy_tracker.py — Snapshot and compare accuracy results across training runs.

Workflow:
  1. python checker/training_manager.py run
  2. python checker/accuracy_tracker.py snapshot "baseline"
  3. (make changes)
  4. python checker/training_manager.py run
  5. python checker/accuracy_tracker.py snapshot "after-fix"
  6. python checker/accuracy_tracker.py compare "baseline" "after-fix"

Commands:
  snapshot <label>                 Save current results as a named snapshot
  compare  <before> <after>        Full side-by-side comparison (5 sections)
  compare  <before> <after> --changes-only   Show only changed fields
  list                             List all snapshots
  history                          Accuracy trend across all snapshots
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

_HERE     = Path(__file__).parent.resolve()   # checker/
_ROOT     = _HERE.parent                       # AuditorReportReader/
_SCORES   = _ROOT / "training" / "scores.json"
_RUNS_DIR = _ROOT / "training" / "runs"
_SNAP_DIR = _ROOT / "training" / "snapshots"

# Column widths
_W_CO     = 28
_W_FL     = 32
_W_PCT    =  8
_W_STATUS = 13


# ---------------------------------------------------------------------------
# Build + save snapshot
# ---------------------------------------------------------------------------

def _load_diff(run_dir: str) -> list[dict]:
    p = Path(run_dir) / "diff.json"
    if not p.exists():
        return []
    return json.loads(p.read_text()).get("fields", [])


def build_snapshot(label: str) -> dict:
    if not _SCORES.exists():
        raise FileNotFoundError(
            f"No scores file: {_SCORES}\n"
            "Run: python checker/training_manager.py run"
        )
    scores = json.loads(_SCORES.read_text())
    companies = {}
    total_matched = total_fields = 0

    for company, info in scores.items():
        companies[company] = {
            "score_pct":   info["score_pct"],
            "matched":     info["matched"],
            "total":       info["total"],
            "by_category": info.get("by_category", {}),
            "fields":      _load_diff(info.get("run_dir", "")),
        }
        total_matched += info["matched"]
        total_fields  += info["total"]

    overall = round(100.0 * total_matched / total_fields, 1) if total_fields else 0.0
    return {
        "label":         label,
        "timestamp":     datetime.now().isoformat(timespec="seconds"),
        "overall_score": overall,
        "total_matched": total_matched,
        "total_fields":  total_fields,
        "companies":     companies,
    }


def cmd_snapshot(label: str) -> None:
    _SNAP_DIR.mkdir(parents=True, exist_ok=True)
    snap = build_snapshot(label)
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = label.replace(" ", "-").replace("/", "-")
    dest = _SNAP_DIR / f"{safe}_{ts}.json"
    dest.write_text(json.dumps(snap, indent=2))
    print(f"[snapshot] Saved : {dest.name}")
    print(f"           Score : {snap['overall_score']}%")
    print(f"           Scope : {len(snap['companies'])} companies  |  "
          f"{snap['total_matched']}/{snap['total_fields']} fields matched")


# ---------------------------------------------------------------------------
# Load snapshot by partial label
# ---------------------------------------------------------------------------

def _find_snapshot(label: str) -> Path:
    if not _SNAP_DIR.exists() or not any(_SNAP_DIR.glob("*.json")):
        raise FileNotFoundError(
            "No snapshots found.\n"
            "Run: python checker/accuracy_tracker.py snapshot <label>"
        )
    files = sorted(_SNAP_DIR.glob("*.json"), reverse=True)
    low = label.lower()
    for f in files:
        if f.stem.lower().startswith(low + "_"):
            return f
    for f in files:
        if low in f.stem.lower():
            return f
    raise FileNotFoundError(
        f"No snapshot matching '{label}'.\n"
        "Run: python checker/accuracy_tracker.py list"
    )


def _load_snapshot(label: str) -> dict:
    return json.loads(_find_snapshot(label).read_text())


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _pct(v: float) -> str:
    return f"{v:6.1f}%"


def _delta(before: float, after: float) -> str:
    d = after - before
    if abs(d) < 0.05:
        return "  0.0%  ="
    sign  = "+" if d > 0 else ""
    arrow = "↑" if d > 0 else "↓"
    return f"{sign}{d:5.1f}%  {arrow}"


def _fmt_val(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, (int, float)):
        return f"{v:,.0f}"
    return str(v)


def _field_key(f: dict) -> str:
    return f"{f['year']}:{f['label']}"


def _aggregate_fields(companies: dict) -> dict:
    """Roll up per-field accuracy across all companies."""
    agg: dict[str, dict] = {}
    for info in companies.values():
        for f in info.get("fields", []):
            k = f["label"]
            if k not in agg:
                agg[k] = {"match": 0, "missing": 0, "wrong": 0, "total": 0}
            agg[k]["total"] += 1
            s = f.get("status", "")
            if s == "MATCH":        agg[k]["match"]   += 1
            elif s == "MISSING":    agg[k]["missing"]  += 1
            elif s == "WRONG_VALUE":agg[k]["wrong"]    += 1
    return agg


def _field_score(e: dict) -> float:
    return round(100.0 * e["match"] / e["total"], 1) if e["total"] else 0.0


# ---------------------------------------------------------------------------
# Compare — all 5 sections
# ---------------------------------------------------------------------------

def cmd_compare(lbl_b: str, lbl_a: str, changes_only: bool = False) -> None:
    snap_b = _load_snapshot(lbl_b)
    snap_a = _load_snapshot(lbl_a)

    ts_b, ts_a = snap_b["timestamp"][:10], snap_a["timestamp"][:10]
    n_b,  n_a  = len(snap_b["companies"]), len(snap_a["companies"])
    ob,   oa   = snap_b["overall_score"],  snap_a["overall_score"]

    # ── Section 1: Overall ───────────────────────────────────────────────────
    print()
    print("═" * 66)
    print("  ACCURACY COMPARISON")
    print(f"  Before : {snap_b['label']:<30} ({ts_b}  {ob}%  {n_b} co.)")
    print(f"  After  : {snap_a['label']:<30} ({ts_a}  {oa}%  {n_a} co.)")
    print("═" * 66)
    print()
    print(f"  OVERALL    {_pct(ob)}  →  {_pct(oa)}   Δ {_delta(ob, oa)}")
    print()

    # ── Section 2: Per-company ───────────────────────────────────────────────
    print("─" * 66)
    print("  BY COMPANY")
    print("─" * 66)
    print(f"  {'Company':<{_W_CO}}  {'Before':>{_W_PCT}}  {'After':>{_W_PCT}}   Δ")

    all_cos = sorted(set(snap_b["companies"]) | set(snap_a["companies"]))
    for co in all_cos:
        bi = snap_b["companies"].get(co)
        ai = snap_a["companies"].get(co)
        pb = bi["score_pct"] if bi else None
        pa = ai["score_pct"] if ai else None
        if pb is None:
            print(f"  {co:<{_W_CO}}  {'N/A':>{_W_PCT}}  {_pct(pa):>{_W_PCT}}   (new)")
        elif pa is None:
            print(f"  {co:<{_W_CO}}  {_pct(pb):>{_W_PCT}}  {'N/A':>{_W_PCT}}   (removed)")
        else:
            print(f"  {co:<{_W_CO}}  {_pct(pb):>{_W_PCT}}  {_pct(pa):>{_W_PCT}}   {_delta(pb, pa)}")
    print()

    # ── Section 3: Per-field aggregate ───────────────────────────────────────
    print("─" * 66)
    print("  BY FIELD  (aggregated across all companies)")
    print("─" * 66)
    print(f"  {'Field':<{_W_FL}}  {'Before':>{_W_PCT}}  {'After':>{_W_PCT}}   Δ")

    agg_b = _aggregate_fields(snap_b["companies"])
    agg_a = _aggregate_fields(snap_a["companies"])
    rows  = []
    for fl in sorted(set(agg_b) | set(agg_a)):
        sb = _field_score(agg_b[fl]) if fl in agg_b else None
        sa = _field_score(agg_a[fl]) if fl in agg_a else None
        if sb is None or sa is None:
            continue
        rows.append((fl, sb, sa, sa - sb))

    # Regressions first, then biggest gains, then unchanged
    rows.sort(key=lambda r: (0 if r[3] < -0.05 else (2 if abs(r[3]) < 0.05 else 1), -r[3]))
    has_regression = any(r[3] < -0.05 for r in rows)
    for fl, sb, sa, d in rows:
        print(f"  {fl:<{_W_FL}}  {_pct(sb):>{_W_PCT}}  {_pct(sa):>{_W_PCT}}   {_delta(sb, sa)}")

    if not has_regression:
        print("\n  Regressions: None  ✓")
    print()

    # ── Section 4: Full detail — every field × every company ─────────────────
    print("─" * 66)
    print("  FULL DETAIL  (every field × every company)")
    if changes_only:
        print("  [--changes-only: showing only fields that changed]")
    print("─" * 66)

    fixes       : list[dict] = []
    regressions : list[dict] = []

    for co in all_cos:
        b_info   = snap_b["companies"].get(co, {})
        a_info   = snap_a["companies"].get(co, {})
        b_fields = {_field_key(f): f for f in b_info.get("fields", [])}
        a_fields = {_field_key(f): f for f in a_info.get("fields", [])}

        # Preserve original field order; append any new fields at the end
        ordered_keys: list[str] = []
        seen: set[str] = set()
        for k in list(b_fields) + list(a_fields):
            if k not in seen:
                ordered_keys.append(k)
                seen.add(k)

        printed_header = False
        for key in ordered_keys:
            bf  = b_fields.get(key)
            af  = a_fields.get(key)
            bs  = bf["status"] if bf else "—"
            as_ = af["status"] if af else "—"
            changed = bs != as_

            if changes_only and not changed:
                continue

            if not printed_header:
                print()
                bar = "─" * max(0, 58 - len(co))
                print(f"  ── {co} {bar}")
                print(f"  {'Year':<6}  {'Field':<{_W_FL}}  {'Before':<{_W_STATUS}}  {'After':<{_W_STATUS}}")
                printed_header = True

            src    = bf if bf else af
            year   = src.get("year", "")
            label  = src.get("label", key)
            arrow  = ("↑ FIXED " if (changed and as_ == "MATCH") else
                      "↓ BROKEN" if (changed and bs  == "MATCH") else
                      "~ SHIFT " if  changed                     else
                      "=")
            print(f"  {year:<6}  {label:<{_W_FL}}  {bs:<{_W_STATUS}}  {as_:<{_W_STATUS}}  {arrow}")

            # Show actual values when status changed
            if changed and bf and af:
                bv = _fmt_val(bf.get("filled"))
                av = _fmt_val(af.get("filled"))
                cv = _fmt_val(af.get("correct"))
                if bv != av:
                    print(f"  {'':6}  {'':>{_W_FL}}  filled: {bv}  →  {av}  (correct: {cv})")

            # Collect for Section 5
            if changed:
                entry = {
                    "company": co, "year": year, "label": label,
                    "before": bs,  "after": as_,
                    "filled_before": _fmt_val(bf.get("filled")) if bf else "—",
                    "filled_after":  _fmt_val(af.get("filled")) if af else "—",
                    "correct":       _fmt_val(af.get("correct")) if af else "—",
                }
                if as_ == "MATCH":
                    fixes.append(entry)
                elif bs == "MATCH":
                    regressions.append(entry)

    # ── Section 5: Change summary ─────────────────────────────────────────────
    print()
    print("─" * 66)
    print("  CHANGE SUMMARY")
    print("─" * 66)

    if fixes:
        print(f"\n  ↑ Fixed  ({len(fixes)} field(s)):")
        for e in fixes:
            print(f"    {e['company']:<{_W_CO}}  {e['year']:<6}  {e['label']:<{_W_FL}}  "
                  f"{e['before']} → {e['after']}")
            if e["before"] != "MISSING":
                print(f"    {'':>{_W_CO}}  {'':6}  "
                      f"filled: {e['filled_before']}  →  {e['filled_after']}  "
                      f"(correct: {e['correct']})")
    else:
        print("\n  ↑ Fixed: none")

    if regressions:
        print(f"\n  ↓ Broken  ({len(regressions)} field(s)):  ← ACTION NEEDED")
        for e in regressions:
            print(f"    {e['company']:<{_W_CO}}  {e['year']:<6}  {e['label']:<{_W_FL}}  "
                  f"{e['before']} → {e['after']}")
            print(f"    {'':>{_W_CO}}  {'':6}  "
                  f"filled: {e['filled_before']}  →  {e['filled_after']}  "
                  f"(correct: {e['correct']})")
    else:
        print("\n  ↓ Broken: none  ✓")

    # Count unchanged fields (from before snapshot)
    total_b = sum(len(snap_b["companies"].get(co, {}).get("fields", [])) for co in all_cos)
    unchanged = max(0, total_b - len(fixes) - len(regressions))
    print(f"\n  =  Unchanged: {unchanged} fields")
    print()


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

def cmd_list() -> None:
    if not _SNAP_DIR.exists() or not any(_SNAP_DIR.glob("*.json")):
        print("No snapshots saved yet.")
        print("Run: python checker/accuracy_tracker.py snapshot <label>")
        return

    files = sorted(_SNAP_DIR.glob("*.json"))
    print(f"\n  {'Label':<36}  {'Date':<12}  {'Overall':>8}  {'Companies':>10}  Matched")
    print("  " + "─" * 72)
    for f in files:
        try:
            s = json.loads(f.read_text())
            print(f"  {s.get('label','?'):<36}  "
                  f"{s.get('timestamp','')[:10]:<12}  "
                  f"{s.get('overall_score',0):>7.1f}%  "
                  f"{len(s.get('companies',{})):>10}  "
                  f"{s.get('total_matched',0)}/{s.get('total_fields',0)}")
        except Exception:
            print(f"  {f.name}  (unreadable)")
    print()


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

def cmd_history() -> None:
    if not _SNAP_DIR.exists() or not any(_SNAP_DIR.glob("*.json")):
        print("No snapshots saved yet.")
        return

    snaps = []
    for f in _SNAP_DIR.glob("*.json"):
        try:
            snaps.append(json.loads(f.read_text()))
        except Exception:
            pass
    snaps.sort(key=lambda s: s.get("timestamp", ""))

    print(f"\n  {'Snapshot':<36}  {'Date':<12}  {'Overall':>8}  {'Companies':>10}")
    print("  " + "─" * 66)
    prev = None
    for s in snaps:
        label = s.get("label", "?")
        ts    = s.get("timestamp", "")[:10]
        score = s.get("overall_score", 0)
        n_co  = len(s.get("companies", {}))
        flag  = ""
        if prev is not None:
            d = score - prev
            if d > 0.05:
                flag = f"  ↑ +{d:.1f}%"
            elif d < -0.05:
                flag = f"  ↓ {d:.1f}%  ← regression"
        print(f"  {label:<36}  {ts:<12}  {score:>7.1f}%  {n_co:>10}{flag}")
        prev = score
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Snapshot and compare extraction accuracy across code changes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python checker/accuracy_tracker.py snapshot "baseline"
  python checker/accuracy_tracker.py snapshot "after-trade-rec-fix"
  python checker/accuracy_tracker.py compare  "baseline" "after-trade-rec-fix"
  python checker/accuracy_tracker.py compare  "baseline" "after-trade-rec-fix" --changes-only
  python checker/accuracy_tracker.py list
  python checker/accuracy_tracker.py history
        """,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_snap = sub.add_parser("snapshot", help="Save current results as a named snapshot")
    p_snap.add_argument("label", help="Snapshot name, e.g. 'baseline'")

    p_cmp = sub.add_parser("compare", help="Side-by-side comparison of two snapshots")
    p_cmp.add_argument("before", help="Label of the before snapshot")
    p_cmp.add_argument("after",  help="Label of the after snapshot")
    p_cmp.add_argument("--changes-only", action="store_true",
                       help="Show only fields that changed status in Section 4")

    sub.add_parser("list",    help="List all saved snapshots")
    sub.add_parser("history", help="Show accuracy trend across all snapshots")

    args = parser.parse_args()

    if args.cmd == "snapshot":
        cmd_snapshot(args.label)
    elif args.cmd == "compare":
        cmd_compare(args.before, args.after,
                    changes_only=getattr(args, "changes_only", False))
    elif args.cmd == "list":
        cmd_list()
    elif args.cmd == "history":
        cmd_history()


if __name__ == "__main__":
    main()
