---
name: sharepoint-audit
description: >
  Runs the full SharePoint → Auditor → CAWF comparison pipeline for the
  AuditorReportReader project. Use this skill whenever the user mentions
  "SharePoint audit", "fetch from SharePoint", "run the pipeline", "compare CAWF",
  "get from SharePoint and compare", "audit from SharePoint", "process Appleton",
  or any request that involves downloading audited accounts from the MS - Project
  Appleton SharePoint folder and comparing the AI extraction against the
  Credit Underwriting CAWF Excel. Also trigger proactively when the user asks
  about accuracy of the auditor reader against real underwriter data.
---

# SharePoint Audit Pipeline

## What this skill does

Automates the full end-to-end workflow for every company under
**MS - Project Appleton** (SharePoint — requires Microsoft login):

1. **Download PDF** — `Financial Statement / Audited Account` → latest PDF
2. **Download CAWF** — `Credit Underwriting` → latest CAWF Excel
3. **Extract** — runs Gemini pipeline on the PDF → filled Excel
4. **Compare** — `diff_checker.compare()` → accuracy % per field
5. **Report** — summary table + `output/sharepoint_run/summary.json`

## Prerequisites

Both env vars must be set (add to `.env` file):

```
GEMINI_API_KEY=AIza...
SP_CLIENT_ID=<your-azure-app-client-id>
```

First-time login: the script will prompt you to visit `https://microsoft.com/devicelogin`
and enter a short code. Token is cached — subsequent runs are silent.

## How to invoke

Always run from `AuditorReportReader/`:

```bash
# List company folders first (confirms connection):
python checker/sharepoint_pipeline.py --list-only

# Process all companies:
python checker/sharepoint_pipeline.py

# One company only (partial name match):
python checker/sharepoint_pipeline.py --company "Greatocean"

# Re-run fresh (ignore LLM cache):
python checker/sharepoint_pipeline.py --no-cache
```

Output lands in `output/sharepoint_run/<CompanyName>/`:
- `<report>.pdf` — downloaded audited accounts
- `<report>_filled.xlsx` — AI-extracted Financial Statements
- `<CAWF>.xlsx` — underwriter's CAWF reference
- `summary.json` — full accuracy breakdown for all companies

## SharePoint folder layout expected

```
MS - Project Appleton/
  <Company Name>/
    Financial Statement/
      Audited Account/        ← latest .pdf picked by modified date
    Credit Underwriting/      ← latest CAWF .xlsx picked (name contains "CAWF")
```

If folder names differ, update constants at top of `checker/sharepoint_pipeline.py`:
```python
_FOLDER_FIN_STMT  = "Financial Statement"
_FOLDER_AUDITED   = "Audited Account"
_FOLDER_CREDIT_UW = "Credit Underwriting"
_CAWF_KEYWORD     = "CAWF"
```

## Interpreting accuracy results

| Score | Meaning |
|---|---|
| **≥ 90%** | Excellent — AI matches underwriter closely |
| **70–89%** | Good — minor scale/rounding issues |
| **50–69%** | Moderate — likely RM'000 vs full-amount mismatch |
| **< 50%** | Needs attention — check PDF quality or Gemini prompts |

Error categories:
- `MATCH` / `ROUNDING` — correct (within 0.5%)
- `SCALE_x1000` — RM'000 detection issue (multiply by 1000 missed)
- `MISSING` — AI did not extract a field the underwriter filled
- `WRONG_VALUE` — genuine extraction error

## If comparison errors with "sheet not found"

`diff_checker.compare()` requires both files to have a **"Summary of Information"**
sheet in Financial Statements Template format (column B = labels, row 4 = years).

If the CAWF has a different layout, tell the user:
> "The CAWF Excel at `<path>` doesn't match the expected format. To compare,
> save the underwriter's figures into a copy of Financial Statements Template.xlsx
> and use that as the reference, or let me know the CAWF column layout."

## Parallel subagent pattern (for large batches)

```
Team Lead: list companies → spawn one subagent per company in parallel

Agent(description="Audit Greatocean",
      prompt="cd AuditorReportReader && python checker/sharepoint_pipeline.py --company 'Greatocean'
              Report: company name, score_pct, any errors.")
```
