import re
import json
from pathlib import Path
from typing import Optional

import tkinter as tk
from tkinter import filedialog

import pdfplumber


def _norm(s: str) -> str:
    """Normalize whitespace to make regex easier."""
    s = s.replace("\u00a0", " ")  # non-breaking space
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n+", "\n", s)
    return s.strip()


def read_pdf_text(pdf_path: str) -> str:
    """Read all pages from a PDF into one normalized text string."""
    if not Path(pdf_path).exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    chunks = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            chunks.append(page.extract_text() or "")
    return _norm("\n".join(chunks))


def extract_first(pattern: str, text: str, flags=re.IGNORECASE | re.DOTALL) -> Optional[str]:
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else None


def extract_int_after_label(label: str, text: str) -> Optional[int]:
    """
    Extract integer after a label like:
      'Winding Up Record 0'
      'Credit Applications Pending 3'
    Handles spacing/newlines.
    """
    label_esc = re.escape(label)
    pattern = rf"{label_esc}\s*[:\-]?\s*([0-9]+)"
    v = extract_first(pattern, text)
    return int(v) if v is not None else None


def extract_date_after_label(label: str, text: str) -> Optional[str]:
    """
    Extract date after label like:
      'Incorporation Date 04 Feb 2021'
    """
    label_esc = re.escape(label)
    pattern = rf"{label_esc}\s*[:\-]?\s*([0-9]{{1,2}}\s+[A-Za-z]{{3}}\s+[0-9]{{4}})"
    return extract_first(pattern, text)


def extract_word_after_label(label: str, text: str) -> Optional[str]:
    """
    Extract a short value after a label, e.g.:
      'Status EXISTING'
      'Private Exempt Company YES'
    """
    label_esc = re.escape(label)
    pattern = rf"{label_esc}\s*[:\-]?\s*([A-Za-z0-9\/\-\.\(\) ]{{1,80}})"
    v = extract_first(pattern, text)
    if not v:
        return None
    return v.split("\n")[0].strip()


def extract_iscore(text: str) -> Optional[int]:
    """
    Match:
      'i-SCORE 758'
    Returns first occurrence.
    """
    v = extract_first(r"\bi-SCORE\b\s*([0-9]{3})\b", text)
    return int(v) if v else None


def extract_legal_suits_total(text: str) -> Optional[int]:
    """
    Prefer summary 'Legal Suits 0' if present.
    Fallback: litigation section 'LEGAL SUITS ... Total: 0'
    """
    v = extract_int_after_label("Legal Suits", text)
    if v is not None:
        return v

    v2 = extract_first(r"LEGAL\s+SUITS.*?Total\s*:\s*([0-9]+)", text)
    return int(v2) if v2 else None


def extract_fields(pdf_path: str) -> dict:
    """Extract required fields from PDF."""
    text = read_pdf_text(pdf_path)

    incorporation_date = extract_date_after_label("Incorporation Date", text)
    incorporation_year = int(incorporation_date[-4:]) if incorporation_date else None

    return {
        "pdf_file": pdf_path,
        "i_SCORE": extract_iscore(text),
        "Incorporation_Year": incorporation_year,
        "Status": extract_word_after_label("Status", text),
        "Private_Exempt_Company": extract_word_after_label("Private Exempt Company", text),

        "Winding_Up_Record": extract_int_after_label("Winding Up Record", text),
        "Credit_Applications_Approved_Last_12_months": extract_int_after_label(
            "Credit Applications Approved for Last 12 months", text
        ),
        "Credit_Applications_Pending": extract_int_after_label("Credit Applications Pending", text),
        "Legal_Action_taken_from_Banking": extract_int_after_label("Legal Action taken (from Banking)", text),
        "Existing_No_of_Facility_from_Banking": extract_int_after_label(
            "Existing No. of Facility (from Banking)", text
        ),

        "Legal_Suits": extract_legal_suits_total(text),
    }


def pick_pdf_file() -> Optional[str]:
    """Open a file picker to select a PDF."""
    root = tk.Tk()
    root.withdraw()
    root.update()  # prevent some mac focus issues

    file_path = filedialog.askopenfilename(
        title="Select Experian PDF",
        filetypes=[("PDF files", "*.pdf")],
    )

    root.destroy()
    return file_path if file_path else None


if __name__ == "__main__":
    try:
        pdf_path = pick_pdf_file()
        if not pdf_path:
            print("No PDF selected. Exit.")
            raise SystemExit(0)

        print(f"Selected PDF: {pdf_path}")
        result = extract_fields(pdf_path)
        print(json.dumps(result, indent=2))

    except Exception as e:
        print(f"ERROR: {e}")
        raise
