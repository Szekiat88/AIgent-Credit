"""
sp_rest.py — SharePoint REST API with sharing-link guest authentication.

How it works:
  1. Follow the sharing link → SharePoint issues FedAuth cookies
  2. Use those cookies for all subsequent REST API calls
  3. No Azure app, no SP_CLIENT_ID — just the sharing link

Set SP_SHARING_LINK in your .env file and this module self-authenticates on import.
"""

from __future__ import annotations

import difflib
import os
import re
import time
import urllib.parse
from pathlib import Path
from typing import Optional

import requests

# ---------------------------------------------------------------------------
# Site constants
# ---------------------------------------------------------------------------

_SP_BASE      = "https://magnisave-my.sharepoint.com"
_SP_SITE_PATH = "/personal/joe_kwan_magnisavegroup_com"
_SP_API       = f"{_SP_BASE}{_SP_SITE_PATH}/_api"
ROOT_FOLDER   = "/personal/joe_kwan_magnisavegroup_com/Documents/MS - Project Appleton"

FOLDER_FIN_STMT  = "Financial Statements"
FOLDER_AUDITED   = "Audited Account"
FOLDER_CREDIT_UW = "Credit Underwriting"
CAWF_KEYWORD     = "CAWF"
EXCEL_EXTS       = {".xlsx", ".xlsm", ".xls"}

# ---------------------------------------------------------------------------
# Session — shared across all calls, holds FedAuth cookies after authenticate()
# ---------------------------------------------------------------------------

_SESSION = requests.Session()
_SESSION.headers.update({
    "Accept":     "application/json;odata=verbose",
    "User-Agent": "Mozilla/5.0 AppleWebKit/537.36 Chrome/120.0",
})

_authenticated = False


def authenticate(sharing_link: str) -> None:
    """
    Follow a SharePoint sharing link to get FedAuth guest cookies.
    Call once before any list/download operations.
    """
    global _authenticated
    resp = _SESSION.get(sharing_link, timeout=30, allow_redirects=True)
    if resp.status_code not in (200, 302):
        raise PermissionError(
            f"Could not access sharing link (HTTP {resp.status_code}).\n"
            "Check that SP_SHARING_LINK in your .env is correct and not expired."
        )
    _authenticated = True


def _ensure_auth() -> None:
    if _authenticated:
        return
    link = os.environ.get("SP_SHARING_LINK", "")
    if link:
        print("[SharePoint] Authenticating via sharing link ...")
        authenticate(link)
    else:
        raise PermissionError(
            "SharePoint returned 403.\n"
            "Add SP_SHARING_LINK to your .env file:\n"
            "  SP_SHARING_LINK=https://magnisave-my.sharepoint.com/:f:/g/..."
        )


# ---------------------------------------------------------------------------
# Core request
# ---------------------------------------------------------------------------

def _get(path: str) -> dict:
    _ensure_auth()
    url  = f"{_SP_API}/{path}"
    resp = _SESSION.get(url, timeout=30)
    if resp.status_code in (401, 403):
        raise PermissionError(
            "SharePoint returned 403 — sharing link may have expired.\n"
            "Update SP_SHARING_LINK in your .env file."
        )
    if not resp.ok:
        raise RuntimeError(f"SharePoint API error {resp.status_code}: {url}\n{resp.text[:300]}")
    return resp.json()

# ---------------------------------------------------------------------------
# Navigation helpers
# ---------------------------------------------------------------------------

def list_subfolders(server_rel_path: str) -> list[dict]:
    """Return all subfolders. Each item has Name + ServerRelativeUrl."""
    encoded = urllib.parse.quote(server_rel_path)
    data    = _get(
        f"web/GetFolderByServerRelativeUrl('{encoded}')"
        f"/Folders?$select=Name,ServerRelativeUrl,TimeLastModified&$orderby=Name"
    )
    return data.get("d", {}).get("results", [])


def list_files(server_rel_path: str) -> list[dict]:
    """Return all files sorted by modified date descending."""
    encoded = urllib.parse.quote(server_rel_path)
    data    = _get(
        f"web/GetFolderByServerRelativeUrl('{encoded}')"
        f"/Files?$select=Name,ServerRelativeUrl,TimeLastModified,Length"
        f"&$orderby=TimeLastModified desc"
    )
    return data.get("d", {}).get("results", [])


def _norm(s: str) -> str:
    """Lowercase + collapse whitespace — used for all name comparisons."""
    return " ".join(s.lower().split())


def _year_in_name(name: str) -> int:
    """Return the highest 4-digit year found in a filename, or 0."""
    hits = re.findall(r'\b(20\d{2})\b', name)
    return max(int(y) for y in hits) if hits else 0


def find_subfolder(folders: list[dict], name: str) -> Optional[dict]:
    """
    Find a subfolder tolerating human typos in the folder name.

    Match priority:
      1. Exact (normalised whitespace + case)
      2. One name contains the other
      3. Fuzzy similarity ≥ 0.72  (catches double-letters, missing 's', etc.)

    Examples of names that all resolve to FOLDER_FIN_STMT:
      "Financial Statement", "Financial Statements",
      "Finnancial Statements", "Financials Statements"
    """
    if not folders:
        return None
    target = _norm(name)

    # 1. Exact
    for f in folders:
        if _norm(f["Name"]) == target:
            return f

    # 2. Substring either direction
    for f in folders:
        fn = _norm(f["Name"])
        if target in fn or fn in target:
            return f

    # 3. Fuzzy — difflib similarity ≥ 0.72
    normed = [_norm(f["Name"]) for f in folders]
    matches = difflib.get_close_matches(target, normed, n=1, cutoff=0.72)
    if matches:
        for f in folders:
            if _norm(f["Name"]) == matches[0]:
                return f

    return None


def get_latest_file(files: list[dict], exts: set,
                    name_contains: str = "") -> Optional[dict]:
    """
    Return the most recent file matching extension + optional name filter.

    Sort order: year extracted from filename (desc) → TimeLastModified (desc).
    Year-in-filename wins because SharePoint modified dates can be upload dates,
    not the year the accounts were prepared.
    """
    files = [f for f in files if Path(f["Name"]).suffix.lower() in exts]
    if name_contains:
        files = [f for f in files if name_contains.lower() in f["Name"].lower()]
    if not files:
        return None
    files.sort(
        key=lambda f: (_year_in_name(f["Name"]), f.get("TimeLastModified", "")),
        reverse=True,
    )
    return files[0]


def get_latest_audited_file(files: list[dict], exts: set) -> Optional[dict]:
    """
    Return the most recent file whose name contains 'audited', or None.
    Does NOT fall back to unnamed files — callers use Tier 3 for that.
    """
    pdfs = [
        f for f in files
        if Path(f["Name"]).suffix.lower() in exts
        and "audited" in f["Name"].lower()
    ]
    if not pdfs:
        return None
    pdfs.sort(
        key=lambda f: (_year_in_name(f["Name"]), f.get("TimeLastModified", "")),
        reverse=True,
    )
    return pdfs[0]


def download(server_rel_url: str, dest: Path, force: bool = False) -> bool:
    """
    Download a file by server-relative URL to dest.
    Returns True if downloaded, False if skipped (already exists and not force).
    """
    _ensure_auth()
    if dest.exists() and not force:
        return False
    encoded = urllib.parse.quote(server_rel_url)
    url     = f"{_SP_API}/web/GetFileByServerRelativeUrl('{encoded}')/$value"
    resp    = _SESSION.get(url, timeout=120, stream=True)
    if not resp.ok:
        raise RuntimeError(f"Download failed ({resp.status_code}): {server_rel_url}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            f.write(chunk)
    time.sleep(0.2)
    return True
