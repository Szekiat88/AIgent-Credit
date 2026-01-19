from __future__ import annotations

import json
import re
import tkinter as tk
from tkinter import filedialog
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict

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


# =============================
# DATA STRUCTURE
# =============================
@dataclass
class BankingAccountRecord:
    no: int
    raw_lines: List[str]
    raw_text: str


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

    output: Dict[str, Any] = {
        "source_pdf": pdf_path,
        "section": {
            "start_marker": START_MARKER,
            "end_marker": END_MARKER,
        },
        "total_records": len(records),
        "records": [asdict(r) for r in records],
    }

    out_file = "detailed_credit_report_banking_accounts.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"✅ Extracted {len(records)} records")
    print(f"✅ Saved to {out_file}")


if __name__ == "__main__":
    main()
