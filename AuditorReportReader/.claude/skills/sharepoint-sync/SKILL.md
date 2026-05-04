---
name: sharepoint-sync
description: >
  Download audited account PDFs and CAWF Excels from the MS - Project Appleton
  SharePoint into training/inbox/ so they can be used as training data.
  Use this skill whenever the user wants to sync from SharePoint to training,
  download training data, populate the inbox, or prepare cases for accuracy testing.
---

# SharePoint → Training Sync

## What this skill does

Downloads matching PDF + Excel pairs from every company folder under
**MS - Project Appleton** (SharePoint) into `training/inbox/` — ready for
`training_manager.py inbox` to register them as accuracy training cases.

```
SharePoint: MS - Project Appleton/
  <Company>/
    Financial Statements/ ... → <Company>.pdf  ─┐
    Credit Underwriting/      → <Company>.xlsx ─┘  → training/inbox/
```

---

## PDF finding strategy (2-path, each with filename check + page-peek)

The downloader always checks subfolders first. Within each path, it first
looks for a filename containing "audited"; if that fails it reads PDFs
**one by one** (pages 1–3) to find the latest financial statement.
Only if the subfolder path yields nothing does it fall back to the
Financial Statements folder directly.

```
Financial Statements/
  │
  ├─ Path A: audited subfolder found?
  │    ├─ YES → look for "audited" filename inside subfolder
  │    │           found  → download ✓
  │    │           not found → page-peek PDFs in subfolder → download ✓
  │    └─ NO  → go to Path B
  │
  └─ Path B: Financial Statements folder directly
               look for "audited" filename in folder
                 found  → download ✓
                 not found → page-peek PDFs in folder → download ✓
```

---

### Path A — Audited subfolder (always checked first)

1. Inside the Financial Statements folder, look for **any subfolder whose name
   contains "audited"** (e.g. "Audited Account", "Audited", "Audited FS 2024").
2. List all PDFs inside that subfolder.
3. **Step A1 — filename check:** look for a PDF whose filename contains "audited".
   If found → **download it. Done.**
4. **Step A2 — page-peek:** no "audited" filename found. Read every PDF in the
   subfolder **one by one** (pages 1–3). Look for "financial statement" keyword.
   Pick the PDF with the most recent year. If found → **download it. Done.**

---

### Path B — Financial Statements folder directly (only if Path A found nothing)

Reached when no audited subfolder exists, **or** the subfolder contained no
matching PDF (neither by filename nor by page content).

1. List all PDFs directly inside the Financial Statements folder (flat, no drill-down).
2. **Step B1 — filename check:** look for a PDF whose filename contains "audited".
   If found → **download it. Done.**
3. **Step B2 — page-peek:** no "audited" filename found. Read every PDF in the
   folder **one by one** (pages 1–3). Look for "financial statement" keyword.
   Pick the PDF with the most recent year. If found → **download it. Done.**

---

### Page-peek detail (Steps A2 and B2)

**For each PDF in the folder (sorted newest-first by SharePoint modified date):**

1. Download the PDF to a **temporary file**.
2. Read **pages 1, 2, then 3** in order:
   - First attempt: `pdfplumber` (fast; works if PDF has a text layer).
   - Fallback: **Tesseract OCR** via `pdf2image` + `pytesseract` (for scanned/
     image-based PDFs — the common case for Malaysian audited accounts).
3. Search for the keyword **"financial statement"** (case-insensitive).
4. If found, record the **highest 4-digit year** on pages 1–3
   (e.g. "For the year ended 31 December 2024" → year 2024).
5. Delete the temp file. Move on to the next PDF.
6. After all PDFs are checked, pick the candidate with the **most recent year**.
   Ties broken by SharePoint modified date.

Console output during page-peek:
```
    [note]     no "audited" filename — reading PDFs one by one (3 files)
    [peek 1/3] Annual Report 2024.pdf
    [peek 1/3] ✓ "financial statement" found  |  year: 2024
    [peek 2/3] Management Accounts Q3.pdf
    [peek 2/3] ✗ keyword not found — skipped
    [peek 3/3] Draft Accounts 2023.pdf
    [peek 3/3] ✓ "financial statement" found  |  year: 2023
    [result]   Latest → Annual Report 2024.pdf  (year 2024)
```

---

### When everything fails

If neither Path A nor Path B finds a PDF (no subfolders, no "audited" files,
and no "financial statement" keyword on pages 1–3 of any PDF), the company
is skipped with the message `no audited PDF found`.

---

## Financial Statements folder matching

The folder search is fuzzy — any of these resolve correctly:

| Actual SharePoint name      | Resolves? |
|-----------------------------|-----------|
| `Financial Statements`      | ✓ exact   |
| `Financial Statement`       | ✓ substring |
| `Financials Statements`     | ✓ fuzzy (≥ 0.72 similarity) |
| `Financials`                | ✓ substring |
| `Financial Stmt`            | ✓ fuzzy   |

---

## Prerequisites

Add to your `.env` file (in `AuditorReportReader/`):

```
SP_SHARING_LINK=https://magnisave-my.sharepoint.com/:f:/g/...
```

No Azure app registration needed — the sharing link provides guest authentication.
No `GEMINI_API_KEY` needed for download (only needed when running training).

---

## How to invoke

Always run from `AuditorReportReader/`:

```bash
# Step 1 — list company folders (confirms connection works):
python downloader/sp_to_training.py --list-only

# Step 2 — download all companies:
python downloader/sp_to_training.py

# Step 3 — one company only (partial name match):
python downloader/sp_to_training.py --company "Greatocean"

# Step 4 — force re-download (overwrite existing files):
python downloader/sp_to_training.py --force
```

---

## Full training workflow (after download)

```bash
# Register downloaded pairs as training cases:
python checker/training_manager.py inbox

# Run AI extraction + accuracy comparison:
python checker/training_manager.py run

# Open HTML accuracy report in browser:
python checker/generate_report.py --open
```

---

## File naming

Files are always saved as `<CompanyFolderName>.pdf` and `<CompanyFolderName>.xlsx`
(matching stems), regardless of their original name on SharePoint.
This is required for `training_manager.py inbox` to pair them correctly.

---

## First-time login

On the first run the script prints a device-code sign-in prompt:

```
  1. Open: https://microsoft.com/devicelogin
  2. Enter code: XXXXXXXX
  3. Sign in as: <your email>
```

The token is cached in `checker/.sharepoint_token_cache.json` — future runs are silent.

---

## If a company is skipped

| Console message | Cause |
|-----------------|-------|
| `no 'Financial Statements' folder` | Folder missing or name too different to fuzzy-match |
| `no audited PDF found` | Both paths failed — no "audited" filename and no "financial statement" text found on pages 1–3 of any PDF in either the audited subfolder or the Financial Statements folder |
| `no Excel in Credit Underwriting` | No Excel uploaded to the Credit Underwriting folder yet |

---

## Interpreting accuracy after training run

| Score | Meaning |
|-------|---------|
| ≥ 90% | Excellent — AI matches underwriter closely |
| 70–89% | Good — minor rounding or label issues |
| 50–69% | Moderate — likely RM'000 vs full-amount mismatch |
| < 50% | Needs attention — check PDF quality or Gemini prompts |
