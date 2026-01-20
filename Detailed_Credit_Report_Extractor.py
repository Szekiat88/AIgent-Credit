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
    next_six_joined = "".join(first_six_numbers)

    return {
        "term": term,
        "numeric_sequence": first_six_numbers,
        "first_number": first_number,
        "first_number_digit_counts_0_1_2_3_5_plus": _digit_counts(first_number or ""),
        "next_six_numbers_digit_counts_0_1_2_3_5_plus": _digit_counts(next_six_joined),
        "trailing_words": trailing_words,
    }


def analyze_account_lines(records: List[BankingAccountRecord]) -> Dict[str, Any]:
    results: List[Dict[str, Any]] = []
    amounts_by_record_no: Dict[int, List[Decimal]] = {}
    first_line_numbers_after_date_by_record_no: Dict[str, List[float]] = {}
    next_first_digit_totals = {"0": 0, "1": 0, "2": 0, "3": 0, "5_plus": 0}
    next_six_digit_totals = {"0": 0, "1": 0, "2": 0, "3": 0, "5_plus": 0}

    for record in records:
        if record.raw_lines:
            first_line_numbers_after_date_by_record_no[str(record.no)] = [
                float(value)
                for value in _extract_numbers_after_date(record.raw_lines[0])
                if value is not None
            ]
        for line in record.raw_lines:
            matched_keyword = next((kw for kw in ACCOUNT_KEYWORDS if kw in line), None)
            if not matched_keyword:
                continue
            amount_before_date = _extract_amount_before_date(line)

            term_details = _extract_term_details(line)
            if term_details:
                next_first_counts = term_details.get(
                    "first_number_digit_counts_0_1_2_3_5_plus", {}
                )
                next_six_counts = term_details.get(
                    "next_six_numbers_digit_counts_0_1_2_3_5_plus", {}
                )
                for key in next_six_digit_totals:
                    next_first_digit_totals[key] += next_first_counts.get(key, 0)
                    next_six_digit_totals[key] += next_six_counts.get(key, 0)
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

    amounts_by_record_no_float = {
        str(key): {
            "amounts": [float(value) for value in values],
            "total": float(sum(values, Decimal("0"))),
        }
        for key, values in amounts_by_record_no.items()
    }
    totals_by_record_no_float: Dict[str, float] = {}
    for entry in results:
        amount = entry.get("amount_before_date")
        record_no = entry.get("record_no")
        if amount is None or record_no is None:
            continue
        key = str(record_no)
        totals_by_record_no_float[key] = totals_by_record_no_float.get(key, 0.0) + amount
    first_line_numbers_after_date_filtered: Dict[str, List[float]] = {}
    first_line_numbers_after_date_gt_total: Dict[str, Optional[bool]] = {}
    for key, total in totals_by_record_no_float.items():
        numbers = first_line_numbers_after_date_by_record_no.get(key, [])
        first_line_numbers_after_date_filtered[key] = numbers
        first_value = numbers[0] if numbers else None
        first_line_numbers_after_date_gt_total[key] = (
            first_value > total if first_value is not None else None
        )
    return {
        # "matched_lines": results,
        "amount_totals": {
            "by_record_no": totals_by_record_no_float,
        },
        "amounts_by_record_no": amounts_by_record_no_float,
        "first_line_numbers_after_date_by_record_no": first_line_numbers_after_date_filtered,
        "first_line_numbers_after_date_gt_total_by_record_no": (
            first_line_numbers_after_date_gt_total
        ),
        "digit_counts_totals": {
            "next_first_numbers_digit_counts_0_1_2_3_5_plus": next_first_digit_totals
        },
        "amounts_by_record_no": amounts_by_record_no_float,
        "digit_counts_totals": {
            "next_first_numbers_digit_counts_0_1_2_3_5_plus": next_first_digit_totals,
            "next_six_numbers_digit_counts_0_1_2_3_5_plus": next_six_digit_totals,
        },
    }


def extract_total_balances(pdf_path: str) -> Dict[str, Optional[float]]:
    pattern_outstanding = re.compile(
        r"OUTSTANDING\s*([0-9,]+(?:\.\d{2})?)",
        re.IGNORECASE,
    )
    pattern_limit = re.compile(
        r"LIMIT\s*:\s*([0-9,]+(?:\.\d{2})?)",
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
def extract_detailed_credit_report(pdf_path: str) -> Dict[str, Any]:
    section_lines = extract_section_lines(pdf_path)
    records = split_into_records(section_lines)
    total_balances = extract_total_balances(pdf_path)

    output: Dict[str, Any] = {
        "source_pdf": pdf_path,
        "section": {
            "start_marker": START_MARKER,
            "end_marker": END_MARKER,
        },
        # "total_records": len(records),
        # "records": [
        #     {
        #         **asdict(r),
        #         "first_line_numbers_after_date": [
        #             float(value)
        #             for value in _extract_numbers_after_date(r.raw_lines[0])
        #             if value is not None
        #         ],
        #     }
        #     for r in records
        # ],
        "account_line_analysis": analyze_account_lines(records),
        "totals": total_balances,
    }

    return output


def main():
    pdf_path = pick_pdf_file()
    if not pdf_path:
        print("❌ No PDF selected.")
        return

    print(f"📄 Selected PDF: {pdf_path}")

    output = extract_detailed_credit_report(pdf_path)
    out_file = "detailed_credit_report_banking_accounts.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    record_count = len(output.get("account_line_analysis", {}).get("amount_totals", {}).get("by_record_no", {}))
    print(f"✅ Extracted {record_count} records")
    print(f"✅ Saved to {out_file}")


if __name__ == "__main__":
    main()
