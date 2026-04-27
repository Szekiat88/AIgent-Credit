# Cloud Report — Upload Extraction Results to GitHub Pages Dashboard

Upload all training results to GitHub and publish the accuracy dashboard online.

---

## What this skill does

1. Regenerates the HTML accuracy dashboard from the latest training data
2. Commits the report + data files to GitHub
3. Pushes to `main` branch — GitHub Pages serves it automatically at:
   `https://szekiat88.github.io/AIgent-Credit/AuditorReportReader/docs/report.html`

---

## Invocation

```
/cloud-report                 → generate report and push to GitHub
/cloud-report --no-push       → generate report locally only (no upload)
/cloud-report --open          → generate and open in browser first
```

---

## Phase 1 — Re-run training diff (if new data)

If any training case has been re-run since the last push, re-diff it first:

```bash
cd AuditorReportReader
python training_manager.py diff --case <name>
```

Or for a full fresh run (requires GEMINI_API_KEY):
```bash
python training_manager.py run
```

---

## Phase 2 — Generate the report

```bash
cd AuditorReportReader
python generate_report.py
```

This writes:
- `docs/report.html` — self-contained HTML dashboard
- `docs/data.json` — raw JSON with all scores and field-level detail

Confirm the accuracy numbers printed match what you expect:
```
Overall accuracy: XX%  (matched/total fields)
```

If `--open` was requested, also run:
```bash
python generate_report.py --open
```

---

## Phase 3 — Commit and push

Stage only the report files (never commit PDFs, caches, or client data):

```bash
cd "/Users/newuser/Documents/GitHub/AIgent Credit"
git add AuditorReportReader/docs/report.html
git add AuditorReportReader/docs/data.json
git add AuditorReportReader/generate_report.py
git add AuditorReportReader/gemini_extractor.py
git add AuditorReportReader/.claude/commands/
git add AuditorReportReader/training_manager.py
git add AuditorReportReader/diff_checker.py
git add AuditorReportReader/training/scores.json
git add AuditorReportReader/training/patterns.json
git add AuditorReportReader/CLAUDE.md
git add .gitignore
```

Also stage any other changed `.py` files:
```bash
git diff --name-only | grep '\.py$' | xargs git add
```

Commit with a clear message:
```bash
git commit -m "Training report: XX% accuracy (YY/ZZ fields matched)"
```

Push:
```bash
git push origin main
```

---

## Phase 4 — Verify dashboard is live

After pushing, the dashboard is accessible at:
```
https://szekiat88.github.io/AIgent-Credit/AuditorReportReader/docs/report.html
```

**First-time setup only** (do this once in GitHub Settings):
1. Go to https://github.com/Szekiat88/AIgent-Credit/settings/pages
2. Under "Source", select **Deploy from a branch**
3. Branch: `main` / Folder: `/ (root)`
4. Click **Save**
5. Wait ~2 minutes for the first deployment

After setup, every `git push` automatically updates the live dashboard within ~60 seconds.

---

## What the dashboard shows

- **Overall accuracy %** — big number at the top
- **Matched / Total fields** — how many fields the pipeline got right
- **Fields to Fix** — how many still have errors
- **Top failing fields** — ranked by error count with dominant error type
- **Per-case results** — score, error breakdown, expandable field-by-field table
  showing what the pipeline extracted vs what is correct

---

## Adding new training cases

1. Drop `CompanyName.pdf` + `CompanyName.xlsx` into `AuditorReportReader/training/inbox/`
2. Run: `python training_manager.py inbox`
3. Run: `python training_manager.py run --case CompanyName` (needs GEMINI_API_KEY)
4. Run `/cloud-report` to update the dashboard

---

## Files never committed (sensitive / generated)

- `*.pdf` — client auditor reports
- `.llm_cache/` — Gemini API responses
- `.ocr_cache/` — OCR text cache
- `training/runs/` — run output directories
- `*_FILLED.xlsx`, `*_filled.xlsx` — filled Excel outputs
- `samples/`, `samples_output/` — client data
- `.DS_Store` — macOS metadata
