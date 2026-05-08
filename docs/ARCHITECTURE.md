# Architecture: zeevaro-packages

## Overview

`zeevaro-packages` is a **static-file private package index** built on GitHub Pages. It supports two ecosystems:

- **PyPI** — implements [PEP 503](https://peps.python.org/pep-0503/) (Simple Repository API) using plain HTML, enabling direct `pip`/`uv` installation via `--extra-index-url`
- **npm** — download-only index; GitHub Pages cannot implement the npm registry protocol, so package pages provide download links and SHA-256 checksums

No server, no database, no running process.

---

## Component diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│  Source repo  (private)                                             │
│                                                                     │
│  ┌──────────────┐   git tag push   ┌──────────────────────────────┐ │
│  │  Developer   │ ──────────────► │  release.yml                 │ │
│  └──────────────┘                 │  PyPI:  python -m build       │ │
│                                   │  npm:   npm pack              │ │
│                                   │  upload to GitHub Release     │ │
│                                   │  curl repository_dispatch     │ │
│                                   └──────────────────────────────┘ │
└──────────────────────────────────────────┬──────────────────────────┘
                                           │ repository_dispatch
                                           │ event_type: new-release
                                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  zeevaro/zeevaro-pypi  (public repo)                                │
│                                                                     │
│  ┌──────────────────────────────┐                                  │
│  │  update_packages.yml         │                                  │
│  │  1. pip install jinja2       │                                  │
│  │  2. python update_package.py │◄── PACKAGES_READ_PAT             │
│  │  3. git commit + push        │                                  │
│  │  4. deploy GitHub Pages      │                                  │
│  └──────────────────────────────┘                                  │
│                                                                     │
│  Static files served by GitHub Pages:                              │
│  ┌─────────────────────────────────────────────┐                   │
│  │  index.html          (root package list,     │                   │
│  │                       generated from         │                   │
│  │                       index_template.html)   │                   │
│  │  <package>/                                  │                   │
│  │    index.html        (version + hash list)   │                   │
│  │  pkg_template.html   (Jinja2 template)       │                   │
│  │  index_template.html (Jinja2 root template)  │                   │
│  └─────────────────────────────────────────────┘                   │
└──────────────────────────────────────────┬──────────────────────────┘
                                           │ GitHub Pages
                                           │ https://zeevaro.github.io/zeevaro-pypi/
                                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Consumer project                                                   │
│                                                                     │
│  PyPI: pip / uv reads index HTML                                    │
│        follows browser_download_url → github.com release asset     │
│        ~/.netrc provides PAT for github.com → S3 redirect          │
│                                                                     │
│  npm:  developer browses package page, downloads .tgz,             │
│        verifies SHA-256 checksum manually                           │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Data flow: new release

1. Developer tags a release (`vX.Y.Z`) in the source repo and pushes
2. `release.yml` in the source repo triggers:
   - **PyPI:** builds `<package>-X.Y.Z-py3-none-any.whl` and `<package>-X.Y.Z.tar.gz`
   - **npm:** runs `npm pack` producing `<package>-X.Y.Z.tgz`
3. Artifacts are uploaded to the GitHub Release page (private)
4. `release.yml` fires a `repository_dispatch` event to `zeevaro-pypi` with `{"tag": "vX.Y.Z"}`
5. `update_packages.yml` wakes up; runs `update_package.py`
6. `update_package.py` validates that every entry in `packages.json` has a required `ecosystem` field
7. For each package entry: loads the per-package SHA-256 cache from `<package>/file_cache.json`
8. For each non-draft, non-prerelease release asset matching the ecosystem's file type (`.whl`/`.tar.gz` for PyPI, `.tgz` for npm): uses cached hash if known, otherwise downloads and hashes via the API URL
9. Saves the updated cache back to `<package>/file_cache.json`
10. Renders `pkg_template.html` with the full file list → overwrites `<package>/index.html`
11. Regenerates root `index.html` from `index_template.html` (includes all packages with ecosystem badges)
12. Commits and pushes updated HTML and cache files
13. GitHub Pages redeploys (typically < 60 seconds)

---

## Data flow: pip install (PyPI packages)

1. `pip` sends `GET https://zeevaro.github.io/zeevaro-pypi/<package>/`
2. Receives HTML with `<a href="https://github.com/<org>/<repo>/releases/download/vX.Y.Z/<package>-X.Y.Z-py3-none-any.whl#sha256=HASH">` links
3. `pip` selects the best matching wheel, follows the URL
4. GitHub redirects to a pre-signed S3 URL (302) — GitHub requires auth for private repos
5. `~/.netrc` provides credentials for `github.com` → download proceeds
6. `pip` verifies the downloaded file's SHA-256 against the `#sha256=` fragment in the URL
7. Package is installed

---

## Data flow: npm package download

1. Developer browses `https://zeevaro.github.io/zeevaro-pypi/<package>/`
2. Page shows all versions with `.tgz` download links and SHA-256 checksums
3. Developer downloads the desired `.tgz`, verifies SHA-256 with `sha256sum`
4. Install locally: `npm install ./package-name-1.0.0.tgz`

**Why not a real npm registry?** The npm registry protocol requires specific API endpoints returning `application/json` responses. GitHub Pages serves all files as `text/html`, making it incompatible with `npm install` via a registry URL. The download-only approach is the correct static-site alternative.

---

## Ecosystem support

| Ecosystem | File types | Install method | `packages.json` field |
|---|---|---|---|
| `pypi` | `.whl`, `.tar.gz` | `pip install --extra-index-url ...` | `requires_python` (optional) |
| `npm` | `.tgz` | Download only | — |

The `ecosystem` field in `packages.json` is **required** for every entry. Missing it causes `update_package.py` to exit with an error.

---

## Key design decisions

### Why static HTML, not a real PyPI server?

A static GitHub Pages site is zero-maintenance, zero-cost, and has 100% uptime (GitHub SLA). A real PyPI server requires a running instance, storage, backups, and operational overhead.

### Why store artifacts on GitHub Releases, not in this repo?

Git is not designed for binary blobs. GitHub Releases are designed for binary artifacts — stored in object storage with CDN delivery.

### Why is the index repo public but the packages private?

PEP 503 only requires pip to read the HTML index. The HTML contains download URLs, not file contents. The download URLs point to GitHub Release assets, which are private (require auth). The HTML exposure is harmless.

### Why SHA-256 hashes in the index?

PEP 503 mandates the `#sha256=` URL fragment for supply-chain integrity. `pip` verifies the hash after download. For npm, the hash is displayed on the package page for manual verification. Hashes are computed by `update_package.py` at index-build time.

### Why `repository_dispatch` instead of a shared workflow?

`repository_dispatch` is GitHub's official cross-repo event mechanism. The dispatch is sent after release assets are confirmed uploaded, so the index is never updated before the files are available.

---

## File reference

| File | Role |
|---|---|
| `index.html` | Root package index — auto-generated from `index_template.html`; do not edit by hand |
| `index_template.html` | Jinja2 template for the root index — edit this instead of `index.html` |
| `<package>/index.html` | Per-package version listing with SHA-256 hashes — auto-generated, do not edit |
| `<package>/file_cache.json` | SHA-256 cache keyed by filename — persists across runs so only new assets are downloaded; auto-generated, do not edit |
| `<package>/data/index.html` | Full package metadata as JSON-in-HTML — auto-generated |
| `<package>/v<version>/index.html` | Per-version metadata as JSON-in-HTML — auto-generated |
| `<package>/latest/index.html` | Latest version metadata as JSON-in-HTML — auto-generated |
| `packages.json` | Registry of indexed packages — one object per package; `ecosystem` field is required |
| `pkg_template.html` | Jinja2 template used to generate per-package pages; ecosystem-aware via `{% if ecosystem == 'npm' %}` |
| `update_package.py` | Automation script — queries GitHub API, hashes new assets, updates cache, renders templates |
| `requirements.txt` | Python deps for `update_package.py` (jinja2 only) |
| `.github/workflows/update_packages.yml` | GitHub Actions workflow — triggered by dispatch or manually; deploys Pages |

---

## Security model

| Threat | Mitigation |
|---|---|
| Someone reads the public index and learns package names/versions | Acceptable — internal package names are not secrets |
| Someone reads the public index and learns download URLs | URL knowledge alone is insufficient; downloading requires a valid GitHub PAT |
| Supply chain attack via index manipulation | SHA-256 hashes in the index are computed from the actual artifacts; pip verifies them on download; npm users verify manually |
| Confused deputy (pip prefers `--extra-index-url` over `--index-url`) | Use unique organization-prefixed package names that cannot collide with public PyPI; always pin versions |
| PAT leaked in logs | `PACKAGES_READ_PAT` and `PYPI_INDEX_DISPATCH_PAT` are stored as GitHub secrets — never echoed to logs |
