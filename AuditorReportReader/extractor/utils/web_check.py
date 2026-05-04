"""
Web blacklist check for auditor firm and accountant name.

Searches MIA (Malaysian Institute of Accountants) disciplinary register
and general web for negative associations.

Returns "CLEAN", "FLAGGED", or "INCONCLUSIVE".
"""

import re
import time
from typing import Optional

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

_FLAG_KEYWORDS = [
    "blacklisted", "disciplinary", "suspended", "struck off",
    "conviction", "fraud", "criminal", "deregistered",
    "misconduct", "banned", "cancel", "revoke",
]

_SAFE_KEYWORDS = [
    "registered", "approved", "licensed", "member since",
    "chartered accountant",
]


def _search_web(query: str, max_results: int = 5) -> list[str]:
    """
    Perform a DuckDuckGo HTML search and return snippet texts.
    Falls back to empty list on any network error.
    """
    try:
        import requests
        url = "https://html.duckduckgo.com/html/"
        resp = requests.post(
            url,
            data={"q": query, "b": "", "kl": ""},
            headers=_HEADERS,
            timeout=10,
        )
        snippets = re.findall(
            r'class="result__snippet"[^>]*>(.*?)</a>',
            resp.text,
            re.DOTALL,
        )
        return [re.sub(r'<[^>]+>', '', s).strip() for s in snippets[:max_results]]
    except Exception:
        return []


def _analyse_snippets(snippets: list[str]) -> tuple[str, list[str]]:
    """Return ('CLEAN'|'FLAGGED'|'INCONCLUSIVE', [evidence_lines])."""
    if not snippets:
        return "INCONCLUSIVE", ["No search results returned"]

    evidence = []
    flagged = False
    for snippet in snippets:
        sl = snippet.lower()
        hits = [k for k in _FLAG_KEYWORDS if k in sl]
        if hits:
            flagged = True
            evidence.append(f"[FLAG] {snippet[:200]}")

    if flagged:
        return "FLAGGED", evidence

    safe_hits = sum(1 for s in snippets for k in _SAFE_KEYWORDS if k in s.lower())
    if safe_hits > 0:
        return "CLEAN", [f"Found {safe_hits} positive indicator(s)"]

    return "INCONCLUSIVE", ["Results found but no clear flag or positive signal"]


def check_firm(firm_name: str) -> dict:
    """Check auditor firm against MIA and general web."""
    if firm_name in ("NOT FOUND", "", None):
        return {"status": "INCONCLUSIVE", "query": "", "evidence": ["Firm name not extracted"]}

    query = f'"{firm_name}" blacklisted MIA Malaysia accountant disciplinary'
    snippets = _search_web(query)
    time.sleep(1)  # be polite
    status, evidence = _analyse_snippets(snippets)
    return {"status": status, "query": query, "evidence": evidence}


def check_accountant(name: str) -> dict:
    """Check individual accountant name."""
    if name in ("NOT FOUND", "", None):
        return {"status": "INCONCLUSIVE", "query": "", "evidence": ["Name not extracted"]}

    query = f'"{name}" MIA Malaysia disciplinary accountant suspended'
    snippets = _search_web(query)
    time.sleep(1)
    status, evidence = _analyse_snippets(snippets)
    return {"status": status, "query": query, "evidence": evidence}
