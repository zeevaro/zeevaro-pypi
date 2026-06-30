#!/usr/bin/env python3
"""Rebuild all package index pages from GitHub Releases.

Reads packages.json and regenerates <package-name>/index.html for each entry
by querying the GitHub Releases API and rendering pkg_template.html.

Each entry in packages.json must include an "ecosystem" field ("pypi" or "npm").

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
import shutil
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

# Maximum number of versions to keep in the index per package.
# Override per-package with "max_versions" in packages.json.
DEFAULT_MAX_VERSIONS = 10


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


def _extract_pypi_version(filename: str) -> str:
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


def _sanitize_pkg_dir(package_name: str) -> str:
    """Convert package_name to a filesystem/URL-safe directory name.

    '@scope/name' -> 'scope-name'
    'plain-pkg'   -> 'plain-pkg'  (unchanged)
    """
    return package_name.lstrip("@").replace("/", "-")


def _extract_npm_version(filename: str, sanitized_name: str) -> str:
    """Extract version from '<sanitized_name>-<version>.tgz'.

    Example: 'zeevaro-tradex-js-1.2.3.tgz', 'zeevaro-tradex-js' -> '1.2.3'
    """
    prefix = sanitized_name + "-"
    if filename.startswith(prefix) and filename.endswith(".tgz"):
        return filename[len(prefix):-4]
    return "unknown"


def _bootstrap_cache_from_html(html_path: Path, requires_python: str | None) -> dict:
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
            "version": _extract_pypi_version(filename),
            "file_type": "whl" if filename.endswith(".whl") else "sdist",
        }
    return cache


def load_file_cache(pkg_dir: Path, requires_python: str | None = None) -> dict:
    cache_path = pkg_dir / "file_cache.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text())
    return _bootstrap_cache_from_html(pkg_dir / "index.html", requires_python)


def save_file_cache(pkg_dir: Path, cache: dict) -> None:
    (pkg_dir / "file_cache.json").write_text(
        json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8"
    )


def collect_pypi_files(repo: str, requires_python: str | None, token: str, cache: dict, tag_prefix: str = "") -> list[dict]:
    """Return all non-draft, non-prerelease wheel and sdist assets for a repo."""
    releases = github_api_get(f"{API_BASE}/repos/{repo}/releases?per_page=100", token)
    print(f"  Found {len(releases)} release(s)")

    files = []
    for release in releases:
        if release.get("draft") or release.get("prerelease"):
            continue
        if tag_prefix and not release["tag_name"].startswith(tag_prefix):
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
                    "version": _extract_pypi_version(name),
                    "file_type": "whl" if name.endswith(".whl") else "sdist",
                }
                cache[name] = record
                files.append(record)
    return files


def collect_npm_files(repo: str, pkg: dict, token: str, cache: dict) -> list[dict]:
    """Return all non-draft, non-prerelease .tgz assets for a repo."""
    sanitized_name = _sanitize_pkg_dir(pkg["package_name"])
    tag_prefix = pkg.get("tag_prefix", "")
    releases = github_api_get(f"{API_BASE}/repos/{repo}/releases?per_page=100", token)
    print(f"  Found {len(releases)} release(s)")

    files = []
    for release in releases:
        if release.get("draft") or release.get("prerelease"):
            continue
        if tag_prefix and not release["tag_name"].startswith(tag_prefix):
            continue
        for asset in release.get("assets", []):
            name = asset["name"]
            if not name.endswith(".tgz"):
                continue
            if name in cache:
                cache[name].setdefault("api_url", asset["url"])
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
                    "version": _extract_npm_version(name, sanitized_name),
                    "file_type": "tgz",
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
        "requires_python": f.get("requires_python"),
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


def _prune_old_version_dirs(output_dir: Path, kept_versions: set[str]) -> None:
    """Remove v<version> directories that are no longer in the index."""
    for entry in output_dir.iterdir():
        if entry.is_dir() and entry.name.startswith("v") and entry.name not in {"latest", "data"}:
            version = entry.name[1:]
            if version not in kept_versions:
                shutil.rmtree(entry)
                print(f"  Pruned old version dir {entry.name}/")


def write_html_outputs(output_dir: Path, pkg: dict, version_groups: list[dict], repo_meta: dict) -> None:
    """Write data/index.html and v/<version>/index.html + v/latest/index.html."""
    package_name = pkg["package_name"]
    versions = [g["version"] for g in version_groups]
    latest_version = versions[0] if versions else None

    data = {
        "package_name": package_name,
        "ecosystem": pkg.get("ecosystem", "pypi"),
        "description": repo_meta.get("description") or "",
        "repo_url": repo_meta.get("html_url") or "",
        "requires_python": pkg.get("requires_python"),
        "latest_version": latest_version,
        "total_versions": len(versions),
        "versions": versions,
        "version_groups": [
            {"version": g["version"], "files": [_public_file(f) for f in g["files"]]}
            for g in version_groups
        ],
    }

    data_dir = output_dir / "data"
    data_dir.mkdir(exist_ok=True)
    (data_dir / "index.html").write_text(_json_to_html(data, package_name, "data"), encoding="utf-8")
    print(f"  Wrote {data_dir / 'index.html'}")

    v_dir = output_dir

    for group in version_groups:
        ver = group["version"]
        ver_data = {
            "package_name": package_name,
            "ecosystem": pkg.get("ecosystem", "pypi"),
            "version": ver,
            "requires_python": pkg.get("requires_python"),
            "files": [_public_file(f) for f in group["files"]],
        }

        ver_dir = v_dir / f"v{ver}"
        ver_dir.mkdir(exist_ok=True)
        (ver_dir / "index.html").write_text(_json_to_html(ver_data, package_name, ver), encoding="utf-8")

    if latest_version:
        latest_data = {
            "package_name": package_name,
            "ecosystem": pkg.get("ecosystem", "pypi"),
            "version": latest_version,
            "requires_python": pkg.get("requires_python"),
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

    for pkg in PACKAGES:
        if "ecosystem" not in pkg:
            sys.exit(f"error: package '{pkg.get('package_name')}' is missing the required 'ecosystem' field in packages.json")

    env = Environment(loader=FileSystemLoader(str(ROOT)), autoescape=True)
    template = env.get_template("pkg_template.html")
    index_template = env.get_template("index_template.html")

    pkg_summaries: list[dict] = []

    for pkg in PACKAGES:
        ecosystem = pkg["ecosystem"]
        sanitized_name = _sanitize_pkg_dir(pkg["package_name"])
        print(f"\nProcessing {pkg['package_name']} ({pkg['repo']}) [{ecosystem}] ...")
        output_dir = ROOT / sanitized_name
        output_dir.mkdir(exist_ok=True)

        cache = load_file_cache(output_dir, pkg.get("requires_python"))
        if ecosystem == "npm":
            files = collect_npm_files(pkg["repo"], pkg, token, cache)
        else:
            files = collect_pypi_files(pkg["repo"], pkg.get("requires_python"), token, cache, pkg.get("tag_prefix", ""))
        save_file_cache(output_dir, cache)
        print(f"  Collected {len(files)} artifact(s)")

        repo_meta = github_api_get(f"{API_BASE}/repos/{pkg['repo']}", token)
        version_groups = _group_by_version(files)

        max_versions = pkg.get("max_versions", DEFAULT_MAX_VERSIONS)
        if len(version_groups) > max_versions:
            pruned = version_groups[max_versions:]
            version_groups = version_groups[:max_versions]
            print(f"  Capped to {max_versions} versions (dropped {len(pruned)} oldest)")
        _prune_old_version_dirs(output_dir, {g["version"] for g in version_groups})

        # Rebuild files list from kept version_groups only (for template rendering)
        files = [f for g in version_groups for f in g["files"]]

        html = template.render(
            package_name=pkg["package_name"],
            ecosystem=ecosystem,
            package_files=files,
            version_groups=version_groups,
            description=repo_meta.get("description") or "",
            repo_url=repo_meta.get("html_url") or "",
            requires_python=pkg.get("requires_python"),
        )
        (output_dir / "index.html").write_text(html, encoding="utf-8")
        print(f"  Wrote {output_dir / 'index.html'}")
        write_html_outputs(output_dir, pkg, version_groups, repo_meta)

        pkg_summaries.append({
            "name": sanitized_name,
            "display_name": pkg["package_name"],
            "ecosystem": ecosystem,
            "description": repo_meta.get("description") or "",
            "url": sanitized_name + "/",
            "version_req": pkg.get("requires_python") or "",
            "latest_version": version_groups[0]["version"] if version_groups else "",
        })

    index_html = index_template.render(packages=pkg_summaries)
    (ROOT / "index.html").write_text(index_html, encoding="utf-8")
    print("\nWrote index.html")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
