#!/usr/bin/env python3
"""Rebuild all package index pages from GitHub Releases.

Reads PACKAGES below and regenerates <package-name>/index.html for each entry
by querying the GitHub Releases API, downloading each asset to compute its
SHA-256 hash, and rendering pkg_template.html.

Environment variables:
    GITHUB_TOKEN  — PAT with repo scope on all source repos listed in PACKAGES.
                    Must be able to list releases and download release assets.

Usage:
    GITHUB_TOKEN=ghp_... python update_package.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.request
from pathlib import Path

try:
    from jinja2 import Environment, FileSystemLoader
except ImportError:
    sys.exit("jinja2 is required: pip install jinja2")

# ---------------------------------------------------------------------------
# Package registry — add one dict per package to index.
# ---------------------------------------------------------------------------
PACKAGES = [
    {
        "repo": "zeevaro/zeevaro-middleware",
        "package_name": "zeevaro-middleware",
        "requires_python": ">=3.12",
    },
    # To add a new package, append an entry here:
    # {
    #     "repo": "zeevaro/your-new-package",
    #     "package_name": "your-new-package",
    #     "requires_python": ">=3.12",
    # },
]

API_BASE = "https://api.github.com"
ROOT = Path(__file__).resolve().parent


def github_api_get(url: str, token: str) -> list | dict:
    """Paginated GitHub API GET — returns combined list for list responses."""
    results: list = []
    while url:
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
            link_header = resp.headers.get("Link", "")
        if isinstance(data, list):
            results.extend(data)
        else:
            return data
        url = None
        for part in link_header.split(","):
            if 'rel="next"' in part.strip():
                url = part.split(";")[0].strip().strip("<>")
    return results


def sha256_of_asset(asset_url: str, token: str) -> str:
    """Stream-download a GitHub release asset and return its hex SHA-256.

    asset_url must be the GitHub API asset URL (not the browser_download_url).
    GitHub redirects to a pre-signed S3 URL; urllib follows the 302 automatically.
    The S3 URL uses query-string signing, so no Authorization header is needed there.
    """
    req = urllib.request.Request(asset_url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/octet-stream",
    })
    h = hashlib.sha256()
    with urllib.request.urlopen(req) as resp:
        while chunk := resp.read(65536):
            h.update(chunk)
    return h.hexdigest()


def collect_files(repo: str, requires_python: str, token: str) -> list[dict]:
    """Return all non-draft, non-prerelease wheel and sdist assets for a repo."""
    releases = github_api_get(f"{API_BASE}/repos/{repo}/releases?per_page=100", token)
    print(f"  Found {len(releases)} release(s)")

    files = []
    for release in releases:
        if release.get("draft") or release.get("prerelease"):
            continue
        for asset in release.get("assets", []):
            name = asset["name"]
            if not (name.endswith(".whl") or name.endswith(".tar.gz")):
                continue
            print(f"  Hashing {name} ...", flush=True)
            digest = sha256_of_asset(asset["url"], token)
            files.append({
                "filename": name,
                "url": asset["browser_download_url"],
                "sha256": digest,
                "requires_python": requires_python,
            })
    return files


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        sys.exit("error: GITHUB_TOKEN environment variable is required")

    env = Environment(loader=FileSystemLoader(str(ROOT)), autoescape=True)
    template = env.get_template("pkg_template.html")

    for pkg in PACKAGES:
        print(f"\nProcessing {pkg['package_name']} ({pkg['repo']}) ...")
        files = collect_files(pkg["repo"], pkg["requires_python"], token)
        print(f"  Collected {len(files)} artifact(s)")

        html = template.render(package_name=pkg["package_name"], package_files=files)
        output_dir = ROOT / pkg["package_name"]
        output_dir.mkdir(exist_ok=True)
        (output_dir / "index.html").write_text(html, encoding="utf-8")
        print(f"  Wrote {output_dir / 'index.html'}")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
