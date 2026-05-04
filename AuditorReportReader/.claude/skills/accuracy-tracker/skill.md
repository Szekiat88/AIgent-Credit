---
name: accuracy-tracker
description: >
  Save accuracy snapshots before and after code changes, then show a side-by-side
  comparison to confirm whether a change improved or degraded extraction accuracy.
  Use this skill whenever the user wants to track accuracy changes, compare before/after
  results, save a baseline, see which fields improved or regressed, or view accuracy history.
---

# Accuracy Change Tracker

## What this skill does

Snapshots the current training results (from `training/scores.json` + each company's
`diff.json`) under a named label, then compares any two snapshots side by side at
**four levels of detail**: overall → per-company → per-field aggregate → every single
field for every single company.

```
Before change  →  snapshot "baseline"
Make changes   →  re-run training
After change   →  snapshot "after-fix"
                  compare "baseline" "after-fix"  →  full side-by-side report
```

---

## Typical workflow

```bash
# 1. Run training to get current results:
python checker/training_manager.py run

# 2. Save snapshot BEFORE your change:
python checker/accuracy_tracker.py snapshot "baseline"

# 3. Make your code/prompt changes, then re-run training:
python checker/training_manager.py run

# 4. Save snapshot AFTER your change:
python checker/accuracy_tracker.py snapshot "after-gemini-prompt-fix"

# 5. Compare the two — full side-by-side report:
python checker/accuracy_tracker.py compare "baseline" "after-gemini-prompt-fix"
```

---

## All commands

```bash
# Save current training results as a named snapshot:
python checker/accuracy_tracker.py snapshot "<label>"

# Full side-by-side comparison (all 4 levels):
python checker/accuracy_tracker.py compare "<label-before>" "<label-after>"

# Comparison showing only fields that changed status:
python checker/accuracy_tracker.py compare "<label-before>" "<label-after>" --changes-only

# List all saved snapshots with their overall accuracy and date:
python checker/accuracy_tracker.py list

# Show accuracy trend across all snapshots in chronological order:
python checker/accuracy_tracker.py history
```

Labels are free-form strings. Partial matching is supported — `compare base after`
matches `baseline` and `after-gemini-prompt-fix`.

---

## Snapshot storage

Each snapshot is a single JSON file capturing the state at that moment:

```
training/snapshots/
  baseline_20260504_121700.json
  after-gemini-prompt-fix_20260505_090300.json
```

Contents per snapshot:
- Label + timestamp
- Overall weighted accuracy (%)
- Per-company: `score_pct`, `matched`, `total`, `by_category`
- Per-company per-field: `year`, `label`, `field`, `filled`, `correct`, `status`
  (MATCH / MISSING / WRONG_VALUE)

**No API calls** — reads `training/scores.json` and every company's latest `diff.json`.
Always run `training_manager.py run` first to get fresh results before snapshotting.

---

## Full side-by-side comparison output

The compare command prints four sections in order:

---

### Section 1 — Overall score

```
══════════════════════════════════════════════════════════════
  ACCURACY COMPARISON
  Before : baseline                (2026-05-04  84.2%  28 co.)
  After  : after-gemini-prompt-fix (2026-05-05  86.7%  28 co.)
══════════════════════════════════════════════════════════════

  OVERALL    84.2%  →  86.7%   Δ +2.5%  ↑
```

---

### Section 2 — Per-company summary

```
──────────────────────────────────────────────────────────────
  BY COMPANY
──────────────────────────────────────────────────────────────
  Company                    Before    After     Δ
  Greatocean                  98.2%    98.2%    0.0%  =
  AIKSIN                      85.2%    87.0%   +1.8%  ↑
  Mandrill                    74.1%    82.3%   +8.2%  ↑
  Exaco Marketing SB          64.3%    66.0%   +1.7%  ↑
  Ace Logistic SB              4.5%    12.0%   +7.5%  ↑
  ...
```

---

### Section 3 — Per-field aggregate (across all companies)

Each field's accuracy = MATCH count across all companies ÷ total occurrences of
that field. Shows which field types improved regardless of company.

```
──────────────────────────────────────────────────────────────
  BY FIELD  (aggregated across all companies)
──────────────────────────────────────────────────────────────
  Field                        Before    After     Δ
  Revenue                      100.0%   100.0%    0.0%  =
  Cost of Sales                 96.4%    96.4%    0.0%  =
  Gross Profit                  96.4%    96.4%    0.0%  =
  Trade Receivables             30.0%    60.0%  +30.0%  ↑
  Other Receivables             28.6%    57.1%  +28.5%  ↑
  Other Payables & Accruals     50.0%    71.4%  +21.4%  ↑
  Amount Due to Director        25.0%    25.0%    0.0%  =
  Total Asset                  100.0%   100.0%    0.0%  =
  ...

  Regressions (fields that got worse):  None  ✓
```

Fields sorted: regressions first (if any), then biggest gains, then unchanged.

---

### Section 4 — Full detail: every field, every company, side by side

This is the complete raw view. Every row shows the exact before/after status
for every (company, year, field) combination, with the actual extracted vs
correct values shown when status changed.

```
──────────────────────────────────────────────────────────────
  FULL DETAIL  (every field × every company)
──────────────────────────────────────────────────────────────

  ── Greatocean ─────────────────────────────────────────────
  Year  Field                        Before        After
  2023  Revenue                      MATCH         MATCH         =
  2023  Cost of Sales                MATCH         MATCH         =
  2023  Gross Profit                 MATCH         MATCH         =
  2023  Trade Receivables            MISSING       MATCH         ↑ FIXED
        filled: NOT FOUND  →  1,479,007
  2023  Other Receivables            MISSING       MATCH         ↑ FIXED
        filled: NOT FOUND  →  1,450,282
  2023  Amount Due from Directors    MISSING       MISSING       =
  2023  Cash & Cash At Bank          MATCH         MATCH         =
  2023  Total Asset                  MATCH         MATCH         =
  2023  Trade Payables               MISSING       MISSING       =
  2023  Other Payables & Accruals    MISSING       MATCH         ↑ FIXED
        filled: NOT FOUND  →  1,774,472
  2023  Total Liabilities            MATCH         MATCH         =
  2023  Equity                       MATCH         MATCH         =
  2024  Revenue                      MATCH         MATCH         =
  2024  Trade Receivables            MISSING       MATCH         ↑ FIXED
        filled: NOT FOUND  →  2,009,356
  2024  Others                       WRONG_VALUE   MATCH         ↑ FIXED
        filled: 39,982  →  586,401  (correct: 586,401)
  2024  Other Payables & Accruals    WRONG_VALUE   MATCH         ↑ FIXED
        filled: 635,954  →  2,264,925  (correct: 2,264,925)
  ...

  ── Mandrill ───────────────────────────────────────────────
  Year  Field                        Before        After
  2023  Revenue                      MATCH         MATCH         =
  2023  Staff Cost                   MATCH         WRONG_VALUE   ↓ BROKEN
        filled: 1,074,780  →  950,000  (correct: 1,074,780)
  2023  Trade Receivables            MISSING       MATCH         ↑ FIXED
  ...

  ── AIKSIN ─────────────────────────────────────────────────
  ...
```

When a field changed status, the actual values are shown on the next line
so you can see exactly what the extractor returned before vs after.

---

### Section 5 — Change summary (at the bottom)

A quick-scan digest of everything that changed:

```
──────────────────────────────────────────────────────────────
  CHANGE SUMMARY
──────────────────────────────────────────────────────────────
  ↑ Fixed   (14 fields across 5 companies):
    Greatocean  2023  Trade Receivables         MISSING → MATCH
    Greatocean  2023  Other Receivables         MISSING → MATCH
    Greatocean  2023  Other Payables            MISSING → MATCH
    Greatocean  2024  Trade Receivables         MISSING → MATCH
    Greatocean  2024  Others                    WRONG_VALUE → MATCH
    Greatocean  2024  Other Payables            WRONG_VALUE → MATCH
    Mandrill    2024  Trade Receivables         MISSING → MATCH
    Mandrill    2024  Trade Payables            MISSING → MATCH
    ...

  ↓ Broken  (1 field across 1 company):
    Mandrill    2023  Staff Cost                MATCH → WRONG_VALUE
                      filled: 1,074,780  →  950,000  (correct: 1,074,780)

  =  Unchanged: 188 fields
```

---

## History view

```
  Snapshot                          Date        Overall   Companies
  baseline                          2026-05-04   84.2%       28
  after-gemini-prompt-fix           2026-05-05   86.7%       28
  after-balance-sheet-rewrite       2026-05-06   89.1%       28
  after-notes-parsing               2026-05-07   87.4%       28  ← regression
```

---

## What each status means

| Status | Meaning |
|--------|---------|
| `MATCH` | AI extracted the correct value |
| `MISSING` | AI returned `NOT FOUND` or `null` — field not extracted |
| `WRONG_VALUE` | AI extracted a value but it does not match the CAWF |

A fix is `MISSING → MATCH` or `WRONG_VALUE → MATCH`.
A regression is `MATCH → MISSING` or `MATCH → WRONG_VALUE`.
