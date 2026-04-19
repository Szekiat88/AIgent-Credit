# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

**AIgent Credit** is a specialized ETL pipeline that automates credit assessment paperwork. It extracts structured data from Experian-style credit report PDFs and fills an Excel "Knockout Matrix" workbook, eliminating manual data entry for underwriters.

**Core workflow:** Experian PDF → three parallel extractors (summary, detailed banking, non-bank lender) → merged JSON → Excel template mapping → column L highlighting for knockout criteria.

## Architecture & Data Flow

The application follows a three-stage extraction + merge pattern:

### 1. **Summary Extraction** (`load_file_version.py`)
Regex-based extraction of "front of report" structured fields from PDF:
- Subject names (dynamic count: issuer + directors/guarantors)
- Credit scores (i-SCORE)
- Incorporation date, company status, legal flags
- Enquiry counts, trade credit references
- Litigation defendant flags (per subject)

All fields support **multi-subject variants**: `Field`, `Field_2`, `Field_3`, etc. via dynamic suffix generation in `extract_fields()`.

### 2. **Detailed Banking Extraction** (`Detailed_Credit_Report_Extractor.py`)
Parses "DETAILED CREDIT REPORT (BANKING ACCOUNTS)" sections:
- Splits account lines by record number (1-based numeric prefix)
- Extracts per-account: outstanding amounts, limits, overdraft flags, term codes (MTH/BUL/REV/IDF/IRR)
- Counts MIA (missed installment) digits: 0/1/2/3/5+ buckets across "next 6 months" and "next 1 month"
- Aggregates per-section totals and legal status codes (mapped: "10" → "Summon/Writ files", etc.)
- Handles **multiple sections**: returns `sections[]` array with per-section analysis

**Key output:** `digit_counts_totals` (rolled-up MIA counts for CCRIS conduct), `overdraft_comparisons`, `outstanding_limit_comparisons`.

### 3. **Non-Bank Lender Extraction** (`Non_Bank_Lender_Credit_Information.py`)
Parses "NON-BANK LENDER CREDIT INFORMATION (NLCI)" block:
- Month header initials → month names (smart sequence matching despite ambiguity: J/M/A duplicates)
- Per-record: approval date, monthly values, legal markers (LOD/SUE/WRIT/SUMMONS/SETTLED/WITHDRAWN), status dates
- Frequency buckets: 0/1/2/3/4+ for last 1 month and last 6 months
- Aggregates `stats_totals` across all records

### 4. **Merge & Excel Fill** (`merged_credit_report.py`, `insert_excel_file.py`)
- **Merge:** Orchestrator calls three extractors, returns unified dict with `summary_report`, `detailed_credit_report`, `non_bank_lender_credit_information`
- **Placements:** `build_knockout_placements()` maps merged data to explicit (row label, column offset, value) tuples via hardcoded Knockout Matrix row labels (e.g., `LBL_SCORE_RAW`, `LBL_OVERDRAFT`)
- **Multi-subject columns:** Subject index → column offset formula: `offset = (subject_index - 1) * 2` (issuer at +0, subject 2 at +2, subject 3 at +4, etc.)
- **Excel writing:** Finds Issuer header in template, locates row labels in column D (normalized text), writes values, applies red-bold highlighting for column L matches

### 5. **Column L Validation** (`column_l_validator.py`, `knockout_health.py`)
- Column L contains **knockout criteria** (e.g., "no", ">=2", "MIA2+ past 6 months OR MIA1+ current 1 month")
- `_matches_criteria()` evaluates each cell value against its row's criterion
- Matching cells get red bold font
- `knockout_health.py` evaluates column L health **programmatically** from merged JSON without filling Excel (used for pre-flight checks and validation vs. filled workbooks)

## Key Files & Responsibilities

| File | Role |
|------|------|
| **insert_excel_file.py** | Main entry point for Excel pipeline. Loads/generates merged report, builds placements, fills template, applies column L highlighting. CLI args: `--pdf`, `--merged-json`, `--excel`, `--issuer`. |
| **merged_credit_report.py** | Orchestrator: calls three extractors in sequence, merges results. Standalone CLI: `--pdf`, `--output`, `--pretty`. |
| **load_file_version.py** | Regex-based summary extraction. Multi-subject support via `extract_fields()` → dynamic suffix generation. |
| **Detailed_Credit_Report_Extractor.py** | Banking account parsing. Multi-section support. Handles MIA digit counting, overdraft/outstanding-limit comparisons, legal status codes. |
| **Non_Bank_Lender_Credit_Information.py** | NLCI block parsing. Month header interpretation, frequency bucketing, legal marker extraction. |
| **pdf_utils.py** | Shared helpers: `read_pdf_text()` (pdfplumber + normalization), `pick_pdf_file()` (tkinter file dialog), money parsing, section extraction by markers. |
| **column_l_validator.py** | Column L matching logic. Understands "no", numeric thresholds, MIA patterns, legal status notes. Standalone CLI: `--excel`, `--output`. |
| **knockout_health.py** | Programmatic column L evaluation from merged JSON. Detects hits, unresolved rows, template mismatch validation. |
| **text_normalize.py** | Whitespace collapse, smart typography folding (curly quotes → straight), case normalization. Used for label matching. |

## Running & Building

### Development

**Extract merged JSON from PDF (inspection):**
```bash
python merged_credit_report.py --pdf /path/to/report.pdf --output merged.json --pretty
```

**Fill Excel from PDF (main workflow):**
```bash
python insert_excel_file.py --pdf /path/to/report.pdf
```

**Fill Excel from saved JSON (faster repeat runs):**
```bash
python insert_excel_file.py --merged-json merged.json
```

**Validate column L health (pre-flight check):**
```bash
python knockout_health.py --merged-json merged.json
```

**Apply column L highlighting to a filled workbook:**
```bash
python column_l_validator.py --excel Knockout_Matrix_FILLED.xlsx
```

**Run tests:**
```bash
python -m pytest tests/test_knockout_health.py -v
python -m pytest tests/ -v  # all tests
```

### Building Windows EXE

Install dependencies and build with PyInstaller spec:
```bash
pip install -r requirements.txt
pyinstaller AIgent_Credit.spec --clean
```

Output: `dist/AIgent_Credit.exe`. **Important:** Copy `Knockout Matrix Template.xlsx` to the same folder as the EXE before distribution. See `BUILD_INSTRUCTIONS.md` and `DISTRIBUTION_GUIDE.md` for details.

## Dependencies

- **openpyxl ≥3.1.0** — Read/write Excel workbooks
- **pdfplumber ≥0.10.0** — PDF text extraction with marker-based section splitting
- **pyinstaller ≥6.0.0** — EXE packaging (dev only)

## Critical Patterns & Edge Cases

### Multi-Subject Extraction
All extractors return **dynamic-length lists** for fields that vary by subject (scores, enquiries, litigation flags):
- Summary: `extract_fields()` counts subjects via `extract_name_of_subject_all()`, generates `Field`, `Field_2`, `Field_3` keys
- Excel fill: `build_knockout_placements()` auto-detects `num_subjects`, writes subject name columns in +2 step offsets
- Column L: subject columns detected via header keywords (issuer/director/guarantor)

**Normalization:** Text normalization (`normalize_compare_text()`) handles:
- Whitespace collapse (newlines → spaces, multiple spaces → single)
- Smart typography (curly quotes → straight) when `smart_typography=True`
- Case-insensitive matching for row labels in template

### Banking Sections
The detailed report can have **multiple "DETAILED CREDIT REPORT (BANKING ACCOUNTS)" sections** (e.g., separate borrower + guarantor sections). `extract_all_sections()` returns all occurrences; `sections[]` array preserves per-section analysis. Excel fill maps section indices to subject columns via `banking_status_by_section[sec_i]` lookups.

### MIA Digit Counting
CCRIS uses digit patterns (0/1/2/3/4+) in term codes (MTH/BUL/REV/IDF/IRR) to represent conduct. Parsing extracts **first 6 numeric tokens** after term keyword, counts digits by bucket, and rolls up totals. NLCI uses frequency buckets (0/1/2/3/4+) on monthly conduct values instead.

### Overdraft vs. Outstanding-Limit
Account lines may contain:
- **Overdraft lines** (OVRDRAFT keyword): amount before date = outstanding, first number after date = limit
- **Banking facility lines** (other keywords): parsed via regex patterns for OUTSTANDING/LIMIT pairs

These are tracked separately in `overdraft_comparisons` and `outstanding_limit_comparisons`, then merged across sections for Excel display.

### Column L Matching
Criteria text uses compact notation:
- `"no"` — Matches "No", "N/A", zeros, or (for operations years) `<3`
- `"yes"` — Matches "Yes" prefix
- `"≥X"` or `">X"` or `"<X"` — Numeric thresholds
- `"MIA2+ (past 6 months) AND MIA1+ (current 1 month)"` — Complex pattern matching via segment parsing

See `column_l_validator._matches_criteria()` for full rule set.

## Testing

**Unit tests:** `tests/test_knockout_health.py` covers:
- Placement lookup (hit/miss on label + subject index)
- Knockout health evaluation (5-year vs. 2-year incorporation)
- Validation agreement between programmatic evaluation and filled Excel

No external fixtures; tests create minimal templates and merged JSON dicts in-memory.

## Common Issues & Troubleshooting

### Template Not Found
EXE searches in order:
1. PyInstaller temp dir (`sys._MEIPASS`)
2. EXE directory
3. Current working directory

**Solution:** Place `Knockout Matrix Template.xlsx` in same folder as EXE, or use `--excel` flag.

### Row Label Mismatch
If a placement is marked "missing", the row label in code does not match the template text (whitespace, typography, line breaks). Check `insert_excel_file.py` constants (`LBL_*`) against template column D values; use `normalize_compare_text()` to debug.

### Multi-Subject Columns Overflow
Template has finite columns (e.g., max 20). If detected subject count > available columns, excess names are printed as warnings and skipped. Adjust template if more subjects expected.

### PDF Section Not Found
If "DETAILED CREDIT REPORT (BANKING ACCOUNTS)" section is missing, extractor returns empty `sections[]` and falls back to summary totals. Check PDF structure matches expected markers.

## File Locations

- **Main scripts:** Root directory (insert_excel_file.py, merged_credit_report.py, etc.)
- **Excel template:** `Knockout Matrix Template.xlsx` (root; bundled in spec)
- **Tests:** `tests/test_knockout_health.py`
- **Dependencies:** `requirements.txt`
- **Build config:** `AIgent_Credit.spec` (PyInstaller)
- **Docs:** `BUILD_INSTRUCTIONS.md`, `DISTRIBUTION_GUIDE.md`, `TROUBLESHOOTING.md`, `study.md`
