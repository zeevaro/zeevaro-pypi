# zeevaro-packages

A private package index for Zeevaro internal libraries, hosted on GitHub Pages. Supports both **Python (PyPI)** packages compliant with [PEP 503](https://peps.python.org/pep-0503/) and **npm** packages (download-only).

## What this is

This repository acts as a private package index. It stores **only HTML index pages and metadata** — no wheel, sdist, or tgz files. The actual artifacts live as assets on their respective GitHub Release pages.

- **Python packages** can be installed directly via `pip` or `uv` using `--extra-index-url`
- **npm packages** are download-only — GitHub Pages cannot serve a real npm registry, so package pages provide download links and SHA-256 checksums for manual verification

```bash
# Python packages
pip install <package-name> \
  --extra-index-url https://zeevaro.github.io/zeevaro-pypi/

# npm packages — browse the package page and download the .tgz directly
https://zeevaro.github.io/zeevaro-pypi/<package-name>/
```

## Packages indexed

See the [live index](https://zeevaro.github.io/zeevaro-pypi/) for the full list. The index page has ecosystem filter buttons (All / PyPI / npm).

## Quick links

- **Index URL:** `https://zeevaro.github.io/zeevaro-pypi/`

---

## How it works

```
Developer tags a release in a source repo
    │
    ▼
release.yml builds artifacts, uploads to GitHub Release
    │
    ▼
release.yml fires repository_dispatch → this repo
    │
    ▼
update_packages.yml runs update_package.py
    │  (queries GitHub Releases API; hashes only new assets — known hashes
    │   are read from <package>/file_cache.json)
    ▼
<package>/index.html and file_cache.json are updated
index.html (root) is regenerated from index_template.html
    │
    ▼
GitHub Pages redeploys — new version is instantly available
```

The artifacts remain private (GitHub Release assets on the source repo). The HTML index is public — it only exposes download URLs and SHA-256 hashes, not file contents. Downloading still requires a GitHub PAT via `.netrc`.

---

## `packages.json` schema

Every entry in `packages.json` requires the `ecosystem` field:

| Field | Required | Description |
|---|---|---|
| `repo` | yes | GitHub repo in `org/name` format |
| `package_name` | yes | Package name as it appears in the index. Scoped npm names like `@scope/name` are supported |
| `ecosystem` | yes | `"pypi"` or `"npm"` |
| `requires_python` | PyPI only | Python version constraint, e.g. `">=3.12"` |

Example:

```json
[
  {
    "repo": "your-org/your-python-pkg",
    "package_name": "your-python-pkg",
    "ecosystem": "pypi",
    "requires_python": ">=3.12"
  },
  {
    "repo": "your-org/your-npm-pkg",
    "package_name": "@your-org/your-npm-pkg",
    "ecosystem": "npm"
  }
]
```

---

## Repository secrets required

| Secret | Purpose |
|---|---|
| `PACKAGES_READ_PAT` | PAT with `repo` scope on all indexed source repos — used by `update_package.py` to list and download release assets for SHA-256 hashing |

---

## Installing Python packages (consumers)

### One-off install

```bash
pip install <package-name>==<version> \
  --extra-index-url https://zeevaro.github.io/zeevaro-pypi/
```

### `pyproject.toml` (uv-managed projects)

```toml
[project]
dependencies = [
    "<package-name>>=<version>",
]

[tool.uv]
extra-index-url = ["https://zeevaro.github.io/zeevaro-pypi/"]
```

### `requirements.txt` projects

```
--extra-index-url https://zeevaro.github.io/zeevaro-pypi/
<package-name>>=<version>
```

### Authentication

The HTML index is public, but the `.whl` files are private GitHub Release assets. Add to `~/.netrc`:

```
machine github.com login <your-github-username> password <your-github-pat>
```

The PAT needs `repo` scope (or fine-grained `Contents: read`) on the source repo.

---

## Downloading npm packages

Browse to the package page, e.g. `https://zeevaro.github.io/zeevaro-pypi/<package-name>/`, and download the `.tgz` file. Verify the SHA-256 checksum shown on the page against the downloaded file:

```bash
sha256sum <package-name>-<version>.tgz
```

---

## Manually rebuilding the index

If a release was missed or you need to backfill:

1. Go to **Actions** → **Update Package Index** → **Run workflow**

This re-queries all GitHub Releases for every indexed package. Known assets are read from `<package>/file_cache.json` (no re-download); only genuinely new or missing assets are hashed.

---

## Adding a new package

See [docs/ONBOARDING.md](docs/ONBOARDING.md) for the complete step-by-step guide.

## Secrets & authentication

See [docs/SECRETS.md](docs/SECRETS.md) for the full list of required PATs and where to add them.
