"""Shared utilities for PDF extraction operations."""

import re
import tkinter as tk
from tkinter import filedialog
from typing import Optional, List
from decimal import Decimal, InvalidOperation

import pdfplumber


# =============================
# COMMON REGEX PATTERNS
# =============================
RE_DATE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
RE_MONEY = re.compile(r"\b\d{1,3}(?:,\d{3})*(?:\.\d{2})?\b")


# =============================
# FILE PICKER
# =============================
def pick_pdf_file() -> Optional[str]:
    """Open a file picker to select a PDF."""
    return pick_file("Select Experian PDF", [("PDF files", "*.pdf")])


def pick_excel_file() -> Optional[str]:
    """Open a file picker to select an Excel file."""
    return pick_file("Select Knockout Matrix Excel File", [("Excel files", "*.xlsx")])


def pick_file(title: str, filetypes: List[tuple]) -> Optional[str]:
    """Open a file picker with custom title and file types."""
    root = tk.Tk()
    root.withdraw()
    root.update()  # prevent some mac focus issues

    file_path = filedialog.askopenfilename(
        title=title,
        filetypes=filetypes,
    )

    root.destroy()
    return file_path if file_path else None


# =============================
# MONEY PARSING
# =============================
def parse_money(value: str) -> Optional[float]:
    """Parse a string containing a money value to float."""
    if not value:
        return None
    try:
        return float(value.replace(",", ""))
    except (ValueError, AttributeError):
        return None


def parse_decimal(value: str) -> Optional[Decimal]:
    """Parse a string containing a money value to Decimal."""
    try:
        return Decimal(value.replace(",", ""))
    except (InvalidOperation, AttributeError):
        return None


# =============================
# PDF SECTION EXTRACTION
# =============================
def extract_section_lines(pdf_path: str, start_marker: str, end_marker: str) -> List[str]:
    """
    Extract lines between two markers in a PDF.
    
    Args:
        pdf_path: Path to the PDF file
        start_marker: Text marker that indicates start of section
        end_marker: Text marker that indicates end of section
        
    Returns:
        List of lines between the markers
    """
    lines_between: List[str] = []
    in_section = False

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue

                if not in_section and start_marker.lower() in line.lower():
                    in_section = True
                    continue

                if in_section and end_marker.lower() in line.lower():
                    return lines_between

                if in_section:
                    lines_between.append(line)

    return lines_between


def extract_all_sections(pdf_path: str, start_marker: str, end_marker: str) -> List[List[str]]:
    """
    Extract ALL sections between two markers in a PDF (handles multiple occurrences).
    
    Args:
        pdf_path: Path to the PDF file
        start_marker: Text marker that indicates start of section
        end_marker: Text marker that indicates end of section
        
    Returns:
        List of sections, where each section is a list of lines
    """
    all_sections: List[List[str]] = []
    current_section: List[str] = []
    in_section = False

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue

                if start_marker.lower() in line.lower():
                    # If we were already in a section, save it before starting new one
                    if in_section and current_section:
                        all_sections.append(current_section)
                        current_section = []
                    in_section = True
                    continue

                if in_section and end_marker.lower() in line.lower():
                    # End of current section
                    if current_section:
                        all_sections.append(current_section)
                    current_section = []
                    in_section = False
                    continue

                if in_section:
                    current_section.append(line)

    # Don't forget the last section if the PDF ends without an end marker
    if in_section and current_section:
        all_sections.append(current_section)

    return all_sections
