"""
sharepoint_downloader.py — Download auditor report files from a SharePoint folder.

Supports two auth methods:
  A) Delegated (Guest user login) — run once, browser pop-up, token cached
  B) App-only (IT-registered app)  — fully headless, no login needed

Usage:
  # First time (opens browser to sign in):
  python sharepoint_downloader.py --url "https://company.sharepoint.com/sites/Finance/Shared Documents/Auditor Reports"

  # Download to specific folder:
  python sharepoint_downloader.py --url "<sharepoint_folder_url>" --out ./training/inbox

  # Use app-only credentials (Option C):
  python sharepoint_downloader.py --url "<url>" --tenant-id <tid> --client-id <cid> --client-secret <secret>

  # Decode a sharing link (Option B):
  python sharepoint_downloader.py --sharing-link "https://company.sharepoint.com/:f:/..."

Setup:
  pip install msal requests

Environment variables (alternative to CLI flags):
  SP_TENANT_ID     — Azure tenant ID (from Azure Portal)
  SP_CLIENT_ID     — App registration client ID
  SP_CLIENT_SECRET — App registration client secret (app-only auth only)
"""

import argparse
import base64
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional
import urllib.parse

try:
    import msal
    import requests
except ImportError:
    print("[ERROR] Missing dependencies. Run:")
    print("  pip install msal requests")
    sys.exit(1)

# ── constants ─────────────────────────────────────────────────────────────────

_GRAPH_BASE  = "https://graph.microsoft.com/v1.0"
_SCOPES_DELEGATED = ["Files.Read.All", "Sites.Read.All"]
_TOKEN_CACHE  = Path(__file__).parent / ".sharepoint_token_cache.json"
_DEFAULT_OUT  = Path(__file__).parent.parent / "training" / "inbox"

# ── auth ──────────────────────────────────────────────────────────────────────

def _build_app_delegated(tenant_id: str, client_id: str) -> msal.PublicClientApplication:
    """Build an MSAL public client for delegated (user) auth with token caching."""
    cache = msal.SerializableTokenCache()
    if _TOKEN_CACHE.exists():
        cache.deserialize(_TOKEN_CACHE.read_text())

    app = msal.PublicClientApplication(
        client_id=client_id,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
        token_cache=cache,
    )
    return app, cache


def _build_app_confidential(tenant_id: str, client_id: str,
                             client_secret: str) -> msal.ConfidentialClientApplication:
    """Build an MSAL confidential client for app-only auth."""
    return msal.ConfidentialClientApplication(
        client_id=client_id,
        client_credential=client_secret,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
    )


def get_token_delegated(tenant_id: str, client_id: str) -> str:
    """
    Get an access token via device code flow.
    Prints a short code + URL — open the URL on any browser, enter the code.
    Token is cached locally — subsequent runs reuse it silently.
    """
    app, cache = _build_app_delegated(tenant_id, client_id)

    # Try silent refresh first (cached token)
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(_SCOPES_DELEGATED, account=accounts[0])
        if result and "access_token" in result:
            print("[Auth] Using cached token.")
            return result["access_token"]

    # Device code flow — no redirect URI or browser popup needed
    flow = app.initiate_device_flow(scopes=_SCOPES_DELEGATED)
    if "user_code" not in flow:
        print(f"[ERROR] Could not start device flow: {flow}")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("  SIGN IN REQUIRED")
    print("=" * 60)
    print(f"  1. Open this URL in any browser:")
    print(f"     https://microsoft.com/devicelogin")
    print(f"  2. Enter this code:  {flow['user_code']}")
    print(f"  3. Sign in as:       szekiatpua10222@outlook.com")
    print("=" * 60 + "\n")

    result = app.acquire_token_by_device_flow(flow)   # blocks until user signs in

    if "access_token" not in result:
        print(f"[ERROR] Auth failed: {result.get('error_description', result)}")
        sys.exit(1)

    # Cache token for next run
    if cache.has_state_changed:
        _TOKEN_CACHE.write_text(cache.serialize())
    print("[Auth] Sign-in successful. Token cached for future runs.\n")
    return result["access_token"]


def get_token_app_only(tenant_id: str, client_id: str, client_secret: str) -> str:
    """Get an access token via app credentials (no user login needed)."""
    app = _build_app_confidential(tenant_id, client_id, client_secret)
    result = app.acquire_token_for_client(
        scopes=["https://graph.microsoft.com/.default"]
    )
    if "access_token" not in result:
        print(f"[ERROR] App auth failed: {result.get('error_description', result)}")
        sys.exit(1)
    return result["access_token"]


# ── Graph API helpers ─────────────────────────────────────────────────────────

def _graph_get(token: str, url: str) -> dict:
    """Make a Graph API GET request."""
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    resp = requests.get(url, headers=headers, timeout=30)
    if resp.status_code == 401:
        print("[ERROR] Access denied. Check your permissions on the SharePoint site.")
        sys.exit(1)
    if not resp.ok:
        print(f"[ERROR] Graph API error {resp.status_code}: {resp.text[:400]}")
        sys.exit(1)
    return resp.json()


def _graph_download(token: str, url: str, dest: Path):
    """Download a file from Graph API."""
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers, timeout=120, stream=True)
    if not resp.ok:
        print(f"  [SKIP] Download failed ({resp.status_code}): {dest.name}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            f.write(chunk)


# ── URL → Graph API endpoint conversion ──────────────────────────────────────

def _sharepoint_url_to_graph(sp_url: str) -> tuple:
    """
    Convert a SharePoint web URL into a Graph API drive item URL.
    Returns (site_id, drive_id, item_path_or_id).

    Example input:
      https://contoso.sharepoint.com/sites/Finance/Shared%20Documents/Audits/2024
    """
    parsed = urllib.parse.urlparse(sp_url)
    host   = parsed.netloc                # contoso.sharepoint.com
    path   = parsed.path                  # /sites/Finance/...

    # Extract site path — everything up to and including the site name
    m = re.match(r"(/sites/[^/]+|/teams/[^/]+|/)", path)
    site_path = m.group(0) if m else "/"

    # Remainder = folder path within the site
    folder_path = path[len(site_path):]   # e.g. Shared Documents/Audits/2024

    site_graph_url = (
        f"{_GRAPH_BASE}/sites/{host}:{site_path}"
    )
    return site_graph_url, folder_path.lstrip("/")


def _sharing_link_to_graph(sharing_link: str) -> str:
    """
    Convert a SharePoint sharing link (/:f:/...) to a Graph API shares endpoint.
    Works for both file and folder sharing links.
    """
    # Encode the sharing URL as base64url for Graph API
    encoded = base64.urlsafe_b64encode(sharing_link.encode()).decode().rstrip("=")
    return f"{_GRAPH_BASE}/shares/u!{encoded}/driveItem"


# ── file listing & download ───────────────────────────────────────────────────

_WANTED_EXTS = {".pdf", ".xlsx", ".xlsm", ".xls", ".xlsb"}


def list_folder_items(token: str, folder_url: str) -> list:
    """Return all files (recursively) under a Graph API folder URL."""
    items = []
    url = folder_url + "/children?$select=name,size,file,folder,@microsoft.graph.downloadUrl&$top=200"
    while url:
        data = _graph_get(token, url)
        for item in data.get("value", []):
            if "file" in item:
                items.append(item)
            elif "folder" in item:
                # Recurse into subfolder
                child_url = f"{_GRAPH_BASE}/drives/{item.get('parentReference',{}).get('driveId','')}/items/{item['id']}"
                items.extend(list_folder_items(token, child_url))
        url = data.get("@odata.nextLink")
    return items


def download_files(token: str, items: list, out_dir: Path,
                   exts: set = _WANTED_EXTS) -> list:
    """Download wanted files into out_dir. Returns list of downloaded paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    downloaded = []

    for item in items:
        name = item.get("name", "")
        ext  = Path(name).suffix.lower()
        if ext not in exts:
            continue

        dest = out_dir / name
        if dest.exists():
            print(f"  [SKIP] Already exists: {name}")
            downloaded.append(dest)
            continue

        dl_url = item.get("@microsoft.graph.downloadUrl")
        if not dl_url:
            # Fall back to content endpoint
            drive_id = item.get("parentReference", {}).get("driveId", "")
            item_id  = item.get("id", "")
            dl_url   = f"{_GRAPH_BASE}/drives/{drive_id}/items/{item_id}/content"

        size_kb = item.get("size", 0) // 1024
        print(f"  [Download] {name}  ({size_kb} KB)")
        _graph_download(token, dl_url, dest)
        downloaded.append(dest)
        time.sleep(0.2)   # polite rate limiting

    return downloaded


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Download auditor report files from SharePoint via Microsoft Graph API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive login (browser pop-up, token cached for next time):
  python sharepoint_downloader.py \\
      --url "https://contoso.sharepoint.com/sites/Finance/Shared Documents/Audits" \\
      --tenant-id common \\
      --client-id <your-azure-app-client-id>

  # Sharing link (/:f:/... URL the company sent you):
  python sharepoint_downloader.py \\
      --sharing-link "https://contoso.sharepoint.com/:f:/s/Finance/Abc123..." \\
      --tenant-id common \\
      --client-id <your-azure-app-client-id>

  # App-only (headless, no browser):
  python sharepoint_downloader.py \\
      --url "https://contoso.sharepoint.com/sites/Finance/..." \\
      --tenant-id <tid> --client-id <cid> --client-secret <secret>
        """
    )
    parser.add_argument("--url",            help="SharePoint folder web URL")
    parser.add_argument("--sharing-link",   help="SharePoint sharing link (/:f:/...)")
    parser.add_argument("--out",            default=str(_DEFAULT_OUT),
                        help=f"Output directory (default: {_DEFAULT_OUT})")
    parser.add_argument("--tenant-id",      default=os.environ.get("SP_TENANT_ID", "common"),
                        help="Azure tenant ID or 'common' (default: SP_TENANT_ID env var)")
    parser.add_argument("--client-id",      default=os.environ.get("SP_CLIENT_ID", ""),
                        help="Azure app registration client ID (SP_CLIENT_ID env var)")
    parser.add_argument("--client-secret",  default=os.environ.get("SP_CLIENT_SECRET", ""),
                        help="App client secret for app-only auth (SP_CLIENT_SECRET env var)")
    parser.add_argument("--list-only",      action="store_true",
                        help="List files without downloading")

    args = parser.parse_args()

    if not args.url and not args.sharing_link:
        parser.error("Provide either --url or --sharing-link")

    if not args.client_id:
        print("[ERROR] --client-id is required (or set SP_CLIENT_ID env var).")
        print("        Register a free Azure app at https://portal.azure.com")
        print("        See setup guide: https://learn.microsoft.com/en-us/azure/active-directory/develop/quickstart-register-app")
        sys.exit(1)

    out_dir = Path(args.out)

    # ── Get access token ──────────────────────────────────────────────────────
    if args.client_secret:
        print("[Auth] Using app-only credentials (no browser needed)")
        token = get_token_app_only(args.tenant_id, args.client_id, args.client_secret)
    else:
        token = get_token_delegated(args.tenant_id, args.client_id)

    # ── Resolve folder URL to Graph API endpoint ──────────────────────────────
    if args.sharing_link:
        print(f"[SharePoint] Resolving sharing link...")
        drive_item_url = _sharing_link_to_graph(args.sharing_link)
        item_data = _graph_get(token, drive_item_url)
        if "folder" not in item_data:
            # It's a single file — download it directly
            print(f"  Sharing link points to a single file: {item_data.get('name')}")
            items = [item_data]
        else:
            folder_url = drive_item_url + "/children"
            items = list_folder_items(token, drive_item_url)
    else:
        print(f"[SharePoint] Resolving folder URL...")
        site_url, folder_path = _sharepoint_url_to_graph(args.url)

        # Get site info
        site_data = _graph_get(token, site_url)
        site_id   = site_data["id"]
        print(f"  Site: {site_data.get('displayName', site_id)}")

        # Get default drive
        drive_data = _graph_get(token, f"{_GRAPH_BASE}/sites/{site_id}/drive")
        drive_id   = drive_data["id"]

        # Navigate to the folder
        if folder_path:
            folder_url = f"{_GRAPH_BASE}/drives/{drive_id}/root:/{folder_path}"
        else:
            folder_url = f"{_GRAPH_BASE}/drives/{drive_id}/root"

        folder_data = _graph_get(token, folder_url)
        print(f"  Folder: {folder_data.get('name', folder_path or 'root')}")
        items = list_folder_items(token, folder_url)

    # ── List or download ──────────────────────────────────────────────────────
    wanted = [i for i in items if Path(i.get("name","")).suffix.lower() in _WANTED_EXTS]
    print(f"\n  Found {len(items)} items, {len(wanted)} are PDFs/Excel files\n")

    if args.list_only:
        for item in wanted:
            size_kb = item.get("size", 0) // 1024
            print(f"  {item['name']}  ({size_kb} KB)")
        return

    downloaded = download_files(token, wanted, out_dir)
    print(f"\n  Downloaded {len(downloaded)} file(s) → {out_dir}")

    if downloaded:
        print("\n  Next step: register new files as training cases:")
        print("    python training_manager.py inbox")


if __name__ == "__main__":
    main()
