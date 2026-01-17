import re
from typing import Optional, Tuple, List, Dict

import tkinter as tk
from tkinter import filedialog

import pdfplumber
import pandas as pd

# Camelot requires: pip install camelot-py[cv]
import camelot
from pypdf.errors import PdfReadError, PdfStreamError


HEADER_TEXT = "DETAILED CREDIT REPORT (BANKING ACCOUNTS)"
TARGET_FACILITIES = [
    "OVRDRAFT",
    "TEMPOVDT",
    "RVVGCRDT",
    "INVOIFIN",
    "TRECEIPT",
    "BAOWNPCH",
    "BAOWNEXP",
]


def find_first_table_page(pdf_path: str, needle: str = HEADER_TEXT) -> Optional[int]:
    """
    Returns 1-based page number of the FIRST page containing `needle`,
    or None if not found.
    """
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if needle in text:
                return i
    return None


def _is_good_table(df: pd.DataFrame) -> bool:
    """Heuristic to ignore tiny/blank tables."""
    if df is None or df.empty:
        return False
    # Remove all-empty rows/cols
    df2 = df.replace(r"^\s*$", pd.NA, regex=True).dropna(how="all").dropna(axis=1, how="all")
    if df2.shape[0] < 2 or df2.shape[1] < 4:
        return False
    # Must contain at least 1 expected keyword in the table area
    joined = " ".join(df2.astype(str).fillna("").values.flatten()).upper()
    expected = ["OUTSTANDING", "BALANCE", "LIMIT", "FACILITY", "LENDER", "DATE"]
    return any(k in joined for k in expected)


def extract_first_detailed_credit_table(
    pdf_path: str,
    flavor: str = "lattice",      # "lattice" works well when table has borders
    table_regions: Optional[List[str]] = None,  # e.g. ["50,750,560,80"] if you want to lock area
) -> Tuple[pd.DataFrame, int]:
    """
    Extract the FIRST table under the FIRST occurrence of
    'DETAILED CREDIT REPORT (BANKING ACCOUNTS)'.

    Returns: (table_df, page_number_1_based)
    Raises: ValueError if not found.
    """
    page_no = find_first_table_page(pdf_path)
    if page_no is None:
        raise ValueError(f"Header not found: {HEADER_TEXT}")

    # Camelot uses 1-based page indexing in string form
    pages_str = str(page_no)

    try:
        tables = camelot.read_pdf(
            pdf_path,
            pages=pages_str,
            flavor=flavor,
            table_regions=table_regions,  # optional; helps if extraction is messy
            strip_text="\n",
        )
    except (PdfReadError, PdfStreamError, OSError) as exc:
        raise ValueError(f"Failed to read PDF with Camelot: {exc}") from exc

    if tables.n == 0:
        # fallback: try stream (works for whitespace-separated tables)
        try:
            tables = camelot.read_pdf(
                pdf_path,
                pages=pages_str,
                flavor="stream",
                table_regions=table_regions,
                strip_text="\n",
            )
        except (PdfReadError, PdfStreamError, OSError) as exc:
            raise ValueError(f"Failed to read PDF with Camelot: {exc}") from exc

    for t in tables:
        df = t.df
        if _is_good_table(df):
            # Clean up: normalize spaces
            df = df.applymap(lambda x: re.sub(r"\s+", " ", str(x)).strip() if x is not None else "")
            return df, page_no

    raise ValueError("No valid table found on the header page (try table_regions or different flavor).")


def pick_pdf_file() -> Optional[str]:
    """Open a file picker to select a PDF."""
    root = tk.Tk()
    root.withdraw()
    root.update()

    file_path = filedialog.askopenfilename(
        title="Select Experian PDF",
        filetypes=[("PDF files", "*.pdf")],
    )

    root.destroy()
    return file_path if file_path else None


def validate_pdf_file(pdf_path: str) -> None:
    """Raise ValueError if the file is not a readable PDF."""
    try:
        with pdfplumber.open(pdf_path):
            return
    except Exception as exc:
        raise ValueError(f"Selected file is not a readable PDF: {exc}") from exc


def _normalize_facility(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def _parse_amount(value: str) -> Optional[float]:
    cleaned = re.sub(r"[,\s]", "", value)
    if cleaned in {"", "-", "N/A"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _find_header_row(df: pd.DataFrame) -> Optional[int]:
    for idx in range(len(df)):
        row_text = " ".join(df.iloc[idx].astype(str).fillna("").tolist()).upper()
        if "FACILITY" in row_text and ("LIMIT" in row_text or "OUTSTANDING" in row_text):
            return idx
    return None


def _find_column_index(header_row: pd.Series, keyword: str) -> Optional[int]:
    for idx, value in enumerate(header_row.astype(str).fillna("").tolist()):
        if keyword in value.upper():
            return idx
    return None


def evaluate_facility_limits(df: pd.DataFrame) -> Dict[str, str]:
    header_row_index = _find_header_row(df)
    if header_row_index is None:
        return {facility: "N/A" for facility in TARGET_FACILITIES}

    header_row = df.iloc[header_row_index]
    facility_idx = _find_column_index(header_row, "FACILITY")
    limit_idx = _find_column_index(header_row, "LIMIT")
    outstanding_idx = _find_column_index(header_row, "OUTSTANDING")

    if facility_idx is None or limit_idx is None or outstanding_idx is None:
        return {facility: "N/A" for facility in TARGET_FACILITIES}

    normalized_targets = {facility: _normalize_facility(facility) for facility in TARGET_FACILITIES}
    status_map: Dict[str, List[str]] = {facility: [] for facility in TARGET_FACILITIES}

    for row_idx in range(header_row_index + 1, len(df)):
        row = df.iloc[row_idx]
        facility_raw = str(row.iloc[facility_idx]).strip()
        if not facility_raw:
            continue
        normalized_facility = _normalize_facility(facility_raw)
        for facility, normalized_target in normalized_targets.items():
            if normalized_facility == normalized_target:
                limit_value = _parse_amount(str(row.iloc[limit_idx]))
                outstanding_value = _parse_amount(str(row.iloc[outstanding_idx]))
                if limit_value is None or outstanding_value is None:
                    continue
                status_map[facility].append("Yes" if outstanding_value <= limit_value else "No")

    results = {}
    for facility, statuses in status_map.items():
        if not statuses:
            results[facility] = "N/A"
        elif "No" in statuses:
            results[facility] = "No"
        else:
            results[facility] = "Yes"
    return results


if __name__ == "__main__":
    pdf_path = pick_pdf_file()
    if not pdf_path:
        print("No PDF selected. Exit.")
        raise SystemExit(0)

    validate_pdf_file(pdf_path)
    df, page_no = extract_first_detailed_credit_table(pdf_path)
    print(f"Extracted FIRST DETAILED CREDIT REPORT table from page {page_no}")
    print(df)

    facility_results = evaluate_facility_limits(df)
    print("Facility Limit Check (Outstanding <= Limit):")
    for facility, status in facility_results.items():
        print(f"  {facility}: {status}")

    # Optional: Save output
    df.to_csv("detailed_credit_report_first_table.csv", index=False)
    print("Saved: detailed_credit_report_first_table.csv")
