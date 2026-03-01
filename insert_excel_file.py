"""Fill Knockout Matrix Excel from merged credit report data."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import openpyxl
from openpyxl.worksheet.worksheet import Worksheet

from merged_credit_report import merge_reports, resolve_pdf_path
from pdf_utils import pick_excel_file
import pdfplumber

SHEET_NAME = "Knock-Out"
LABEL_COL = 4  # Column D
DEFAULT_EXCEL = "Knockout Matrix Template.xlsx"
SCORE_RANGE_EQUIVALENTS = [
    (742, float("inf"), "A"), (701, 740, "A"), (661, 700, "B"),
    (621, 660, "B"), (581, 620, "C"), (541, 580, "C"),
    (501, 540, "D"), (461, 500, "E"), (421, 460, "F"), (0, 420, "F"),
]
MULTI_COL_PATTERNS = [
    "Scoring by CRA Agency (Issuer's Credit Agency Score)",
    "Scoring by CRA Agency (Credit Score Equivalent)",
    "Winding Up / Bankruptcy Proceedings Record",
    "Credit Applications Approved for Last 12 months (per primary CRA report)",
    "Credit Applications Pending (per primary CRA report)",
    "Legal Action taken (from Banking) (per primary CRA report)",
    "Existing No. of Facility (from Banking) (per primary CRA report)",
    "Legal Suits (per primary CRA report) (either as Plaintiff or Defendant)",
    "Legal Case - Status (per primary CRA report)",
    "Trade / Credit Reference (per primary CRA report)",
    "Total Enquiries for Last 12 months (per primary CRA report) (Financial Related Search Count)",
    "Special Attention Account (per primary CRA report)",
    "Summary of Total Liabilities (Outstanding) (per primary CRA report)",
    "Summary of Total Liabilities (Total Limit) (per primary CRA report)",
    "Overdraft facility outstanding amount does not exceed the approved overdraft limit as per CCRIS (based on the primary CRA report)",
    "Issuer's Total Banking Outstanding Facilities does not exceed the Total Banking Limit (per primary CRA report)",
    "Issuer's Total Non- Bank Lender Outstanding Facilities does not exceed the Total Non-Bank Lender Limit (per primary CRA report)",
    "CCRIS Loan Account - Conduct Count (per primary CRA report)",
    "CCRIS Loan Account - Legal Status (per primary CRA report)",
    "Non-Bank Lender Credit Information (NLCI)- Conduct Count (per primary CRA report)",
    "Non-Bank Lender Credit Information (NLCI) - Legal Status (per primary CRA report)",
]


def _norm(s: str) -> str:
    """Normalize string for comparison."""
    s = s or ""
    s = s.replace("\u2019", "'").replace("\u2018", "'")
    s = s.replace("\u201c", '"').replace("\u201d", '"')
    return re.sub(r"\s+", " ", s.replace("\n", " ")).strip().lower()


def _safe_int(value: Any) -> int:
    """Safely convert value to int."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _format_number(value: Optional[float | int]) -> Optional[str]:
    """Format number for display."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (int, float)):
        return f"{int(value)}" if float(value).is_integer() else f"{value}"
    return str(value)


def _format_mia_counts(value: Dict[str, Any]) -> Optional[str]:
    """Format MIA counts for display."""
    counts = {
        "next_six": value.get("next_six_numbers_digit_counts_0_1_2_3_5_plus"),
        "next_first": value.get("next_first_numbers_digit_counts_0_1_2_3_5_plus"),
        "last_1": value.get("last_1_month", {}).get("freq") if isinstance(value.get("last_1_month"), dict) else None,
        "last_6": value.get("last_6_months", {}).get("freq") if isinstance(value.get("last_6_months"), dict) else None,
    }
    
    if not any(isinstance(v, dict) for v in counts.values()):
        return None

    def format_counts(counts_dict: Dict[str, Any], plus_key: str) -> str:
        """Format counts as 'MIA1: X, MIA2: Y, ...'"""
        return f"MIA1: {_safe_int(counts_dict.get('1', 0))}, MIA2: {_safe_int(counts_dict.get('2', 0))}, MIA3: {_safe_int(counts_dict.get('3', 0))}, MIA4+: {_safe_int(counts_dict.get(plus_key, 0))}"

    parts = []
    if isinstance(counts["next_first"], dict):
        parts.append(f"current 1 month {format_counts(counts['next_first'], '5_plus')}")
    if isinstance(counts["last_1"], dict):
        parts.append(f"current 1 month {format_counts(counts['last_1'], '4+')}")
    if isinstance(counts["next_six"], dict):
        parts.append(f"past 6 months {format_counts(counts['next_six'], '5_plus')}")
    if isinstance(counts["last_6"], dict):
        parts.append(f"past 6 months {format_counts(counts['last_6'], '4+')}")

    return " and /or ".join(parts) if parts else None


def _format_cell_value(value: Any) -> Any:
    """Format cell value for Excel insertion."""
    if isinstance(value, dict):
        print(f"⚠️ Warning: Complex dict value for cell, attempting to format: {value}")
        mia_counts = _format_mia_counts(value)
        print(f"⚠️ Formatted MIA counts: {mia_counts}")
        return mia_counts if mia_counts else json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=False)
    return value


def _first_value(items: list[float] | None) -> Optional[float]:
    """Safely get first value from list."""
    if not items:
        return None
    return items[0]


def _compute_overdraft_compliance(analysis: Dict[str, Any]) -> str:
    """Compute overdraft compliance status."""
    totals_by_record = analysis.get("amount_totals", {}).get("by_record_no", {})
    first_values = analysis.get("first_line_numbers_after_date_by_record_no", {})
    
    if not totals_by_record and not first_values:
        return "N/A"

    failures = []
    for record_no, total in totals_by_record.items():
        first_val = _first_value(first_values.get(record_no))
        if first_val is not None and float(total) > float(first_val):
            failures.append(record_no)
    
    return "Yes" if not failures else "No"


def score_to_equivalent(score: Optional[int]) -> Optional[str]:
    """Convert credit score to equivalent grade."""
    if score is None:
        return None
    for lower, upper, grade in SCORE_RANGE_EQUIVALENTS:
        if lower <= score <= upper:
            return grade
    return None


def _format_non_bank_mia(stats: Dict[str, Any]) -> Optional[str]:
    """Format non-bank lender MIA counts for display."""
    if not isinstance(stats, dict):
        return None
    
    last_1 = stats.get("last_1_month", {}).get("freq") if isinstance(stats.get("last_1_month"), dict) else None
    last_6 = stats.get("last_6_months", {}).get("freq") if isinstance(stats.get("last_6_months"), dict) else None
    
    if not isinstance(last_1, dict) and not isinstance(last_6, dict):
        return None
    
    def format_counts(counts_dict: Dict[str, Any], plus_key: str) -> str:
        """Format counts as 'MIA1: X, MIA2: Y, ...'"""
        return f"MIA1: {_safe_int(counts_dict.get('1', 0))}, MIA2: {_safe_int(counts_dict.get('2', 0))}, MIA3: {_safe_int(counts_dict.get('3', 0))}, MIA4+: {_safe_int(counts_dict.get(plus_key, 0))}"
    
    parts = []
    if isinstance(last_1, dict):
        parts.append(f"current 1 month {format_counts(last_1, '4+')}")
    if isinstance(last_6, dict):
        parts.append(f"past 6 months {format_counts(last_6, '4+')}")
    
    return " and /or ".join(parts) if parts else None


def _get_non_bank_data(non_bank: Dict[str, Any]) -> tuple:
    """Extract non-bank lender data."""
    totals = non_bank.get("totals", {}) if isinstance(non_bank.get("totals"), dict) else {}
    stats = non_bank.get("stats_totals", {}) if isinstance(non_bank.get("stats_totals"), dict) else {}
    records = non_bank.get("records", []) if isinstance(non_bank.get("records"), list) else []
    
    # Format MIA counts for conduct count display
    mia_formatted = _format_non_bank_mia(stats)
    
    # Conduct count - use formatted MIA string if available, otherwise count records
    conduct_count = mia_formatted
    if conduct_count is None and records:
        # Fallback: count records (accounts) with ANY MIA (1, 2, 3, or 4+) in last 6 months
        count = 0
        for record in records:
            record_stats = record.get("stats", {})
            last_6_values = record_stats.get("last_6_months", {}).get("values", [])
            # Check if this record has ANY MIA (1, 2, 3, or 4+) in the last 6 months
            if any(val is not None and val >= 1 for val in last_6_values):
                count += 1
        conduct_count = count if count > 0 else None
    
    # Legal status
    markers = sorted({record.get("legal_marker") for record in records if record.get("legal_marker")})
    legal_status = ", ".join(markers) if markers else "No"
    
    return totals, stats, conduct_count, legal_status


def _within_limit(outstanding, limit) -> str:
    """Check if outstanding is within limit."""
    return "YES" if outstanding is not None and limit is not None and outstanding <= limit else "NO"


def build_knockout_data(merged: Dict[str, Any]) -> Dict[str, Any]:
    """Build knockout matrix data from merged report."""
    summary = merged.get("summary_report", {})
    detailed = merged.get("detailed_credit_report", {})
    non_bank = merged.get("non_bank_lender_credit_information", {})
    
    totals = detailed.get("totals", {})
    total_limit = totals.get("total_limit") or summary.get("Borrower_Total_Limit_RM")
    total_outstanding = totals.get("total_outstanding_balance") or summary.get("Borrower_Outstanding_RM")
    
    non_bank_totals, non_bank_stats, non_bank_conduct, non_bank_legal = _get_non_bank_data(non_bank)
    
    # Detect number of subjects
    num_subjects = 1
    while summary.get(f"Name_Of_Subject_{num_subjects + 1}"):
        num_subjects += 1
    
    # Helper functions
    def get_subject_field(field_name: str, subject_idx: int):
        return summary.get(field_name if subject_idx == 1 else f"{field_name}_{subject_idx}")
    
    def add_multi_subject_data(label: str, field_name: str, format_func=None):
        for i in range(1, num_subjects + 1):
            suffix = f" {i}" if i > 1 else ""
            value = get_subject_field(field_name, i)
            data[f"{label}{suffix}"] = format_func(value) if format_func else value
    
    # Build data
    data = {}
    
    # Credit scores
    for i in range(1, num_subjects + 1):
        suffix = f" {i}" if i > 1 else ""
        score = get_subject_field("i_SCORE", i)
        data[f"Scoring by CRA Agency (Issuer's Credit Agency Score){suffix}"] = _format_number(score)
        data[f"Scoring by CRA Agency (Credit Score Equivalent){suffix}"] = score_to_equivalent(score)
    
    # Single-column fields
    data["Business has been in operations for at least THREE (3) years (Including upgrade from Sole Proprietorship and Partnership under similar business activity)"] = _format_number(summary.get("Incorporation_Year"))
    data["Company Status (Existing Only)"] = summary.get("Status")
    data["Exempt Private Company"] = summary.get("Private_Exempt_Company")
    
    # Multi-subject fields
    add_multi_subject_data("Winding Up / Bankruptcy Proceedings Record", "Winding_Up_Record", _format_number)
    add_multi_subject_data("Credit Applications Approved for Last 12 months (per primary CRA report)", "Credit_Applications_Approved_Last_12_months", _format_number)
    add_multi_subject_data("Credit Applications Pending (per primary CRA report)", "Credit_Applications_Pending", _format_number)
    add_multi_subject_data("Legal Action taken (from Banking) (per primary CRA report)", "Legal_Action_taken_from_Banking", _format_number)
    add_multi_subject_data("Existing No. of Facility (from Banking) (per primary CRA report)", "Existing_No_of_Facility_from_Banking", _format_number)
    add_multi_subject_data("Legal Suits (per primary CRA report) (either as Plaintiff or Defendant)", "Legal_Suits", _format_number)
    add_multi_subject_data("Trade / Credit Reference (per primary CRA report)", "Trade_Credit_Reference", _format_number)

    
    # Legal Case Status
    for i in range(1, num_subjects + 1):
        suffix = f" {i}" if i > 1 else ""
        data[f"Legal Case - Status (per primary CRA report){suffix}"] = ", ".join([
            str(get_subject_field("Legal_Suits_Subject_As_Defendant_Defendant_Name", i) or "No"),
            str(get_subject_field("Other_Known_Legal_Suits_Subject_As_Defendant_Defendant_Name", i) or "No"),
            str(get_subject_field("Case_Withdrawn_Settled_Defendant_Name", i) or "No")
        ])
    
    # Note: "Trade / Credit Reference" is handled separately with section-based Amount Due data
    # Do not add subject-based data here to avoid conflicts with section data insertion
    add_multi_subject_data("Total Enquiries for Last 12 months (per primary CRA report) (Financial Related Search Count)", "Total_Enquiries_Last_12_months", _format_number)
    add_multi_subject_data("Special Attention Account (per primary CRA report)", "Special_Attention_Account", _format_number)
    add_multi_subject_data("Summary of Total Liabilities (Outstanding) (per primary CRA report)", "Borrower_Outstanding_RM", _format_number)
    add_multi_subject_data("Summary of Total Liabilities (Total Limit) (per primary CRA report)", "Borrower_Total_Limit_RM", _format_number)
    
    # Company-level data
    sections = detailed.get("sections", [])
    if not sections:
        sections = [{"account_line_analysis": detailed.get("account_line_analysis", {})}]
    
    overdraft_compliance = _compute_overdraft_compliance(sections[0].get("account_line_analysis", {})) if sections else "N/A"
    banking_status = f"{_within_limit(total_outstanding, total_limit)}, outstanding: {total_outstanding}, limit: {total_limit}"
    non_bank_within = _within_limit(non_bank_totals.get("total_outstanding"), non_bank_totals.get("total_limit"))
    
    for i in range(1, num_subjects + 1):
        suffix = f" {i}" if i > 1 else ""
        data[f"Overdraft facility outstanding amount does not exceed the approved overdraft limit as per CCRIS (based on the primary CRA report){suffix}"] = overdraft_compliance
        data[f"Issuer's Total Banking Outstanding Facilities does not exceed the Total Banking Limit (per primary CRA report){suffix}"] = banking_status
        data[f"Issuer's Total Non- Bank Lender Outstanding Facilities does not exceed the Total Non-Bank Lender Limit (per primary CRA report){suffix}"] = non_bank_within
        data[f"CCRIS Loan Account - Legal Status (per primary CRA report){suffix}"] = sections[0].get("account_line_analysis", {}).get("Bank_LOD") if sections else None
        data[f"Non-Bank Lender Credit Information (NLCI)- Conduct Count (per primary CRA report){suffix}"] = non_bank_conduct
        data[f"Non-Bank Lender Credit Information (NLCI) - Legal Status (per primary CRA report){suffix}"] = non_bank_legal
    
    data["Total Limit"] = _format_number(total_limit)
    data["Total Outstanding Balance"] = _format_number(total_outstanding)
    
    return data


def find_issuer_data_column(ws: Worksheet) -> int:
    """Find the 'Issuer' column for Knock-Out Items section."""
    for r in range(1, 11):
        for c in range(1, ws.max_column + 1):
            v = ws.cell(r, c).value
            if isinstance(v, str) and _norm(v) == "issuer":
                return c
    raise ValueError("Cannot find Issuer header column.")


def build_label_row_index(ws: Worksheet, label_col: int = LABEL_COL) -> Dict[str, int]:
    """Map each Knock-Out label text in column D to row number."""
    return {
        _norm(v): r
        for r in range(1, ws.max_row + 1)
        if (v := ws.cell(r, label_col).value) and isinstance(v, str) and v.strip()
    }


def set_issuer_name(ws: Worksheet, issuer_col: int, issuer_name: str) -> None:
    """Set Issuer Name next to 'Issuer Name:' label."""
    for r in range(1, ws.max_row + 1):
        v = ws.cell(r, 4).value
        if isinstance(v, str) and "issuer name" in _norm(v):
            ws.cell(r, issuer_col).value = issuer_name
            return


def set_cra_report_dates(ws: Worksheet, cra_report_date: Optional[str]) -> None:
    """Set CRA report dates in the worksheet."""
    if not cra_report_date:
        return
    
    for r in range(1, 15):
        for c in range(1, ws.max_column + 1):
            v = ws.cell(r, c).value
            if isinstance(v, str) and _norm(v) == "date (cra report):":
                target_col = c + 1
                for offset in range(1, 4):
                    next_cell = ws.cell(r, c + offset)
                    if isinstance(next_cell.value, str) and "dd/mm/yyyy" in next_cell.value.lower():
                        target_col = c + offset
                        break
                ws.cell(r, target_col).value = cra_report_date
                return


def _insert_section_data(ws: Worksheet, label: str, label_index: Dict[str, int], 
                         issuer_data_col: int, data_by_section: List[Any], 
                         format_func=None) -> int:
    """Insert section data into Excel columns."""
    row = label_index.get(_norm(label))
    if not row:
        print(f"⚠️ Could not find row for '{label}'")
        return 0
    
    written = 0
    for section_idx, data in enumerate(data_by_section):
        col_offset = section_idx * 2
        target_col = issuer_data_col + col_offset
        value = format_func(data) if format_func else data
        ws.cell(row, target_col).value = value
        written += 1
    
    return written


def fill_knockout_matrix(
    file_path: str,
    issuer_name: str,
    data_by_label: Dict[str, Any],
    cra_report_date: Optional[str] = None,
    all_subject_names: Optional[list[str]] = None,
    ccris_conduct_counts_by_section: Optional[list[Dict[str, Any]]] = None,
    trade_amounts_by_section: Optional[list[list[float]]] = None,
) -> str:
    """Fill the knockout matrix Excel template with data."""
    wb = openpyxl.load_workbook(file_path)
    if SHEET_NAME not in wb.sheetnames:
        raise ValueError(f"Sheet '{SHEET_NAME}' not found. Found: {wb.sheetnames}")

    ws = wb[SHEET_NAME]
    
    # Set issuer name
    for r in range(1, 30):
        if isinstance(ws.cell(r, 4).value, str) and "issuer name" in _norm(ws.cell(r, 4).value):
            set_issuer_name(ws, 5, issuer_name)
            break
    
    set_cra_report_dates(ws, cra_report_date)
    issuer_data_col = find_issuer_data_column(ws)
    
    # Insert subject names
    if all_subject_names is None:
        all_subject_names = [issuer_name]

    # Detect available subject columns from the header row so we do not write
    # names into unrelated columns when the template only defines a subset.
    # (Issuer + Director / Guarantor columns are every 2 columns apart.)
    subject_cols: list[int] = []
    for c in range(issuer_data_col, ws.max_column + 1, 2):
        header_values = [ws.cell(r, c).value for r in range(1, 12)]
        header_text = " ".join(str(v) for v in header_values if isinstance(v, str)).lower()
        if any(k in header_text for k in ("issuer", "director", "guarantor", "key person")):
            subject_cols.append(c)

    if not subject_cols:
        # Fallback to the original behavior if the template headers are unusual.
        subject_cols = [issuer_data_col + i * 2 for i in range(min(3, len(all_subject_names)))]

    for i, subject_name in enumerate(all_subject_names[:len(subject_cols)]):
        if subject_name:
            ws.cell(7, subject_cols[i]).value = subject_name

    # Keep overflow names visible instead of silently dropping them.
    if len(all_subject_names) > len(subject_cols) and subject_cols:
        overflow = [n for n in all_subject_names[len(subject_cols):] if n]
        if overflow:
            last_col = subject_cols[-1]
            existing = ws.cell(7, last_col).value
            existing_text = f"{existing}" if existing else ""
            overflow_text = " ; ".join(overflow)
            ws.cell(7, last_col).value = f"{existing_text} ; {overflow_text}" if existing_text else overflow_text
    
    label_index = build_label_row_index(ws, LABEL_COL)
    
    # Write main data
    missing = []
    written = 0
    
    for label, value in data_by_label.items():
        normalized_label = _norm(label)
        row = label_index.get(normalized_label)
        target_col = issuer_data_col
        
        # Check for multi-column fields
        if not row:
            for pattern in MULTI_COL_PATTERNS:
                for i in range(2, 20):
                    if normalized_label == _norm(pattern + f" {i}"):
                        row = label_index.get(_norm(pattern))
                        target_col = issuer_data_col + (i - 1) * 2
                        break
                if row:
                    break
        
        if not row:
            missing.append(label)
            continue

        ws.cell(row, target_col).value = _format_cell_value(value)
        written += 1

    # Insert CCRIS Conduct Count
    if ccris_conduct_counts_by_section:
        written += _insert_section_data(
            ws, "CCRIS Loan Account - Conduct Count (per primary CRA report)",
            label_index, issuer_data_col, ccris_conduct_counts_by_section,
            _format_cell_value
        )

    # Save output
    output_path = f"{os.path.splitext(file_path)[0]}_FILLED{os.path.splitext(file_path)[1]}"
    wb.save(output_path)

    if missing:
        print("⚠️ Missing labels:")
        for m in missing:
            print(f"  - {m}")

    return output_path


def _get_pdf_path(args, merged: Dict[str, Any]) -> Optional[str]:
    """Get PDF path from arguments or merged data."""
    if args.pdf:
        return args.pdf
    if args.merged_json:
        return merged.get("detailed_credit_report", {}).get("source_pdf") or merged.get("pdf_file")
    return resolve_pdf_path(args.pdf)


def _extract_sections_data(merged: Dict[str, Any]):
    """Extract section data from merged report."""
    detailed = merged.get("detailed_credit_report", {})
    sections = detailed.get("sections", [])
    return [
        section.get("account_line_analysis", {}).get("digit_counts_totals", {})
        for section in sections
        if section.get("account_line_analysis", {}).get("digit_counts_totals")
    ]


def _find_excel_template(excel_name: str = DEFAULT_EXCEL) -> Optional[str]:
    """
    Find the Excel template file. Checks multiple locations:
    1. PyInstaller temp directory (if bundled)
    2. Same directory as EXE/script
    3. Current working directory
    """
    search_paths = []
    
    # If running as EXE, check PyInstaller's temp directory first
    if getattr(sys, 'frozen', False):
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        if hasattr(sys, '_MEIPASS'):
            search_paths.append(Path(sys._MEIPASS))
        # Also check EXE directory
        search_paths.append(Path(sys.executable).parent)
    
    # Always check current working directory
    search_paths.append(Path.cwd())
    
    # If running as script, also check script directory
    if not getattr(sys, 'frozen', False):
        search_paths.append(Path(__file__).resolve().parent)
    
    # Search all paths
    for path in search_paths:
        excel_path = path / excel_name
        if excel_path.exists():
            return str(excel_path)
    
    return None


def main() -> None:
    """Main entry point."""
    try:
        parser = argparse.ArgumentParser(description="Fill Knockout Matrix Excel from merged credit report data.")
        parser.add_argument("--excel", help="Path to Knockout Matrix Template.xlsx (defaults to template in same directory)")
        parser.add_argument("--merged-json", help="Path to merged JSON output (skips PDF processing)")
        parser.add_argument("--pdf", help="Path to Experian PDF (opens picker if omitted)")
        parser.add_argument("--issuer", help="Issuer name (defaults to Name Of Subject from PDF)")
        args = parser.parse_args()

        # Get Excel file path (works in both script and EXE)
        if args.excel:
            excel_file = args.excel
            if not os.path.exists(excel_file):
                print(f"❌ Excel template not found at specified path: {excel_file}")
                raise SystemExit(1)
        else:
            # Try to find the Excel template automatically
            excel_file = _find_excel_template()
            if not excel_file:
                print(f"❌ Excel template '{DEFAULT_EXCEL}' not found!")
                print(f"\n💡 Please ensure '{DEFAULT_EXCEL}' is in one of these locations:")
                if getattr(sys, 'frozen', False):
                    print(f"   1. Same folder as the EXE: {Path(sys.executable).parent}")
                    print(f"   2. Current working directory: {Path.cwd()}")
                else:
                    print(f"   1. Same folder as the script: {Path(__file__).resolve().parent}")
                    print(f"   2. Current working directory: {Path.cwd()}")
                print(f"\n   OR use --excel argument to specify the full path")
                raise SystemExit(1)
            print(f"📄 Found Excel template: {excel_file}")
        
        # Load or generate merged report
        if args.merged_json:
            print("📄 Loading merged report from JSON...")
            if not os.path.exists(args.merged_json):
                print(f"❌ Merged JSON file not found: {args.merged_json}")
                raise SystemExit(1)
            with open(args.merged_json, "r", encoding="utf-8") as f:
                merged = json.load(f)
            pdf_path = merged.get("pdf_file") or merged.get("detailed_credit_report", {}).get("source_pdf")
            print("✅ Merged report loaded")
        else:
            # Get PDF path (opens picker if not provided)
            pdf_path = resolve_pdf_path(args.pdf)
            if not pdf_path:
                print("❌ No PDF file selected")
                raise SystemExit(1)
            
            print(f"📄 Processing PDF: {os.path.basename(pdf_path)}")
            print("📊 Generating merged report (this may take a moment for large PDFs)...")
            print("💡 Tip: Save merged JSON with 'python merged_credit_report.py --pdf file.pdf' for faster subsequent runs")
            merged = merge_reports(pdf_path)

        summary = merged.get("summary_report", {})
        issuer_name = args.issuer or summary.get("Name_Of_Subject") or "UNKNOWN ISSUER"

        # Keep all detected subject names (issuer + directors/guarantors) so they can
        # be written to the subject header columns in the knockout template.
        raw_subject_names = summary.get("all_names_of_subject") or []
        all_subject_names = [
            re.sub(r"\s+", " ", str(name)).strip()
            for name in raw_subject_names
            if name and str(name).strip()
        ]

        # Ensure issuer is always the first displayed subject.
        if issuer_name and issuer_name not in all_subject_names:
            all_subject_names.insert(0, issuer_name)
        
        # Build data
        data = build_knockout_data(merged)
        ccris_sections = _extract_sections_data(merged)
        
        # Extract trade amounts (extract PDF text once to avoid memory issues)
        # Get PDF path if not already set
        if not pdf_path:
            pdf_path = _get_pdf_path(args, merged)
        
        if pdf_path and os.path.exists(pdf_path):
            # Read the PDF once; share the text for all subsequent extractions.
            pdf_text_lines: List[str] = []
            try:
                print("📄 Reading PDF text...")
                with pdfplumber.open(pdf_path) as pdf:
                    for page in pdf.pages:
                        pdf_text_lines.extend((page.extract_text() or "").splitlines())
            except Exception as e:
                print(f"⚠️ Could not read PDF: {e}")

         
        elif not pdf_path:
            print("ℹ️  No PDF path available - skipping PDF extractions")
        
        # Fill Excel
        print(f"\n📝 Filling Excel template: {os.path.basename(excel_file)}")
        output = fill_knockout_matrix(
            excel_file,
            issuer_name,
            data,
            cra_report_date=summary.get("Last_Updated_By_Experian"),
            all_subject_names=all_subject_names or None,
            ccris_conduct_counts_by_section=ccris_sections or None,
        )
        print(f"\n✅ Success! File saved: {os.path.basename(output)}")
        print(f"📁 Location: {os.path.dirname(os.path.abspath(output))}")
    
    except KeyboardInterrupt:
        print("\n❌ Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
