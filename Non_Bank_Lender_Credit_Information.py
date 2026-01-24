import re
from typing import List, Dict, Any, Optional, Tuple
import pdfplumber
import tkinter as tk
from tkinter import filedialog

RE_TOTAL_LINE = re.compile(r"^\s*TOTAL\s+[\d,]+\.\d{2}\s+TOTAL\s+[\d,]+\.\d{2}\s*$", re.IGNORECASE)
RE_OUTSTANDING = re.compile(r"\bOUTSTANDING\s+CREDIT\b", re.IGNORECASE)
RE_DATE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
RE_INT_1_2 = re.compile(r"^\d{1,2}$")

# Expand this list when you see more markers in PDFs
LEGAL_MARKERS = {"LOD", "SUE", "WRIT", "SUMMONS", "SETTLED", "WITHDRAWN"}

MONTHS = [
    ("Jan","J"), ("Feb","F"), ("Mar","M"), ("Apr","A"), ("May","M"), ("Jun","J"),
    ("Jul","J"), ("Aug","A"), ("Sep","S"), ("Oct","O"), ("Nov","N"), ("Dec","D"),
]

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
START_MARKER = "NON-BANK LENDER CREDIT INFORMATION (NLCI)"
END_MARKER = "WRITTEN-OFF ACCOUNT"

def _month_seq(start_idx: int, direction: int, length: int):
    seq = []
    idx = start_idx
    for _ in range(length):
        name, ini = MONTHS[idx % 12]
        seq.append((name, ini))
        idx += direction
    return seq

def best_month_mapping(initials: List[str]) -> Dict[str, Any]:
    """
    Find best month-name sequence that matches the initials, despite duplicates (J/M/A).
    If not confident -> you should fallback to M01..Mn.
    """
    initials = [x.upper() for x in initials if x and x.isalpha()]
    n = len(initials)
    if n == 0:
        return {"months": [], "score": 0, "confident": False}

    best = None
    for start in range(12):
        for direction in (-1, +1):
            seq = _month_seq(start, direction, n)
            seq_ini = [ini for _, ini in seq]
            score = sum(1 for a, b in zip(initials, seq_ini) if a == b)
            cand = {
                "months": [m for m, _ in seq],
                "score": score,
                "direction": "backward" if direction == -1 else "forward",
                "start_month": seq[0][0],
            }
            if best is None or cand["score"] > best["score"]:
                best = cand

    # confidence: allow 1 mismatch (OCR noise)
    best["confident"] = best["score"] >= max(n - 1, int(n * 0.9))
    return best

def parse_header_initials(header_line: str) -> List[str]:
    after = re.split(r"OUTSTANDING\s+CREDIT", header_line, flags=re.IGNORECASE)[-1].strip()
    return [t for t in after.split() if len(t) == 1 and t.isalpha()]

def extract_block(lines: List[str]) -> Tuple[List[str], Optional[str], Optional[str]]:
    header_line = None
    total_line = None
    data_lines = []
    in_block = False

    for line in lines:
        if not in_block and RE_OUTSTANDING.search(line):
            in_block = True
            header_line = line
            continue

        if in_block:
            if RE_TOTAL_LINE.match(line):
                total_line = line
                break
            if re.match(r"^\s*\d+\s", line):   # record line starts with number
                data_lines.append(line)

    return data_lines, header_line, total_line

def extract_month_nums_and_middle_words(tokens: List[str]) -> Tuple[List[int], List[str], Optional[str], Optional[str]]:
    """
    Returns:
      monthly_nums: consecutive ints immediately before legal marker
      middle_words: tokens between end of months and legal marker/date (if any)
      legal_marker: e.g. LOD
      status_date: e.g. 31/01/2025
    """
    # find legal marker index
    idx = None
    legal_marker = None
    for i, t in enumerate(tokens):
        if t in LEGAL_MARKERS:
            idx = i
            legal_marker = t
            break
    if idx is None:
        return [], [], None, None

    status_date = tokens[idx + 1] if idx + 1 < len(tokens) and RE_DATE.match(tokens[idx + 1]) else None

    # walk backwards from idx-1: collect ints; stop when not int
    monthly = []
    j = idx - 1
    while j >= 0 and RE_INT_1_2.match(tokens[j]):
        monthly.append(int(tokens[j]))
        j -= 1
    monthly.reverse()

    start_months = idx - len(monthly)
    between = tokens[start_months:idx]
    middle_words = [x for x in between if not RE_INT_1_2.match(x)]

    return monthly, middle_words, legal_marker, status_date

def freq_bucket(values: List[int]) -> Dict[str, int]:
    """
    Count: '0', '1', '2', '3', '4+'
    """
    out = {"0": 0, "1": 0, "2": 0, "3": 0, "4+": 0}
    for v in values:
        if v == 0: out["0"] += 1
        elif v == 1: out["1"] += 1
        elif v == 2: out["2"] += 1
        elif v == 3: out["3"] += 1
        else: out["4+"] += 1
    return out

def summarize_last_periods(month_values_in_order: List[int]) -> Dict[str, Any]:
    """
    Assumption: month_values_in_order is already ordered from MOST RECENT -> OLDER.
    """
    last1 = month_values_in_order[:1]
    last6 = month_values_in_order[:6]

    last1_freq = freq_bucket(last1)
    last6_freq = freq_bucket(last6)

    return {
        "last_1_month": {
            "values": last1,
            "freq": last1_freq,
            "freq_total": sum(last1_freq.values()),
        },
        "last_6_months": {
            "values": last6,
            "freq": last6_freq,
            "freq_total": sum(last6_freq.values()),
        }
    }

def sum_freq_buckets(stats_list: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    summed = {
        "last_1_month": {"0": 0, "1": 0, "2": 0, "3": 0, "4+": 0},
        "last_6_months": {"0": 0, "1": 0, "2": 0, "3": 0, "4+": 0},
    }

    for stats in stats_list:
        for period in ("last_1_month", "last_6_months"):
            freq = stats.get(period, {}).get("freq", {})
            for key in summed[period]:
                summed[period][key] += int(freq.get(key, 0))

    return summed

def parse_outstanding_with_stats(lines: List[str]) -> Dict[str, Any]:
    data_lines, header_line, total_line = extract_block(lines)
    if not header_line:
        raise ValueError("OUTSTANDING CREDIT header not found")

    initials = parse_header_initials(header_line)
    month_info = best_month_mapping(initials)

    records = []
    for line in data_lines:
        tokens = line.split()
        rec_no = int(tokens[0])
        approval_date = tokens[1]

        monthly_nums, middle_words, legal_marker, status_date = extract_month_nums_and_middle_words(tokens)

        # Map months (if confident) else keep index columns
        if month_info["confident"]:
            months = month_info["months"]  # order aligned to initials (most recent -> older) if header is that way
            month_map = {months[i]: (monthly_nums[i] if i < len(monthly_nums) else None) for i in range(len(months))}
            # For stats we only use the numeric sequence we have, assuming it corresponds to most recent -> older
            stats = summarize_last_periods(monthly_nums)
        else:
            month_map = {f"M{i+1:02d}": monthly_nums[i] for i in range(len(monthly_nums))}
            stats = summarize_last_periods(monthly_nums)

        records.append({
            "no": rec_no,
            "approval_date": approval_date,
            "month_header_initials": initials,
            "month_mapping_confident": month_info["confident"],
            "month_map": month_map,
            "middle_wording": " ".join(middle_words) if middle_words else None,
            "legal_marker": legal_marker,
            "status_date": status_date,
            "stats": stats,
            "raw": line
        })

    stats_totals = sum_freq_buckets([record["stats"] for record in records])

    totals = None
    if total_line:
        m = re.search(r"TOTAL\s+([\d,]+\.\d{2})\s+TOTAL\s+([\d,]+\.\d{2})", total_line, re.IGNORECASE)
        if m:
            totals = {
                "total_limit": float(m.group(1).replace(",", "")),
                "total_outstanding": float(m.group(2).replace(",", "")),
            }

    return {
        "records": records,
        "stats_totals": {
            "last_1_month": {
                "freq": stats_totals["last_1_month"],
                "freq_total": sum(stats_totals["last_1_month"].values()),
            },
            "last_6_months": {
                "freq": stats_totals["last_6_months"],
                "freq_total": sum(stats_totals["last_6_months"].values()),
            },
        },
        "totals": totals
    }

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


def extract_non_bank_lender_credit_information(pdf_path: str) -> Dict[str, Any]:
    section_lines = extract_section_lines(pdf_path)
    result: Dict[str, Any] = {
        "source_pdf": pdf_path,
        "section": {"start_marker": START_MARKER, "end_marker": END_MARKER},
        "records": [],
        "stats_totals": None,
        "totals": None,
    }
    if not section_lines:
        result["error"] = "Non-bank lender section not found."
        return result

    try:
        parsed = parse_outstanding_with_stats(section_lines)
    except ValueError as exc:
        result["error"] = str(exc)
        return result

    result.update(parsed)
    return result


if __name__ == "__main__":
    pdf_path = pick_pdf_file()
    result = extract_non_bank_lender_credit_information(pdf_path)
    import json
    print(json.dumps(result, indent=2))
