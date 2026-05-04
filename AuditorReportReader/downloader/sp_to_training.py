"""
sp_to_training.py — Download SharePoint files into training/inbox/ for accuracy training.

Downloads the latest audited account PDF and CAWF Excel for each company under
MS - Project Appleton and saves them as matching-stem pairs so that
`training_manager.py inbox` can register them automatically.

PDF finding uses a 2-path strategy (each path has a filename check + page-peek fallback):
  Path A — audited subfolder inside Financial Statements:
              Step A1: look for PDF filename containing "audited"
              Step A2: if not found, read PDFs one by one (pages 1-3) for "financial statement"
  Path B — Financial Statements folder directly (only if Path A found nothing):
              Step B1: look for PDF filename containing "audited"
              Step B2: if not found, read PDFs one by one (pages 1-3) for "financial statement"

Workflow:
  1. python downloader/sp_to_training.py          ← download all companies
  2. python checker/training_manager.py inbox     ← register as training cases
  3. python checker/training_manager.py run       ← extract + compare accuracy
  4. python checker/generate_report.py --open     ← view HTML report

Usage:
  python downloader/sp_to_training.py               # download all
  python downloader/sp_to_training.py --list-only   # list company folders only
  python downloader/sp_to_training.py --company "Greatocean"
  python downloader/sp_to_training.py --force       # re-download even if cached
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path

_HERE    = Path(__file__).parent.resolve()   # downloader/
_ROOT    = _HERE.parent                       # AuditorReportReader/
_CHECKER = _ROOT / "checker"
sys.path.insert(0, str(_CHECKER))

# Auto-load .env
_env = _ROOT / ".env"
if _env.exists():
    for _line in _env.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

import sp_rest

_DEFAULT_OUT = _ROOT / "training" / "inbox"


# ---------------------------------------------------------------------------
# Tier 3 helpers — page-peek
# ---------------------------------------------------------------------------

def _peek_pdf_text(path: Path, max_pages: int = 3) -> str:
    """
    Extract text from the first max_pages of a PDF.
    Tries pdfplumber first (fast); falls back to Tesseract OCR for image-based PDFs.
    """
    text = ""
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages[:max_pages]:
                text += (page.extract_text() or "")
    except Exception:
        pass
    if len(text.strip()) > 50:
        return text
    # Fallback: OCR via pdf2image + pytesseract
    try:
        from pdf2image import convert_from_path
        import pytesseract
        images = convert_from_path(str(path), first_page=1, last_page=max_pages, dpi=150)
        for img in images:
            text += pytesseract.image_to_string(img)
    except Exception:
        pass
    return text


def _year_in_text(text: str) -> int:
    """Return the highest 4-digit year found in text, or 0."""
    hits = re.findall(r'\b(20\d{2})\b', text)
    return max(int(y) for y in hits) if hits else 0


def _find_pdf_by_page_peek(pdf_files: list[dict]):
    """
    Download each PDF one by one, read pages 1–3, and return the file dict
    whose text contains "financial statement" with the most recent year.
    Returns None if no candidate is found.
    """
    candidates = []
    total = len(pdf_files)

    for i, f in enumerate(pdf_files, 1):
        print(f"    [peek {i}/{total}] {f['Name']}")
        tmp = Path(tempfile.mktemp(suffix=".pdf"))
        try:
            sp_rest.download(f["ServerRelativeUrl"], tmp, force=True)
            text = _peek_pdf_text(tmp)
            if "financial statement" in text.lower():
                year = _year_in_text(text) or _year_in_name_local(f["Name"])
                print(f"    [peek {i}/{total}] ✓ \"financial statement\" found  |  year: {year or 'unknown'}")
                candidates.append((year, f.get("TimeLastModified", ""), f))
            else:
                print(f"    [peek {i}/{total}] ✗ keyword not found — skipped")
        except Exception as exc:
            print(f"    [peek {i}/{total}] ✗ error: {exc}")
        finally:
            tmp.unlink(missing_ok=True)

    if not candidates:
        return None

    candidates.sort(key=lambda t: (t[0], t[1]), reverse=True)
    winner = candidates[0][2]
    print(f"    [result]   Latest → {winner['Name']}  (year {candidates[0][0] or 'unknown'})")
    return winner


def _year_in_name_local(name: str) -> int:
    """Return the highest 4-digit year found in a filename, or 0."""
    hits = re.findall(r'\b(20\d{2})\b', name)
    return max(int(y) for y in hits) if hits else 0


# ---------------------------------------------------------------------------
# Per-company download
# ---------------------------------------------------------------------------

def _search_path_for_pdf(path: str, label: str):
    """
    Search one folder path for the best audited PDF.
    Step 1: prefer filename containing "audited".
    Step 2: if not found, read PDFs one by one (pages 1-3) for "financial statement".
    Returns a file dict or None.
    """
    files    = sp_rest.list_files(path)
    all_pdfs = [f for f in files if Path(f["Name"]).suffix.lower() == ".pdf"]

    # Step 1 — filename check
    pdf_item = sp_rest.get_latest_audited_file(all_pdfs, {".pdf"})
    if pdf_item:
        print(f"    [found]    '{pdf_item['Name']}'  (via filename in {label})")
        return pdf_item

    # Step 2 — page-peek
    if all_pdfs:
        print(f"    [note]     no 'audited' filename in {label} — reading PDFs one by one ({len(all_pdfs)} file(s))")
        return _find_pdf_by_page_peek(all_pdfs)

    print(f"    [note]     no PDF files in {label}")
    return None


def download_company(company: dict, out_dir: Path, force: bool = False) -> dict:
    """
    Download the latest audited PDF and CAWF Excel for one company.

    PDF search uses a 2-path strategy inside the Financial Statements folder:
      Path A — audited subfolder:
                 A1: filename contains "audited"  → done
                 A2: page-peek (pages 1-3)        → done
      Path B — Financial Statements flat (only if Path A found nothing):
                 B1: filename contains "audited"  → done
                 B2: page-peek (pages 1-3)        → done

    PDF and CAWF are independent — a missing PDF does not skip the Excel.
    Files saved as: <CompanyName>.pdf + <CompanyName>.xlsx
    """
    name         = company["Name"]
    company_path = company["ServerRelativeUrl"]
    result       = {"company": name}
    issues       = []

    top_folders = sp_rest.list_subfolders(company_path)

    # ── PDF: 2-path strategy inside Financial Statements ─────────────────────
    fin = sp_rest.find_subfolder(top_folders, sp_rest.FOLDER_FIN_STMT)
    if not fin:
        issues.append(f"no '{sp_rest.FOLDER_FIN_STMT}' folder")
        print(f"    [skip pdf] no Financial Statements folder found")
    else:
        print(f"    [folder]   {fin['Name']}")
        fin_path = fin["ServerRelativeUrl"]
        pdf_item = None

        # Path A — audited subfolder (always checked first)
        audited_folders = sp_rest.list_subfolders(fin_path)
        audited_sub     = sp_rest.find_subfolder(audited_folders, sp_rest.FOLDER_AUDITED)
        if audited_sub:
            print(f"    [folder]   {audited_sub['Name']}  [Path A]")
            pdf_item = _search_path_for_pdf(
                audited_sub["ServerRelativeUrl"],
                label=audited_sub["Name"],
            )

        # Path B — Financial Statements flat (only if Path A found nothing)
        if not pdf_item:
            if audited_sub:
                print(f"    [path B]   subfolder had no match — searching '{fin['Name']}' directly")
            else:
                print(f"    [path B]   no audited subfolder — searching '{fin['Name']}' directly")
            pdf_item = _search_path_for_pdf(fin_path, label=fin["Name"])

        if not pdf_item:
            issues.append("no audited PDF found")
            print(f"    [skip pdf] no audited PDF found")
        else:
            pdf_dest = out_dir / f"{name}.pdf"
            if pdf_dest.exists() and not force:
                print(f"    [cached]   {pdf_dest.name}")
            else:
                size_kb = int(pdf_item.get("Length", 0)) // 1024
                print(f"    [download] {pdf_item['Name']}  ({size_kb} KB)  → {pdf_dest.name}")
                sp_rest.download(pdf_item["ServerRelativeUrl"], pdf_dest, force=force)
            result["pdf"] = str(pdf_dest)
            result["pdf_filename"] = pdf_item["Name"]

    # ── CAWF Excel: Credit Underwriting (always attempted) ───────────────────
    uw = sp_rest.find_subfolder(top_folders, sp_rest.FOLDER_CREDIT_UW)
    if not uw:
        issues.append(f"no '{sp_rest.FOLDER_CREDIT_UW}' folder")
        print(f"    [skip xlsx] no '{sp_rest.FOLDER_CREDIT_UW}' folder")
    else:
        uw_files  = sp_rest.list_files(uw["ServerRelativeUrl"])
        cawf_item = (
            sp_rest.get_latest_file(uw_files, exts=sp_rest.EXCEL_EXTS,
                                    name_contains=sp_rest.CAWF_KEYWORD)
            or sp_rest.get_latest_file(uw_files, exts=sp_rest.EXCEL_EXTS)
        )
        if not cawf_item:
            issues.append("no Excel in Credit Underwriting")
            print(f"    [skip xlsx] no Excel in Credit Underwriting")
        else:
            cawf_dest = out_dir / f"{name}.xlsx"
            if cawf_dest.exists() and not force:
                print(f"    [cached]   {cawf_dest.name}")
            else:
                size_kb = int(cawf_item.get("Length", 0)) // 1024
                print(f"    [download] {cawf_item['Name']}  ({size_kb} KB)  → {cawf_dest.name}")
                sp_rest.download(cawf_item["ServerRelativeUrl"], cawf_dest, force=force)
            result["cawf"] = str(cawf_dest)
            result["cawf_filename"] = cawf_item["Name"]

    if issues:
        result["issues"] = issues
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download SharePoint audited accounts + CAWF Excels into training/inbox/",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
After downloading, register and run training:
  python checker/training_manager.py inbox
  python checker/training_manager.py run
  python checker/generate_report.py --open
        """,
    )
    parser.add_argument("--list-only", action="store_true",
                        help="List company folders and exit without downloading")
    parser.add_argument("--company",   help="Download only this company (partial name match)")
    parser.add_argument("--force",     action="store_true",
                        help="Re-download even if the file already exists in inbox/")
    parser.add_argument("--out",       default=str(_DEFAULT_OUT),
                        help=f"Destination folder (default: training/inbox/)")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── List company folders ──────────────────────────────────────────────────
    print(f"[SharePoint] Listing {sp_rest.ROOT_FOLDER} ...")
    try:
        companies = sp_rest.list_subfolders(sp_rest.ROOT_FOLDER)
    except PermissionError as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)

    if args.company:
        nl = args.company.lower()
        companies = [c for c in companies if nl in c["Name"].lower()]
        if not companies:
            print(f"[ERROR] No folder matching '{args.company}'")
            sys.exit(1)

    print(f"[SharePoint] {len(companies)} company folder(s) found\n")

    if args.list_only:
        for c in companies:
            mod = (c.get("TimeLastModified") or "")[:10]
            print(f"  • {c['Name']:<40}  modified {mod}")
        return

    # ── Download each company ─────────────────────────────────────────────────
    results: list[dict] = []
    for company in companies:
        print(f"{'─'*56}")
        print(f"  {company['Name']}")
        try:
            r = download_company(company, out_dir, force=args.force)
        except PermissionError as exc:
            print(f"  [ERROR] {exc}")
            sys.exit(1)
        except Exception as exc:
            r = {"company": company["Name"], "error": str(exc)}
        results.append(r)

        # Write sidecar so training_manager can display original filenames
        sidecar = {}
        if "pdf_filename" in r:
            sidecar["pdf_filename"] = r["pdf_filename"]
        if "cawf_filename" in r:
            sidecar["cawf_filename"] = r["cawf_filename"]
        if sidecar:
            (out_dir / f"{company['Name']}.meta.json").write_text(
                json.dumps(sidecar, indent=2)
            )

    # ── Summary ───────────────────────────────────────────────────────────────
    ok      = [r for r in results if "pdf" in r and "cawf" in r]
    skipped = [r for r in results if "skipped" in r]
    errors  = [r for r in results if "error" in r]

    print(f"\n{'='*56}")
    print(f"  DOWNLOAD SUMMARY")
    print(f"{'='*56}")
    print(f"  Downloaded : {len(ok)}")
    for r in ok:
        print(f"    ✓  {r['company']}")
    if skipped:
        print(f"  Skipped    : {len(skipped)}")
        for r in skipped:
            print(f"    –  {r['company']}  ({r['skipped']})")
    if errors:
        print(f"  Errors     : {len(errors)}")
        for r in errors:
            print(f"    ✗  {r['company']}  ({r['error']})")

    if not ok:
        print()
        return

    print(f"\n  Files saved to: {out_dir}")

    # ── Auto-register downloaded pairs as training cases ──────────────────────
    print(f"\n{'='*56}")
    print(f"  REGISTERING CASES")
    print(f"{'='*56}")
    from training_manager import cmd_inbox
    cmd_inbox()

    print(f"\n  Done. Run training next:")
    print(f"    python checker/training_manager.py run")
    print(f"    python checker/generate_report.py --open")
    print()


if __name__ == "__main__":
    main()
