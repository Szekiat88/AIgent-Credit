"""
AuditorReportReader — main CLI entry point.

Architecture: OCR → Page Classifier → Gemini LLM (4 calls) → Validate → Excel

Usage:
    python auditor_report_reader.py --pdf Greatocean\ 2024.pdf
    python auditor_report_reader.py --pdf report.pdf --excel template.xlsx
    python auditor_report_reader.py --pdf report.pdf --year 2024 --api-key AIza...
    python auditor_report_reader.py --pdf report.pdf --no-cache   # force re-extraction

Environment:
    GEMINI_API_KEY  — Gemini API key (or pass via --api-key)
"""

import argparse
import os
import sys
from pathlib import Path

# Auto-load .env from AuditorReportReader root (never overrides existing env vars)
_env = Path(__file__).parent.parent / ".env"
if _env.exists():
    for _line in _env.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())


def _resolve(path: str) -> str:
    p = os.path.abspath(path)
    if not os.path.exists(p):
        print(f"[ERROR] File not found: {p}")
        sys.exit(1)
    return p


def main():
    parser = argparse.ArgumentParser(
        description="P2P Credit Analyst — Auditor Report Reader (Gemini LLM edition)"
    )
    parser.add_argument("--pdf", required=True, help="Path to auditor report PDF")
    parser.add_argument(
        "--excel",
        default="Financial Statements Template.xlsx",
        help="Path to Financial Statements Template.xlsx",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Output Excel path (default: <pdf_stem>_filled.xlsx)",
    )
    parser.add_argument(
        "--year",
        default="",
        help="Financial year e.g. 2024.  Auto-detected from OCR text if omitted.",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("GEMINI_API_KEY", ""),
        help="Gemini API key",
    )
    parser.add_argument(
        "--model",
        default="gemini-2.5-flash-lite",
        help="Gemini model name (default: gemini-2.5-flash-lite)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Ignore cached LLM results and re-run Gemini calls",
    )
    parser.add_argument(
        "--no-web",
        action="store_true",
        help="Skip web blacklist search",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="OCR DPI (higher = better quality, slower).  Default 300.",
    )
    args = parser.parse_args()

    if not args.api_key:
        print("[ERROR] Gemini API key required. Set GEMINI_API_KEY or use --api-key.")
        sys.exit(1)

    pdf_path = _resolve(args.pdf)
    excel_path = _resolve(args.excel)
    output_path = args.output or (os.path.splitext(pdf_path)[0] + "_filled.xlsx")

    # ── Step 1: OCR ──────────────────────────────────────────────────────────
    print("\n=== STEP 1: OCR ===")
    from pipeline.pdf_ocr import extract_pages, full_text
    pages = extract_pages(pdf_path, dpi=args.dpi)
    all_text = full_text(pages)
    print(f"  Pages extracted: {len(pages)}")

    # ── Step 2: Detect financial year ────────────────────────────────────────
    print("\n=== STEP 2: Detect financial year ===")
    target_year = args.year
    if not target_year:
        # Quick regex scan before sending to LLM
        import re
        m = re.search(
            r'(?:year\s+ended?\s+\d{1,2}\s+\w+\s+(20\d{2})'
            r'|\d{1,2}[/\-]\d{1,2}[/\-](20\d{2})'
            r'|\b(20\d{2})\b)',
            all_text, re.I
        )
        if m:
            target_year = next(g for g in m.groups() if g)
    print(f"  Target year: {target_year or '(not detected — Gemini will infer)'}")

    # ── Step 3: Load keyword hints from Excel ─────────────────────────────────
    print("\n=== STEP 3: Load keyword hints ===")
    from utils.keyword_map import load_user_keyword_map
    hints = load_user_keyword_map(excel_path)
    print(f"  User-defined hints: {len(hints)} field(s)")

    # ── Step 4: LLM extraction via Gemini ────────────────────────────────────
    print("\n=== STEP 4: Gemini LLM extraction ===")
    from utils import json_cache as jcache
    file_hash = jcache.pdf_hash(pdf_path)
    print(f"  PDF hash: {file_hash[:12]}...")

    if args.no_cache:
        removed = jcache.clear(file_hash)
        if removed:
            print(f"  Cache cleared ({removed} entries deleted)")

    from pipeline.gemini_extractor import GeminiExtractor
    extractor = GeminiExtractor(
        pages=pages,
        target_year=target_year,
        hints=hints,
        api_key=args.api_key,
        model=args.model,
    )
    results = extractor.extract_all(pdf_hash_val=file_hash)
    audit_checks          = results["audit_checks"]
    financial_data        = results["financial_data"]
    prior_financial_data  = results.get("prior_financial_data") or {}
    detected_year         = results.get("detected_year") or target_year
    prior_year            = results.get("prior_year") or ""
    year_end_date         = results.get("year_end_date") or ""
    prior_year_end_date   = results.get("prior_year_end_date") or ""
    token_usage           = results.get("token_usage") or {}

    # Use Gemini-detected year if we didn't have one from regex
    if detected_year and not target_year:
        target_year = detected_year

    print(f"\n  Opinion      : {audit_checks['opinion']}")
    print(f"  True & Fair  : {audit_checks['true_and_fair']}")
    print(f"  Firm         : {audit_checks['firm_name']}")
    print(f"  Accountant   : {audit_checks['accountant_name']}")
    print(f"  Signatures   : {audit_checks['signature_consistency']}")
    print(f"  Stat. Decl.  : {audit_checks['statutory_declaration']['status']}")
    print(f"  Years        : {target_year} (current)  {prior_year or '(prior not detected)'}")

    # ── Step 5: Arithmetic validation ────────────────────────────────────────
    print("\n=== STEP 5: Arithmetic validation ===")
    from pipeline.validator import run_checks, print_validation

    print(f"  [{target_year}]")
    val_results = run_checks(financial_data)
    print_validation(val_results)

    prior_val_results = {}
    if prior_financial_data and prior_year:
        print(f"  [{prior_year}]")
        prior_val_results = run_checks(prior_financial_data)
        print_validation(prior_val_results)

    # ── Step 6: Extraction summary ────────────────────────────────────────────
    def _print_summary(year: str, data: dict):
        found = sum(1 for v in data.values() if v.get("value") is not None)
        total = len(data)
        print(f"\n  [{year}] Fields extracted: {found}/{total}")
        for field, result in data.items():
            val  = result.get("value")
            conf = result.get("confidence", 0.0)
            status = f"{val:,.2f}" if val is not None else "NOT FOUND"
            print(f"    {field:<42} {status:>18}  conf={conf:.0f}%")

    _print_summary(target_year, financial_data)
    if prior_financial_data and prior_year:
        _print_summary(prior_year, prior_financial_data)

    # ── Step 7: Web blacklist check ───────────────────────────────────────────
    print("\n=== STEP 6: Web blacklist check ===")
    if args.no_web:
        blacklist_firm = {"status": "SKIPPED", "query": "", "evidence": []}
        blacklist_accountant = {"status": "SKIPPED", "query": "", "evidence": []}
        print("  Skipped (--no-web)")
    else:
        from utils.web_check import check_firm, check_accountant
        print(f"  Checking firm: {audit_checks['firm_name']}")
        blacklist_firm = check_firm(audit_checks["firm_name"])
        print(f"    → {blacklist_firm['status']}")
        print(f"  Checking accountant: {audit_checks['accountant_name']}")
        blacklist_accountant = check_accountant(audit_checks["accountant_name"])
        print(f"    → {blacklist_accountant['status']}")

    # ── Step 8: Write Excel ───────────────────────────────────────────────────
    print("\n=== STEP 7: Write Excel ===")
    from pipeline.excel_filler import write_output
    recommendation = write_output(
        template_path=excel_path,
        output_path=output_path,
        target_year=target_year,
        audit_checks=audit_checks,
        financial_data=financial_data,
        blacklist_firm=blacklist_firm,
        blacklist_accountant=blacklist_accountant,
        validation_results=val_results,
        prior_financial_data=prior_financial_data,
        prior_year=prior_year,
        prior_validation_results=prior_val_results,
        token_usage=token_usage,
        year_end_date=year_end_date,
        prior_year_end_date=prior_year_end_date,
    )

    years_filled = target_year
    if prior_year:
        years_filled = f"{prior_year} + {target_year}"

    print(f"\n{'='*60}")
    print(f"  OUTPUT FILE   : {output_path}")
    print(f"  YEARS FILLED  : {years_filled or '(inferred by Gemini)'}")
    print(f"  OPINION       : {audit_checks['opinion']}")
    print(f"  RECOMMENDATION: {recommendation}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
