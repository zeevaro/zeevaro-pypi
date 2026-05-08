# Contributing to zeevaro-packages

This document covers how to make changes to the index infrastructure itself — the automation scripts, workflow, and templates. For adding a new package, see [ONBOARDING.md](ONBOARDING.md).

---

## Repository structure

```
zeevaro-pypi/
├── index.html                        # Root package index — AUTO-GENERATED, do not edit by hand
├── index_template.html               # Jinja2 template for the root index — edit this instead
├── pkg_template.html                 # Jinja2 template for per-package pages (ecosystem-aware)
├── update_package.py                 # Index rebuild script
├── requirements.txt                  # Python deps for update_package.py
├── packages.json                     # Registry — ecosystem field is REQUIRED on every entry
├── .github/
│   └── workflows/
│       └── update_packages.yml       # Triggered by dispatch or manually
├── <package-name>/
│   ├── index.html                    # Auto-generated — do not edit by hand
│   ├── file_cache.json               # SHA-256 cache — auto-generated — do not edit by hand
│   ├── data/index.html               # Full metadata JSON-in-HTML — auto-generated
│   ├── latest/index.html             # Latest version metadata — auto-generated
│   └── v<version>/index.html         # Per-version metadata — auto-generated
├── README.md
├── docs/
│   ├── ARCHITECTURE.md
│   ├── ONBOARDING.md
│   ├── SECRETS.md
│   └── CONTRIBUTING.md
```

**Rules:**
- Never manually edit `index.html` (root) — it is regenerated from `index_template.html` on every build run
- Never manually edit `<package-name>/index.html` or `<package-name>/file_cache.json` — both are overwritten on every workflow run
- All changes to package index content must go through `update_package.py`
- Every entry in `packages.json` must include the `"ecosystem"` field (`"pypi"` or `"npm"`)

---

## Local development

### Setup

```bash
git clone https://github.com/zeevaro/zeevaro-pypi.git
cd zeevaro-pypi
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Running `update_package.py` locally

You need a PAT with `repo` scope on the source repos listed in `packages.json`:

```bash
export GITHUB_TOKEN=ghp_your_token_here
python update_package.py
```

Inspect the output — each `<package-name>/index.html` should be generated, and root `index.html` should be regenerated from `index_template.html`.

For PyPI packages: confirm each page contains `<a href="...whl#sha256=...">` entries for every release.
For npm packages: confirm each page shows `.tgz` download links and SHA-256 checksums.

### Testing the index with a local server

```bash
bash scripts/start.sh
```

Or manually:

```bash
python -m http.server 8080
```

Test a PyPI package in another terminal:

```bash
pip install <your-package-name> \
  --extra-index-url http://localhost:8080/ \
  --no-cache-dir
```

---

## Modifying `update_package.py`

The script dispatches on the `ecosystem` field of each package entry. Key functions:

| Function | Ecosystem | Role |
|---|---|---|
| `collect_pypi_files()` | pypi | Fetches `.whl` and `.tar.gz` assets from GitHub Releases |
| `collect_npm_files()` | npm | Fetches `.tgz` assets from GitHub Releases |
| `_sanitize_pkg_dir()` | both | Converts `@scope/name` → `scope-name` for filesystem/URL use |
| `_extract_pypi_version()` | pypi | Extracts version from wheel/sdist filename |
| `_extract_npm_version()` | npm | Extracts version from `<sanitized-name>-<version>.tgz` |

When making changes:

1. Run it locally against the real GitHub API (`GITHUB_TOKEN=... python update_package.py`)
2. For PyPI: inspect `<package-name>/index.html` — confirm all versions appear with correct SHA-256 hashes and valid PEP 503 links
3. For npm: inspect `<package-name>/index.html` — confirm `.tgz` download links and SHA-256 hashes appear
4. For both: inspect root `index.html` — confirm ecosystem badges and filter buttons render correctly
5. Run `bash scripts/start.sh` and verify the UI works in a browser
6. Do **not** commit generated `<package>/index.html` or `<package>/file_cache.json` changes — the workflow regenerates both; your PR should only contain source file changes

---

## Modifying `pkg_template.html`

The template is rendered by Jinja2 and is ecosystem-aware via `{% if ecosystem == 'npm' %}` conditionals.

Template variables:

| Variable | Type | Description |
|---|---|---|
| `package_name` | `str` | Package name, may be a scoped npm name like `@scope/name` |
| `ecosystem` | `str` | `"pypi"` or `"npm"` |
| `package_files` | `list[dict]` | All file records with keys: `filename`, `url`, `sha256`, `file_type`, `requires_python` |
| `version_groups` | `list[dict]` | Files grouped by version: `[{"version": "1.0.0", "files": [...]}]` |
| `description` | `str` | GitHub repo description |
| `repo_url` | `str` | GitHub repo URL |
| `requires_python` | `str \| None` | Python version constraint (PyPI only; `None` for npm) |

File record fields:

| Field | PyPI | npm |
|---|---|---|
| `file_type` | `"whl"` or `"sdist"` | `"tgz"` |
| `requires_python` | version string | `None` |

The rendered PyPI output must be valid PEP 503 HTML: each file `<a>` tag's `href` must end in `#sha256=<64-char-hex>`.

---

## Modifying `index_template.html`

This Jinja2 template is rendered to `index.html` after every build run. Template variables:

| Variable | Type | Description |
|---|---|---|
| `packages` | `list[dict]` | One entry per processed package |

Per-package dict fields:

| Field | Description |
|---|---|
| `name` | Filesystem-safe name (e.g. `org-pkg-name` for `@org/pkg-name`) |
| `display_name` | Original name as in `packages.json` (may contain `@scope/`) |
| `ecosystem` | `"pypi"` or `"npm"` |
| `description` | GitHub repo description |
| `url` | Relative URL to package page (e.g. `zeevaro-middleware/`) |
| `version_req` | `requires_python` value for PyPI packages, empty string for npm |
| `latest_version` | Latest released version, or empty string if no releases |

---

## Modifying `update_packages.yml`

The workflow has three responsibilities:
1. Run `update_package.py` to regenerate HTML
2. Commit and push the updated HTML back to `main`
3. Deploy the repo to GitHub Pages

Key constraints:
- The `environment: github-pages` block is required for Pages deployment — do not remove it
- `concurrency: group: pages` prevents two simultaneous deployments from racing
- `permissions: pages: write` and `id-token: write` are required for the `deploy-pages` action

---

## Branching and review

All changes to this repo go through a pull request:

1. Create a branch: `git checkout -b feat/add-my-package`
2. Make changes
3. Open a PR — describe what package is being added or what infra change is being made
4. At least one review from a repo admin before merging
5. After merging to `main`, manually trigger **Update Package Index** once to confirm the automation still works

---

## Deployment

GitHub Pages deploys automatically on every push to `main` via the `deploy-pages` action inside `update_packages.yml`. There is no separate deployment step.

You can monitor the deployment status at:
`https://github.com/zeevaro/zeevaro-pypi/actions`

GitHub Pages typically reflects changes within 60 seconds of the workflow completing.
