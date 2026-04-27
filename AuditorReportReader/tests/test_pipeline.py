"""
Integration test for the Gemini-based pipeline.

Uses a mock Gemini response so no real API key is needed.
Run with:  python test_pipeline.py
"""

import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))  # AuditorReportReader/
import json
import tempfile
import shutil
import unittest
from unittest.mock import patch, MagicMock

# ── stub google.generativeai before it tries to contact the internet ──────────
_mock_genai = MagicMock()
_mock_genai.GenerationConfig = dict
_mock_model = MagicMock()

# Realistic Gemini responses
_AUDIT_RESPONSE = {
    "opinion": "UNQUALIFIED",
    "true_and_fair": True,
    "opinion_evidence": "In our opinion the financial statements give a true and fair view",
    "firm_name": "JC & ASSOCIATES PLT",
    "accountant_name": "CHU WOOI SIONG",
    "mia_number": "AF 002208",
    "signature_date": "15 March 2024",
    "directors_report_date": "15 March 2024",
    "statement_by_directors_date": "15 March 2024",
    "statutory_declaration": {
        "cop_name": "MOHD FAIZAL BIN HASSAN",
        "cop_date": "15 March 2024",
        "status": "VALID",
        "notes": ""
    }
}

_IS_RESPONSE = {
    "year": "2024",
    "scale_note": "RM full amounts",
    "revenue": 27983932.0,
    "cost_of_sales": 24122517.0,
    "gross_profit": 3861415.0,
    "depreciation": 450000.0,
    "staff_cost": 800000.0,
    "other_operating_expenses": 2649105.0,
    "other_income": 120000.0,
    "interest_expenses": 350000.0,
    "taxes": 80000.0,
    "net_profit": 252310.0,
    "total_comprehensive_income": 252310.0
}

_BS_RESPONSE = {
    "year": "2024",
    "scale_note": "RM full amounts",
    "non_current_assets": 7603046.0,
    "current_assets": 13374961.0,
    "trade_receivables": 8000000.0,
    "other_receivables_and_prepayments": 1200000.0,
    "other_receivables": None,
    "amount_due_from_directors": None,
    "amount_due_from_related_companies": None,
    "deposits_and_prepayments": 200000.0,
    "inventories": 1974961.0,
    "cash_and_cash_equivalents": 2000000.0,
    "total_assets": 20978007.0,
    "non_current_liabilities": 3364658.0,
    "nca_bank_borrowings": 3261796.0,
    "nca_hire_purchase": 39595.0,
    "nca_other_payables": None,
    "current_liabilities": 13374961.0,
    "trade_payables": 6000000.0,
    "other_payables_and_accruals": 1200000.0,
    "cl_other_payables": None,
    "amount_due_to_directors": None,
    "amount_due_to_related_companies": None,
    "cl_others": None,
    "cl_bank_borrowings": 5800000.0,
    "cl_hire_purchase": 374961.0,
    "total_liabilities": 16739619.0,
    "total_equity": 4238388.0,
    "share_capital": 500000.0,
    "retained_earnings": 3738388.0,
    "revaluation_reserve": None,
    "total_liabilities_and_equity": 20978007.0
}

_NOTES_RESPONSE = {
    "interest_breakdown": {
        "bank_overdraft": 50000.0,
        "bank_acceptance": 100000.0,
        "hire_purchase": 40000.0,
        "term_loan": 160000.0,
        "revolving_credit": None,
        "other_interest": None,
        "total": 350000.0
    },
    "staff_cost_breakdown": {
        "directors_emoluments": 200000.0,
        "directors_fees": None,
        "wages_salaries": 500000.0,
        "epf": 60000.0,
        "socso": 20000.0,
        "eis": 5000.0,
        "other_staff_costs": 15000.0,
        "total": 800000.0
    }
}


class TestPipelineMock(unittest.TestCase):

    def _make_mock_pages(self):
        """Minimal page list for the classifier."""
        return [
            {"page": i, "text": f"<<PAGE {i}>> sample text page {i}"}
            for i in range(1, 6)
        ]

    def _mock_model_call(self, prompt, generation_config=None):
        resp = MagicMock()
        if "audit information" in prompt.lower() or "statutory declaration" in prompt.lower():
            resp.text = json.dumps(_AUDIT_RESPONSE)
        elif "income statement figures" in prompt.lower():
            resp.text = json.dumps(_IS_RESPONSE)
        elif "balance sheet" in prompt.lower() or "total assets" in prompt.lower():
            resp.text = json.dumps(_BS_RESPONSE)
        else:
            resp.text = json.dumps(_NOTES_RESPONSE)
        return resp

    def test_gemini_extractor_builds_correct_data(self):
        """GeminiExtractor.extract_all() returns properly shaped dicts."""
        with patch.dict(sys.modules, {"google.generativeai": _mock_genai}):
            _mock_genai.GenerativeModel.return_value = _mock_model
            _mock_model.generate_content.side_effect = self._mock_model_call
            _mock_genai.configure = MagicMock()

            # Re-import to pick up mock
            if "gemini_extractor" in sys.modules:
                del sys.modules["gemini_extractor"]
            import gemini_extractor as ge

            extractor = ge.GeminiExtractor(
                pages=self._make_mock_pages(),
                target_year="2024",
                hints={},
                api_key="test-key",
            )
            results = extractor.extract_all(pdf_hash_val="")

        audit = results["audit_checks"]
        fin = results["financial_data"]   # current year (legacy flat mock → current_year)

        self.assertEqual(audit["opinion"], "UNQUALIFIED")
        self.assertTrue(audit["true_and_fair"])
        self.assertEqual(audit["firm_name"], "JC & ASSOCIATES PLT")
        self.assertEqual(audit["accountant_name"], "CHU WOOI SIONG")
        self.assertEqual(audit["statutory_declaration"]["status"], "VALID")
        self.assertIn("CONSISTENT", audit["signature_consistency"])

        self.assertAlmostEqual(fin["Revenue"]["value"], 27983932.0)
        self.assertAlmostEqual(fin["Gross Profit"]["value"], 3861415.0)
        self.assertAlmostEqual(fin["Total Asset"]["value"], 20978007.0)
        self.assertAlmostEqual(fin["Total Liabilities"]["value"], 16739619.0)
        self.assertAlmostEqual(fin["Equity"]["value"], 4238388.0)

        # TCI validation flag should be set (net_profit == total_comprehensive_income)
        self.assertTrue(fin["Net Profit (Loss) for the Year"].get("validated_vs_tci"))

    def test_validator_passes_on_good_data(self):
        """Arithmetic checks PASS when BS adds up correctly."""
        from validator import run_checks
        # Use the mock BS data (liabilities + equity = total assets within tolerance)
        fin = {}
        mapping = {
            "Revenue": 27983932, "Cost of Sales": 24122517, "Gross Profit": 3861415,
            "Total Asset": 20978007, "Total Liabilities": 16739619, "Equity": 4238388,
            "Non Current Asset": 7603046, "Current Asset": 13374961,
            "Non Current Liabilities": 3364658, "Current Liabilities": 13374961,
        }
        for k, v_val in mapping.items():
            fin[k] = {"value": float(v_val)}

        results = run_checks(fin)
        self.assertEqual(results["Gross Profit = Revenue - COS"]["status"], "PASS")
        # Total Assets = Liabilities + Equity: 16739619 + 4238388 = 20978007 ✓
        self.assertEqual(results["Total Assets = Liabilities + Equity"]["status"], "PASS")

    def test_page_classifier_detects_sections(self):
        """Page classifier assigns correct types to keyword-rich pages."""
        from page_classifier import classify_pages
        pages = [
            {"page": 1, "text": "independent auditors report we have audited"},
            {"page": 2, "text": "statement of financial position total assets current liabilities"},
            {"page": 3, "text": "statement of comprehensive income revenue cost of sales gross profit"},
            {"page": 4, "text": "notes to the financial statements accounting policies"},
            {"page": 5, "text": "statutory declaration commissioner of oaths pengakuan berkanun"},
        ]
        pm = classify_pages(pages)
        self.assertEqual(pm[1], "audit")
        self.assertEqual(pm[2], "balance_sheet")
        self.assertEqual(pm[3], "income_statement")
        self.assertEqual(pm[4], "notes")
        self.assertEqual(pm[5], "statutory_decl")

    def test_json_cache_roundtrip(self):
        """json_cache save/load roundtrip works."""
        import json_cache
        orig_dir = json_cache._CACHE_DIR
        with tempfile.TemporaryDirectory() as tmp:
            json_cache._CACHE_DIR = os.path.join(tmp, ".llm_cache")
            try:
                data = {"opinion": "UNQUALIFIED", "firm": "TEST PLT"}
                json_cache.save("abc123", "audit", data)
                loaded = json_cache.load("abc123", "audit")
                self.assertEqual(loaded, data)
                self.assertIsNone(json_cache.load("abc123", "balance_sheet"))
                count = json_cache.clear("abc123")
                self.assertEqual(count, 1)
                self.assertIsNone(json_cache.load("abc123", "audit"))
            finally:
                json_cache._CACHE_DIR = orig_dir


if __name__ == "__main__":
    unittest.main(verbosity=2)
