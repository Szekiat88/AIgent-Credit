"""
Gemini 2.5 Flash-Lite extraction engine.

All text understanding — audit opinion, firm details, financial figures — runs
through a single LLM. No hardcoded keyword lists in this file.

4 API calls per PDF:
  1. audit_section    → opinion, firm, accountant, dates, statutory decl
  2. income_statement → P&L line items
  3. balance_sheet    → assets, liabilities, equity
  4. notes            → interest & staff cost breakdowns (best-effort)

Results are cached in .llm_cache/ so re-runs cost nothing.
"""

import json
import re
import textwrap
from typing import Optional

import google.generativeai as genai

from utils import json_cache
from pipeline.page_classifier import classify_pages, text_for_sections, section_summary

_DEFAULT_MODEL = "gemini-2.5-flash-lite"

# ---------------------------------------------------------------------------
# System prompt (cached by Gemini via system_instruction)
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = textwrap.dedent("""\
    You are an expert Malaysian financial report analyst.
    You receive OCR-extracted text from scanned auditor report PDFs.
    The text may contain OCR errors, broken lines, or Malay/English mixed content.

    Your job is to extract structured information and return ONLY valid JSON.

    Key rules:
    - Return ONLY a JSON object, no prose, no markdown fences.
    - Use null (not "null" string) when a field is not found.
    - Monetary values: return as plain numbers (e.g. 27983932, not "27,983,932").
    - Scale detection: if the report header says "RM'000" or "in thousands",
      multiply ALL monetary amounts by 1000 before returning.
      If it says "RM million" or "in millions", multiply by 1000000.
    - For losses or negative equity, use negative numbers (e.g. -500000).
    - Malaysian reports often use both English and Malay section names.
    - The signing auditor's MIA/AF number looks like "AF 002208" or "MIA No. 1234".
""")


class GeminiExtractor:
    """Orchestrates 4 Gemini calls to extract all data from a PDF."""

    def __init__(
        self,
        pages: list,
        target_year: str,
        hints: dict,
        api_key: str,
        model: str = _DEFAULT_MODEL,
    ):
        self.pages = pages
        self.target_year = target_year
        self.hints = hints          # from Excel KeywordMap — user domain hints
        self.pdf_hash_val = ""      # set by extract_all()
        self._token_usage: dict = {}  # section → {prompt_tokens, output_tokens, total_tokens}

        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(
            model_name=model,
            system_instruction=_SYSTEM_PROMPT,
        )
        self._page_map = classify_pages(pages)
        print(f"  Page map: {section_summary(self._page_map)}")

    # ------------------------------------------------------------------
    # public entry point
    # ------------------------------------------------------------------

    def extract_all(self, pdf_hash_val: str = "") -> dict:
        """
        Run all 4 extraction calls. Returns:
          {
            "audit_checks":   {...},
            "financial_data": {field_name: {"value": float, "confidence": float}, ...}
          }
        """
        self.pdf_hash_val = pdf_hash_val

        # Audit: always use first 15 pages — Malaysian audit reports are at the front
        audit_text = self._first_n_pages_text(15)

        is_text = text_for_sections(self.pages, ["income_statement"], self._page_map)
        bs_text = text_for_sections(self.pages, ["balance_sheet"], self._page_map)

        # Notes: include all "notes" pages PLUS any "other" pages that come after the
        # first notes page — this captures continuation note pages (e.g. Note 22, 23)
        # that the classifier didn't explicitly tag as "notes".
        note_pages_list = sorted(
            p["page"] for p in self.pages if self._page_map.get(p["page"]) == "notes"
        )
        if note_pages_list:
            min_notes_page = note_pages_list[0]
            notes_parts = []
            for p in self.pages:
                t = self._page_map.get(p["page"])
                if t == "notes" or (t == "other" and p["page"] >= min_notes_page):
                    notes_parts.append(f"<<PAGE {p['page']}>>\n{p['text']}")
            notes_text = "\n\n".join(notes_parts)
        else:
            notes_text = text_for_sections(self.pages, ["notes"], self._page_map)

        # fallback: if classifier found nothing useful, send full text
        if not is_text.strip() or not bs_text.strip():
            all_text = self._full_text()
            if not is_text.strip():
                is_text = all_text
            if not bs_text.strip():
                bs_text = all_text

        print("  [Gemini] Call 1/4 — audit section")
        audit_raw = self._call("audit", audit_text, self._audit_prompt(audit_text))

        print("  [Gemini] Call 2/4 — income statement")
        is_raw = self._call("income_statement", is_text,
                            self._income_statement_prompt(is_text))

        print("  [Gemini] Call 3/4 — balance sheet")
        bs_raw = self._call("balance_sheet", bs_text,
                            self._balance_sheet_prompt(bs_text))

        print("  [Gemini] Call 4/4 — notes (best-effort)")
        notes_raw = self._call("notes", notes_text,
                               self._notes_prompt(notes_text)) if notes_text.strip() else {}

        audit_checks = self._build_audit_checks(audit_raw)
        cur_fin, pri_fin, detected_year, prior_year, \
            year_end_date, prior_year_end_date = self._build_financial_data(
                is_raw, bs_raw, notes_raw
            )

        # Prefer the explicitly detected year over the hint
        resolved_year  = detected_year  or self.target_year or ""
        resolved_prior = prior_year or ""

        return {
            "audit_checks":          audit_checks,
            "financial_data":        cur_fin,            # current year
            "prior_financial_data":  pri_fin,            # prior year
            "detected_year":         resolved_year,
            "prior_year":            resolved_prior,
            "year_end_date":         year_end_date,      # e.g. "31/12/2022"
            "prior_year_end_date":   prior_year_end_date,
            "token_usage":           self._token_usage,
        }

    # ------------------------------------------------------------------
    # Gemini call with caching
    # ------------------------------------------------------------------

    def _call(self, section: str, text: str, prompt: str) -> dict:
        """Call Gemini or return cached result."""
        if self.pdf_hash_val:
            cached = json_cache.load(self.pdf_hash_val, section)
            # Only use cache if it has at least one non-null value — an empty {}
            # or all-null dict means the previous call failed and should be retried.
            if cached is not None and any(v is not None for v in cached.values()):
                print(f"    (cached)")
                return cached
            elif cached is not None:
                print(f"    (cache empty/null — will retry Gemini call)")

        if not text.strip():
            return {}

        try:
            response = self._model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json",
                    temperature=0.0,
                ),
            )
            raw_text = response.text.strip()
            # Strip any accidental markdown fences
            raw_text = re.sub(r'^```(?:json)?\s*', '', raw_text)
            raw_text = re.sub(r'\s*```$', '', raw_text)
            data = json.loads(raw_text)
            # Capture token usage metadata
            usage = getattr(response, 'usage_metadata', None)
            if usage:
                self._token_usage[section] = {
                    "prompt_tokens":  getattr(usage, 'prompt_token_count', 0) or 0,
                    "output_tokens":  getattr(usage, 'candidates_token_count', 0) or 0,
                    "total_tokens":   getattr(usage, 'total_token_count', 0) or 0,
                }
        except json.JSONDecodeError as e:
            print(f"    [WARN] JSON parse error for {section}: {e}")
            data = {}
        except Exception as e:
            print(f"    [WARN] Gemini call failed for {section}: {e}")
            data = {}

        # Only cache successful non-empty responses
        if self.pdf_hash_val and data:
            json_cache.save(self.pdf_hash_val, section, data)
        return data

    # ------------------------------------------------------------------
    # Prompt builders
    # ------------------------------------------------------------------

    def _hint_lines(self, field_names: list) -> str:
        """Inject user-defined keyword hints into the prompt."""
        lines = []
        for fname in field_names:
            entry = self.hints.get(fname, {})
            extra = entry.get("primary", []) + entry.get("fallback", [])
            if extra:
                lines.append(f"  - {fname} may also be labelled: {', '.join(extra)}")
        return ("\n\nUser-defined label hints:\n" + "\n".join(lines)) if lines else ""

    def _audit_prompt(self, text: str) -> str:
        year_hint = f"The financial year under review is {self.target_year}." if self.target_year else ""
        return textwrap.dedent(f"""\
            {year_hint}

            Extract audit information from the OCR text below and return JSON
            matching this schema exactly:

            {{
              "opinion": "UNQUALIFIED" | "QUALIFIED" | "ADVERSE" | "DISCLAIMED",
              "true_and_fair": true | false,
              "opinion_evidence": "verbatim sentence that shows the opinion",
              "firm_name": "auditing firm name (e.g. JC & ASSOCIATES PLT)",
              "accountant_name": "name of the INDIVIDUAL signing accountant (not the firm)",
              "mia_number": "AF/MIA number e.g. AF 002208",
              "signature_date": "date auditor signed the independent auditors report",
              "directors_report_date": "date the directors SIGNED the directors report",
              "statement_by_directors_date": "date from statement by directors",
              "statutory_declaration": {{
                "cop_name": "Commissioner of Oaths name (the officer BEFORE WHOM the declaration is made)",
                "cop_date": "date of statutory declaration",
                "status": "VALID" | "FLAGGED",
                "notes": "describe any missing or inconsistent items, or empty string"
              }}
            }}

            OCR ARTIFACT RULES (very important — scanned documents have errors):
            - "Pate:" or "P<date>:" is OCR noise for "Date:" — treat it as a signing date
            - Garbled digits like "2.9 OCT 202%" mean "29 OCT 2024" — interpret them
            - Side-by-side text "FIRM NAME   PERSON NAME" on the same line means both appear;
              the person name is the INDIVIDUAL accountant (e.g. "JC & ASSOCIATES  CHU WOOI SIONG")
            - The auditor's signature block looks like:
                FIRM NAME      PERSON NAME
                AF XXXXXX      MEMBER_NO J
                Chartered Accountants   Chartered Accountant
                Date: DD Month YYYY
            - directors_report_date is the date directors SIGNED the report (near "Signed on behalf"
              or "Date:" at the END of the Directors Report section — NOT the financial year end date)
            - The declarant in the statutory declaration (e.g. "I, Lim Jun Yeong, ... do solemnly declare")
              is NOT the Commissioner of Oaths. The COP is the officer "Before me," line.

            Classification rules for opinion:
            - UNQUALIFIED: "true and fair view", "present fairly", "unqualified opinion"
            - QUALIFIED: "except for", "subject to", "qualified opinion"
            - ADVERSE: "adverse opinion", "does not give a true and fair view"
            - DISCLAIMED: "disclaimer of opinion", "unable to form an opinion"

            Statutory declaration status:
            - VALID if COP name and date are both present and year matches audit year
            - FLAGGED otherwise (missing fields or year mismatch)

            Text to analyse:
            {text[:22000]}
        """)

    def _income_statement_prompt(self, text: str) -> str:
        year_hint = (f"The current (most recent) financial year is {self.target_year}.") \
                    if self.target_year else \
                    "Extract figures for both the most recent and prior financial years."
        hints = self._hint_lines([
            "Revenue", "Cost of Sales", "Gross Profit", "Depreciation",
            "Staff Cost", "Other Operating Expenses", "Other Income",
            "Interest / Finance Expenses", "Taxes",
            "Net Profit (Loss) for the Year",
        ])
        schema = textwrap.dedent("""\
            {
              "year": "YYYY",
              "year_end_date": "DD/MM/YYYY",
              "scale_note": "e.g. RM'000 detected, multiplied by 1000",
              "revenue": number | null,
              "cost_of_sales": number | null,
              "gross_profit": number | null,
              "admin_and_operating_expenses": number | null,
              "depreciation": number | null,
              "staff_cost": number | null,
              "other_operating_expenses": number | null,
              "other_income": number | null,
              "interest_expenses": number | null,
              "taxes": number | null,
              "net_profit": number | null,
              "total_comprehensive_income": number | null
            }""")
        return textwrap.dedent(f"""\
            {year_hint}

            Extract income statement figures from the OCR text below.
            The report shows TWO years side by side (current year and prior year).
            Extract BOTH years.

            Check the report header for scale: if "RM'000" or "in thousands",
            multiply every amount by 1000. If "RM million", multiply by 1000000.

            Return JSON with this exact structure:
            {{
              "current_year": {schema},
              "prior_year": {schema}
            }}

            Rules (apply to both years):
            - Extract ONLY from the "Statement of Comprehensive Income" or
              "Statement of Profit or Loss" section. Do NOT use numbers from the
              Statement of Cash Flows, notes, or any other section.
            - SIGN RULE (critical): ALL monetary amounts must be returned as POSITIVE
              numbers. Parentheses () in a Malaysian income statement mean the item is
              an expense/deduction — return the ABSOLUTE VALUE. This applies to:
              cost_of_sales, admin_and_operating_expenses, staff_cost, depreciation,
              other_operating_expenses, interest_expenses, taxes. Never return negative
              values for these fields even if the PDF shows them in parentheses.
            - Revenue and gross_profit are positive numbers.
            - net_profit is positive for profit, negative for a net loss.
            - If gross profit is not explicitly stated, compute revenue - cost_of_sales.
            - IMPORTANT — operating expenses classification (choose ONE case):
              CASE A: ONE combined line "Administrative and other operating expenses"
                (the label itself says "and other") → admin_and_operating_expenses = that
                amount. Set depreciation, staff_cost, other_operating_expenses to null.
              CASE B: Explicit "Depreciation" AND/OR "Staff cost"/"Employee benefits"
                lines on the IS face → extract each individually; admin_and_operating_expenses = null.
              CASE C: "Administrative expenses" (labeled exactly as such, separate from
                "Other operating expenses") + a separate "Other operating expenses" line.
                This is the TWO-LINE pattern common in Malaysian tech/services reports.
                → staff_cost = "Administrative expenses" value
                → other_operating_expenses = "Other operating expenses" value
                → admin_and_operating_expenses = null
                Do NOT sum them — they are already separate.
              CASE D: Multiple functional lines like "Administration expenses" + "Distribution
                costs" + "Selling expenses" (no generic "Other operating expenses" label)
                → SUM them all into admin_and_operating_expenses; breakdown from notes.
            - "interest_expenses": take ONLY from the P&L face (labelled "Finance costs"
              or "Interest expense"). Do NOT use cash flow figures like "Interest paid".
            - "total_comprehensive_income" may equal net_profit; include if separately stated.
            - "year_end_date": the exact financial year end date in DD/MM/YYYY format
              (e.g. "31/12/2022", "30/04/2024"). Read from the statement header or title.
            {hints}

            Text to analyse:
            {text[:15000]}
        """)

    def _balance_sheet_prompt(self, text: str) -> str:
        year_hint = (f"The current (most recent) financial year is {self.target_year}.") \
                    if self.target_year else \
                    "Extract figures for both the most recent and prior financial years."
        hints = self._hint_lines([
            "Non Current Asset", "Current Asset", "Trade Receivables",
            "Other Receivables and Prepayments", "Amount Due from Directors",
            "Amount Due from Related Companies", "Stock", "Cash & Cash At Bank",
            "Total Asset", "Non Current Liabilities", "Current Liabilities",
            "Trade Payables", "Amount Due to Director",
            "Total Liabilities", "Equity", "Total Liabilities and Equity",
        ])
        schema = textwrap.dedent("""\
            {
              "year": "YYYY",
              "scale_note": "e.g. RM'000 detected, multiplied by 1000",
              "non_current_assets": number | null,
              "current_assets": number | null,
              "trade_receivables": number | null,
              "other_receivables_face": number | null,
              "other_receivables_and_prepayments": number | null,
              "other_receivables": number | null,
              "amount_due_from_directors": number | null,
              "amount_due_from_related_companies": number | null,
              "deposits_and_prepayments": number | null,
              "inventories": number | null,
              "cash_and_cash_equivalents": number | null,
              "total_assets": number | null,
              "non_current_liabilities": number | null,
              "nca_bank_borrowings": number | null,
              "nca_hire_purchase": number | null,
              "nca_other_payables": number | null,
              "deferred_tax_liabilities": number | null,
              "current_liabilities": number | null,
              "trade_payables": number | null,
              "other_payables_face": number | null,
              "other_payables_and_accruals": number | null,
              "cl_other_payables": number | null,
              "tax_payable": number | null,
              "amount_due_to_directors": number | null,
              "amount_due_to_related_companies": number | null,
              "cl_others": number | null,
              "cl_bank_borrowings": number | null,
              "cl_hire_purchase": number | null,
              "contract_liabilities": number | null,
              "total_liabilities": number | null,
              "total_equity": number | null,
              "share_capital": number | null,
              "retained_earnings": number | null,
              "revaluation_reserve": number | null,
              "total_liabilities_and_equity": number | null
            }""")
        return textwrap.dedent(f"""\
            {year_hint}

            Extract balance sheet figures from the OCR text.
            The report shows TWO years side by side. Extract BOTH years.
            Check the report header for scale: if "RM'000" or "in thousands",
            multiply every amount by 1000. If "RM million", multiply by 1000000.

            Return JSON with this exact structure:
            {{
              "current_year": {schema},
              "prior_year": {schema}
            }}

            Rules (apply to both years):
            - All asset values are positive.
            - All liability and equity values are positive.
            - retained_earnings may be negative (accumulated losses).

            RECEIVABLES (critical — many reports combine trade + non-trade on BS face):
            - "trade_receivables": use the TRADE sub-total from the receivables note (e.g.
              Note 10), which is sum of third-party + related-party TRADE receivables only.
              If the BS shows a combined "Trade and other receivables" line, do NOT use
              that combined figure — go to the note for the trade-only sub-total.
            - "other_receivables_face": ALL current assets that are NOT trade receivables,
              inventories, cash/bank balances, amount_due_from_directors, OR
              amount_due_from_related_companies. Add together: deposits, prepayments,
              current tax assets (if receivable), development costs under development
              (if a CA line), and any other miscellaneous current asset lines on the BS
              face. This is the "Others" bucket for the template row.
            - "amount_due_from_directors": look in receivables note under "Amount owing
              by a director" or "Amount due from directors".
            - "amount_due_from_related_companies": look in receivables note under "Amount
              owing by related parties" or "Amount due from related companies" (NON-TRADE
              only — do NOT use the trade-related-party receivables here).

            PAYABLES (same pattern — combine line on BS, breakdown in note):
            - "trade_payables": use the TRADE sub-total from the payables note (e.g. Note
              16), which is trade payables to third parties only. Do NOT use the combined
              "Trade and other payables" BS line total.
            - "other_payables_face": the non-trade payables subtotal from the payables note
              (includes other payables, accruals, SST, amount owing to director/related
              companies). This is the NON-TRADE total from the note.
            - "amount_due_to_directors": look in payables note under "Amount owing to a
              director", "Amount due to directors", or "Director loan". Often in the
              non-trade section of the payables note.
            - "tax_payable": income tax payable shown as a SEPARATE CL line on the BS
              face (NOT inside the trade-and-other payables note).
            - "contract_liabilities": separately stated CL line "Contract liabilities" or
              "Deferred revenue" on the BS face (Note 17 or similar). Typically represents
              deposits received from customers for services not yet rendered.

            BORROWINGS:
            - "nca_bank_borrowings": NCA "Loans and borrowings", "Term loans",
              "Bank loans", "Bank borrowings" (non-current portion only).
            - "nca_hire_purchase": NCA "Hire purchase", "Finance lease", "Lease
              liabilities" (non-current).
            - "nca_other_payables" / "deferred_tax_liabilities": deferred tax in NCA.
            - "cl_bank_borrowings": current "Loans and borrowings", bank overdraft,
              trust receipts, revolving credit, bankers acceptance, short-term loans,
              current portion of term loans. Include ALL short-term bank facilities
              due within 12 months. Do NOT include lease liabilities here.
            - "cl_hire_purchase": current "Hire purchase payable", "Finance lease
              liabilities", "Lease liabilities" (current portion only).

            OTHER:
            - "cash_and_cash_equivalents": include cash, bank balances AND fixed deposits.
            - "other_receivables_and_prepayments": ONLY if a SINGLE combined BS line
              already includes directors; otherwise leave null.
            {hints}

            Text to analyse:
            {text[:18000]}
        """)

    def _notes_prompt(self, text: str) -> str:
        year_hint = f"Year: {self.target_year}." if self.target_year else ""
        return textwrap.dedent(f"""\
            {year_hint}

            From the notes to financial statements, extract breakdowns for:
            1. Finance costs / interest expenses (split by type)
            2. Staff costs / employee benefits (split by component)
            3. Other receivables note (Note 9 or similar) — breakdown of receivable types
            4. Other payables note (Note 18 or similar) — breakdown of payable types
            5. Note 21 or "Profit before taxation" note — items charged to P&L
               (depreciation, directors' remuneration, staff costs)

            Return JSON:
            {{
              "interest_breakdown": {{
                "bank_overdraft": number | null,
                "bank_acceptance": number | null,
                "hire_purchase": number | null,
                "term_loan": number | null,
                "revolving_credit": number | null,
                "other_interest": number | null,
                "total": number | null
              }},
              "staff_cost_breakdown": {{
                "directors_emoluments": number | null,
                "directors_fees": number | null,
                "wages_salaries": number | null,
                "epf": number | null,
                "socso": number | null,
                "eis": number | null,
                "other_staff_costs": number | null,
                "total": number | null
              }},
              "note9_breakdown": {{
                "third_party_receivables": number | null,
                "related_company_receivables": number | null,
                "deposits": number | null,
                "prepayments": number | null,
                "total": number | null
              }},
              "note18_breakdown": {{
                "other_payables": number | null,
                "accruals": number | null,
                "deposits_received": number | null,
                "total": number | null
              }},
              "note21_breakdown": {{
                "current_year": {{
                  "depreciation": number | null,
                  "directors_remuneration": number | null,
                  "staff_costs": number | null
                }},
                "prior_year": {{
                  "depreciation": number | null,
                  "directors_remuneration": number | null,
                  "staff_costs": number | null
                }}
              }}
            }}

            Rules:
            - Apply the same scale as the main statements (RM'000 → multiply by 1000).
            - If a breakdown is not present in the notes, return null for all sub-fields.
            - "note9_breakdown": look for "Other receivables", "Other receivables, deposits
              and prepayments", or a combined "Trade and Other Receivables" note.
              CRITICAL: extract ONLY the NON-TRADE portion. If the note has a TRADE
              section (third-party trade receivables, related-party trade receivables),
              SKIP those — extract only the non-trade sub-items:
              "third_party_receivables" = non-trade misc receivables from third parties
                (deposits, current tax assets, dev costs, other misc items — NOT trade);
              "related_company_receivables" = "Amount owing by related parties" (non-trade
                only, e.g. advances/loans to related parties that are NOT trade in nature);
              "deposits" = deposits paid to third parties;
              "prepayments" = prepayments.
              Extract sub-items for the current year only.
            - "note18_breakdown": look for "Other payables and accruals" or "Other payables".
              Extract sub-items for the current year only.
            - "note21_breakdown": look for "Profit before taxation is arrived at after
              charging:" or similar. The note shows TWO year columns — extract BOTH.
              "directors_remuneration" and "staff_costs" are separate — do not combine them.

            Text to analyse:
            {text[:35000]}
        """)

    # ------------------------------------------------------------------
    # Response → domain object converters
    # ------------------------------------------------------------------

    def _build_audit_checks(self, raw: dict) -> dict:
        """Convert Gemini audit JSON to the format expected by excel_filler."""
        stat = raw.get("statutory_declaration") or {}
        return {
            "opinion": raw.get("opinion") or "NOT FOUND",
            "true_and_fair": bool(raw.get("true_and_fair")),
            "opinion_evidence": raw.get("opinion_evidence") or "",
            "auditor_section_confidence": 90.0 if raw else 0.0,
            "firm_name": raw.get("firm_name") or "NOT FOUND",
            "accountant_name": raw.get("accountant_name") or "NOT FOUND",
            "mia_number": raw.get("mia_number") or "NOT FOUND",
            "signature_date": raw.get("signature_date") or "NOT FOUND",
            "signature_dates": {
                "Directors Report": raw.get("directors_report_date") or "NOT FOUND",
                "Statement by Directors": raw.get("statement_by_directors_date") or "NOT FOUND",
                "Auditors Report": raw.get("signature_date") or "NOT FOUND",
            },
            "signature_consistency": self._check_sig_consistency(raw),
            "statutory_declaration": {
                "cop_name": stat.get("cop_name") or "NOT FOUND",
                "cop_date": stat.get("cop_date") or "NOT FOUND",
                "stamp_present": False,
                "date_consistent": stat.get("status") == "VALID",
                "status": stat.get("status") or "FLAGGED",
                "notes": stat.get("notes") or "",
            },
        }

    @staticmethod
    def _check_sig_consistency(raw: dict) -> str:
        dr = raw.get("directors_report_date") or ""
        sd = raw.get("statement_by_directors_date") or ""
        audit = raw.get("signature_date") or ""
        director_dates = [d for d in [dr, sd] if d]
        if not director_dates:
            return "INSUFFICIENT DATA"
        if len(set(d.lower() for d in director_dates)) > 1:
            return f"INCONSISTENT — Directors' Report: {dr}, Statement by Directors: {sd}"
        note = f" (Auditors signed: {audit})" if audit else ""
        return f"CONSISTENT{note}"

    @staticmethod
    def _reconcile_bs_scale(is_data: dict, bs_data: dict) -> dict:
        """
        If IS detected no scaling but BS applied ×1000, the BS was wrong.
        Divide all numeric BS fields by 1000 to match the IS scale.
        This handles PDFs where the IS header says plain RM but the BS
        header says RM'000, causing Gemini to multiply the BS inconsistently.
        """
        if not is_data or not bs_data:
            return bs_data
        is_note = (is_data.get("scale_note") or "").lower()
        bs_note = (bs_data.get("scale_note") or "").lower()
        if "no multiplication" in is_note and "multiplied by 1000" in bs_note:
            corrected = {}
            for k, v in bs_data.items():
                corrected[k] = v / 1000 if isinstance(v, (int, float)) else v
            corrected["scale_note"] = bs_note + " [CORRECTED ÷1000 to match IS scale]"
            print(f"    [Scale] BS scale mismatch detected — divided all BS values by 1000")
            return corrected
        return bs_data

    def _build_financial_data(self, is_raw: dict, bs_raw: dict,
                               notes_raw: dict) -> tuple:
        """
        Convert Gemini extraction JSON for both years.
        Returns (current_fin_data, prior_fin_data, current_year_str, prior_year_str).
        Handles both new nested format {"current_year": {...}, "prior_year": {...}}
        and legacy flat format for backward compatibility with tests.
        """
        # Unpack nested format (new) vs flat (legacy / tests)
        if "current_year" in is_raw or "prior_year" in is_raw:
            is_cur = is_raw.get("current_year") or {}
            is_pri = is_raw.get("prior_year") or {}
        else:
            is_cur = is_raw
            is_pri = {}

        if "current_year" in bs_raw or "prior_year" in bs_raw:
            bs_cur = bs_raw.get("current_year") or {}
            bs_pri = bs_raw.get("prior_year") or {}
        else:
            bs_cur = bs_raw
            bs_pri = {}

        # Scale reconciliation: if IS detected full RM but BS detected RM'000,
        # the BS multiplied when it shouldn't have — undo the multiplication.
        bs_cur = self._reconcile_bs_scale(is_cur, bs_cur)
        bs_pri = self._reconcile_bs_scale(is_pri, bs_pri)

        # Note 21 breakdown — may be nested (new) or flat (legacy)
        n21_raw = notes_raw.get("note21_breakdown") or {}
        if "current_year" in n21_raw:
            n21_cur = n21_raw.get("current_year") or {}
            n21_pri = n21_raw.get("prior_year") or {}
        else:
            n21_cur = n21_raw  # legacy flat format
            n21_pri = {}

        cur_fin = self._make_fin_data(is_cur, bs_cur, notes_raw, n21_cur)
        pri_fin = self._make_fin_data(is_pri, bs_pri, {}, n21_pri)

        return (
            cur_fin,
            pri_fin,
            is_cur.get("year") or "",
            is_pri.get("year") or "",
            is_cur.get("year_end_date") or "",
            is_pri.get("year_end_date") or "",
        )

    def _make_fin_data(self, is_data: dict, bs_data: dict,
                       notes_raw: dict, n21: dict) -> dict:
        """
        Build one year's financial_data dict from IS, BS and notes fragments.
        notes_raw is used for Note 9/18 sub-details (current year only).
        n21 is the already-unpacked note21 data for this specific year.
        """
        conf = 90.0 if is_data or bs_data else 0.0

        def v(val, confidence: float = conf) -> dict:
            return {
                "value": float(val) if val is not None else None,
                "confidence": confidence,
            }

        def _sum(*vals) -> Optional[float]:
            parts = [float(x) for x in vals if x is not None]
            return sum(parts) if parts else None

        n9  = notes_raw.get("note9_breakdown") or {}
        n18 = notes_raw.get("note18_breakdown") or {}

        # ── IS: handle combined admin expense line ─────────────────────────────
        admin_combined = is_data.get("admin_and_operating_expenses")

        # When the IS uses a combined expense line, always prefer Note 21 for
        # depreciation and staff cost — any IS-face values came from notes pages
        # being mixed into the IS text by the classifier.
        if admin_combined is not None and n21:
            is_dep   = n21.get("depreciation")
            n21_dir  = n21.get("directors_remuneration")
            n21_wages = n21.get("staff_costs")
            is_staff = _sum(n21_dir, n21_wages)
        else:
            is_dep   = is_data.get("depreciation")
            if is_dep is None:
                is_dep = n21.get("depreciation")
            is_staff = is_data.get("staff_cost")
            if is_staff is None:
                is_staff = _sum(n21.get("directors_remuneration"), n21.get("staff_costs"))

        is_ooex = is_data.get("other_operating_expenses")
        if is_ooex is None and admin_combined is not None:
            dep   = is_dep   or 0.0
            staff = is_staff or 0.0
            is_ooex = float(admin_combined) - dep - staff if (dep or staff) \
                      else float(admin_combined)

        # ── BS: Other Receivables and Prepayments ────────────────────────────
        # ore_combined = all CA except trade, inventories, cash
        # = other_receivables_face (misc CA) + directors + related companies
        ore_combined = bs_data.get("other_receivables_and_prepayments")
        if ore_combined is None:
            ore_combined = _sum(
                bs_data.get("other_receivables_face"),
                bs_data.get("amount_due_from_directors"),
                bs_data.get("amount_due_from_related_companies"),
            )
        # Fallback: derive from CA balance check (CA - trade - inventories - cash)
        if ore_combined is None:
            ca  = bs_data.get("current_assets")
            tr  = bs_data.get("trade_receivables")
            inv = bs_data.get("inventories")
            cs  = bs_data.get("cash_and_cash_equivalents")
            if ca is not None and tr is not None and cs is not None:
                computed = float(ca) - float(tr) - (float(inv) if inv else 0.0) - float(cs)
                if computed > 0:
                    ore_combined = computed

        other_recv_sub = bs_data.get("other_receivables") or n9.get("third_party_receivables")
        amt_rel_recv   = bs_data.get("amount_due_from_related_companies") \
                         or n9.get("related_company_receivables")

        # dep_prep maps to the "Others" row = other_receivables_face (misc CA bucket)
        dep_prep = bs_data.get("deposits_and_prepayments")
        if dep_prep is None:
            # other_receivables_face = all CA items excluding trade/directors/related/cash/inventories
            dep_prep = bs_data.get("other_receivables_face")
        if dep_prep is None and n9:
            dep_prep = _sum(n9.get("deposits"), n9.get("prepayments"))

        # ── BS: NCA Other Payables ────────────────────────────────────────────
        nca_other = bs_data.get("nca_other_payables") or bs_data.get("deferred_tax_liabilities")

        # ── BS: Other Payables & Accruals ────────────────────────────────────
        # other_payables_face is the non-trade subtotal from the note, which already
        # includes amount_due_to_directors in Mandrill-style reports. Do NOT add
        # directors again. Add tax_payable and contract_liabilities (CL residuals).
        op_combined = bs_data.get("other_payables_and_accruals")
        tax_pay = bs_data.get("tax_payable")
        if op_combined is None:
            op_combined = _sum(
                bs_data.get("other_payables_face"),
                tax_pay,
                bs_data.get("contract_liabilities"),
            )

        cl_op = bs_data.get("cl_other_payables") or n18.get("other_payables")

        cl_others_val = bs_data.get("cl_others")
        if cl_others_val is None:
            cl_others_val = _sum(
                n18.get("accruals"),
                n18.get("deposits_received"),
                tax_pay,
            )

        data = {
            # Income Statement
            "Revenue":                           v(is_data.get("revenue")),
            "Cost of Sales":                     v(is_data.get("cost_of_sales")),
            "Gross Profit":                      v(is_data.get("gross_profit")),
            "Depreciation":                      v(is_dep),
            "Staff Cost":                        v(is_staff),
            "Other Operating Expenses":          v(is_ooex),
            "Other Income":                      v(is_data.get("other_income")),
            "Interest / Finance Expenses":       v(is_data.get("interest_expenses")),
            "Taxes":                             v(is_data.get("taxes")),
            "Net Profit (Loss) for the Year":    v(is_data.get("net_profit")),

            # Balance Sheet — Assets
            "Non Current Asset":                         v(bs_data.get("non_current_assets")),
            "Current Asset":                             v(bs_data.get("current_assets")),
            "Trade Receivables":                         v(bs_data.get("trade_receivables")),
            "Other Receivables and Prepayments":         v(ore_combined),
            "Other Receivables":                         v(other_recv_sub),
            "Amount Due from Directors":                 v(bs_data.get("amount_due_from_directors")),
            "Amount Due from Related Companies":         v(amt_rel_recv),
            "Others":                                    v(dep_prep),
            "Stock":                                     v(bs_data.get("inventories")),
            "Cash & Cash At Bank":                       v(bs_data.get("cash_and_cash_equivalents")),
            "Total Asset":                               v(bs_data.get("total_assets")),

            # Balance Sheet — Liabilities
            "Non Current Liabilities":          v(bs_data.get("non_current_liabilities")),
            "NCA Bank Borrowings":              v(bs_data.get("nca_bank_borrowings")),
            "NCA Hire Purchase":                v(bs_data.get("nca_hire_purchase")),
            "NCA Other Payables":               v(nca_other),
            "Current Liabilities":              v(bs_data.get("current_liabilities")),
            "Trade Payables":                   v(bs_data.get("trade_payables")),
            "Other Payables & Accruals":        v(op_combined),
            "CL Other Payables":                v(cl_op),
            "Amount Due to Director":           v(bs_data.get("amount_due_to_directors")),
            "Amount Due to Related Companies":  v(bs_data.get("amount_due_to_related_companies")),
            "CL Others":                        v(cl_others_val),
            "CL Bank Borrowings":               v(bs_data.get("cl_bank_borrowings")),
            "CL Hire Purchase":                 v(bs_data.get("cl_hire_purchase")),
            "Total Liabilities":                v(bs_data.get("total_liabilities")),

            # Equity
            "Equity":                           v(bs_data.get("total_equity")),
            "Share Capital":                    v(bs_data.get("share_capital")),
            "Retained Earnings":                v(bs_data.get("retained_earnings")),
            "Revaluation Reserve":              v(bs_data.get("revaluation_reserve")),
            "Total Liabilities and Equity":     v(bs_data.get("total_liabilities_and_equity")),
        }

        # TCI validation flag (current year only — TCI rarely in prior year notes)
        net = data["Net Profit (Loss) for the Year"]["value"]
        tci_val = is_data.get("total_comprehensive_income")
        if net is not None and tci_val is not None:
            data["Net Profit (Loss) for the Year"]["validated_vs_tci"] = (
                abs(net - float(tci_val)) < max(1.0, abs(net) * 0.001)
            )

        return data

    def _full_text(self) -> str:
        return "\n\n".join(
            f"<<PAGE {p['page']}>>\n{p['text']}" for p in self.pages
        )

    def _first_n_pages_text(self, n: int) -> str:
        return "\n\n".join(
            f"<<PAGE {p['page']}>>\n{p['text']}"
            for p in self.pages[:n]
        )
