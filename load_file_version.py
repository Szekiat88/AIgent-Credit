import re
import json
from pathlib import Path
from typing import Optional

import tkinter as tk
from tkinter import filedialog

import pdfplumber

RE_MONEY = re.compile(r"\b\d{1,3}(?:,\d{3})*(?:\.\d{2})?\b")


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


def extract_last_updated_by_experian(text: str) -> Optional[str]:
    """
    Extract the "Last Updated by Experian" date.
    Accepts either DD MMM YYYY or DD/MM/YYYY style dates.
    """
    patterns = [
        r"Order Date:\s*[:\-]?\s*([0-9]{1,2}\s+[A-Za-z]{3}\s+[0-9]{4})",
        r"Order Date:\s*[:\-]?\s*([0-9]{1,2}/[0-9]{1,2}/[0-9]{4})",
    ]
    for pattern in patterns:
        value = extract_first(pattern, text)
        if value:
            return value
    return None


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


def extract_name_of_subject(text: str) -> Optional[str]:
    """
    Extract the Name Of Subject field.
    Accepts any non-empty line after the label.
    """
    v = extract_first(r"Name Of Subject\s*[:\-]?\s*([^\n]+)", text)
    return v.strip() if v else None


def parse_money(value: str) -> Optional[float]:
    if not value:
        return None
    return float(value.replace(",", ""))


def extract_iscore(text: str) -> Optional[int]:
    """
    Match:
      'i-SCORE 758'
    Returns first occurrence.
    """
    v = extract_first(r"\bi-SCORE\b\s*([0-9]{3})\b", text)
    return int(v) if v else None


def extract_iscore_second(text: str) -> Optional[int]:
    """
    Match:
      'i-SCORE 758'
    Returns second occurrence if present.
    """
    matches = re.findall(r"\bi-SCORE\b\s*([0-9]{3})\b", text, re.IGNORECASE | re.DOTALL)
    if len(matches) < 2:
        return None
    return int(matches[1])


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


def extract_section_after_header(header: str, text: str) -> Optional[str]:
    header_esc = re.escape(header)
    pattern = rf"{header_esc}.*?(?=\n[A-Z][A-Z &/\-]{{5,}}\n|$)"
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    return match.group(0) if match else None


def extract_borrower_liabilities(text: str) -> tuple[Optional[float], Optional[float]]:
    section = extract_section_after_header("SUMMARY OF POTENTIAL & CURRENT LIABILITIES", text)
    if not section:
        return None, None

    lines = [line.strip() for line in section.splitlines() if line.strip()]
    header_idx = next(
        (idx for idx, line in enumerate(lines) if "Outstanding" in line and "Total Limit" in line),
        None,
    )
    if header_idx is None:
        search_lines = lines
    else:
        search_lines = lines[header_idx + 1 :]

    for idx, line in enumerate(search_lines):
        if re.search(r"\bBorrower\b", line, re.IGNORECASE):
            combined = line
            if idx + 1 < len(search_lines):
                combined = f"{combined} {search_lines[idx + 1]}"
            amounts = [m.group(0) for m in RE_MONEY.finditer(combined)]
            if len(amounts) >= 2:
                return parse_money(amounts[0]), parse_money(amounts[1])
    return None, None


def extract_trade_credit_amount_due(text: str) -> Optional[float]:
    section = extract_text_between_headers(
        "TRADE / CREDIT REFERENCE (CR)",
        "LEGEND",
        text,
    )
    if not section:
        return None
    amounts = re.findall(
        r"Amount\s+Due\s*[:\-]?\s*([0-9][0-9,]*(?:\.\d{2})?)",
        section,
        re.IGNORECASE,
    )
    if not amounts:
        return None
    return sum(parse_money(amount) or 0 for amount in amounts)


def extract_text_between_headers(start_header: str, end_header: str, text: str) -> Optional[str]:
    start_esc = re.escape(start_header)
    end_esc = re.escape(end_header)
    pattern = rf"{start_esc}(.*?){end_esc}"
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    return match.group(1) if match else None

def extract_litigation_defendant_flags(text: str) -> dict[str, str]:
    section = extract_section_after_header("SECTION 3: LITIGATION INFORMATION", text)
    labels = [
        "CASE WITHDRAWN / SETTLED",
        "OTHER KNOWN LEGAL SUITS WITH LIMITED DETAILS - SUBJECT AS DEFENDANT",
        "LEGAL SUITS - SUBJECT AS DEFENDANT",
    ]

    def subsection_after_label(section_text: str, label: str) -> Optional[str]:
        label_esc = re.escape(label)
        other_labels = [re.escape(item) for item in labels if item != label]
        if other_labels:
            boundary = "|".join(other_labels)
            pattern = rf"{label_esc}\s*(.*?)(?=({boundary})|$)"
        else:
            pattern = rf"{label_esc}\s*(.*)$"
        match = re.search(pattern, section_text, re.IGNORECASE | re.DOTALL)
        return match.group(1) if match else None

    def has_defendant_name(block: Optional[str]) -> bool:
        if not block:
            return False
        return re.search(r"\bDefendant Name\b", block, re.IGNORECASE) is not None

    if not section:
        return {
            "Case_Withdrawn_Settled_Defendant_Name": "No",
            "Other_Known_Legal_Suits_Subject_As_Defendant_Defendant_Name": "No",
            "Legal_Suits_Subject_As_Defendant_Defendant_Name": "No",
        }

    return {
        "Case_Withdrawn_Settled_Defendant_Name": "Yes"
        if has_defendant_name(subsection_after_label(section, labels[0]))
        else "No",
        "Other_Known_Legal_Suits_Subject_As_Defendant_Defendant_Name": "Yes"
        if has_defendant_name(subsection_after_label(section, labels[1]))
        else "No",
        "Legal_Suits_Subject_As_Defendant_Defendant_Name": "Yes"
        if has_defendant_name(subsection_after_label(section, labels[2]))
        else "No",
    }


def extract_fields(pdf_path: str) -> dict:
    """Extract required fields from PDF."""
    text = read_pdf_text(pdf_path)
    print("text: ", text)

    incorporation_date = extract_date_after_label("Incorporation Date", text)
    incorporation_year = int(incorporation_date[-4:]) if incorporation_date else None
    borrower_outstanding, borrower_total_limit = extract_borrower_liabilities(text)
    litigation_flags = extract_litigation_defendant_flags(text)

    return {
        "pdf_file": pdf_path,
        "Name_Of_Subject": extract_name_of_subject(text),
        "i_SCORE": extract_iscore(text),
        "i_SCORE_2": extract_iscore_second(text),
        "Incorporation_Year": incorporation_year,
        "Status": extract_word_after_label("Status", text),
        "Private_Exempt_Company": extract_word_after_label("Private Exempt Company", text),
        "Last_Updated_By_Experian": extract_last_updated_by_experian(text),

        "Winding_Up_Record": extract_int_after_label("Winding Up Record", text),
        "Credit_Applications_Approved_Last_12_months": extract_int_after_label(
            "Credit Applications Approved for Last 12 months", text
        ),
        "Credit_Applications_Pending": extract_int_after_label("Credit Applications Pending", text),
        "Legal_Action_taken_from_Banking": extract_int_after_label("Legal Action taken (from Banking)", text),
        "Existing_No_of_Facility_from_Banking": extract_int_after_label(
            "Existing No. of Facility (from Banking)", text
        ),
        "Total_Enquiries_Last_12_months": extract_int_after_label(
            "Total Enquiries for Last 12 months", text
        ),
        "Special_Attention_Account": extract_int_after_label("Special Attention Account", text),

        "Legal_Suits": extract_legal_suits_total(text),
        "Borrower_Outstanding_RM": borrower_outstanding,
        "Borrower_Total_Limit_RM": borrower_total_limit,
        "Trade_Credit_Reference_Amount_Due_RM": extract_trade_credit_amount_due(text),
        **litigation_flags,
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
