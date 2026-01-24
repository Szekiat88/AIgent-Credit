from __future__ import annotations

import argparse
import json
import os
import re
import tkinter as tk
from pathlib import Path
from tkinter import filedialog
from typing import Any, Dict, Optional

import openpyxl
from openpyxl.worksheet.worksheet import Worksheet

from merged_credit_report import merge_reports, resolve_pdf_path

SHEET_NAME = "Knock-Out"
LABEL_COL = 4  # D
DEFAULT_EXCEL = "Knockout Matrix Template.xlsx"
SCORE_RANGE_EQUIVALENTS = [
    (742, float("inf"), "A"),
    (701, 740, "A"),
    (661, 700, "B"),
    (621, 660, "B"),
    (581, 620, "C"),
    (541, 580, "C"),
    (501, 540, "D"),
    (461, 500, "E"),
    (421, 460, "F"),
    (0, 420, "F"),
]


def pick_excel_file() -> Optional[str]:
    root = tk.Tk()
    root.withdraw()
    root.update()

    path = filedialog.askopenfilename(
        title="Select Knockout Matrix Excel File",
        filetypes=[("Excel files", "*.xlsx")],
    )

    root.destroy()
    return path if path else None


def _norm(s: str) -> str:
    s = s or ""
    s = s.replace("\u2019", "'").replace("\u2018", "'")
    s = s.replace("\u201c", '"').replace("\u201d", '"')
    s = s.replace("\n", " ")
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def _format_number(value: Optional[float | int]) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (int, float)):
        return f"{int(value)}" if float(value).is_integer() else f"{value}"
    return str(value)


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _format_mia_counts(value: Dict[str, Any]) -> Optional[str]:
    next_six_counts = value.get("next_six_numbers_digit_counts_0_1_2_3_5_plus")
    next_first_counts = value.get("next_first_numbers_digit_counts_0_1_2_3_5_plus")
    last_1_counts = value.get("last_1_month", {}).get("freq") if isinstance(value.get("last_1_month"), dict) else None
    last_6_counts = value.get("last_6_months", {}).get("freq") if isinstance(value.get("last_6_months"), dict) else None

    if not any(isinstance(v, dict) for v in (next_six_counts, next_first_counts, last_1_counts, last_6_counts)):
        return None

    def format_counts(counts: Dict[str, Any], plus_key: str) -> str:
        mia1 = _safe_int(counts.get("1"))
        mia2 = _safe_int(counts.get("2"))
        mia3 = _safe_int(counts.get("3"))
        mia4_plus = _safe_int(counts.get(plus_key))
        return f"MIA1: {mia1}, MIA2: {mia2}, MIA3: {mia3}, MIA4+: {mia4_plus}"

    parts = []
    if isinstance(next_first_counts, dict):
        parts.append(f"current 1 month {format_counts(next_first_counts, '5_plus')}")
    if isinstance(last_1_counts, dict):
        parts.append(f"current 1 month {format_counts(last_1_counts, '4+')}")
    if isinstance(next_six_counts, dict):
        parts.append(f"past 6 months {format_counts(next_six_counts, '5_plus')}")
    if isinstance(last_6_counts, dict):
        parts.append(f"past 6 months {format_counts(last_6_counts, '4+')}")

    return " and /or ".join(parts) if parts else None


def _format_cell_value(value: Any) -> Any:
    if isinstance(value, dict):
        mia_counts = _format_mia_counts(value)
        if mia_counts is not None:
            return mia_counts
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=False)
    return value


def _first_value(items: list[float] | None) -> Optional[float]:
    if not items:
        return None
    return items[0]


def load_merged_report(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def resolve_excel_path(arg_excel: Optional[str]) -> str:
    if arg_excel:
        return arg_excel
    return str(Path(__file__).resolve().parent / DEFAULT_EXCEL)


def _compute_overdraft_compliance(analysis: Dict[str, Any]) -> str:
    totals_by_record = analysis.get("amount_totals", {}).get("by_record_no", {})
    first_values = analysis.get("first_line_numbers_after_date_by_record_no", {})
    if not totals_by_record and not first_values:
        return "N/A"

    failures = []
    for record_no, total in totals_by_record.items():
        first_value = _first_value(first_values.get(record_no))
        if first_value is None:
            continue
        if float(total) > float(first_value):
            failures.append(record_no)

    return "Yes" if not failures else "No"


def score_to_equivalent(score: Optional[int]) -> Optional[str]:
    if score is None:
        return None
    for lower, upper, grade in SCORE_RANGE_EQUIVALENTS:
        if lower <= score <= upper:
            return grade
    return None


def _non_bank_conduct_count(stats_totals: Dict[str, Any]) -> Optional[int]:
    last_6 = stats_totals.get("last_6_months", {}).get("freq")
    if not last_6:
        return None
    return sum(int(last_6.get(key, 0)) for key in ("1", "2", "3", "4+"))


def _non_bank_legal_status(records: list[Dict[str, Any]]) -> Optional[str]:
    markers = sorted({record.get("legal_marker") for record in records if record.get("legal_marker")})
    if not markers:
        return "No"
    return ", ".join(markers)


def build_knockout_data(merged: Dict[str, Any]) -> Dict[str, Any]:
    summary = merged.get("summary_report", {})
    detailed = merged.get("detailed_credit_report", {})
    non_bank = merged.get("non_bank_lender_credit_information", {})
    analysis = detailed.get("account_line_analysis", {})
    totals = detailed.get("totals", {})
    non_bank_totals = non_bank.get("totals", {}) if isinstance(non_bank.get("totals", {}), dict) else {}
    non_bank_stats = non_bank.get("stats_totals", {}) if isinstance(non_bank.get("stats_totals", {}), dict) else {}
    non_bank_records = non_bank.get("records", []) if isinstance(non_bank.get("records", []), list) else []

    total_limit = totals.get("total_limit") or summary.get("Borrower_Total_Limit_RM")
    total_outstanding = totals.get("total_outstanding_balance") or summary.get("Borrower_Outstanding_RM")
    total_banking_within_limit = (
        "YES" if total_outstanding is not None and total_limit is not None and total_outstanding <= total_limit else "NO"
    )
    non_bank_total_limit = non_bank_totals.get("total_limit")
    non_bank_total_outstanding = non_bank_totals.get("total_outstanding")
    non_bank_within_limit = (
        "YES"
        if non_bank_total_outstanding is not None
        and non_bank_total_limit is not None
        and non_bank_total_outstanding <= non_bank_total_limit
        else "NO"
    )
    non_bank_conduct_count = _non_bank_conduct_count(non_bank_stats)
    non_bank_legal_status = _non_bank_legal_status(non_bank_records)

    credit_score = summary.get("i_SCORE")

    return {
        "Scoring by CRA Agency (Issuer's Credit Agency Score)": _format_number(credit_score),
        "Scoring by CRA Agency (Credit Score Equivalent)": score_to_equivalent(credit_score),
        "Business has been in operations for at least THREE (3) years (Including upgrade from Sole Proprietorship and Partnership under similar business activity)": _format_number(
            summary.get("Incorporation_Year")
        ),
        "Company Status (Existing Only)": summary.get("Status"),
        "Exempt Private Company": summary.get("Private_Exempt_Company"),
        "Winding Up / Bankruptcy Proceedings Record": _format_number(summary.get("Winding_Up_Record")),
        "Credit Applications Approved for Last 12 months (per primary CRA report)": _format_number(
            summary.get("Credit_Applications_Approved_Last_12_months")
        ),
        "Credit Applications Pending (per primary CRA report)": _format_number(
            summary.get("Credit_Applications_Pending")
        ),
        "Legal Action taken (from Banking) (per primary CRA report)": _format_number(
            summary.get("Legal_Action_taken_from_Banking")
        ),
        "Existing No. of Facility (from Banking) (per primary CRA report)": _format_number(
            summary.get("Existing_No_of_Facility_from_Banking")
        ),
        "Legal Suits (per primary CRA report) (either as Plaintiff or Defendant)": _format_number(
            summary.get("Legal_Suits")
        ),
        "Legal Case - Status (per primary CRA report)": _format_number(
            summary.get("Legal_Suits_Subject_As_Defendant_Defendant_Name") + summary.get("Other_Known_Legal_Suits_Subject_As_Defendant_Defendant_Name") + summary.get("Case_Withdrawn_Settled_Defendant_Name") 
        ),
        "Trade / Credit Reference (per primary CRA report)": _format_number(
            summary.get("Trade_Credit_Reference_Amount_Due_RM")), 
        "Total Enquiries for Last 12 months (per primary CRA report) (Financial Related Search Count)": _format_number(
            summary.get("Total_Enquiries_Last_12_months")
        ),
        "Special Attention Account (per primary CRA report)": _format_number(
            summary.get("Special_Attention_Account")
        ),
        "Summary of Total Liabilities (Outstanding) (per primary CRA report)": _format_number(
            summary.get("Borrower_Outstanding_RM")
        ),
        "Summary of Total Liabilities (Total Limit) (per primary CRA report)": _format_number(
            summary.get("Borrower_Total_Limit_RM")
        ),
        "Overdraft facility outstanding amount does not exceed the approved overdraft limit as per CCRIS (based on the primary CRA report)": _compute_overdraft_compliance(
            analysis
        ),
        "Issuer's Total Banking Outstanding Facilities does not exceed the Total Banking Limit (per primary CRA report)": total_banking_within_limit + ", outstanding: " + str(total_outstanding) + ", limit: " + str(total_limit),
        "Issuer's Total Non- Bank Lender Outstanding Facilities does not exceed the Total Non-Bank Lender Limit (per primary CRA report)": (
            non_bank_within_limit if non_bank_total_limit is not None and non_bank_total_outstanding is not None else "N/A"
        ),
        "CCRIS Loan Account - Conduct Count (per primary CRA report)": analysis.get("digit_counts_totals"),
        "CCRIS Loan Account - Legal Status (per primary CRA report)": analysis.get("Bank_LOD"),
        "Non-Bank Lender Credit Information (NLCI)- Conduct Count (per primary CRA report)": non_bank_stats
        if non_bank_stats
        else _format_number(non_bank_conduct_count),
        "Non-Bank Lender Credit Information (NLCI) - Legal Status (per primary CRA report)": non_bank_legal_status,
        "Total Limit": _format_number(total_limit),
        "Total Outstanding Balance": _format_number(total_outstanding),
    }


def find_issuer_data_column(ws: Worksheet) -> int:
    """
    Find the 'Issuer' column used for the Knock-Out Items section.
    In your template it's M6 (NOT E6).
    We search for the first 'Issuer' header in the top area (rows 1-10).
    """
    best = None
    for r in range(1, 11):
        for c in range(1, ws.max_column + 1):
            v = ws.cell(r, c).value
            if isinstance(v, str) and _norm(v) == "issuer":
                best = (r, c)
                break
        if best:
            break

    if not best:
        raise ValueError("Cannot find Issuer header column (e.g., M6).")
    return best[1]


def build_label_row_index(ws: Worksheet, label_col: int = LABEL_COL) -> Dict[str, int]:
    """
    Map each Knock-Out label text in column D -> row number.
    Column D contains the label (merged across D:K but the value is in D).
    """
    idx: Dict[str, int] = {}
    for r in range(1, ws.max_row + 1):
        v = ws.cell(r, label_col).value
        if isinstance(v, str) and v.strip():
            idx[_norm(v)] = r
    return idx


def set_issuer_name(ws: Worksheet, issuer_col_for_name: int, issuer_name: str) -> None:
    """
    Set Issuer Name next to 'Issuer Name:' (D6 -> E6).
    This is separate from the Knock-Out Items Issuer data column.
    """
    for r in range(1, ws.max_row + 1):
        v = ws.cell(r, 4).value  # D
        if isinstance(v, str) and "issuer name" in _norm(v):
            ws.cell(r, issuer_col_for_name).value = issuer_name
            return


def set_cra_report_dates(ws: Worksheet, cra_report_date: Optional[str]) -> None:
    if not cra_report_date:
        return

    target_label = "date (cra report):"
    for r in range(1, 15):
        for c in range(1, ws.max_column + 1):
            v = ws.cell(r, c).value
            if isinstance(v, str) and _norm(v) == target_label:
                target_col = None
                for offset in range(1, 4):
                    next_cell = ws.cell(r, c + offset)
                    if isinstance(next_cell.value, str) and "dd/mm/yyyy" in next_cell.value.lower():
                        target_col = c + offset
                        break
                if target_col is None:
                    target_col = c + 1
                ws.cell(r, target_col).value = cra_report_date


def fill_knockout_matrix(
    file_path: str,
    issuer_name: str,
    data_by_label: Dict[str, Any],
    cra_report_date: Optional[str] = None,
) -> str:
    wb = openpyxl.load_workbook(file_path)
    if SHEET_NAME not in wb.sheetnames:
        raise ValueError(f"Sheet '{SHEET_NAME}' not found. Found: {wb.sheetnames}")

    ws = wb[SHEET_NAME]

    # 1) Issuer name field is D6 -> E6
    # Find column to the right of 'Issuer Name:' (in your file: E = 5)
    issuer_name_value_col = None
    for r in range(1, 30):
        v = ws.cell(r, 4).value  # D
        if isinstance(v, str) and "issuer name" in _norm(v):
            issuer_name_value_col = 5  # E
            break
    if issuer_name_value_col:
        set_issuer_name(ws, issuer_name_value_col, issuer_name)

    set_cra_report_dates(ws, cra_report_date)

    # 2) Issuer data column for Knock-Out Items: header 'Issuer' at M6
    issuer_data_col = find_issuer_data_column(ws)
    ws.cell(7, issuer_data_col).value = issuer_name

    # 3) Build label row index from column D
    label_index = build_label_row_index(ws, LABEL_COL)

    # 4) Write values into Issuer data column (M)
    missing = []
    written = 0

    for label, value in data_by_label.items():
        row = label_index.get(_norm(label))
        if not row:
            missing.append(label)
            continue

        ws.cell(row, issuer_data_col).value = _format_cell_value(value)
        written += 1

    # 5) Save output
    base, ext = os.path.splitext(file_path)
    output_path = f"{base}_FILLED{ext}"
    wb.save(output_path)

    print(f"✅ Written {written} cells into Issuer column ({openpyxl.utils.get_column_letter(issuer_data_col)}).")
    if missing:
        print("\n⚠️ Labels not found (not written):")
        for m in missing:
            print(" -", m)

    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fill Knockout Matrix Excel from merged credit report data.")
    parser.add_argument("--excel", help="Path to Knockout Matrix Template.xlsx")
    parser.add_argument("--merged-json", help="Path to merged JSON output")
    parser.add_argument("--pdf", help="Path to Experian PDF (opens picker if omitted)")
    parser.add_argument("--issuer", default=None, help="Issuer name to fill in Excel (defaults to Name Of Subject)")
    args = parser.parse_args()

    excel_file = resolve_excel_path(args.excel)

    if args.merged_json:
        merged = load_merged_report(args.merged_json)
    else:
        pdf_path = resolve_pdf_path(args.pdf)
        if not pdf_path:
            print("❌ No PDF selected.")
            raise SystemExit(1)
        merged = merge_reports(pdf_path)

    data = build_knockout_data(merged)
    summary = merged.get("summary_report", {})
    issuer_name = args.issuer or summary.get("Name_Of_Subject") or "UNKNOWN ISSUER"
    cra_report_date = summary.get("Last_Updated_By_Experian")
    print(f"Using CRA report date: {cra_report_date}")

    out = fill_knockout_matrix(excel_file, issuer_name, data, cra_report_date=cra_report_date)
    print("✅ File saved:", out)
