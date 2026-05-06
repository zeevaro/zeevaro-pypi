# Architecture: zeevaro-pypi

## Overview

`zeevaro-pypi` is a **static-file private PyPI index** built on GitHub Pages. It implements [PEP 503](https://peps.python.org/pep-0503/) — the Simple Repository API — using plain HTML files. No server, no database, no running process.

---

## Component diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│  Source repo  (private)                                             │
│                                                                     │
│  ┌──────────────┐   git tag push   ┌──────────────────────────────┐ │
│  │  Developer   │ ──────────────► │  release.yml                 │ │
│  └──────────────┘                 │  1. python -m build           │ │
│                                   │  2. twine check dist/*        │ │
│                                   │  3. upload to GitHub Release  │ │
│                                   │  4. curl repository_dispatch  │ │
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
│  │  index.html          (root package list)     │                   │
│  │  <package>/                                  │                   │
│  │    index.html        (version + hash list)   │                   │
│  │  pkg_template.html   (Jinja2 template)       │                   │
│  └─────────────────────────────────────────────┘                   │
└──────────────────────────────────────────┬──────────────────────────┘
                                           │ GitHub Pages
                                           │ https://zeevaro.github.io/zeevaro-pypi/
                                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Consumer project                                                   │
│                                                                     │
│  pip / uv reads index HTML                                          │
│  follows browser_download_url → github.com release asset           │
│  ~/.netrc provides PAT for github.com → S3 redirect (no auth)      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Data flow: new release

1. Developer tags a release (`vX.Y.Z`) in the source repo and pushes
2. `release.yml` in the source repo triggers, builds `<package>-X.Y.Z-py3-none-any.whl` and `<package>-X.Y.Z.tar.gz`
3. Both artifacts are uploaded to the GitHub Release page (private)
4. `release.yml` fires a `repository_dispatch` event to `zeevaro-pypi` with `{"tag": "vX.Y.Z"}`
5. `update_packages.yml` wakes up; runs `update_package.py`
6. `update_package.py` loads the per-package SHA-256 cache from `<package>/file_cache.json` (bootstrapped from the existing `index.html` if no cache file exists yet)
7. For each entry in `packages.json`: calls `GET /repos/<org>/<repo>/releases` (paginated); for each non-draft, non-prerelease asset — if the filename is already in the cache the stored hash is reused, otherwise the asset is downloaded via the API URL (Bearer token, S3 redirect followed automatically) and hashed
8. Saves the updated cache back to `<package>/file_cache.json`
9. Renders `pkg_template.html` with the full file list → overwrites `<package>/index.html`
10. Commits and pushes the updated HTML and cache files
10. GitHub Pages redeploys (typically < 60 seconds)
11. `pip install <package>==X.Y.Z --extra-index-url ...` now resolves the new version

---

## Data flow: pip install

1. `pip` sends `GET https://zeevaro.github.io/zeevaro-pypi/<package>/`
2. Receives HTML with `<a href="https://github.com/<org>/<repo>/releases/download/vX.Y.Z/<package>-X.Y.Z-py3-none-any.whl#sha256=HASH">` links
3. `pip` selects the best matching wheel, follows the URL
4. GitHub redirects to a pre-signed S3 URL (302) — GitHub requires auth for private repos
5. `~/.netrc` provides credentials for `github.com` → download proceeds
6. `pip` verifies the downloaded file's SHA-256 against the `#sha256=` fragment in the URL
7. Package is installed

---

## Key design decisions

### Why static HTML, not a real PyPI server?

A static GitHub Pages site is zero-maintenance, zero-cost, and has 100% uptime (GitHub SLA). A real PyPI server (`pypiserver`, Artifactory, etc.) requires a running instance, storage, backups, and operational overhead. For a small number of internal packages, static HTML is strictly better.

### Why store artifacts on GitHub Releases, not in this repo?

Git is not designed for binary blobs. Committing `.whl` files into a repo bloats history permanently and makes clones slow. GitHub Releases are designed for binary artifacts — they're stored in object storage with CDN delivery.

### Why is the index repo public but the packages private?

PEP 503 only requires pip to read the HTML index. The HTML contains download URLs, not file contents. The download URLs point to GitHub Release assets, which are private (require auth). The HTML exposure is harmless — knowing a URL is not sufficient to download the file without a valid PAT.

### Why SHA-256 hashes in the index?

PEP 503 mandates the `#sha256=` URL fragment for supply-chain integrity. `pip` verifies the hash after download — any tampered artifact is rejected. The hashes are computed by `update_package.py` at index-build time by downloading and hashing each artifact.

### Why `repository_dispatch` instead of a shared workflow?

`repository_dispatch` is GitHub's official cross-repo event mechanism. It requires no shared infrastructure, no webhook server, and no polling. The dispatch is sent by the source repo's `release.yml` after the release assets are confirmed uploaded, so the index is never updated before the files are available.

---

## File reference

| File | Role |
|---|---|
| `index.html` | Root PEP 503 index — one `<a>` per package |
| `<package>/index.html` | Per-package version listing with SHA-256 hashes — auto-generated, do not edit |
| `<package>/file_cache.json` | SHA-256 cache keyed by filename — persists across runs so only new assets are downloaded; auto-generated, do not edit |
| `packages.json` | Registry of indexed packages — one object per package with `repo`, `package_name`, and `requires_python` |
| `pkg_template.html` | Jinja2 template used by `update_package.py` to generate per-package pages |
| `update_package.py` | Automation script — queries GitHub API, hashes new assets, updates cache, renders template |
| `requirements.txt` | Python deps for `update_package.py` (jinja2 only) |
| `.github/workflows/update_packages.yml` | GitHub Actions workflow — triggered by dispatch or manually; deploys Pages |

---

## Security model

| Threat | Mitigation |
|---|---|
| Someone reads the public index and learns package names/versions | Acceptable — internal package names are not secrets |
| Someone reads the public index and learns download URLs | URL knowledge alone is insufficient; downloading requires a valid GitHub PAT |
| Supply chain attack via index manipulation | SHA-256 hashes in the index are computed from the actual artifacts; pip verifies them on download |
| Confused deputy (pip prefers `--extra-index-url` over `--index-url`) | Use unique organization-prefixed package names that cannot collide with public PyPI; always pin versions |
| PAT leaked in logs | `PACKAGES_READ_PAT` and `PYPI_INDEX_DISPATCH_PAT` are stored as GitHub secrets — never echoed to logs |
