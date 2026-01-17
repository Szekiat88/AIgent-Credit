import re
from typing import Optional, Tuple, List

import pdfplumber
import pandas as pd

# Camelot requires: pip install camelot-py[cv]
import camelot


HEADER_TEXT = "DETAILED CREDIT REPORT (BANKING ACCOUNTS)"


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

    tables = camelot.read_pdf(
        pdf_path,
        pages=pages_str,
        flavor=flavor,
        table_regions=table_regions,  # optional; helps if extraction is messy
        strip_text="\n",
    )

    if tables.n == 0:
        # fallback: try stream (works for whitespace-separated tables)
        tables = camelot.read_pdf(
            pdf_path,
            pages=pages_str,
            flavor="stream",
            table_regions=table_regions,
            strip_text="\n",
        )

    for t in tables:
        df = t.df
        if _is_good_table(df):
            # Clean up: normalize spaces
            df = df.applymap(lambda x: re.sub(r"\s+", " ", str(x)).strip() if x is not None else "")
            return df, page_no

    raise ValueError("No valid table found on the header page (try table_regions or different flavor).")


if __name__ == "__main__":
    pdf_path = "/mnt/data/ZATIKIMIA SDN.  BHD._Experian_251215.pdf"

    df, page_no = extract_first_detailed_credit_table(pdf_path)
    print(f"Extracted FIRST DETAILED CREDIT REPORT table from page {page_no}")
    print(df)

    # Optional: Save output
    df.to_csv("detailed_credit_report_first_table.csv", index=False)
    print("Saved: detailed_credit_report_first_table.csv")
