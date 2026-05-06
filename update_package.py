#!/usr/bin/env python3
"""Rebuild all package index pages from GitHub Releases.

Reads packages.json and regenerates <package-name>/index.html for each entry
by querying the GitHub Releases API and rendering pkg_template.html.

SHA-256 hashes are cached in <package-name>/file_cache.json so that only new
release assets are downloaded on each run. On first run (no cache file), the
script bootstraps from the existing index.html if present; otherwise it
downloads and hashes everything.

Environment variables:
    GITHUB_TOKEN  — PAT with repo scope on all source repos listed in packages.json.
                    Must be able to list releases and download release assets.

Usage:
    GITHUB_TOKEN=ghp_... python update_package.py
"""
from __future__ import annotations

import hashlib
import html as html_lib
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

try:
    from jinja2 import Environment, FileSystemLoader
except ImportError:
    sys.exit("jinja2 is required: pip install jinja2")

API_BASE = "https://api.github.com"
ROOT = Path(__file__).resolve().parent
PACKAGES = json.loads((ROOT / "packages.json").read_text())


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


def _extract_version(filename: str) -> str:
    base = filename[:-7] if filename.endswith(".tar.gz") else filename[:-4]
    parts = base.split("-")
    return parts[1] if len(parts) > 1 else "unknown"


def _version_tuple(v: str) -> tuple:
    try:
        return tuple(int(x) for x in v.split("."))
    except ValueError:
        return (0,)


def _group_by_version(files: list[dict]) -> list[dict]:
    seen: dict[str, list] = {}
    order: list[str] = []
    for f in files:
        v = f["version"]
        if v not in seen:
            seen[v] = []
            order.append(v)
        seen[v].append(f)
    order.sort(key=_version_tuple, reverse=True)
    return [{"version": v, "files": seen[v]} for v in order]


def _bootstrap_cache_from_html(html_path: Path, requires_python: str) -> dict:
    cache: dict = {}
    if not html_path.exists():
        return cache
    text = html_path.read_text(encoding="utf-8")
    pattern = re.compile(
        r'href="([^"]+#sha256=([a-f0-9]+))"[^>]*class="file-link">([^<]+)</a>'
    )
    for m in pattern.finditer(text):
        href, sha256, filename = m.group(1), m.group(2), html_lib.unescape(m.group(3))
        url = href.split("#sha256=")[0]
        cache[filename] = {
            "filename": filename,
            "url": url,
            "sha256": sha256,
            "requires_python": requires_python,
            "version": _extract_version(filename),
            "file_type": "whl" if filename.endswith(".whl") else "sdist",
        }
    return cache


def load_file_cache(pkg_dir: Path, requires_python: str) -> dict:
    cache_path = pkg_dir / "file_cache.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text())
    return _bootstrap_cache_from_html(pkg_dir / "index.html", requires_python)


def save_file_cache(pkg_dir: Path, cache: dict) -> None:
    (pkg_dir / "file_cache.json").write_text(
        json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8"
    )


def collect_files(repo: str, requires_python: str, token: str, cache: dict) -> list[dict]:
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
            if name in cache:
                if "api_url" not in cache[name]:
                    cache[name]["api_url"] = asset["url"]
                print(f"  Using cached hash for {name}")
                files.append(cache[name])
            else:
                print(f"  Hashing {name} ...", flush=True)
                digest = sha256_of_asset(asset["url"], token)
                record = {
                    "filename": name,
                    "url": asset["browser_download_url"],
                    "api_url": asset["url"],
                    "sha256": digest,
                    "requires_python": requires_python,
                    "version": _extract_version(name),
                    "file_type": "whl" if name.endswith(".whl") else "sdist",
                }
                cache[name] = record
                files.append(record)
    return files


def _public_file(f: dict) -> dict:
    return {
        "filename": f["filename"],
        "url": f["url"],
        "api_url": f.get("api_url", ""),
        "sha256": f["sha256"],
        "file_type": f["file_type"],
        "requires_python": f["requires_python"],
    }


def _json_to_html(data: dict, package_name: str, version: str) -> str:
    """Wrap JSON data in a simple HTML template."""
    json_str = json.dumps(data, indent=2)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{package_name} - {version}</title>
  <style>
    body {{
      font-family: monospace;
      background: #0f172a;
      color: #e2e8f0;
      padding: 20px;
    }}
    pre {{
      white-space: pre-wrap;
      word-wrap: break-word;
    }}
  </style>
</head>
<body>
<pre>{json_str}</pre>
</body>
</html>
"""


def write_html_outputs(output_dir: Path, pkg: dict, version_groups: list[dict], repo_meta: dict) -> None:
    """Write data/index.html and v/<version>/index.html + v/latest/index.html."""
    package_name = pkg["package_name"]
    versions = [g["version"] for g in version_groups]
    latest_version = versions[0] if versions else None

    data = {
        "package_name": package_name,
        "description": repo_meta.get("description") or "",
        "repo_url": repo_meta.get("html_url") or "",
        "requires_python": pkg["requires_python"],
        "latest_version": latest_version,
        "total_versions": len(versions),
        "versions": versions,
        "version_groups": [
            {"version": g["version"], "files": [_public_file(f) for f in g["files"]]}
            for g in version_groups
        ],
    }

    # Write main data file as /data/index.html
    data_dir = output_dir / "data"
    data_dir.mkdir(exist_ok=True)
    (data_dir / "index.html").write_text(_json_to_html(data, package_name, "data"), encoding="utf-8")
    print(f"  Wrote {data_dir / 'index.html'}")

    # Version directory
    v_dir = output_dir
    # v_dir.mkdir(exist_ok=True)

    for group in version_groups:
        ver = group["version"]
        ver_data = {
            "package_name": package_name,
            "version": ver,
            "requires_python": pkg["requires_python"],
            "files": [_public_file(f) for f in group["files"]],
        }

        ver_dir = v_dir / f"v{ver}"
        ver_dir.mkdir(exist_ok=True)
        (ver_dir / "index.html").write_text(_json_to_html(ver_data, package_name, ver), encoding="utf-8")

    if latest_version:
        latest_data = {
            "package_name": package_name,
            "version": latest_version,
            "requires_python": pkg["requires_python"],
            "files": [_public_file(f) for f in version_groups[0]["files"]],
        }

        latest_dir = v_dir / "latest"
        latest_dir.mkdir(exist_ok=True)
        (latest_dir / "index.html").write_text(_json_to_html(latest_data, package_name, latest_version), encoding="utf-8")

        print(f"  Wrote {latest_dir}/index.html + {len(versions)} version folders")


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        sys.exit("error: GITHUB_TOKEN environment variable is required")

    env = Environment(loader=FileSystemLoader(str(ROOT)), autoescape=True)
    template = env.get_template("pkg_template.html")

    for pkg in PACKAGES:
        print(f"\nProcessing {pkg['package_name']} ({pkg['repo']}) ...")
        output_dir = ROOT / pkg["package_name"]
        output_dir.mkdir(exist_ok=True)

        cache = load_file_cache(output_dir, pkg["requires_python"])
        files = collect_files(pkg["repo"], pkg["requires_python"], token, cache)
        save_file_cache(output_dir, cache)
        print(f"  Collected {len(files)} artifact(s)")

        repo_meta = github_api_get(f"{API_BASE}/repos/{pkg['repo']}", token)
        version_groups = _group_by_version(files)
        html = template.render(
            package_name=pkg["package_name"],
            package_files=files,
            version_groups=version_groups,
            description=repo_meta.get("description") or "",
            repo_url=repo_meta.get("html_url") or "",
            requires_python=pkg["requires_python"],
        )
        (output_dir / "index.html").write_text(html, encoding="utf-8")
        print(f"  Wrote {output_dir / 'index.html'}")
        write_html_outputs(output_dir, pkg, version_groups, repo_meta)

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
