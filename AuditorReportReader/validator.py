"""
Arithmetic validation of extracted financial data.

Cross-checks:
  1. Gross Profit = Revenue − Cost of Sales
  2. Net Profit ≈ Total Comprehensive Income  (already flagged by Gemini extractor)
  3. Total Assets = Total Liabilities + Equity
  4. Current Assets + Non-Current Assets ≈ Total Assets
  5. Current Liabilities + Non-Current Liabilities ≈ Total Liabilities
"""

from typing import Optional


_TOL_PCT = 0.5   # 0.5% tolerance for rounding differences


def _pct_diff(a: float, b: float) -> float:
    denom = max(abs(a), abs(b), 1.0)
    return abs(a - b) / denom * 100


def _get(data: dict, field: str) -> Optional[float]:
    return data.get(field, {}).get("value")


def run_checks(financial_data: dict) -> dict:
    """
    Returns a dict of check_name → {status, computed, reported, diff_pct}.
    status is 'PASS', 'FAIL', or 'SKIP' (when a required value is missing).
    """
    results = {}

    # 1. Gross Profit check
    rev = _get(financial_data, "Revenue")
    cos = _get(financial_data, "Cost of Sales")
    gp_reported = _get(financial_data, "Gross Profit")
    if rev is not None and cos is not None and gp_reported is not None:
        gp_computed = rev - cos
        diff = _pct_diff(gp_computed, gp_reported)
        results["Gross Profit = Revenue - COS"] = {
            "status": "PASS" if diff <= _TOL_PCT else "FAIL",
            "computed": gp_computed,
            "reported": gp_reported,
            "diff_pct": round(diff, 2),
        }
    else:
        results["Gross Profit = Revenue - COS"] = {"status": "SKIP"}

    # 2. Total Assets = Liabilities + Equity
    ta = _get(financial_data, "Total Asset")
    tl = _get(financial_data, "Total Liabilities")
    eq = _get(financial_data, "Equity")
    if ta is not None and tl is not None and eq is not None:
        computed = tl + eq
        diff = _pct_diff(computed, ta)
        results["Total Assets = Liabilities + Equity"] = {
            "status": "PASS" if diff <= _TOL_PCT else "FAIL",
            "computed": computed,
            "reported": ta,
            "diff_pct": round(diff, 2),
        }
    else:
        results["Total Assets = Liabilities + Equity"] = {"status": "SKIP"}

    # 3. Assets subtotal check
    nca = _get(financial_data, "Non Current Asset")
    ca = _get(financial_data, "Current Asset")
    if ta is not None and nca is not None and ca is not None:
        computed = nca + ca
        diff = _pct_diff(computed, ta)
        results["NCA + CA = Total Assets"] = {
            "status": "PASS" if diff <= _TOL_PCT else "FAIL",
            "computed": computed,
            "reported": ta,
            "diff_pct": round(diff, 2),
        }
    else:
        results["NCA + CA = Total Assets"] = {"status": "SKIP"}

    # 4. Liabilities subtotal check
    ncl = _get(financial_data, "Non Current Liabilities")
    cl = _get(financial_data, "Current Liabilities")
    if tl is not None and ncl is not None and cl is not None:
        computed = ncl + cl
        diff = _pct_diff(computed, tl)
        results["NCL + CL = Total Liabilities"] = {
            "status": "PASS" if diff <= _TOL_PCT else "FAIL",
            "computed": computed,
            "reported": tl,
            "diff_pct": round(diff, 2),
        }
    else:
        results["NCL + CL = Total Liabilities"] = {"status": "SKIP"}

    return results


def print_validation(results: dict) -> bool:
    """Print validation results. Returns True if all checks pass or skip."""
    all_ok = True
    for name, r in results.items():
        status = r["status"]
        if status == "SKIP":
            print(f"    [SKIP] {name} — missing data")
        elif status == "PASS":
            print(f"    [PASS] {name}")
        else:
            all_ok = False
            print(f"    [FAIL] {name}: "
                  f"computed={r['computed']:,.0f}  "
                  f"reported={r['reported']:,.0f}  "
                  f"diff={r['diff_pct']:.2f}%")
    return all_ok
