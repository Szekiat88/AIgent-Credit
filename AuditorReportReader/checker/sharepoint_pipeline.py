"""
sharepoint_pipeline.py — SharePoint → Auditor Pipeline → CAWF Comparison

Works anonymously — no login required if the SharePoint folder is public.

Folder layout expected under the root:
  <Company>/
    Financial Statement/
      Audited Account/   ← latest PDF downloaded from here
    Credit Underwriting/ ← latest CAWF Excel downloaded from here

Usage:
  # List all company folders found:
  python checker/sharepoint_pipeline.py --list-only

  # Process all companies:
  python checker/sharepoint_pipeline.py

  # One company only (partial match):
  python checker/sharepoint_pipeline.py --company "Greatocean"

  # Force fresh Gemini calls (ignore LLM cache):
  python checker/sharepoint_pipeline.py --no-cache

Required env var:
  GEMINI_API_KEY   — for PDF extraction (not needed with --list-only)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_HERE      = Path(__file__).parent.resolve()   # checker/
_ROOT      = _HERE.parent                       # AuditorReportReader/
_EXTRACTOR = _ROOT / "extractor"
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_EXTRACTOR))

# Auto-load .env
_env = _ROOT / ".env"
if _env.exists():
    for _line in _env.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

import sp_rest


# ---------------------------------------------------------------------------
# Auditor extraction
# ---------------------------------------------------------------------------

def _run_auditor(pdf_path: Path, out_path: Path,
                 api_key: str, model: str, no_cache: bool = False) -> None:
    import re as _re
    from utils import json_cache
    from pipeline.pdf_ocr import extract_pages, full_text
    from pipeline.gemini_extractor import GeminiExtractor
    from pipeline.validator import run_checks
    from pipeline.excel_filler import write_output

    template = _ROOT / "Financial Statements Template.xlsx"
    if not template.exists():
        raise FileNotFoundError(f"Template not found: {template}")

    pages    = extract_pages(str(pdf_path), dpi=300)
    all_text = full_text(pages)

    m = _re.search(r"\b(20\d{2})\b", all_text)
    target_year = m.group(1) if m else ""

    file_hash = json_cache.pdf_hash(str(pdf_path))
    if no_cache:
        removed = json_cache.clear(file_hash)
        if removed:
            print(f"    [cache]    cleared {removed} entries")

    extractor = GeminiExtractor(
        pages=pages, target_year=target_year, hints={},
        api_key=api_key, model=model,
    )
    results = extractor.extract_all(pdf_hash_val=file_hash)

    financial_data = results["financial_data"]
    prior_data     = results.get("prior_financial_data") or {}

    write_output(
        template_path=str(template),
        output_path=str(out_path),
        target_year=results.get("detected_year") or target_year,
        audit_checks=results["audit_checks"],
        financial_data=financial_data,
        blacklist_firm={"status": "SKIPPED", "query": "", "evidence": []},
        blacklist_accountant={"status": "SKIPPED", "query": "", "evidence": []},
        validation_results=run_checks(financial_data),
        prior_financial_data=prior_data,
        prior_year=results.get("prior_year") or "",
        prior_validation_results=run_checks(prior_data) if prior_data else {},
        token_usage=results.get("token_usage") or {},
        year_end_date=results.get("year_end_date") or "",
        prior_year_end_date=results.get("prior_year_end_date") or "",
    )


# ---------------------------------------------------------------------------
# Per-company pipeline
# ---------------------------------------------------------------------------

def process_company(company: dict, out_dir: Path,
                    api_key: str, model: str, no_cache: bool = False) -> dict:
    """
    company dict has keys: Name, ServerRelativeUrl (SharePoint REST API format).
    """
    name         = company["Name"]
    company_path = company["ServerRelativeUrl"]

    print(f"\n{'='*64}")
    print(f"  {name}")
    print(f"{'='*64}")

    company_out = out_dir / name
    company_out.mkdir(parents=True, exist_ok=True)

    top_folders = sp_rest.list_subfolders(company_path)
    pdf_path  = None
    cawf_path = None
    issues    = []

    # ── 1. Latest audited PDF (independent — missing PDF does not skip CAWF) ──
    fin = sp_rest.find_subfolder(top_folders, sp_rest.FOLDER_FIN_STMT)
    if not fin:
        issues.append(f"no '{sp_rest.FOLDER_FIN_STMT}' folder (checked fuzzy)")
        print(f"  [skip pdf] no Financial Statements folder found")
    else:
        print(f"    [folder]   {fin['Name']}")
        # Try "Audited Account" subfolder; fall back to searching fin directly
        audited_folders = sp_rest.list_subfolders(fin["ServerRelativeUrl"])
        audited = sp_rest.find_subfolder(audited_folders, sp_rest.FOLDER_AUDITED)
        if audited:
            print(f"    [folder]   {audited['Name']}")
            search_path = audited["ServerRelativeUrl"]
        else:
            print(f"    [note]     no '{sp_rest.FOLDER_AUDITED}' subfolder — searching '{fin['Name']}' directly")
            search_path = fin["ServerRelativeUrl"]
        pdf_files = sp_rest.list_files(search_path)
        pdf_item  = sp_rest.get_latest_file(pdf_files, exts={".pdf"})
        if not pdf_item:
            issues.append("no PDF found")
            print(f"  [skip pdf] no PDF found")
        else:
            pdf_path = company_out / pdf_item["Name"]
            if pdf_path.exists():
                print(f"    [cached]   {pdf_path.name}")
            else:
                size_kb = int(pdf_item.get("Length", 0)) // 1024
                print(f"    [download] {pdf_item['Name']}  ({size_kb} KB)")
                sp_rest.download(pdf_item["ServerRelativeUrl"], pdf_path)

    # ── 2. Latest CAWF Excel (always attempted) ───────────────────────────────
    uw = sp_rest.find_subfolder(top_folders, sp_rest.FOLDER_CREDIT_UW)
    if not uw:
        issues.append(f"no '{sp_rest.FOLDER_CREDIT_UW}' folder")
        print(f"  [skip xlsx] no '{sp_rest.FOLDER_CREDIT_UW}' folder")
    else:
        uw_files  = sp_rest.list_files(uw["ServerRelativeUrl"])
        cawf_item = (
            sp_rest.get_latest_file(uw_files, exts=sp_rest.EXCEL_EXTS,
                                    name_contains=sp_rest.CAWF_KEYWORD)
            or sp_rest.get_latest_file(uw_files, exts=sp_rest.EXCEL_EXTS)
        )
        if not cawf_item:
            issues.append("no Excel in Credit Underwriting")
            print(f"  [skip xlsx] no Excel in Credit Underwriting")
        else:
            cawf_path = company_out / cawf_item["Name"]
            if cawf_path.exists():
                print(f"    [cached]   {cawf_path.name}")
            else:
                size_kb = int(cawf_item.get("Length", 0)) // 1024
                print(f"    [download] {cawf_item['Name']}  ({size_kb} KB)")
                sp_rest.download(cawf_item["ServerRelativeUrl"], cawf_path)

    if pdf_path is None:
        msg = "; ".join(issues) if issues else "no PDF found"
        return {"company": name, "skipped": msg}

    if cawf_path is None:
        msg = "; ".join(issues) if issues else "no CAWF Excel found"
        return {"company": name, "skipped": msg,
                "pdf": str(pdf_path)}

    # ── 3. Run auditor extraction ─────────────────────────────────────────────
    filled_path = company_out / f"{pdf_path.stem}_filled.xlsx"
    print(f"  [extract]  running pipeline on {pdf_path.name} ...")
    try:
        _run_auditor(pdf_path, filled_path, api_key, model, no_cache=no_cache)
        print(f"  [extract]  done → {filled_path.name}")
    except Exception as exc:
        print(f"  [extract]  FAILED: {exc}")
        return {"company": name, "error": f"extraction failed: {exc}",
                "pdf": str(pdf_path)}

    # ── 4. Compare filled Excel vs CAWF ──────────────────────────────────────
    print(f"  [compare]  {filled_path.name}  vs  {cawf_path.name}")
    import diff_checker
    result = diff_checker.compare(str(filled_path), str(cawf_path))

    if "error" in result:
        print(f"  [compare]  {result['error']}")
        print(f"  [note]     The CAWF Excel needs a 'Summary of Information' sheet")
        print(f"             in Financial Statements Template format.")
        return {"company": name, "error": result["error"],
                "pdf": str(pdf_path), "filled": str(filled_path),
                "cawf": str(cawf_path)}

    diff_checker.print_report(result, case_name=name)

    s = result["summary"]
    return {
        "company":     name,
        "score_pct":   s["score_pct"],
        "matched":     s["matched"],
        "total":       s["total"],
        "by_category": s["by_category"],
        "pdf":         str(pdf_path),
        "filled":      str(filled_path),
        "cawf":        str(cawf_path),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="SharePoint → Auditor pipeline → CAWF comparison",
    )
    parser.add_argument("--company",   help="Process only this company (partial name match)")
    parser.add_argument("--list-only", action="store_true",
                        help="List company folders and exit without processing")
    parser.add_argument("--no-cache",  action="store_true",
                        help="Force fresh Gemini calls (ignore LLM cache)")
    parser.add_argument("--model",     default="gemini-2.5-flash-lite")
    parser.add_argument("--out",       default=str(_ROOT / "output" / "sharepoint_run"),
                        help="Output directory for downloads and filled Excels")
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key and not args.list_only:
        print("[ERROR] Set GEMINI_API_KEY in your .env file before running extraction.")
        sys.exit(1)

    out_dir = Path(args.out)

    # ── List company subfolders ───────────────────────────────────────────────
    print(f"[SharePoint] Listing {sp_rest.ROOT_FOLDER} ...")
    try:
        company_folders = sp_rest.list_subfolders(sp_rest.ROOT_FOLDER)
    except PermissionError as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)

    if args.company:
        nl = args.company.lower()
        company_folders = [f for f in company_folders if nl in f["Name"].lower()]
        if not company_folders:
            print(f"[ERROR] No folder matching '{args.company}'")
            sys.exit(1)

    print(f"[SharePoint] {len(company_folders)} company folder(s) found")

    if args.list_only:
        for f in company_folders:
            mod = (f.get("TimeLastModified") or "")[:10]
            print(f"  • {f['Name']:<40}  modified {mod}")
        return

    # ── Process each company ──────────────────────────────────────────────────
    results = []
    for item in company_folders:
        try:
            r = process_company(item, out_dir, api_key, args.model,
                                no_cache=args.no_cache)
        except PermissionError as exc:
            print(f"[ERROR] {exc}")
            sys.exit(1)
        except Exception as exc:
            print(f"  [ERROR] {item['Name']}: {exc}")
            r = {"company": item["Name"], "error": str(exc)}
        results.append(r)

    # ── Save JSON summary ─────────────────────────────────────────────────────
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))

    # ── Print summary table ───────────────────────────────────────────────────
    print(f"\n{'='*64}")
    print(f"  SUMMARY")
    print(f"{'='*64}")
    for r in results:
        name = r["company"]
        if "skipped" in r:
            print(f"  {name:<38}  SKIPPED — {r['skipped']}")
        elif "error" in r:
            print(f"  {name:<38}  ERROR — {r['error']}")
        else:
            pct = r["score_pct"]
            bar = "█" * int(pct / 5)
            print(f"  {name:<38}  {pct:5.1f}%  {bar}")
    print(f"{'='*64}")
    print(f"\n  Full results: {summary_path}")


if __name__ == "__main__":
    main()
