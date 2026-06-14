"""
GitHub-based storage for the Excel data file.

Uses the GitHub Contents API to read/write a single Excel workbook stored on a
dedicated data branch. Storing data on a SEPARATE branch (not the production
branch) means saves do NOT trigger production redeploys, so writes are fast
(just the API round-trip, ~1-2s) instead of waiting for a full Vercel rebuild.

Environment variables:
  GITHUB_TOKEN        - Fine-grained PAT with Contents read/write on the repo (required)
  GITHUB_REPO         - "owner/repo" (default: LeviSantosAraujo/IBU-Operations-Schedule)
  GITHUB_DATA_BRANCH  - Branch used to store data (default: "data")
  GITHUB_DATA_FILE    - Path of the Excel file in the repo (default: "ibu_schedule.xlsx")
"""

import os
import base64
from typing import Optional

import requests

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO", "LeviSantosAraujo/IBU-Operations-Schedule")
GITHUB_DATA_BRANCH = os.getenv("GITHUB_DATA_BRANCH", "data")
GITHUB_DATA_FILE = os.getenv("GITHUB_DATA_FILE", "ibu_schedule.xlsx")

GITHUB_AVAILABLE = bool(GITHUB_TOKEN)

# Cache of the latest known blob SHA, required by the Contents API to update a file
_sha_cache: dict = {}

_API_BASE = "https://api.github.com"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _contents_url() -> str:
    return f"{_API_BASE}/repos/{GITHUB_REPO}/contents/{GITHUB_DATA_FILE}"


def github_get_file() -> Optional[bytes]:
    """Fetch the Excel file bytes from the data branch. Returns None on any failure."""
    if not GITHUB_AVAILABLE:
        print("[GH] GITHUB_TOKEN not set, skipping GitHub read")
        return None

    try:
        url = f"{_contents_url()}?ref={GITHUB_DATA_BRANCH}"
        print(f"[GH] GET {GITHUB_DATA_FILE} @ {GITHUB_DATA_BRANCH}")
        resp = requests.get(url, headers=_headers(), timeout=10)

        if resp.status_code == 404:
            print("[GH] File not found on data branch (first run)")
            return None
        if resp.status_code != 200:
            print(f"[GH] GET failed: HTTP {resp.status_code} - {resp.text[:200]}")
            return None

        data = resp.json()
        # Remember sha so writes can update in place
        _sha_cache[GITHUB_DATA_FILE] = data.get("sha")

        content = data.get("content")
        if content:
            return base64.b64decode(content)

        # Large files (>1MB) come back without inline content; use download_url
        download_url = data.get("download_url")
        if download_url:
            dl = requests.get(download_url, timeout=10)
            if dl.status_code == 200:
                return dl.content
        print("[GH] No content returned")
        return None
    except Exception as e:
        print(f"[GH] Error reading file: {e}")
        return None


def _fetch_current_sha() -> Optional[str]:
    """Get the current file SHA (needed to update an existing file)."""
    try:
        url = f"{_contents_url()}?ref={GITHUB_DATA_BRANCH}"
        resp = requests.get(url, headers=_headers(), timeout=10)
        if resp.status_code == 200:
            return resp.json().get("sha")
    except Exception as e:
        print(f"[GH] Error fetching sha: {e}")
    return None


def github_put_file(data: bytes, message: str = "Update schedule data") -> bool:
    """Commit the Excel file to the data branch via the Contents API."""
    if not GITHUB_AVAILABLE:
        print("[GH] GITHUB_TOKEN not set, skipping GitHub write")
        return False

    try:
        sha = _sha_cache.get(GITHUB_DATA_FILE) or _fetch_current_sha()

        payload = {
            "message": message,
            "content": base64.b64encode(data).decode("utf-8"),
            "branch": GITHUB_DATA_BRANCH,
        }
        if sha:
            payload["sha"] = sha

        print(f"[GH] PUT {GITHUB_DATA_FILE} @ {GITHUB_DATA_BRANCH} ({len(data)} bytes)")
        resp = requests.put(_contents_url(), headers=_headers(), json=payload, timeout=20)

        if resp.status_code in (200, 201):
            new_sha = resp.json().get("content", {}).get("sha")
            if new_sha:
                _sha_cache[GITHUB_DATA_FILE] = new_sha
            print("[GH] Write success")
            return True

        # Stale sha -> refetch and retry once
        if resp.status_code == 409:
            print("[GH] 409 conflict, refetching sha and retrying")
            fresh = _fetch_current_sha()
            if fresh:
                payload["sha"] = fresh
                retry = requests.put(_contents_url(), headers=_headers(), json=payload, timeout=20)
                if retry.status_code in (200, 201):
                    _sha_cache[GITHUB_DATA_FILE] = retry.json().get("content", {}).get("sha")
                    print("[GH] Write success on retry")
                    return True

        print(f"[GH] PUT failed: HTTP {resp.status_code} - {resp.text[:200]}")
        return False
    except Exception as e:
        print(f"[GH] Error writing file: {e}")
        return False
