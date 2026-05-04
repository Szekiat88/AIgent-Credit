"""
training_manager.py — Bulk upload and training system for AuditorReportReader.

Workflow:
  1. Drop PDF + correct Excel pairs into  training/inbox/
     (file names must match:  CompanyX.pdf  +  CompanyX.xlsx)
  2. Run:  python training_manager.py inbox       ← registers all inbox pairs
  3. Run:  python training_manager.py run         ← extracts + diffs all cases
  4. Run:  python training_manager.py report      ← aggregate accuracy + patterns

Individual commands:
  python training_manager.py add --pdf Foo.pdf --excel Foo_correct.xlsx --name Foo --industry trading
  python training_manager.py list
  python training_manager.py run --case Foo
  python training_manager.py run --case Foo --no-cache
  python training_manager.py report
  python training_manager.py diff --case Foo     ← re-diff last run without re-extracting

Environment:
  GEMINI_API_KEY  — required for 'run' command
"""

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Ensure AuditorReportReader modules are importable
_HERE = Path(__file__).parent.resolve()   # checker/
_ROOT = _HERE.parent                       # AuditorReportReader/
_EXTRACTOR = _ROOT / "extractor"           # extractor/ (pipeline + utils live here)
sys.path.insert(0, str(_HERE))             # diff_checker (checker/ sibling)
sys.path.insert(0, str(_EXTRACTOR))        # pipeline.* and utils.*

# Auto-load .env from AuditorReportReader root
_env = _ROOT / ".env"
if _env.exists():
    for _line in _env.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

import diff_checker

# ---------------------------------------------------------------------------
# directory layout
# ---------------------------------------------------------------------------

_TRAINING   = _ROOT / "training"
_CASES      = _TRAINING / "cases"
_RUNS       = _TRAINING / "runs"
_INBOX      = _TRAINING / "inbox"
_SCORES     = _TRAINING / "scores.json"
_PATTERNS   = _TRAINING / "patterns.json"

_TEMPLATE   = _ROOT / "Financial Statements Template.xlsx"

_EXCEL_EXTS = (".xlsx", ".xlsm", ".xls")


def _ensure_dirs():
    for d in [_TRAINING, _CASES, _RUNS, _INBOX, _INBOX / "processed"]:
        d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# scores / patterns persistence
# ---------------------------------------------------------------------------

def _load_scores() -> dict:
    return json.loads(_SCORES.read_text()) if _SCORES.exists() else {}


def _save_scores(scores: dict):
    _SCORES.write_text(json.dumps(scores, indent=2, default=str))


def _load_patterns() -> dict:
    return json.loads(_PATTERNS.read_text()) if _PATTERNS.exists() else {}


def _save_patterns(patterns: dict):
    _PATTERNS.write_text(json.dumps(patterns, indent=2, default=str))


# ---------------------------------------------------------------------------
# add / inbox
# ---------------------------------------------------------------------------

def cmd_add(pdf_path: str, excel_path: str, name: str,
            industry: str = "", notes: str = "",
            pdf_filename: str = "", cawf_filename: str = ""):
    """Register one PDF + correct Excel pair as a training case."""
    _ensure_dirs()
    case_dir = _CASES / name
    case_dir.mkdir(exist_ok=True)

    shutil.copy2(pdf_path,   case_dir / "report.pdf")
    shutil.copy2(excel_path, case_dir / "correct.xlsx")

    meta = {
        "name":           name,
        "industry":       industry,
        "notes":          notes,
        "added":          datetime.now().isoformat(),
        "source_pdf":     pdf_path,
        "source_excel":   excel_path,
        "pdf_filename":   pdf_filename  or Path(pdf_path).name,
        "cawf_filename":  cawf_filename or Path(excel_path).name,
    }
    (case_dir / "metadata.json").write_text(json.dumps(meta, indent=2))
    print(f"  [Added] '{name}'  →  {case_dir}")


def cmd_inbox():
    """
    Scan training/inbox/ for PDF + Excel pairs (matching stems) and
    register each as a training case, then move files to inbox/processed/.
    """
    _ensure_dirs()
    pdfs = sorted(_INBOX.glob("*.pdf")) + sorted(_INBOX.glob("*.PDF"))
    added = skipped = 0

    for pdf in pdfs:
        stem = pdf.stem
        excel = None
        for ext in _EXCEL_EXTS:
            candidate = _INBOX / (stem + ext)
            if candidate.exists():
                excel = candidate
                break

        if excel is None:
            print(f"  [SKIP]  {pdf.name}  — no matching Excel file found")
            skipped += 1
            continue

        # Read sidecar metadata written by sp_to_training.py (if present)
        sidecar_path = _INBOX / (stem + ".meta.json")
        sidecar = json.loads(sidecar_path.read_text()) if sidecar_path.exists() else {}

        cmd_add(str(pdf), str(excel), name=stem,
                pdf_filename=sidecar.get("pdf_filename", ""),
                cawf_filename=sidecar.get("cawf_filename", ""))

        # Move processed files out of inbox
        proc = _INBOX / "processed"
        shutil.move(str(pdf),   proc / pdf.name)
        shutil.move(str(excel), proc / excel.name)
        if sidecar_path.exists():
            shutil.move(str(sidecar_path), proc / sidecar_path.name)
        added += 1

    print(f"\n  Inbox done: {added} added, {skipped} skipped.")
    if skipped:
        print("  Tip: Excel filename must match PDF filename (e.g. Foo.pdf + Foo.xlsx)")


# ---------------------------------------------------------------------------
# extraction runner
# ---------------------------------------------------------------------------

def _run_extraction(pdf_path: str, output_path: str,
                    api_key: str, model: str, no_cache: bool = False):
    """Run the full AuditorReportReader pipeline on one PDF."""
    from utils import json_cache
    from pipeline.pdf_ocr import extract_pages, full_text
    from pipeline.gemini_extractor import GeminiExtractor
    from pipeline.validator import run_checks
    from pipeline.excel_filler import write_output

    if not _TEMPLATE.exists():
        raise FileNotFoundError(
            f"Template not found: {_TEMPLATE}\n"
            "Place 'Financial Statements Template.xlsx' next to training_manager.py"
        )

    pages = extract_pages(str(pdf_path), dpi=300)
    all_text = full_text(pages)

    # Quick regex year detection (same as main CLI)
    target_year = ""
    m = re.search(
        r"(?:year\s+ended?\s+\d{1,2}\s+\w+\s+(20\d{2})"
        r"|\d{1,2}[/\-]\d{1,2}[/\-](20\d{2})"
        r"|\b(20\d{2})\b)",
        all_text, re.I,
    )
    if m:
        target_year = next(g for g in m.groups() if g)

    file_hash = json_cache.pdf_hash(str(pdf_path))
    if no_cache:
        removed = json_cache.clear(file_hash)
        if removed:
            print(f"    Cache cleared ({removed} entries)")

    extractor = GeminiExtractor(
        pages=pages, target_year=target_year, hints={},
        api_key=api_key, model=model,
    )
    results = extractor.extract_all(pdf_hash_val=file_hash)

    audit_checks = results["audit_checks"]
    financial_data = results["financial_data"]
    prior_data = results.get("prior_financial_data") or {}
    detected_year = results.get("detected_year") or target_year
    prior_year = results.get("prior_year") or ""
    year_end_date = results.get("year_end_date") or ""
    prior_year_end = results.get("prior_year_end_date") or ""
    token_usage = results.get("token_usage") or {}

    val_results = run_checks(financial_data)
    prior_val = run_checks(prior_data) if prior_data else {}

    write_output(
        template_path=str(_TEMPLATE),
        output_path=output_path,
        target_year=detected_year,
        audit_checks=audit_checks,
        financial_data=financial_data,
        blacklist_firm={"status": "SKIPPED", "query": "", "evidence": []},
        blacklist_accountant={"status": "SKIPPED", "query": "", "evidence": []},
        validation_results=val_results,
        prior_financial_data=prior_data,
        prior_year=prior_year,
        prior_validation_results=prior_val,
        token_usage=token_usage,
        year_end_date=year_end_date,
        prior_year_end_date=prior_year_end,
    )


# ---------------------------------------------------------------------------
# run command
# ---------------------------------------------------------------------------

def cmd_run(case_name: str = "", api_key: str = "",
            model: str = "gemini-2.5-flash-lite", no_cache: bool = False):
    """Run extraction + diff on all cases (or one specific case)."""
    _ensure_dirs()

    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("[ERROR] Gemini API key required. Set GEMINI_API_KEY or use --api-key.")
        return

    # Determine which cases to run
    if case_name:
        cases = [case_name]
    else:
        cases = sorted(d.name for d in _CASES.iterdir() if d.is_dir())

    if not cases:
        print("[Training] No cases found. Use 'add' or 'inbox' first.")
        return

    scores = _load_scores()
    all_diffs = []

    for name in cases:
        case_dir = _CASES / name
        pdf_path = case_dir / "report.pdf"
        correct_path = case_dir / "correct.xlsx"

        if not pdf_path.exists():
            print(f"\n  [SKIP] {name}: report.pdf missing"); continue
        if not correct_path.exists():
            print(f"\n  [SKIP] {name}: correct.xlsx missing"); continue

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = _RUNS / f"{ts}_{name}"
        run_dir.mkdir()
        filled_path = run_dir / "filled.xlsx"

        print(f"\n{'='*64}")
        print(f"  Case: {name}")
        print(f"{'='*64}")

        # Extract
        try:
            _run_extraction(
                pdf_path=str(pdf_path),
                output_path=str(filled_path),
                api_key=api_key,
                model=model,
                no_cache=no_cache,
            )
        except Exception as e:
            print(f"  [ERROR] Extraction failed: {e}")
            import traceback; traceback.print_exc()
            continue

        # Also save a copy in the case dir for re-diffing later
        shutil.copy2(str(filled_path), case_dir / "last_filled.xlsx")

        # Diff
        diff_results = diff_checker.compare(str(filled_path), str(correct_path))
        diff_path = run_dir / "diff.json"
        diff_path.write_text(json.dumps(diff_results, indent=2, default=str))

        diff_checker.print_report(diff_results, name)
        all_diffs.append((name, diff_results))

        # Record score
        s = diff_results.get("summary", {})
        scores[name] = {
            "last_run":     ts,
            "score_pct":    s.get("score_pct", 0),
            "matched":      s.get("matched", 0),
            "total":        s.get("total", 0),
            "by_category":  s.get("by_category", {}),
            "run_dir":      str(run_dir),
        }
        _save_scores(scores)

    # Update aggregate patterns
    _update_patterns(all_diffs)

    # Print aggregate report
    print()
    cmd_report()


# ---------------------------------------------------------------------------
# re-diff (no re-extraction)
# ---------------------------------------------------------------------------

def cmd_diff(case_name: str):
    """Re-run diff on the last extraction output without re-extracting."""
    case_dir = _CASES / case_name
    filled_path = case_dir / "last_filled.xlsx"
    correct_path = case_dir / "correct.xlsx"

    if not filled_path.exists():
        print(f"  [ERROR] No previous run found for '{case_name}'. Run 'run --case {case_name}' first.")
        return

    diff_results = diff_checker.compare(str(filled_path), str(correct_path))
    diff_checker.print_report(diff_results, case_name)


# ---------------------------------------------------------------------------
# pattern aggregation
# ---------------------------------------------------------------------------

def _update_patterns(diffs: list):
    """Aggregate mismatch patterns across all diffs and save to patterns.json."""
    if not diffs:
        return

    # field → {category → count}
    field_errors: dict = {}
    # category → total count
    cat_totals: dict = {}

    for name, diff in diffs:
        for entry in diff.get("fields", []):
            status = entry["status"]
            if status == "MATCH":
                continue
            label = entry["label"]
            field_errors.setdefault(label, {})
            field_errors[label][status] = field_errors[label].get(status, 0) + 1
            cat_totals[status] = cat_totals.get(status, 0) + 1

    # Sort fields by total error count descending
    field_summary = {}
    for label, cats in field_errors.items():
        total_errors = sum(cats.values())
        dominant_error = max(cats, key=lambda k: cats[k])
        field_summary[label] = {
            "total_errors":    total_errors,
            "dominant_error":  dominant_error,
            "breakdown":       cats,
        }

    patterns = {
        "updated":          datetime.now().isoformat(),
        "cases_analysed":   len(diffs),
        "error_totals":     cat_totals,
        "fields_ranked":    dict(
            sorted(field_summary.items(), key=lambda x: -x[1]["total_errors"])
        ),
    }
    _save_patterns(patterns)


# ---------------------------------------------------------------------------
# list / report
# ---------------------------------------------------------------------------

def cmd_list():
    _ensure_dirs()
    cases = sorted(d.name for d in _CASES.iterdir() if d.is_dir()) \
            if _CASES.exists() else []
    scores = _load_scores()

    print(f"\n  {'Name':<28} {'Industry':<18} {'Score':>7}  {'Match':>10}  Last Run")
    print("  " + "-" * 74)
    for name in cases:
        meta_path = _CASES / name / "metadata.json"
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        industry = meta.get("industry", "—")
        sc = scores.get(name, {})
        score   = f"{sc['score_pct']}%" if sc else "not run"
        matched = f"{sc.get('matched','?')}/{sc.get('total','?')}" if sc else "—"
        last    = sc.get("last_run", "—")[:15] if sc else "—"
        print(f"  {name:<28} {industry:<18} {score:>7}  {matched:>10}  {last}")

    print(f"\n  Total: {len(cases)} case(s)")
    print(f"  Inbox: {_INBOX}")
    print(f"  Cases: {_CASES}")


def cmd_report():
    """Print aggregate accuracy report and top error patterns."""
    scores = _load_scores()
    patterns = _load_patterns()

    if not scores:
        print("\n[Training] No runs yet. Use 'run' first.")
        return

    # Overall accuracy
    total_m = sum(s.get("matched", 0) for s in scores.values())
    total_t = sum(s.get("total", 0) for s in scores.values())
    overall = round(100 * total_m / total_t, 1) if total_t else 0.0

    bar = "=" * 64
    print(f"\n{bar}")
    print(f"  AGGREGATE TRAINING REPORT")
    print(f"  Cases run     : {len(scores)}")
    print(f"  Overall score : {total_m}/{total_t}  ({overall}%)")
    print(bar)

    # Per-case table
    print(f"\n  {'Case':<28} {'Score':>7}  {'Match':>10}")
    print("  " + "-" * 50)
    for name, s in sorted(scores.items(), key=lambda x: -x[1].get("score_pct", 0)):
        print(f"  {name:<28} {s.get('score_pct', 0):>6.1f}%  "
              f"{s.get('matched','?'):>5}/{s.get('total','?')}")

    # Error category totals
    all_cats: dict = {}
    for s in scores.values():
        for cat, cnt in s.get("by_category", {}).items():
            if cat != "MATCH":
                all_cats[cat] = all_cats.get(cat, 0) + cnt

    if all_cats:
        print(f"\n  Error categories (total across all cases):")
        for cat, cnt in sorted(all_cats.items(), key=lambda x: -x[1]):
            bar_vis = "█" * min(cnt, 40)
            print(f"    {cat:<20} {cnt:>4}  {bar_vis}")

    # Top failing fields
    fields_ranked = patterns.get("fields_ranked", {})
    if fields_ranked:
        top = list(fields_ranked.items())[:15]
        print(f"\n  Top fields needing improvement (across all cases):")
        print(f"  {'Field':<42} {'Errors':>6}  Dominant Error")
        print("  " + "-" * 70)
        for label, info in top:
            dom = info.get("dominant_error", "?")
            tot = info.get("total_errors", 0)
            print(f"  {label:<42} {tot:>6}  {dom}")

    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="AuditorReportReader — Training Data Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Drop files into training/inbox/, then:
  python training_manager.py inbox
  python training_manager.py run
  python training_manager.py report

  # Add a single case manually:
  python training_manager.py add --pdf Mandrill.pdf --excel Mandrill_Sample.xlsx --name Mandrill --industry trading

  # Re-run one case with fresh Gemini calls:
  python training_manager.py run --case Mandrill --no-cache
        """,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # ── add ──────────────────────────────────────────────────────────────────
    p_add = sub.add_parser("add", help="Register one PDF + Excel pair")
    p_add.add_argument("--pdf",      required=True, help="Path to auditor report PDF")
    p_add.add_argument("--excel",    required=True, help="Path to correct filled Excel")
    p_add.add_argument("--name",     required=True, help="Case name (no spaces)")
    p_add.add_argument("--industry", default="",    help="Industry tag e.g. trading, manufacturing")
    p_add.add_argument("--notes",    default="",    help="Free-text notes about this case")

    # ── inbox ─────────────────────────────────────────────────────────────────
    sub.add_parser("inbox",
        help="Process matching PDF+Excel pairs from training/inbox/")

    # ── run ──────────────────────────────────────────────────────────────────
    p_run = sub.add_parser("run", help="Extract + diff all cases (or one)")
    p_run.add_argument("--case",     default="",   help="Specific case name (default: all)")
    p_run.add_argument("--api-key",  default=os.environ.get("GEMINI_API_KEY", ""),
                       help="Gemini API key")
    p_run.add_argument("--model",    default="gemini-2.5-flash-lite")
    p_run.add_argument("--no-cache", action="store_true",
                       help="Ignore cached LLM results and re-run Gemini calls")

    # ── diff (re-diff only) ───────────────────────────────────────────────────
    p_diff = sub.add_parser("diff", help="Re-diff last run output (no re-extraction)")
    p_diff.add_argument("--case", required=True, help="Case name")

    # ── list ─────────────────────────────────────────────────────────────────
    sub.add_parser("list", help="List all training cases with scores")

    # ── report ───────────────────────────────────────────────────────────────
    sub.add_parser("report", help="Aggregate accuracy + error pattern report")

    args = parser.parse_args()

    if args.cmd == "add":
        cmd_add(args.pdf, args.excel, args.name, args.industry, args.notes)

    elif args.cmd == "inbox":
        cmd_inbox()

    elif args.cmd == "run":
        cmd_run(
            case_name=args.case,
            api_key=args.api_key,
            model=args.model,
            no_cache=args.no_cache,
        )

    elif args.cmd == "diff":
        cmd_diff(args.case)

    elif args.cmd == "list":
        cmd_list()

    elif args.cmd == "report":
        cmd_report()


if __name__ == "__main__":
    main()
