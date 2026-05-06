# zeevaro-pypi

A private Python package index for Zeevaro internal libraries, hosted on GitHub Pages and compliant with [PEP 503](https://peps.python.org/pep-0503/) (the Simple Repository API).

## What this is

This repository acts as a private PyPI server. It stores **only HTML index pages** — no wheel or sdist files. The actual package artifacts live as assets on their respective GitHub Release pages. This index tells `pip` and `uv` where to find them.

```bash
pip install <package-name> \
  --extra-index-url https://zeevaro.github.io/zeevaro-pypi/
```

## Packages indexed

See the [live index](https://zeevaro.github.io/zeevaro-pypi/) for the full list of available packages.

## Quick links

- **Index URL:** `https://zeevaro.github.io/zeevaro-pypi/`

---

## How it works

```
Developer tags a release in a source repo
    │
    ▼
release.yml builds wheel + sdist, uploads to GitHub Release
    │
    ▼
release.yml fires repository_dispatch → this repo
    │
    ▼
update_packages.yml runs update_package.py
    │  (queries GitHub Releases API, downloads each asset to compute SHA-256)
    ▼
<package>/index.html is rewritten with new download links
    │
    ▼
GitHub Pages redeploys — new version is instantly pip-installable
```

The wheel files remain private (GitHub Release assets on the source repo). The HTML index is public — it only exposes the download URL, not the file contents. Downloading the asset still requires a GitHub PAT via `.netrc`.

---

## Repository secrets required

| Secret | Purpose |
|---|---|
| `PACKAGES_READ_PAT` | PAT with `repo` scope on all indexed source repos — used by `update_package.py` to list and download release assets for SHA-256 hashing |

---

## Installing packages (consumers)

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

## Manually rebuilding the index

If a release was missed or you need to backfill:

1. Go to **Actions** → **Update Package Index** → **Run workflow**

This re-queries all GitHub Releases for every indexed package and regenerates the full index from scratch.

---

## Adding a new package

See [docs/ONBOARDING.md](docs/ONBOARDING.md) for the complete step-by-step guide.

## Secrets & authentication

See [docs/SECRETS.md](docs/SECRETS.md) for the full list of required PATs and where to add them.
