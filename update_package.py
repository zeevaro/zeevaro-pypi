#!/usr/bin/env python3
"""Rebuild zeevaro-middleware index from GitHub Releases.

Environment variables:
    GITHUB_TOKEN  — PAT with repo scope on zeevaro/zeevaro-middleware
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

REPO = "zeevaro/zeevaro-middleware"
PACKAGE_NAME = "zeevaro-middleware"
REQUIRES_PYTHON = ">=3.12"
API_BASE = "https://api.github.com"
ROOT = Path(__file__).resolve().parent


def github_api_get(url: str, token: str) -> list | dict:
    results = []
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
    # asset_url is the GitHub API URL (requires Bearer auth).
    # urllib follows the 302 redirect to S3; S3 uses query-string signing so no auth header needed there.
    req = urllib.request.Request(asset_url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/octet-stream",
    })
    h = hashlib.sha256()
    with urllib.request.urlopen(req) as resp:
        while chunk := resp.read(65536):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        sys.exit("error: GITHUB_TOKEN environment variable is required")

    print(f"Fetching releases for {REPO} ...", flush=True)
    releases = github_api_get(f"{API_BASE}/repos/{REPO}/releases?per_page=100", token)
    print(f"Found {len(releases)} release(s)")

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
                "requires_python": REQUIRES_PYTHON,
            })

    print(f"Collected {len(files)} artifact(s)")

    env = Environment(loader=FileSystemLoader(str(ROOT)), autoescape=True)
    html = env.get_template("pkg_template.html").render(
        package_name=PACKAGE_NAME, package_files=files
    )
    output_dir = ROOT / PACKAGE_NAME
    output_dir.mkdir(exist_ok=True)
    (output_dir / "index.html").write_text(html, encoding="utf-8")
    print(f"Wrote {output_dir / 'index.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
