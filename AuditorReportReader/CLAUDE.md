# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

**AuditorReportReader** is a P2P credit analyst tool that reads any Malaysian auditor report PDF (scanned/image-based), extracts structured audit and financial data, and fills `Financial Statements Template.xlsx`.

**Full LLM architecture**: All text understanding — audit opinion, firm details, financial line items — is handled by **Gemini 2.5 Flash-Lite**. No hardcoded keyword matching.

## Running

```bash
# Live run (requires Gemini API key)
export GEMINI_API_KEY=AIza...
python auditor_report_reader.py --pdf "Greatocean 2024.pdf"

# Re-run using cached Gemini responses (free)
python auditor_report_reader.py --pdf "Greatocean 2024.pdf"

# Force fresh Gemini calls (re-runs cost ~$0.001–0.002)
python auditor_report_reader.py --pdf "Greatocean 2024.pdf" --no-cache

# Skip web blacklist check (faster)
python auditor_report_reader.py --pdf "Greatocean 2024.pdf" --no-web

# Run mock integration tests (no API key needed)
python tests/test_pipeline.py
```

## Architecture & Data Flow

```
PDF → OCR (Tesseract) → Page Classifier → Gemini (4 calls) → Validator → Excel
```

1. **`pdf_ocr.py`** — Tesseract 5 OCR via pytesseract + pdf2image. MD5 hash-based cache in `.ocr_cache/`. Returns `[{"page": N, "text": "..."}]`.

2. **`page_classifier.py`** — Keyword-signal classifier. Maps each page to: `audit | income_statement | balance_sheet | notes | statutory_decl | directors_report | other`. No LLM, instant, free.

3. **`gemini_extractor.py`** — **The LLM brain**. `GeminiExtractor` class makes 4 Gemini calls:
   - Call 1: first 15 pages → audit opinion, firm/accountant info, signature dates, statutory declaration
   - Call 2: income_statement pages → all P&L line items
   - Call 3: balance_sheet pages → all assets/liabilities/equity
   - Call 4: notes pages → interest & staff cost breakdowns
   
   Each call returns JSON. Cached in `.llm_cache/<pdf_hash>_<section>.json`.

4. **`json_cache.py`** — LLM result cache. Key = PDF MD5 + section name. Save/load JSON. `clear()` deletes all sections for a PDF.

5. **`validator.py`** — Arithmetic cross-checks only (no LLM). Verifies: Gross Profit = Revenue − COS, Total Assets = Liabilities + Equity, NCA + CA = Total Assets, NCL + CL = Total Liabilities. 0.5% tolerance for rounding.

6. **`keyword_map.py`** — Kept for two purposes:
   - `BUILT_IN_FIELDS` dict maps field names → Excel row numbers (used by `excel_filler.py`)
   - `load_user_keyword_map()` loads the Excel "KeywordMap" sheet — these hints are injected into Gemini prompts, not used for matching
   
7. **`excel_filler.py`** — Pure writer, no extraction logic. Fills three sheets:
   - **Summary of Information**: financial values in columns C–G, row 3 has date headers, row 22 = audit opinion
   - **auditor**: Phase 1-3 audit checks, blacklist check, statutory declaration
   - **CreditFlag**: all flags + arithmetic validation + PROCEED/ESCALATE/DECLINE recommendation

8. **`web_check.py`** — DuckDuckGo HTML search for MIA blacklist. No LLM.

9. **`auditor_report_reader.py`** — 7-step CLI orchestrator.

## Financial Data Format

`financial_data` dict passed to `excel_filler.write_output()`:
```python
{
    "Revenue": {"value": 27983932.0, "confidence": 90.0},
    "Cost of Sales": {"value": 24122517.0, "confidence": 90.0},
    ...
    "Net Profit (Loss) for the Year": {
        "value": 252310.0, "confidence": 90.0,
        "validated_vs_tci": True   # set when TCI also extracted
    }
}
```
Field names must exactly match `BUILT_IN_FIELDS` keys in `keyword_map.py` — that's the link to Excel row numbers.

## Gemini Prompt Design Rules

- System instruction is sent once (cached by Gemini's context): role + scale detection rules + JSON-only output requirement
- Each call prompt includes: year hint, JSON schema (exact field names), scale rule reminder, OCR text
- `hints` from Excel KeywordMap are injected as "may also be labelled: X, Y" lines — supports Malay & non-standard terminology
- Fallback: if page classifier finds nothing for a section, full PDF text is sent

## Cache Locations

- `.ocr_cache/<pdf_md5>.json` — Tesseract output (pages list)
- `.llm_cache/<pdf_md5>_<section>.json` — Gemini responses (audit/income_statement/balance_sheet/notes)

## Key Constraints

- **Python 3.9**: use `Optional[X]` from `typing` instead of `X | None`
- **PDF is always image-based**: never trust `pdfplumber` for text; OCR is always used
- **Scale detection**: reports in RM'000 are common — Gemini must multiply by 1000
- **Model name**: `gemini-2.5-flash-lite` — override with `--model` flag if needed
