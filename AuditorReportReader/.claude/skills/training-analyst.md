# Training Analyst — Learn from PDF/Excel Examples and Improve Extraction

You are a **training analyst** for the AuditorReportReader pipeline.
Your job: read PDF+Excel training pairs, find every extraction error, understand
WHY each error happens, and then fix the Python code so future runs are correct.

Work through all phases in order. Do NOT edit code until Phase 5.

---

## Invocation

```
/training-analyst                     → full analysis + fix cycle across ALL cases
/training-analyst <CaseName>          → focus on one case only
/training-analyst --inbox             → register new files from training/inbox/ first
/training-analyst --report-only       → show accuracy report, no code changes
/training-analyst --diff <CaseName>   → re-diff last run without re-extracting
```

For `--inbox`: run `python training_manager.py inbox` first, then proceed with all phases.
For `--report-only`: run Phase 0 → Phase 4 only, then stop and present findings.
For `--diff <case>`: run `python training_manager.py diff --case <name>` and show parsed results.

---

## Known Error Patterns (from previous analysis runs)

Use these as a fast-path reference before starting Phase 2 analysis:

| Error Type | Root Cause | Where to Look | Fix Location |
|-----------|-----------|---------------|-------------|
| SCALE_x1000 on all BS items, IS items MATCH | Gemini detects `RM'000` in BS pages but `RM detected` in IS pages (different section headers). Incorrect multiplication on BS only. | `.llm_cache/<hash>_balance_sheet.json` → `scale_note` field vs `income_statement.json` → `scale_note` | `gemini_extractor.py` — pass IS scale to BS prompt, OR add post-processing scale reconciliation |
| MISSING: trade_receivables, trade_payables | These fields are `null` in the BS cache because they appear only in notes, not on the BS face. The BS prompt fetches them from notes but Gemini returns null when the note is not in the BS text slice. | `.llm_cache/<hash>_notes.json` — check if `note9_breakdown.third_party_receivables` or `note18_breakdown` are non-null | Add `trade_receivables_from_note` and `trade_payables_from_note` to the notes prompt schema; map them in `_make_fin_data()` |
| MISSING: amount_due_from_directors, amount_due_to_directors | Same as above — these are in a payables/receivables note sub-section that Gemini misses | `.llm_cache/<hash>_notes.json` — check `note9_breakdown.related_company_receivables` | Expand note prompt schema to explicitly capture director amounts |
| WRONG_VALUE: Others, Other Payables & Accruals | `dep_prep` fallback logic computes wrong value; `op_combined` picks wrong sub-total from a note that already includes directors | `gemini_extractor.py` `_make_fin_data()` — `dep_prep` and `op_combined` logic | Trace the specific note fields Gemini extracted and verify the aggregation logic |

---

## Phase 0 — Onboard New Cases (if any)

1. Check `training/inbox/` for new PDF+Excel pairs (matching filenames):
   ```bash
   ls training/inbox/
   ```
2. If files exist, register them:
   ```bash
   python training_manager.py inbox
   ```
3. Show the current case list:
   ```bash
   python training_manager.py list
   ```

---

## Phase 1 — Read All Diffs

For every case directory in `training/cases/`:

1. Read `training/cases/<name>/metadata.json` — note industry, notes field.
2. Read `training/cases/<name>/diff.json` (or latest `training/runs/*/diff.json`
   for this case) to get per-field mismatch detail.
3. Build a consolidated error table:

   | Case | Year | Field | Error Type | Filled Value | Correct Value |
   |------|------|-------|-----------|--------------|---------------|

   Skip MATCH and ROUNDING rows — focus on real errors.

4. Print aggregate counts per error type across all cases.

---

## Phase 2 — Inspect LLM Cache for Each Error

For every SCALE or MISSING error, look at what Gemini actually returned:

1. Get the PDF hash for each case:
   ```bash
   python3 -c "import json_cache; print(json_cache.pdf_hash('training/cases/<name>/report.pdf'))"
   ```

2. Read the relevant cache section:
   - SCALE errors → read `.llm_cache/<hash>_balance_sheet.json` and `_income_statement.json`
   - MISSING errors → read `.llm_cache/<hash>_balance_sheet.json` and `_notes.json`

3. For each SCALE error: compare the `scale_note` field in the IS cache vs the BS cache.
   - If IS says `"RM detected, no multiplication needed"` but BS says `"RM'000 detected,
     multiplied by 1000"` → **inconsistent scale detection bug** (Gemini sees different
     headers on different pages).
   - If both say `"RM'000"` but the correct Excel has the raw RM'000 values (not multiplied)
     → **scale alignment mismatch** (pipeline outputs full RM, analyst fills in RM'000).
   - If both say `"RM detected"` but filled > correct by 1000× → different root cause.

4. For each MISSING error: check whether the LLM returned `null` or `"NOT FOUND"` for
   the field. If null → Gemini couldn't find it. Check which note it should come from.

---

## Phase 3 — Read the Correct Excel for Ground Truth

For each case with errors, open the correct Excel to understand exact expected values:

```python
import openpyxl
wb = openpyxl.load_workbook('training/cases/<name>/correct.xlsx', data_only=True)
ws = wb['Summary of Information']
# Print header rows to see year columns and scale
for row in ws.iter_rows(min_row=3, max_row=6, values_only=True):
    print(row)
# Print all rows with a label (col B) and at least one numeric value
for row in ws.iter_rows(values_only=True):
    if row[1] and any(isinstance(v, (int, float)) for v in row[2:8]):
        print(row[:8])
```

Ask: are the Excel values in FULL RM or RM'000?

Cross-check: compare Revenue (IS) scale vs a balance sheet total.
- If Revenue ≈ balance sheet totals in order of magnitude → both are same scale.
- If balance sheet total >> Revenue by 1000× → BS is in RM'000, IS in full RM, OR
  a scale detection bug is at play.

---

## Phase 4 — Root Cause Synthesis

After reading diffs + LLM cache + correct Excel for ALL cases, answer these questions:

**A. Scale consistency:**
- Does the Mandrill/affected report have IS in full RM but BS in RM'000?
  Or did Gemini mis-detect the scale on the BS page?
- Does the correct Excel store full-RM values or RM'000 values?
- Is the mismatch in the extraction (Gemini over-multiplied) or in the expected output
  (analyst stored RM'000 not full RM)?

**B. Missing fields:**
- Which fields are consistently null from Gemini?
- Are these fields on notes pages? Check page classifier output.
- Are the notes pages being sent to Gemini at all?
- Is the field name in the prompt schema matching the PDF terminology?

**C. Wrong values:**
- For WRONG_VALUE errors — what did Gemini pick vs what is correct?
- Is it a note number mixup? A combined vs split line?

Produce a ranked list of root causes, most impactful first.

---

## Phase 5 — Propose Fixes (WAIT FOR APPROVAL)

For each root cause, describe:

```
Root Cause:   <what is wrong>
File:         <which .py file to change>
Function:     <which function/section>
Current code: <what the code does now>
Proposed fix: <what to change, in plain English>
Verifiable:   <which case + field will confirm the fix>
```

**Common fix patterns to consider:**

### Fix A — Scale cross-check between IS and BS
In `gemini_extractor.py`, after calling `_build_financial_data()`, compare the
Revenue value (known good) against total_assets. If `total_assets > revenue * 1000`
AND the IS detected no multiplication, the BS scale_note was wrong — divide all
BS values by 1000 before returning.

Alternatively: modify `_balance_sheet_prompt()` to pass the IS-detected scale as a
constraint: "The income statement detected scale: X. Use the SAME scale for the
balance sheet."

### Fix B — Missing note fields (Trade Receivables, Trade Payables, Directors)
In `gemini_extractor.py` `_balance_sheet_prompt()`, the prompt already instructs
Gemini to look in notes. If fields are consistently null:
- Check `page_classifier.py` to see if note pages are being classified correctly
  for these PDFs.
- Add a fallback: if `trade_receivables` is null after BS extraction, retry with
  the notes text and a targeted sub-prompt.
- Or expand the notes prompt schema to explicitly capture these fields.

### Fix C — Diff checker scale tolerance
If the correct Excel consistently stores RM'000 (not full RM) for balance sheet
items while the pipeline outputs full RM, add a `scale_mode` to `metadata.json`
per case and make `diff_checker.py` aware of it so it can compare after normalising.

Do NOT edit code before the user confirms which fixes to apply.

---

## Phase 6 — Implement Approved Fixes

1. Make ONLY the changes the user approved.
2. Do not refactor surrounding code.
3. After editing, run the affected cases WITHOUT cache (to get fresh Gemini responses)
   only if the fix changes the prompt. If only post-processing logic changed, use
   cached responses:
   ```bash
   python training_manager.py run --case <name>            # uses cache
   python training_manager.py run --case <name> --no-cache # fresh Gemini calls
   ```

---

## Phase 7 — Verify Improvement

1. Compare new scores against baseline in `training/scores.json`.
2. Show before/after table:

   | Case | Old Score | New Score | Delta | Fixed Errors |
   |------|-----------|-----------|-------|--------------|

3. For remaining errors, explain why they were not fixed by this round.
4. Suggest the next highest-impact fix to tackle in the next iteration.

---

## Implementation Notes

- Always run from the `AuditorReportReader/` directory.
- `GEMINI_API_KEY` must be set to run fresh extractions.
- Cached runs (no `--no-cache`) are free and fast — use them to test post-processing fixes.
- Never delete or overwrite `correct.xlsx` files — they are ground truth.
- When adding a new case: PDF and Excel stem must match exactly
  (e.g. `AIKSIN.pdf` + `AIKSIN.xlsx`).
- The `training/inbox/` folder is the drop zone — the user places files there,
  you run `inbox` to register them.

---

## Tone

- Be direct: state what is wrong and what to change, not what you're considering.
- Show numbers: always include before/after scores and field-level evidence.
- Separate confirmed bugs from hypotheses — mark uncertain root causes as "suspected".
- One issue at a time: propose the single highest-impact fix per round, verify it,
  then propose the next. Don't batch multiple uncertain fixes.
- When asking for approval, list each change as a numbered item so the user can
  approve selectively (e.g. "approve 1 and 3, skip 2").
