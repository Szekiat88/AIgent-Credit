"""Extract Amount Due values from Trade/Credit Reference sections in PDF."""

import re
from typing import List, Optional
from pdf_utils import parse_money, extract_all_sections

# Pattern to find "Amount Due" followed by a number
AMOUNT_DUE_PATTERN = re.compile(
    r"amount\s+due\s*:?\s*([0-9,]+(?:\.\d{2})?)",
    re.IGNORECASE
)


def extract_all_trade_sections(pdf_path: str = None, text_lines: List[str] = None) -> List[List[str]]:
    """Extract all trade sections between 'TRADE / CREDIT REFERENCE (CR)' and 'legend' markers."""
    return extract_all_sections(
        pdf_path=pdf_path,
        start_marker="TRADE / CREDIT REFERENCE (CR)",
        end_marker="legend",
        text_lines=text_lines
    )


def extract_amount_due_from_section(section_lines: List[str]) -> List[float]:
    """Extract all Amount Due values from a trade section."""
    amounts = []
    
    for line_num, line in enumerate(section_lines, start=1):
        match = AMOUNT_DUE_PATTERN.search(line)
        if match:
            amount = parse_money(match.group(1))
            if amount is not None:
                amounts.append(amount)
        elif "amount due" in line.lower():
            # Sometimes Amount Due is on one line and the value is on the next
            for offset in range(3):
                if line_num + offset <= len(section_lines):
                    check_line = section_lines[line_num + offset - 1]
                    numbers = re.findall(r'\b\d{1,3}(?:,\d{3})*(?:\.\d{2})?\b', check_line)
                    if numbers:
                        amount = parse_money(numbers[-1])
                        if amount is not None:
                            amounts.append(amount)
                            break
    
    return amounts


def extract_trade_amounts_for_excel(pdf_path: str = None, text_lines: List[str] = None) -> List[List[float]]:
    """Extract Amount Due values from all trade sections for Excel insertion."""
    trade_sections = extract_all_trade_sections(pdf_path=pdf_path, text_lines=text_lines)
    return [
        amounts
        for section_lines in trade_sections
        if (amounts := extract_amount_due_from_section(section_lines))
    ]
