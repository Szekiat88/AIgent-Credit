"""
Lightweight page classifier — maps each OCR page to a section type.

No LLM used. Uses keyword signals only for fast, free classification.
Section types: audit | income_statement | balance_sheet | notes |
               statutory_decl | directors_report | other
"""

from typing import Dict, List, Optional

_SIGNALS: Dict[str, List[str]] = {
    "audit": [
        "independent auditor", "independent auditors",
        "auditor's report", "auditors' report",
        "laporan juruaudit", "laporan juruaudit bebas",
        "we have audited", "we audited",
        "basis for opinion", "key audit matters",
        "responsibilities of the auditors",
    ],
    "income_statement": [
        "statement of comprehensive income",
        "statement of profit or loss",
        "statement of profit and loss",
        "income statement",
        "profit and loss",
        "profit or loss",
        "penyata pendapatan komprehensif",
        "penyata pendapatan",
        "penyata untung rugi",
        "revenue", "turnover", "cost of sales",
        "gross profit", "gross loss",
    ],
    "balance_sheet": [
        "statement of financial position",
        "balance sheet",
        "penyata kedudukan kewangan",
        "total assets", "total liabilities",
        "shareholders' equity", "shareholders equity",
        "equity and liabilities",
        "non-current assets", "current assets",
        "non-current liabilities", "current liabilities",
    ],
    "notes": [
        "notes to the financial statements",
        "notes to financial statements",
        "notes to the accounts",
        "nota kepada penyata kewangan",
        "accounting policies",
        "significant accounting",
        "basis of preparation",
    ],
    "statutory_decl": [
        "statutory declaration",
        "pengakuan berkanun",
        "commissioner of oaths",
        "pesuruhjaya sumpah",
        "subscribed and solemnly declared",
    ],
    "directors_report": [
        "directors' report", "directors report",
        "laporan pengarah",
        "principal activities",
        "board of directors",
        "results of operations",
    ],
}

# Weight of each signal hit when multiple sections compete
_WEIGHTS: Dict[str, float] = {
    "audit": 2.0,
    "income_statement": 1.5,
    "balance_sheet": 1.5,
    "notes": 1.0,
    "statutory_decl": 3.0,
    "directors_report": 1.0,
    "other": 0.0,
}

# If any of these phrases appears in the first 600 chars of a page, the section
# is forced regardless of signal scoring.  This handles continuation pages that
# carry a section header but also contain words that trigger other signals.
_HEADER_OVERRIDES: List[tuple] = [
    ("notes to the financial statements", "notes"),
    ("notes to financial statements", "notes"),
    ("nota kepada penyata kewangan", "notes"),
    ("independent auditor", "audit"),
    ("independent auditors", "audit"),
    ("laporan juruaudit bebas", "audit"),
    ("statutory declaration", "statutory_decl"),
    ("pengakuan berkanun", "statutory_decl"),
]


def classify_pages(pages: List[dict]) -> Dict[int, str]:
    """Return {page_num: section_type} for every page."""
    result: Dict[int, str] = {}
    for pg in pages:
        text_lower = pg["text"].lower()
        # Strong-header override: check first 600 chars only
        header = text_lower[:600]
        override = None
        for phrase, section in _HEADER_OVERRIDES:
            if phrase in header:
                override = section
                break
        if override:
            result[pg["page"]] = override
            continue
        # Signal scoring
        scores: Dict[str, float] = {}
        for sec_type, signals in _SIGNALS.items():
            hits = sum(1 for s in signals if s in text_lower)
            if hits > 0:
                scores[sec_type] = hits * _WEIGHTS.get(sec_type, 1.0)
        if scores:
            result[pg["page"]] = max(scores, key=lambda k: scores[k])
        else:
            result[pg["page"]] = "other"
    return result


def pages_for_section(pages: List[dict], section_type: str,
                      page_map: Dict[int, str]) -> List[dict]:
    """Return page dicts whose type matches section_type."""
    return [p for p in pages if page_map.get(p["page"]) == section_type]


def text_for_sections(pages: List[dict], section_types: List[str],
                      page_map: Dict[int, str]) -> str:
    """Concatenate OCR text from pages matching any of the given types."""
    parts = []
    for p in pages:
        if page_map.get(p["page"]) in section_types:
            parts.append(f"<<PAGE {p['page']}>>\n{p['text']}")
    return "\n\n".join(parts)


def section_summary(page_map: Dict[int, str]) -> str:
    """Human-readable summary for logging: 'audit:1-3, income_statement:5, ...'"""
    from collections import defaultdict
    by_type: Dict[str, List[int]] = defaultdict(list)
    for pg, sec in page_map.items():
        by_type[sec].append(pg)
    parts = []
    for sec, pgs in sorted(by_type.items()):
        pgs_sorted = sorted(pgs)
        if len(pgs_sorted) == 1:
            parts.append(f"{sec}:p{pgs_sorted[0]}")
        else:
            parts.append(f"{sec}:p{pgs_sorted[0]}-{pgs_sorted[-1]}")
    return ", ".join(parts)
