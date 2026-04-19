"""Shared whitespace and typography normalization for comparing labels and cell text."""

from __future__ import annotations

import re
from typing import Any


def normalize_compare_text(value: Any, *, smart_typography: bool = False) -> str:
    """Collapse whitespace, lowercase. Optional smart-quote folding for Excel template labels."""
    s = str(value or "")
    if smart_typography:
        s = s.replace("\u2019", "'").replace("\u2018", "'")
        s = s.replace("\u201c", '"').replace("\u201d", '"')
    return re.sub(r"\s+", " ", s.replace("\n", " ")).strip().lower()
