from __future__ import annotations

import re
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from decimal import Decimal

import pdfplumber

from pdf_utils import parse_decimal, extract_all_sections, RE_MONEY


# =============================
# CONSTANTS
# =============================
START_MARKER = "DETAILED CREDIT REPORT (BANKING ACCOUNTS)"
END_MARKER = "CREDIT APPLICATION"

RE_RECORD_START = re.compile(r"^\s*(\d{1,4})\s+")
RE_DATE = re.compile(r"\b\d{2}/\d{2}/\d{4}\b")
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

LEGAL_STATUS_CODE_MAP = {
    "10": "Summon/Writ files",
    "11": "Judgement order/Order of sale",
    "12": "Bankruptcy",
    "13": "Charging order",
    "14": "Garnishee order",
    "15": "Writ of seizure and sale",
    "16": "Prohibitor order",
    "17": "Winding-up",
    "18": "Auction",
    "19": "Judgement debtor summon",
    "20": "Receiver/Section 176",
}


# =============================
# DATA STRUCTURE
# =============================
@dataclass
class BankingAccountRecord:
    no: int
    raw_lines: List[str]
    raw_text: str


def _extract_amount_before_date(line: str) -> Optional[Decimal]:
    date_match = RE_DATE.search(line)
    if not date_match:
        return None
    before_date = line[: date_match.start()]
    money_matches = list(RE_MONEY.finditer(before_date))
    if not money_matches:
        return None
    return parse_decimal(money_matches[-1].group(0))


def _extract_numbers_after_date(line: str) -> List[Decimal]:
    date_match = RE_DATE.search(line)
    if not date_match:
        return []
    after_date = line[date_match.end() :]
    money_matches = list(RE_MONEY.finditer(after_date))
    values: List[Decimal] = []
    for match in money_matches:
        parsed = parse_decimal(match.group(0))
        if parsed is not None:
            values.append(parsed)
    return values


def _digit_counts(value: str) -> Dict[str, int]:
    counts = {"0": 0, "1": 0, "2": 0, "3": 0, "5_plus": 0}
    for ch in value:
        if ch in {"0", "1", "2", "3"}:
            counts[ch] += 1
        elif ch.isdigit() and ch >= "4":
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
    bank_lod = ""
    if runs:
        last_run = runs[-1]
        numeric_tokens = tokens[last_run["start"] : last_run["end"] + 1]
        bank_lod = " ".join(tokens[last_run["end"] + 1 :]).strip()
    first_six_numbers = numeric_tokens[:6]
    first_number = first_six_numbers[0] if first_six_numbers else None
    next_six_joined = "".join(first_six_numbers)

    return {
        "term": term,
        "numeric_sequence": first_six_numbers,
        "first_number": first_number,
        "first_number_digit_counts_0_1_2_3_5_plus": _digit_counts(first_number or ""),
        "next_six_numbers_digit_counts_0_1_2_3_5_plus": _digit_counts(next_six_joined),
        "bank_lod": bank_lod,
    }


def _extract_legal_status_codes(line: str) -> List[str]:
    sanitized = RE_DATE.sub(" ", line)
    sanitized = RE_MONEY.sub(" ", sanitized)
    return re.findall(r"(?<!\d)(1[0-9]|20)(?!\d)", sanitized)


def _extract_outstanding_limit_values(line: str) -> Dict[str, Optional[Decimal]]:
    number_capture = r"([0-9][0-9,\s]*(?:\.\d{2})?)"
    outstanding_patterns = [
        re.compile(
            rf"OUTSTANDING\s*[:\-]?\s*(?:RM\s*)?{number_capture}",
            re.IGNORECASE,
        )
    ]
    limit_patterns = [
        re.compile(
            rf"LIMIT(?:\s*\(RM\))?\s*[:\-]?\s*(?:RM\s*)?{number_capture}",
            re.IGNORECASE,
        )
    ]
    paired_pattern = re.compile(
        rf"OUTSTANDING\s*[:\-]?\s*(?:RM\s*)?{number_capture}"
        rf"\s*,?\s*LIMIT(?:\s*\(RM\))?\s*[:\-]?\s*(?:RM\s*)?{number_capture}",
        re.IGNORECASE,
    )

    flattened_line = re.sub(r"\s+", " ", line)
    outstanding_value: Optional[Decimal] = None
    limit_value: Optional[Decimal] = None

    paired_match = paired_pattern.search(flattened_line)
    if paired_match:
        outstanding_value = parse_decimal(paired_match.group(1).replace(" ", ""))
        limit_value = parse_decimal(paired_match.group(2).replace(" ", ""))

    if outstanding_value is None:
        for pattern in outstanding_patterns:
            match = pattern.search(flattened_line)
            if match:
                outstanding_value = parse_decimal(match.group(1).replace(" ", ""))
                if outstanding_value is not None:
                    break

    if limit_value is None:
        for pattern in limit_patterns:
            match = pattern.search(flattened_line)
            if match:
                limit_value = parse_decimal(match.group(1).replace(" ", ""))
                if limit_value is not None:
                    break

    return {
        "outstanding": outstanding_value,
        "limit": limit_value,
    }


def analyze_account_lines(records: List[BankingAccountRecord]) -> Dict[str, Any]:
    first_line_numbers_after_date_by_record_no: Dict[str, List[float]] = {}
    next_first_digit_totals = {"0": 0, "1": 0, "2": 0, "3": 0, "5_plus": 0}
    next_six_digit_totals = {"0": 0, "1": 0, "2": 0, "3": 0, "5_plus": 0}
    totals_by_record_no_float: Dict[str, float] = {}
    overdraft_comparisons: Dict[str, Dict[str, Optional[float]]] = {}
    outstanding_limit_comparisons: Dict[str, Dict[str, Optional[float]]] = {}
    legal_status_codes: List[str] = []

    for record in records:
        first_line_values = (
            _extract_numbers_after_date(record.raw_lines[0]) if record.raw_lines else []
        )
        if record.raw_lines:
            first_line_numbers_after_date_by_record_no[str(record.no)] = [
                float(value)
                for value in first_line_values
                if value is not None
            ]
        record_overdraft_outstanding = Decimal("0")
        has_overdraft_keyword = False
        record_outstanding: Optional[Decimal] = None
        record_limit: Optional[Decimal] = None

        for line in record.raw_lines:
            for code in _extract_legal_status_codes(line):
                if code not in legal_status_codes:
                    legal_status_codes.append(code)

            matched_keyword = next((kw for kw in ACCOUNT_KEYWORDS if kw in line), None)
            if matched_keyword == "OVRDRAFT":
                has_overdraft_keyword = True
                overdraft_amount = _extract_amount_before_date(line)
                if overdraft_amount is not None:
                    record_overdraft_outstanding += overdraft_amount
            
            amount_before_date = _extract_amount_before_date(line)
            if amount_before_date is not None:
                key = str(record.no)
                totals_by_record_no_float[key] = totals_by_record_no_float.get(key, 0.0) + float(amount_before_date)

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

            outstanding_limit_values = _extract_outstanding_limit_values(line)
            if (
                record_outstanding is None
                and outstanding_limit_values.get("outstanding") is not None
            ):
                record_outstanding = outstanding_limit_values["outstanding"]
            if record_limit is None and outstanding_limit_values.get("limit") is not None:
                record_limit = outstanding_limit_values["limit"]

        if has_overdraft_keyword:
            overdraft_limit = float(first_line_values[0]) if first_line_values else None
            overdraft_comparisons[str(record.no)] = {
                "outstanding": float(record_overdraft_outstanding),
                "limit": overdraft_limit,
            }
        if record_outstanding is not None or record_limit is not None:
            outstanding_float = float(record_outstanding) if record_outstanding is not None else None
            limit_float = float(record_limit) if record_limit is not None else None
            outstanding_limit_comparisons[str(record.no)] = {
                "outstanding": outstanding_float,
                "limit": limit_float,
                "within_limit": (
                    outstanding_float <= limit_float
                    if outstanding_float is not None and limit_float is not None
                    else None
                ),
            }

    first_line_numbers_after_date_filtered = {
        key: first_line_numbers_after_date_by_record_no.get(key, [])
        for key in totals_by_record_no_float
    }

    return {
        "amount_totals": {
            "by_record_no": totals_by_record_no_float,
        },
        "first_line_numbers_after_date_by_record_no": first_line_numbers_after_date_filtered,
        "digit_counts_totals": {
            "next_first_numbers_digit_counts_0_1_2_3_5_plus": next_first_digit_totals,
            "next_six_numbers_digit_counts_0_1_2_3_5_plus": next_six_digit_totals,
        },
        "overdraft_comparisons": overdraft_comparisons,
        "outstanding_limit_comparisons": outstanding_limit_comparisons,
        "legal_status_codes": legal_status_codes,
        "legal_status_details": [
            f"{code} = {LEGAL_STATUS_CODE_MAP.get(code, 'Unknown')}"
            for code in legal_status_codes
        ],
    }


def extract_total_balances(pdf_path: str) -> Dict[str, Optional[float]]:
    # Read totals from the DETAILED CREDIT REPORT (BANKING ACCOUNTS) section to avoid
    # capturing similarly named fields from other report sections.
    all_section_lines = extract_all_sections(pdf_path, START_MARKER, END_MARKER)

    number_capture = r"([0-9][0-9,\s]*(?:\.\d{2})?)"

    # Compact format seen in extracted lines:
    # "TOTAL TOTAL OUTSTANDING 15,520,690.00 LIMIT: 17,714,987.00"
    # Do not require the word "BALANCE" because many files only show "OUTSTANDING".
    paired_totals_pattern = re.compile(
        rf"OUTSTANDING\s*[:\-]?\s*(?:RM\s*)?{number_capture}"
        rf"\s+LIMIT(?:\s*\(RM\))?\s*[:\-]?\s*(?:RM\s*)?{number_capture}",
        re.IGNORECASE,
    )
    outstanding_patterns = [
        re.compile(
            rf"OUTSTANDING\s*[:\-]?\s*(?:RM\s*)?{number_capture}",
            re.IGNORECASE,
        )
    ]
    limit_patterns = [
        re.compile(
            rf"LIMIT(?:\s*\(RM\))?\s*[:\-]?\s*(?:RM\s*)?{number_capture}",
            re.IGNORECASE,
        )
    ]

    def iter_patterns(patterns):
        if isinstance(patterns, re.Pattern):
            return (patterns,)
        return patterns

    def extract_from_text(text: str) -> Dict[str, Optional[Decimal]]:
        flattened_text = re.sub(r"\s+", " ", text)
        outstanding_value: Optional[Decimal] = None
        limit_value: Optional[Decimal] = None

        paired_match = paired_totals_pattern.search(flattened_text)
        if paired_match:
            outstanding_value = parse_decimal(paired_match.group(1).replace(" ", ""))
            limit_value = parse_decimal(paired_match.group(2).replace(" ", ""))

        if outstanding_value is None:
            for pattern in iter_patterns(outstanding_patterns):
                outstanding_match = pattern.search(flattened_text)
                if outstanding_match:
                    outstanding_value = parse_decimal(outstanding_match.group(1).replace(" ", ""))
                    if outstanding_value is not None:
                        break

        if limit_value is None:
            for pattern in iter_patterns(limit_patterns):
                limit_match = pattern.search(flattened_text)
                if limit_match:
                    limit_value = parse_decimal(limit_match.group(1).replace(" ", ""))
                    if limit_value is not None:
                        break

        return {
            "outstanding": outstanding_value,
            "limit": limit_value,
        }

    per_section_totals: List[Dict[str, Optional[Decimal]]] = []
    for section_lines in all_section_lines:
        section_text = "\n".join(section_lines)
        if section_text.strip():
            per_section_totals.append(extract_from_text(section_text))

    # Fallback when no detailed section is found.
    if not per_section_totals:
        chunks: List[str] = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                chunks.append(page.extract_text() or "")
        full_text = "\n".join(chunks)
        per_section_totals.append(extract_from_text(full_text))

    outstanding_sum = sum(
        (item["outstanding"] for item in per_section_totals if item["outstanding"] is not None),
        Decimal("0"),
    )
    limit_sum = sum(
        (item["limit"] for item in per_section_totals if item["limit"] is not None),
        Decimal("0"),
    )
    has_outstanding = any(item["outstanding"] is not None for item in per_section_totals)
    has_limit = any(item["limit"] is not None for item in per_section_totals)

    return {
        "total_outstanding_balance": float(outstanding_sum) if has_outstanding else None,
        "total_limit": float(limit_sum) if has_limit else None,
    }


# =============================
# STEP 1: SPLIT USING NUMBER DELIMITER
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
    """
    Extract all DETAILED CREDIT REPORT (BANKING ACCOUNTS) sections from PDF.
    Handles multiple occurrences and processes each separately.
    """
    all_section_lines = extract_all_sections(pdf_path, START_MARKER, END_MARKER)
    total_balances = extract_total_balances(pdf_path)
    
    sections_data = []
    
    
    for section_idx, section_lines in enumerate(all_section_lines, start=1):
      
        records = split_into_records(section_lines)
        analysis = analyze_account_lines(records)
        print("Hello: ", analysis)
             
        sections_data.append({
            "section_number": section_idx,
            "record_count": len(records),
            "account_line_analysis": analysis,
        })

    output: Dict[str, Any] = {
        "source_pdf": pdf_path,
        "section": {
            "start_marker": START_MARKER,
            "end_marker": END_MARKER,
        },
        "total_sections_found": len(all_section_lines),
        "sections": sections_data,
        "totals": total_balances,
    }

    return output
