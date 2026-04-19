"""Shared utilities for PDF extraction operations."""

import re
import tkinter as tk
from pathlib import Path
from tkinter import filedialog
from typing import Optional, List, Dict
from decimal import Decimal, InvalidOperation

import pdfplumber


# =============================
# COMMON REGEX PATTERNS
# =============================
RE_DATE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
RE_MONEY = re.compile(r"\b\d{1,3}(?:,\d{3})*(?:\.\d{2})?\b")


# =============================
# PDF TEXT READING
# =============================
def normalize_pdf_text(s: str) -> str:
    """Normalize whitespace on extracted PDF text for stable regex and line splitting."""
    s = s.replace("\u00a0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n+", "\n", s)
    return s.strip()


def read_pdf_text(pdf_path: str) -> str:
    """Read all pages from a PDF into one normalized text string."""
    if not Path(pdf_path).exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    chunks: List[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            chunks.append(page.extract_text() or "")
    return normalize_pdf_text("\n".join(chunks))


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


def parse_outstanding_limit_from_text(text: str) -> Dict[str, Optional[Decimal]]:
    """
    Parse OUTSTANDING and LIMIT amounts from one flattened line or a block of text.
    Used for CCRIS banking account lines and for section-level TOTAL OUTSTANDING / LIMIT blocks.
    """
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

    flattened = re.sub(r"\s+", " ", text)
    outstanding_value: Optional[Decimal] = None
    limit_value: Optional[Decimal] = None

    paired_match = paired_pattern.search(flattened)
    if paired_match:
        outstanding_value = parse_decimal(paired_match.group(1).replace(" ", ""))
        limit_value = parse_decimal(paired_match.group(2).replace(" ", ""))

    if outstanding_value is None:
        for pattern in outstanding_patterns:
            match = pattern.search(flattened)
            if match:
                outstanding_value = parse_decimal(match.group(1).replace(" ", ""))
                if outstanding_value is not None:
                    break

    if limit_value is None:
        for pattern in limit_patterns:
            match = pattern.search(flattened)
            if match:
                limit_value = parse_decimal(match.group(1).replace(" ", ""))
                if limit_value is not None:
                    break

    return {"outstanding": outstanding_value, "limit": limit_value}


# =============================
# PDF SECTION EXTRACTION
# =============================
def extract_all_sections(pdf_path: str = None, start_marker: str = None, end_marker: str = None, text_lines: List[str] = None) -> List[List[str]]:
    """
    Extract ALL sections between two markers in a PDF or from text lines.
    
    Args:
        pdf_path: Path to the PDF file (if text_lines not provided)
        start_marker: Text marker that indicates start of section
        end_marker: Text marker that indicates end of section
        text_lines: Pre-extracted text lines (optional, avoids reloading PDF)
        
    Returns:
        List of sections, where each section is a list of lines
    """
    all_sections: List[List[str]] = []
    current_section: List[str] = []
    in_section = False

    # Use provided text lines or extract from PDF
    if text_lines is None:
        if pdf_path is None:
            raise ValueError("Either pdf_path or text_lines must be provided")
        text_lines = read_pdf_text(pdf_path).splitlines()

    # Process lines
    for line in text_lines:
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
