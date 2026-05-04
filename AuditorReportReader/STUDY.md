# How to Study This Codebase

Start here. This file tells you exactly what to read, in what order, and why.

---

## Three Folders, Three Jobs

```
AuditorReportReader/
│
├── extractor/   ← Job 1: Read a PDF → fill an Excel
├── checker/     ← Job 2: Compare AI-filled Excel vs correct answer
└── downloader/  ← Job 3: Download from SharePoint into training/inbox/
```

---

## Folder 1 — `extractor/`

**Job:** Take a Malaysian auditor report PDF → extract financial data → fill an Excel template.

That job has 5 steps. Each step is one file in `extractor/pipeline/`.

```
PDF file
   │
   ▼
extractor/pipeline/pdf_ocr.py          Step 1 — turn the PDF into text (via Tesseract OCR)
   │
   ▼
extractor/pipeline/page_classifier.py  Step 2 — label each page (audit? income statement? balance sheet?)
   │
   ▼
extractor/pipeline/gemini_extractor.py Step 3 — send text to Gemini → get financial numbers as JSON
   │
   ▼
extractor/pipeline/validator.py        Step 4 — arithmetic checks (Revenue - COS = Gross Profit?)
   │
   ▼
extractor/pipeline/excel_filler.py     Step 5 — write everything into the Excel template
   │
   ▼
CompanyName_filled.xlsx
```

### Reading order for `extractor/`

**Start here (10 min):**
`extractor/auditor_report_reader.py` — the main script the user runs.
Read top to bottom. It calls each step in order with clear `=== STEP N ===` labels.

**Then read the pipeline (in order):**

| File | What it does | Key function |
|------|-------------|--------------|
| `extractor/pipeline/pdf_ocr.py` | Runs Tesseract OCR, caches results | `extract_pages()` |
| `extractor/pipeline/page_classifier.py` | Labels pages by keyword signals | `classify_pages()` |
| `extractor/pipeline/gemini_extractor.py` | Makes 4 Gemini API calls, parses JSON | `extract_all()` |
| `extractor/pipeline/validator.py` | Checks arithmetic (GP = Rev − COS etc.) | `run_checks()` |
| `extractor/pipeline/excel_filler.py` | Writes values + flags into Excel sheets | `write_output()` |

**Then read the utilities (any order):**

| File | What it does |
|------|-------------|
| `extractor/utils/json_cache.py` | Saves/loads Gemini responses to disk so you don't pay twice |
| `extractor/utils/keyword_map.py` | Maps field names ("Revenue") to Excel row numbers |
| `extractor/utils/web_check.py` | DuckDuckGo search to check if auditor is MIA-blacklisted |

**Tests:**
`extractor/tests/test_pipeline.py` — mock-based integration test. No API key needed. Run with:
```bash
python extractor/tests/test_pipeline.py
```

---

## Folder 2 — `checker/`

**Job:** Compare an AI-filled Excel against an underwriter's correct Excel → show accuracy %.

| File | What it does |
|------|-------------|
| `checker/diff_checker.py` | Compares two Excels field by field → accuracy % per category |
| `checker/training_manager.py` | Manages a library of test PDFs + correct Excels; runs bulk accuracy tests |
| `checker/generate_report.py` | Builds an HTML accuracy dashboard from training results |
| `checker/accuracy_tracker.py` | Snapshots accuracy results and compares before/after any code change |
| `checker/sharepoint_pipeline.py` | Downloads PDFs from SharePoint, runs extractor, compares CAWF |
| `checker/sharepoint_downloader.py` | SharePoint auth + file download helpers (Microsoft Graph API) |

### Reading order for `checker/`

Start with `checker/diff_checker.py` — it's the core comparison logic everything else calls.
Then read `checker/training_manager.py` to understand how bulk testing works.
`sharepoint_pipeline.py` is only needed if you're connecting to SharePoint.

---

## Folder 3 — `downloader/`

**Job:** Download PDF + CAWF Excel pairs from SharePoint into `training/inbox/` for training.

| File | What it does |
|------|-------------|
| `downloader/sp_to_training.py` | Downloads matching PDF + Excel pairs into training/inbox/ |

### Full training workflow

```bash
# 1. Download from SharePoint:
python downloader/sp_to_training.py

# 2. Register downloaded pairs as training cases:
python checker/training_manager.py inbox

# 3. Run AI extraction + accuracy comparison:
python checker/training_manager.py run

# 4. View HTML report in browser:
python checker/generate_report.py --open
```

### Tracking accuracy changes (before vs after a code fix)

Use `checker/accuracy_tracker.py` to snapshot results and compare them side by side
so you can see exactly which fields improved and which regressed.

```bash
# Step 1 — run training to get current results:
python checker/training_manager.py run

# Step 2 — save a named snapshot BEFORE your change:
python checker/accuracy_tracker.py snapshot "baseline"

# Step 3 — make your code or prompt changes, then re-run training:
python checker/training_manager.py run

# Step 4 — save a snapshot AFTER your change:
python checker/accuracy_tracker.py snapshot "after-trade-rec-fix"

# Step 5 — compare the two side by side (5 sections of detail):
python checker/accuracy_tracker.py compare "baseline" "after-trade-rec-fix"

# Show only fields that changed status (skip all the unchanged rows):
python checker/accuracy_tracker.py compare "baseline" "after-trade-rec-fix" --changes-only

# List all saved snapshots:
python checker/accuracy_tracker.py list

# Show accuracy trend across all snapshots over time:
python checker/accuracy_tracker.py history
```

The compare output has 5 sections:

| Section | What you see |
|---------|-------------|
| 1. Overall | Single accuracy number before → after → Δ |
| 2. By company | Every company's score before → after → Δ |
| 3. By field aggregate | Each field type's match rate across all companies → Δ |
| 4. Full detail | Every single (company × year × field) row with Before/After status and actual values when something changed |
| 5. Change summary | Only the `↑ FIXED` and `↓ BROKEN` rows listed together at the bottom |

Snapshots are saved to `training/snapshots/` as JSON files. No API calls are made —
it reads the existing `training/scores.json` and each company's `diff.json`.

---

## Folder Map

```
AuditorReportReader/
│
├── extractor/                         ← Job 1: PDF → Excel
│   ├── auditor_report_reader.py       ← START HERE (entry point)
│   ├── pipeline/                      ← Core 5-step data flow
│   │   ├── pdf_ocr.py                 #   Step 1 — OCR
│   │   ├── page_classifier.py         #   Step 2 — classify pages
│   │   ├── gemini_extractor.py        #   Step 3 — LLM extraction
│   │   ├── validator.py               #   Step 4 — arithmetic validation
│   │   └── excel_filler.py            #   Step 5 — write Excel
│   ├── utils/                         ← Support utilities
│   │   ├── json_cache.py              #   cache Gemini responses
│   │   ├── keyword_map.py             #   field name → Excel row mapping
│   │   └── web_check.py              #   MIA blacklist search
│   └── tests/
│       └── test_pipeline.py           ← Mock tests (no API key needed)
│
├── checker/                           ← Job 2: Compare Excel accuracy
│   ├── diff_checker.py                ← START HERE (core comparison logic)
│   ├── training_manager.py            #   bulk test runner
│   ├── generate_report.py             #   HTML accuracy dashboard
│   ├── accuracy_tracker.py            #   snapshot + before/after comparison
│   ├── sharepoint_pipeline.py         #   SharePoint → extract → compare (one shot)
│   └── sharepoint_downloader.py       #   SharePoint auth + download helpers
│
├── downloader/                        ← Job 3: SharePoint → training/inbox/
│   └── sp_to_training.py             ← Download PDF + CAWF pairs for training
│
├── .env                               ← API keys (never committed to git)
├── Financial Statements Template.xlsx ← Excel template (required)
├── data/                              ← sample PDFs
├── output/                            ← filled Excel outputs
├── training/                          ← training cases + accuracy scores
│   ├── inbox/                         ←   drop PDF + Excel pairs here
│   ├── cases/                         ←   registered training cases
│   ├── runs/                          ←   extraction history (diff.json per run)
│   └── snapshots/                     ←   accuracy snapshots for before/after comparison
└── docs/                              ← HTML accuracy reports
```

---

## Key Concepts

### OCR cache (`.ocr_cache/`)
Tesseract is slow. After the first run, `pdf_ocr.py` saves the text to `.ocr_cache/<md5>.json`.
Re-runs skip OCR entirely. Delete this folder to force a fresh OCR.

### LLM cache (`.llm_cache/`)
Gemini API costs money. `utils/json_cache.py` saves each API response to `.llm_cache/<md5>_<section>.json`.
Re-runs use cached responses for free. Use `--no-cache` to force fresh Gemini calls.

### Scale detection (RM'000 vs full amounts)
Malaysian reports often show numbers in thousands (RM'000). Gemini detects this and multiplies by 1000.
If you see numbers that are 1000× off, check `extractor/pipeline/gemini_extractor.py` → scale rule in the prompt.

### The 4 Gemini calls
`extractor/pipeline/gemini_extractor.py` → `extract_all()` makes exactly 4 API calls:
1. First 15 pages → audit opinion, firm name, signatures
2. Income statement pages → Revenue, COS, Gross Profit, Net Profit, etc.
3. Balance sheet pages → Assets, Liabilities, Equity
4. Notes pages → interest expenses, staff costs breakdown

---

## Running the code

```bash
# Install dependencies
pip install -r requirements.txt

# Extract from a PDF (always run from AuditorReportReader/ root)
python extractor/auditor_report_reader.py --pdf "data/Greatocean 2024.pdf"

# Force fresh Gemini calls
python extractor/auditor_report_reader.py --pdf "data/Greatocean 2024.pdf" --no-cache

# Mock tests (no API key needed)
python extractor/tests/test_pipeline.py

# Download training data from SharePoint → register → run → report
python downloader/sp_to_training.py
python checker/training_manager.py inbox
python checker/training_manager.py run
python checker/generate_report.py --open

# SharePoint → extract → compare in one shot (needs SP_CLIENT_ID)
python checker/sharepoint_pipeline.py --list-only

# ── Accuracy change tracking ──────────────────────────────────────────────
# Save a snapshot of current results:
python checker/accuracy_tracker.py snapshot "baseline"

# Compare two snapshots (full detail — all 5 sections):
python checker/accuracy_tracker.py compare "baseline" "after-fix"

# Show only what changed (skip unchanged rows):
python checker/accuracy_tracker.py compare "baseline" "after-fix" --changes-only

# List all saved snapshots:
python checker/accuracy_tracker.py list

# Show accuracy trend over time:
python checker/accuracy_tracker.py history
```
