"""
LLM result cache — persists Gemini responses by PDF hash + section name.

Cache lives in .llm_cache/ relative to the working directory.
Re-running the tool on the same PDF costs nothing (Gemini not called again).
"""

import hashlib
import json
import os
from typing import Optional

_CACHE_DIR = ".llm_cache"


def pdf_hash(pdf_path: str) -> str:
    """MD5 of the PDF file bytes."""
    h = hashlib.md5()
    with open(pdf_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _path(file_hash: str, section: str) -> str:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    return os.path.join(_CACHE_DIR, f"{file_hash}_{section}.json")


def load(file_hash: str, section: str) -> Optional[dict]:
    """Return cached dict or None if not cached."""
    p = _path(file_hash, section)
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return None


def save(file_hash: str, section: str, data: dict) -> None:
    """Persist a Gemini response dict."""
    p = _path(file_hash, section)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def clear(file_hash: str) -> int:
    """Delete all cached sections for a given PDF. Returns count deleted."""
    removed = 0
    if not os.path.isdir(_CACHE_DIR):
        return 0
    for fname in os.listdir(_CACHE_DIR):
        if fname.startswith(file_hash + "_"):
            os.remove(os.path.join(_CACHE_DIR, fname))
            removed += 1
    return removed
