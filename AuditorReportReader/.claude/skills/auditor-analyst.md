# Auditor Report Analyst

You are acting as a **P2P Credit Analyst**. Your job is to read a Malaysian auditor report PDF and fill in the `Financial Statements Template.xlsx` to help determine whether to approve a loan.

Work through the phases below in order. Never skip a phase. Do not start coding until the user confirms the skill spec.

---

## Inputs

- `<PDF>` — The auditor report PDF (e.g. `Greatocean 2024.pdf`)
- `<EXCEL>` — The template to fill (e.g. `Financial Statements Template.xlsx`)
- Optional: `<KEYWORD_MAP>` — An Excel sheet tab named `KeywordMap` that maps custom keywords to template row labels (allows the user to extend mappings without touching code)

---

## Phase 1 — Independent Auditors' Report: Opinion Check

1. Locate the section titled **"INDEPENDENT AUDITORS' REPORT"** (or nearest equivalent).
2. Read the **Opinion** paragraph.
3. Classify the opinion:
   | Detected wording | Classification |
   |---|---|
   | "Qualified Opinion" | `QUALIFIED` |
   | "Disclaimer of Opinion" / "Disclaimed Opinion" | `DISCLAIMED` |
   | "Adverse Opinion" | `ADVERSE` |
   | None of the above (standard unqualified) | `UNQUALIFIED` |
4. Write the classification string (e.g. `QUALIFIED`) into **Cell A1** of the Excel output sheet.
5. Flag any wording that confirms "true and fair view" — note whether this phrase is present or absent.

---

## Phase 2 — Auditor & Accountant Verification

1. Extract from the report:
   - **Auditor firm name** (e.g. "Messrs XYZ & Associates")
   - **Signing partner / accountant name** and their **MIA membership number** if shown
   - **Date of signature**
2. Check the **Statutory Declaration** section:
   - Identify the **Commissioner of Oaths (COP)** name and stamp details.
3. Perform a **web search** for:
   - `"<auditor firm name>" blacklisted MIA Malaysia`
   - `"<accountant name>" MIA disciplinary Malaysia`
4. Record findings in the Excel sheet (dedicated "Auditor Verification" section or notes cell).
5. Cross-check: confirm the **Director Report**, **Statement by Directors**, and **Independent Auditors' Report** all carry consistent signatures/dates.

---

## Phase 3 — Statutory Declaration

1. Locate the **STATUTORY DECLARATION** section.
2. Verify:
   - COP name and stamp are present and legible.
   - Declaration date is consistent with the report date.
3. Flag if any of these are missing or inconsistent.

---

## Phase 4 — Income Statement Extraction

Map the following items from the PDF to the corresponding Excel rows.

### 4a — Revenue & Profit
| Excel Row | PDF Source |
|---|---|
| Gross Profit | "Gross profit" line in Income Statement |
| Other Income | "Other income" / "Other operating income" |
| Net Profit / (Loss) | "Profit/(Loss) for the year" — **must match** "Total comprehensive income for the year" |
| Tax Expense | "Income tax expense" / "Tax expense" |

> **Validation rule:** Net Profit value must equal Total Comprehensive Income. Flag a mismatch if they differ.

### 4b — Staff Costs
Locate the **Staff Costs** note (look for a note reference on the face of the Income Statement). Sum all sub-items found:

| Sub-item to find | Notes |
|---|---|
| Directors' remuneration — Emoluments | May be split across lines |
| Directors' remuneration — Fees | May be split across lines |
| Directors' EPF contribution | |
| Directors' SOCSO contribution | |
| Directors' EIS contribution | |
| Wages, Salaries, Bonus and Allowances | |
| Sales Commission | |
| Staff Welfare | |
| Staff Refreshment | |
| SOCSO contribution (non-director) | |
| EIS contribution (non-director) | |
| EPF contribution (non-director) | |

Insert the **total** into the **Staff Cost** row in Excel.

### 4c — Depreciation
Locate "Depreciation of property, plant and equipment" (or equivalent). Insert into the **Depreciation** row.

### 4d — Finance Expenses
Locate the **Finance Costs** note. Sum all interest lines found:

| Sub-item to find |
|---|
| Bank overdraft interest |
| Bank acceptance interest |
| Hire purchase interest |
| Term loan interest |
| Revolving credit interest |
| Any other line containing "interest" |

Insert the **total** into the **Finance Expenses** row.

### 4e — Other Operating Expenses
**Formula (do not use the raw total directly):**

```
Other Operating Expenses = Administrative and Other Operating Expenses
                           − Staff Costs
                           − Finance Expenses
```

Insert the derived value into the **Other Operating Expenses** row.

---

## Phase 5 — Balance Sheet Extraction

### 5a — Non-Current Assets
Extract the total **Non-Current Assets** figure and each major sub-line (PPE, intangibles, investments, etc.). Insert into Excel.

### 5b — Current Assets
For each line below, check if a **note number** is referenced beside the balance sheet figure. If so, navigate to that note before extracting:

| Excel Row | PDF Source / Logic |
|---|---|
| Amount Due from Related Companies | Look for "Amount due from related companies" or "Amount due from a related party" in the note |
| Other Receivables | From the Trade/Other Receivables note: **total Other Receivables − Related Company amount − Deposits − Prepayments** |
| Others (Deposits & Prepayments) | "Deposits and prepayments" line in the receivables note |
| Stock (Inventories) | "Inventories" on face of balance sheet |
| Cash and Cash at Bank | "Cash and bank balances" / "Cash and cash equivalents" |

### 5c — Equity
Extract total equity and sub-components (share capital, retained earnings, reserves). Insert into Excel.

### 5d — Non-Current Liabilities
Extract total non-current liabilities and sub-lines (term loans, hire purchase payables, deferred tax). Insert into Excel.

### 5e — Current Liabilities
Extract total current liabilities and sub-lines (trade payables, other payables, bank borrowings). Insert into Excel.

---

## Phase 6 — Keyword Flexibility

The code must support a **KeywordMap** sheet in the Excel file with columns:

| Column A | Column B | Column C |
|---|---|---|
| Template Row Label | Primary Keyword(s) | Fallback Keyword(s) |

- At runtime, the code loads all rows from `KeywordMap` before scanning the PDF.
- When searching for a value, it tries **Primary Keywords** first, then **Fallback Keywords**.
- If a keyword from the PDF matches any entry in the map, that value is routed to the corresponding template row.
- Users can add new rows to `KeywordMap` in Excel to handle a new auditor's terminology without touching any Python source.

---

## Phase 7 — Output & Credit Flag Summary

After filling the Excel, append a **Credit Analyst Summary** section (separate sheet tab: `CreditFlag`) with:

1. **Opinion** — classification from Phase 1
2. **True and Fair View** — present / absent
3. **Auditor Blacklist Check** — clean / flagged / inconclusive
4. **Statutory Declaration** — valid / flagged
5. **Net Profit vs Total Comprehensive Income** — match / mismatch
6. **Overall Recommendation** — `PROCEED` / `ESCALATE` / `DECLINE`
   - `DECLINE` if opinion is ADVERSE or DISCLAIMED
   - `ESCALATE` if QUALIFIED, or any flag above is flagged/mismatch
   - `PROCEED` if all checks pass

---

## Implementation Notes (for when coding begins)

- Use `pdfplumber` for PDF text extraction (already a project dependency).
- Use `openpyxl` for Excel read/write (already a project dependency).
- Keyword matching must be **case-insensitive** and handle common OCR noise (extra spaces, line breaks mid-phrase).
- Every extracted value must record its **source page number** for audit trail.
- Different reports may use different years' columns — always detect the **most recent year column** from the header row of each financial table.
- Where a value cannot be found, write `NOT FOUND` in the cell (never leave it blank silently).
