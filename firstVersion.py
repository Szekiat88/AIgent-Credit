import re
import json
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    raise SystemExit(
        "Missing dependency: pdfplumber\n"
        "Install with: pip install pdfplumber"
    )

PDF_DEFAULT = "/mnt/data/AVANT GARDE SOLUTIONS (M) SDN. BHD._Experian_250811.pdf"


def _norm(s: str) -> str:
    """Normalize whitespace to make regex easier."""
    s = s.replace("\u00a0", " ")  # non-breaking space
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n+", "\n", s)
    return s.strip()


def read_pdf_text(pdf_path: str) -> str:
    pdf_path = str(pdf_path)
    if not Path(pdf_path).exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    chunks = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            txt = page.extract_text() or ""
            chunks.append(txt)
    return _norm("\n".join(chunks))


def extract_first(pattern: str, text: str, flags=re.IGNORECASE | re.DOTALL) -> str | None:
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else None


def extract_int_after_label(label: str, text: str) -> int | None:
    """
    Extract integer after a label like:
      'Winding Up Record 0'
      'Credit Applications Pending 3'
    Handles weird spacing / newlines.
    """
    # Escape label safely for regex, then allow flexible whitespace in between
    label_esc = re.escape(label)
    pattern = rf"{label_esc}\s*[:\-]?\s*([0-9]+)"
    val = extract_first(pattern, text)
    return int(val) if val is not None else None


def extract_date_after_label(label: str, text: str) -> str | None:
    """
    Extract date after label like:
      'Incorporation Date 04 Feb 2021'
    """
    label_esc = re.escape(label)
    pattern = rf"{label_esc}\s*[:\-]?\s*([0-9]{{1,2}}\s+[A-Za-z]{{3}}\s+[0-9]{{4}})"
    return extract_first(pattern, text)


def extract_word_after_label(label: str, text: str) -> str | None:
    """
    Extract a single 'word-ish' value after label, e.g.:
      'Status EXISTING'
      'Private Exempt Company N/A'
    """
    label_esc = re.escape(label)
    pattern = rf"{label_esc}\s*[:\-]?\s*([A-Za-z0-9\/\-\.\(\) ]{{1,60}})"
    val = extract_first(pattern, text)
    if val is None:
        return None
    # stop at newline if it captured too much
    return val.split("\n")[0].strip()


def extract_legal_suits_total(text: str) -> int | None:
    """
    Prefer the summary 'Legal Suits 0' if present.
    Fallback to litigation section 'LEGAL SUITS - SUBJECT AS DEFENDANT Total: 0'
    """
    # 1) Summary style
    v = extract_int_after_label("Legal Suits", text)
    if v is not None:
        return v

    # 2) Litigation section style
    v2 = extract_first(r"LEGAL\s+SUITS\s*-\s*SUBJECT\s+AS\s+DEFENDANT\s+Total\s*:\s*([0-9]+)", text)
    if v2 is not None:
        return int(v2)

    return None


def extract_iscore(text: str) -> int | None:
    """
    Match:
      'i-SCORE 758'
    (There can be multiple i-SCORE blocks in the report for PBI persons;
     this returns the FIRST one which is usually the company i-SCORE.)
    """
    v = extract_first(r"\bi-SCORE\b\s*([0-9]{3})\b", text)
    return int(v) if v else None


def extract_iscore_second(text: str) -> int | None:
    """
    Match:
      'i-SCORE 758'
    Returns the second occurrence if present.
    """
    matches = re.findall(r"\bi-SCORE\b\s*([0-9]{3})\b", text, re.IGNORECASE | re.DOTALL)
    if len(matches) < 2:
        return None
    return int(matches[1])


def extract_fields(pdf_path: str) -> dict:
    text = read_pdf_text(pdf_path)

    incorporation_date = extract_date_after_label("Incorporation Date", text)
    incorporation_year = int(incorporation_date[-4:]) if incorporation_date else None

    data = {
        "i_SCORE": extract_iscore(text),
        "i_SCORE_2": extract_iscore_second(text),
        "Incorporation_Year": incorporation_year,
        "Status": extract_word_after_label("Status", text),
        "Private_Exempt_Company": extract_word_after_label("Private Exempt Company", text),

        "Winding_Up_Record": extract_int_after_label("Winding Up Record", text),
        "Credit_Applications_Approved_Last_12_months": extract_int_after_label(
            "Credit Applications Approved for Last 12 months", text
        ),
        "Credit_Applications_Pending": extract_int_after_label("Credit Applications Pending", text),
        "Legal_Action_taken_from_Banking": extract_int_after_label("Legal Action taken (from Banking)", text),
        "Existing_No_of_Facility_from_Banking": extract_int_after_label("Existing No. of Facility (from Banking)", text),

        "Legal_Suits": extract_legal_suits_total(text),
    }

    return data


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", default=PDF_DEFAULT, help="Path to Experian PDF")
    parser.add_argument("--pretty", action="store_true", help="Pretty JSON output")
    args = parser.parse_args()

    result = extract_fields(args.pdf)
    if args.pretty:
        print(json.dumps(result, indent=2))
    else:
        print(json.dumps(result))
