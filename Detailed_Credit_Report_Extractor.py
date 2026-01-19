from __future__ import annotations

import json
import re
import tkinter as tk
from tkinter import filedialog
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict
from decimal import Decimal, InvalidOperation

import pdfplumber


# =============================
# FILE PICKER (YOUR FUNCTION)
# =============================
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


# =============================
# CONSTANTS
# =============================
START_MARKER = "DETAILED CREDIT REPORT (BANKING ACCOUNTS)"
END_MARKER = "CREDIT APPLICATION"

RE_RECORD_START = re.compile(r"^\s*(\d{1,4})\s+")
RE_DATE = re.compile(r"\b\d{2}/\d{2}/\d{4}\b")
RE_MONEY = re.compile(r"\b\d{1,3}(?:,\d{3})*(?:\.\d{2})?\b")
RE_TERM = re.compile(r"\b(MTH|BUL|REV|IDF|IRR)\b")
RE_DIGIT_TOKEN = re.compile(r"^\d+$")

ACCOUNT_KEYWORDS = (
    "OVRDRAFT",
    "TEMPOVDT",
    "RVVGCRDT",
    "INVOIFIN",
    "TRECEIPT",
    "BAOWNPCH",
    "BAOWNEXP",
    "CRDTCARD",
)


# =============================
# DATA STRUCTURE
# =============================
@dataclass
class BankingAccountRecord:
    no: int
    raw_lines: List[str]
    raw_text: str


def _parse_decimal(value: str) -> Optional[Decimal]:
    try:
        return Decimal(value.replace(",", ""))
    except (InvalidOperation, AttributeError):
        return None


def _extract_amount_before_date(line: str) -> Optional[Decimal]:
    date_match = RE_DATE.search(line)
    if not date_match:
        return None
    before_date = line[: date_match.start()]
    money_matches = list(RE_MONEY.finditer(before_date))
    if not money_matches:
        return None
    return _parse_decimal(money_matches[-1].group(0))


def _extract_numbers_after_date(line: str) -> List[Decimal]:
    date_match = RE_DATE.search(line)
    if not date_match:
        return []
    after_date = line[date_match.end() :]
    money_matches = list(RE_MONEY.finditer(after_date))
    values: List[Decimal] = []
    for match in money_matches:
        parsed = _parse_decimal(match.group(0))
        if parsed is not None:
            values.append(parsed)
    return values


def _digit_counts(value: str) -> Dict[str, int]:
    counts = {"0": 0, "1": 0, "2": 0, "3": 0, "5_plus": 0}
    for ch in value:
        if ch in {"0", "1", "2", "3"}:
            counts[ch] += 1
        elif ch.isdigit() and ch >= "5":
            counts["5_plus"] += 1
    return counts


def _extract_term_details(line: str) -> Optional[Dict[str, Any]]:
    match = RE_TERM.search(line)
    if not match:
        return None
    term = match.group(1)
    rest = line[match.end() :].strip()
    tokens = rest.split()
    runs: List[Dict[str, int]] = []
    current_start = None
    current_end = None
    for idx, token in enumerate(tokens):
        if RE_DIGIT_TOKEN.match(token):
            if current_start is None:
                current_start = idx
            current_end = idx
        else:
            if current_start is not None:
                runs.append({"start": current_start, "end": current_end})
                current_start = None
                current_end = None
    if current_start is not None:
        runs.append({"start": current_start, "end": current_end})

    numeric_tokens: List[str] = []
    trailing_words = ""
    if runs:
        last_run = runs[-1]
        numeric_tokens = tokens[last_run["start"] : last_run["end"] + 1]
        trailing_words = " ".join(tokens[last_run["end"] + 1 :]).strip()
    first_six_numbers = numeric_tokens[:6]
    first_number = first_six_numbers[0] if first_six_numbers else None
    next_five_numbers = first_six_numbers[1:6] if len(first_six_numbers) > 1 else []
    next_five_joined = "".join(next_five_numbers)

    return {
        "term": term,
        "numeric_sequence": first_six_numbers,
        "first_number": first_number,
        "first_number_digit_counts_0_1_2_3_5_plus": _digit_counts(first_number or ""),
        "next_five_numbers": next_five_numbers,
        "next_five_numbers_digit_counts_0_1_2_3_5_plus": _digit_counts(next_five_joined),
        "trailing_words": trailing_words,
    }


def analyze_account_lines(records: List[BankingAccountRecord]) -> Dict[str, Any]:
    results: List[Dict[str, Any]] = []
    totals: Dict[str, Decimal] = {}
    totals_by_record_no: Dict[int, Decimal] = {}

    for record in records:
        for line in record.raw_lines:
            matched_keyword = next((kw for kw in ACCOUNT_KEYWORDS if kw in line), None)
            if not matched_keyword:
                continue
            amount_before_date = _extract_amount_before_date(line)
            if amount_before_date is not None:
                totals[matched_keyword] = totals.get(matched_keyword, Decimal("0")) + amount_before_date
                totals_by_record_no[record.no] = totals_by_record_no.get(
                    record.no, Decimal("0")
                ) + amount_before_date

            term_details = _extract_term_details(line)
            results.append(
                {
                    "record_no": record.no,
                    "account_type": matched_keyword,
                    "raw_line": line,
                    "amount_before_date": (
                        float(amount_before_date) if amount_before_date is not None else None
                    ),
                    "term_details": term_details,
                }
            )

    total_amount = sum(totals.values(), Decimal("0"))
    totals_float = {key: float(value) for key, value in totals.items()}
    totals_by_record_no_float = {str(key): float(value) for key, value in totals_by_record_no.items()}
    return {
        "matched_lines": results,
        "amount_totals": {
            "by_account_type": totals_float,
            "by_record_no": totals_by_record_no_float,
            "overall": float(total_amount),
        },
    }


def extract_total_balances(pdf_path: str) -> Dict[str, Optional[float]]:
    pattern_outstanding = re.compile(
        r"TOTAL\s+OUTSTANDING\s+BALANCE\s*:\s*([0-9,]+(?:\.\d{2})?)",
        re.IGNORECASE,
    )
    pattern_limit = re.compile(
        r"TOTAL\s+LIMIT\s*:\s*([0-9,]+(?:\.\d{2})?)",
        re.IGNORECASE,
    )
    chunks: List[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            chunks.append(page.extract_text() or "")
    text = "\n".join(chunks)

    outstanding_match = pattern_outstanding.search(text)
    limit_match = pattern_limit.search(text)

    outstanding_value = _parse_decimal(outstanding_match.group(1)) if outstanding_match else None
    limit_value = _parse_decimal(limit_match.group(1)) if limit_match else None

    return {
        "total_outstanding_balance": float(outstanding_value) if outstanding_value is not None else None,
        "total_limit": float(limit_value) if limit_value is not None else None,
    }


# =============================
# STEP 1: EXTRACT LINES BETWEEN HEADERS
# =============================
def extract_section_lines(pdf_path: str) -> List[str]:
    lines_between: List[str] = []
    in_section = False

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue

                if not in_section and START_MARKER.lower() in line.lower():
                    in_section = True
                    continue

                if in_section and END_MARKER.lower() in line.lower():
                    return lines_between

                if in_section:
                    lines_between.append(line)

    return lines_between


# =============================
# STEP 2: SPLIT USING NUMBER DELIMITER
# =============================
def split_into_records(lines: List[str]) -> List[BankingAccountRecord]:
    records: List[BankingAccountRecord] = []
    current_no: Optional[int] = None
    current_lines: List[str] = []

    def flush():
        nonlocal current_no, current_lines
        if current_no is not None and current_lines:
            records.append(
                BankingAccountRecord(
                    no=current_no,
                    raw_lines=current_lines.copy(),
                    raw_text=" ".join(current_lines),
                )
            )
        current_no = None
        current_lines = []

    for line in lines:
        m = RE_RECORD_START.match(line)
        if m:
            flush()
            current_no = int(m.group(1))
            current_lines = [line]
        else:
            if current_no is not None:
                current_lines.append(line)

    flush()
    return records


# =============================
# MAIN
# =============================
def main():
    pdf_path = pick_pdf_file()
    if not pdf_path:
        print("❌ No PDF selected.")
        return

    print(f"📄 Selected PDF: {pdf_path}")

    section_lines = extract_section_lines(pdf_path)
    records = split_into_records(section_lines)
    total_balances = extract_total_balances(pdf_path)

    output: Dict[str, Any] = {
        "source_pdf": pdf_path,
        "section": {
            "start_marker": START_MARKER,
            "end_marker": END_MARKER,
        },
        "total_records": len(records),
        "records": [
            {
                **asdict(r),
                "first_line_numbers_after_date": [
                    float(value)
                    for value in _extract_numbers_after_date(r.raw_lines[0])
                    if value is not None
                ],
            }
            for r in records
        ],
        "account_line_analysis": analyze_account_lines(records),
        "totals": total_balances,
    }

    out_file = "detailed_credit_report_banking_accounts.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"✅ Extracted {len(records)} records")
    print(f"✅ Saved to {out_file}")


if __name__ == "__main__":
    main()
