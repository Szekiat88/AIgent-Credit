import re
import json
from pathlib import Path
from typing import Optional

import pdfplumber

from pdf_utils import pick_pdf_file, parse_money, RE_MONEY


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
        r"Order Date: \s*[:\-]?\s*([0-9]{1,2}\s+[A-Za-z]{3}\s+[0-9]{4})",
        r"Order Date: \s*[:\-]?\s*([0-9]{4}-[0-9]{1,2}-[0-9]{1,2})",
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


def extract_name_of_subject_all(text: str) -> list[Optional[str]]:
    """
    Extract the FIRST 'Name Of Subject' from each 'PARTICULARS OF THE SUBJECT PROVIDED BY YOU' section.
    Returns ALL names found (dynamic length).
    """

    # Find all occurrences of the section header
    section_pattern = r"PARTICULARS OF THE SUBJECT PROVIDED BY YOU"
    section_positions = [(m.start(), m.end()) for m in re.finditer(section_pattern, text, re.IGNORECASE)]
        
    names = []
    
    if not section_positions:
        print("⚠️  No sections found! Falling back to searching entire document...")
        # Fallback: get ALL from entire document
        all_matches = re.findall(r"Name Of Subject\s*[:\-]?\s*([^\n]+)", text, re.IGNORECASE)
        names = [m.strip() for m in all_matches if m.strip()]
    else:
        # For each section, extract the FIRST "Name Of Subject" only
        for i, (start_pos, end_pos) in enumerate(section_positions, 1):
            # Define section boundary: from this header to the next section or end of document
            if i < len(section_positions):
                next_start = section_positions[i][0]
                section_text = text[end_pos:next_start]
            else:
                section_text = text[end_pos:]
           
            # Extract ALL "Name Of Subject" in this section
            section_matches = re.findall(r"Name Of Subject\s*[:\-]?\s*([^\n]+)", section_text, re.IGNORECASE)
            
            if section_matches:
                # Take only the FIRST match from this section
                first_match = section_matches[0].strip()
                if len(section_matches) > 1:
                    print(f"   ⚠️  Ignoring {len(section_matches) - 1} duplicate(s) in same section: {section_matches[1:]}")
                names.append(first_match)
            else:
                print(f"   ⚠️  No 'Name Of Subject' found in this section")
    
    # Ensure we have at least one element
    if not names:
        names = [None]
    
    return names


def extract_iscores_all(text: str) -> list[Optional[int]]:
    """Extract ALL i-SCORE occurrences from text (pattern: 'i-SCORE 758')."""
    matches = re.findall(r"\bi-SCORE\b\s*([0-9]{3})\b", text, re.IGNORECASE | re.DOTALL)
    scores = [int(m) for m in matches] if matches else [None]
    return scores


def extract_int_after_label_all(label: str, text: str) -> list[Optional[int]]:
    """
    Extract ALL integer occurrences after a label from each section.
    Returns all values found (dynamic length).
    """
    label_esc = re.escape(label)
    pattern = rf"{label_esc}\s*[:\-]?\s*([0-9]+)"
    matches = re.findall(pattern, text, re.IGNORECASE | re.DOTALL)
    values = [int(m) for m in matches] if matches else [None]
    return values


def extract_financial_related_search_count_all(text: str) -> list[Optional[int]]:
    """
    Extract all "FINANCIAL RELATED SEARCH COUNT" blocks and return,
    for each block, the highest month value (Jan..Dec) from the latest year.

    Example block:
      Year Total Jan ... Dec
      2025 3 2 0 ... 1 0 0
      2024 1 0 0 ...

    Output for that block => 2 (max across Jan..Dec of latest year 2025).
    """
    block_pattern = re.compile(
        r"FINANCIAL\s+RELATED\s+SEARCH\s+COUNT\s*:?\s*(.*?)"
        r"(?=COMMERCIAL\s+RELATED\s+SEARCH\s+COUNT)",
        re.IGNORECASE | re.DOTALL,
    )
    row_pattern = re.compile(r"^\s*(20\d{2})\b.*$", re.MULTILINE)

    values: list[Optional[int]] = []
    for block in block_pattern.findall(text):
        row_values: list[tuple[int, Optional[int]]] = []

        for row_match in row_pattern.finditer(block):
            row = row_match.group(0)
            year = int(row_match.group(1))
            nums = [int(token) for token in re.findall(r"\d+", row)]

            # Expected row format: Year Total Jan Feb ... Dec
            # Exclude Year and Total, then evaluate only Jan..Dec values.
            month_values = nums[2:14] if len(nums) >= 14 else nums[2:]
            highest_month = max(month_values) if month_values else None
            row_values.append((year, highest_month))

        if not row_values:
            values.append(None)
            continue

        _, latest_highest_month = max(row_values, key=lambda item: item[0])
        values.append(latest_highest_month)

    return values if values else [None]


def _fit_list_length(values: list, target_len: int) -> list:
    """Trim or pad with None so list length matches target_len."""
    if target_len <= 0:
        return values
    if len(values) >= target_len:
        return values[:target_len]
    return values + [None] * (target_len - len(values))


def extract_legal_suits_all(text: str) -> list[Optional[int]]:
    """
    Extract ALL Legal Suits occurrences.
    Returns all values found (dynamic length).
    """
    matches = re.findall(r"Legal Suits\s*[:\-]?\s*([0-9]+)", text, re.IGNORECASE | re.DOTALL)
    if not matches:
        # Fallback: litigation section 'LEGAL SUITS ... Total: 0'
        matches = re.findall(r"LEGAL\s+SUITS.*?Total\s*:\s*([0-9]+)", text, re.IGNORECASE | re.DOTALL)
    values = [int(m) for m in matches] if matches else [None]
    return values


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
    """Extract first borrower liabilities (Outstanding and Total Limit)."""
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


def extract_borrower_liabilities_all(text: str) -> list[tuple[Optional[float], Optional[float]]]:
    """
    Extract ALL borrower liabilities occurrences.
    Returns list of tuples: [(outstanding_1, limit_1), (outstanding_2, limit_2), ...]
    Dynamic length based on how many are found.
    """
    # Find all sections with "SUMMARY OF POTENTIAL & CURRENT LIABILITIES"
    section_pattern = r"SUMMARY OF POTENTIAL & CURRENT LIABILITIES.*?(?=\n[A-Z][A-Z &/\-]{5,}\n|$)"
    sections = re.findall(section_pattern, text, re.IGNORECASE | re.DOTALL)
    
    all_liabilities = []
    
    if not sections:
        # Fallback: try to find all "Borrower" entries in the entire text
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        header_positions = [
            idx for idx, line in enumerate(lines) 
            if "Outstanding" in line and "Total Limit" in line
        ]
        
        for header_idx in header_positions:
            search_lines = lines[header_idx + 1 : header_idx + 50]  # Look ahead up to 50 lines
            
            for idx, line in enumerate(search_lines):
                if re.search(r"\bBorrower\b", line, re.IGNORECASE):
                    combined = line
                    if idx + 1 < len(search_lines):
                        combined = f"{combined} {search_lines[idx + 1]}"
                    amounts = [m.group(0) for m in RE_MONEY.finditer(combined)]
                    if len(amounts) >= 2:
                        all_liabilities.append((parse_money(amounts[0]), parse_money(amounts[1])))
                        break  # Only take first "Borrower" per header
    else:
        # Process each section
        for section in sections:
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
                        all_liabilities.append((parse_money(amounts[0]), parse_money(amounts[1])))
                        break  # Only take first "Borrower" per section
    
    # Ensure we have at least one element
    if not all_liabilities:
        all_liabilities = [(None, None)]
    
    return all_liabilities


def extract_trade_credit_amount_due_all(text: str) -> list[Optional[float]]:
    """
    Extract ALL trade credit amount due occurrences.
    Each value is the sum of all amounts in that section.
    Returns dynamic length list based on how many sections are found.
    """
    # Find all sections with "TRADE / CREDIT REFERENCE"
    section_pattern = r"TRADE\s*/\s*CREDIT\s+REFERENCE\s*\(CR\)(.*?)(?=AML\s*/\s*Sanction\s+List|$)"
    sections = re.findall(section_pattern, text, re.IGNORECASE | re.DOTALL)
    print(f"✅ Found {sections} 'TRADE / CREDIT REFERENCE' section(s)")
    all_amounts = []
    
    for section in sections:
        amounts = re.findall(
            r"Amount\s+Due\s*[:\-]?\s*([0-9][0-9,]*(?:\.\d{2})?)",
            section,
            re.IGNORECASE,
        )
        if amounts:
            print(f"   ✅ Found amounts in section: {amounts}")
            
            count_over_10k = 0
            
            for amount in amounts:
                value = parse_money(amount) or 0
                if value > 10000:
                    count_over_10k += 1

            all_amounts.append(count_over_10k if count_over_10k > 0 else None)

        else:
            all_amounts.append(None)
    # Ensure we have at least one element
    if not all_amounts:
        all_amounts = [None]
    
    return all_amounts


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


def extract_litigation_defendant_flags_all(text: str) -> list[dict[str, str]]:
    """
    Extract ALL litigation defendant flags occurrences.
    Returns list of dicts with flags for each subject (dynamic length).
    """
    # Find all LITIGATION sections
    litigation_pattern = r"SECTION 3: LITIGATION INFORMATION.*?(?=SECTION|PARTICULARS OF THE SUBJECT|$)"
    sections = re.findall(litigation_pattern, text, re.IGNORECASE | re.DOTALL)
    
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

    def extract_flags_from_section(section: str) -> dict[str, str]:
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
    
    all_flags = []
    for section in sections:
        all_flags.append(extract_flags_from_section(section))
    
    # Ensure we have at least one element
    if not all_flags:
        default_flags = {
            "Case_Withdrawn_Settled_Defendant_Name": "No",
            "Other_Known_Legal_Suits_Subject_As_Defendant_Defendant_Name": "No",
            "Legal_Suits_Subject_As_Defendant_Defendant_Name": "No",
        }
        all_flags = [default_flags]
    
    return all_flags


def extract_fields(pdf_path: str) -> dict:
    """Extract required fields from PDF. Supports dynamic number of subjects."""
    text = read_pdf_text(pdf_path)

    incorporation_date = extract_date_after_label("Incorporation Date", text)
    incorporation_year = int(incorporation_date[-4:]) if incorporation_date else None
    
    # Extract ALL occurrences for multi-subject fields (dynamic length)
    all_litigation_flags = extract_litigation_defendant_flags_all(text)
    all_credit_scores = extract_iscores_all(text)
    all_names_of_subject = extract_name_of_subject_all(text)
    all_winding_up = extract_int_after_label_all("Winding Up Record", text)
    all_credit_apps_approved = extract_int_after_label_all("Credit Applications Approved for Last 12 months", text)
    all_credit_apps_pending = extract_int_after_label_all("Credit Applications Pending", text)
    all_legal_action = extract_int_after_label_all("Legal Action taken (from Banking)", text)
    all_existing_facility = extract_int_after_label_all("Existing No. of Facility (from Banking)", text)
    all_total_enquiries = extract_financial_related_search_count_all(text)
    all_special_attention = extract_int_after_label_all("Special Attention Account", text)
    all_legal_suits = extract_legal_suits_all(text)
    all_liabilities = extract_borrower_liabilities_all(text)
    all_trade_credit = extract_trade_credit_amount_due_all(text)

    target_subject_count = len(all_names_of_subject)
    all_total_enquiries = _fit_list_length(all_total_enquiries, target_subject_count)
    print(f"✅ Extracted all_names_of_subject: {all_names_of_subject}")
    print(f"✅ Extracted all_trade_credit: {str(all_trade_credit)}")
        
    # Build result dictionary dynamically
    result = {
        "pdf_file": pdf_path,
        "Incorporation_Year": incorporation_year,
        "Status": extract_word_after_label("Status", text),
        "Private_Exempt_Company": extract_word_after_label("Private Exempt Company", text),
        "Last_Updated_By_Experian": extract_last_updated_by_experian(text),
        "all_names_of_subject": all_names_of_subject,
    }
    
    # Helper function to add multi-subject fields
    def add_multi_subject_field(field_name: str, values: list):
        for i, value in enumerate(values):
            suffix = f"_{i+1}" if i > 0 else ""
            result[f"{field_name}{suffix}"] = value
    
    # Add all multi-subject fields dynamically
    add_multi_subject_field("Name_Of_Subject", all_names_of_subject)
    add_multi_subject_field("i_SCORE", all_credit_scores)
    add_multi_subject_field("Winding_Up_Record", all_winding_up)
    add_multi_subject_field("Credit_Applications_Approved_Last_12_months", all_credit_apps_approved)
    add_multi_subject_field("Credit_Applications_Pending", all_credit_apps_pending)
    add_multi_subject_field("Legal_Action_taken_from_Banking", all_legal_action)
    add_multi_subject_field("Existing_No_of_Facility_from_Banking", all_existing_facility)
    add_multi_subject_field("Total_Enquiries_Last_12_months", all_total_enquiries)
    add_multi_subject_field("Special_Attention_Account", all_special_attention)
    add_multi_subject_field("Legal_Suits", all_legal_suits)
    add_multi_subject_field("Trade_Credit_Reference", all_trade_credit)
    
    # Add borrower liabilities (Outstanding and Total Limit)
    for i, (outstanding, limit) in enumerate(all_liabilities):
        suffix = f"_{i+1}" if i > 0 else ""
        result[f"Borrower_Outstanding_RM{suffix}"] = outstanding
        result[f"Borrower_Total_Limit_RM{suffix}"] = limit
    
    # Add litigation flags for each subject
    for i, flags in enumerate(all_litigation_flags):
        suffix = f"_{i+1}" if i > 0 else ""
        for key, value in flags.items():
            result[f"{key}{suffix}"] = value
    
    return result
