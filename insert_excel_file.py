from __future__ import annotations

import os
import re
import tkinter as tk
from tkinter import filedialog
from typing import Any, Dict, Optional

import openpyxl
from openpyxl.worksheet.worksheet import Worksheet


SHEET_NAME = "Knock-Out"
LABEL_COL = 4  # D


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


def fill_knockout_matrix(
    file_path: str,
    issuer_name: str,
    data_by_label: Dict[str, Any],
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

    # 2) Issuer data column for Knock-Out Items: header 'Issuer' at M6
    issuer_data_col = find_issuer_data_column(ws)

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

        ws.cell(row, issuer_data_col).value = value
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
    excel_file = pick_excel_file()
    if not excel_file:
        print("❌ No file selected")
        raise SystemExit(1)

    issuer = "YOUR ISSUER SDN BHD"

    # Put your extracted values here
    data = {
        "Scoring by CRA Agency (Issuer's Credit Agency Score)": "742",
        "Scoring by CRA Agency (Credit Score Equivalent)": "AA",
        "Winding Up / Bankruptcy Proceedings Record": "NO INFORMATION AVAILABLE",
        "Credit Applications Approved for Last 12 months (per primary CRA report)": "2",
        "Credit Applications Pending (per primary CRA report)": "0",
        "Legal Case - Status (per primary CRA report)": "SETTLED",
        "Issuer must be a business registered in Malaysia": "YES",
        "Avoid Industry Sector": "PASS",
    }

    out = fill_knockout_matrix(excel_file, issuer, data)
    print("✅ File saved:", out)
