# Contributing to zeevaro-pypi

This document covers how to make changes to the index infrastructure itself — the automation scripts, workflow, and templates. For adding a new package, see [ONBOARDING.md](ONBOARDING.md).

---

## Repository structure

```
zeevaro-pypi/
├── index.html                        # Root PEP 503 index (one <a> per package)
├── pkg_template.html                 # Jinja2 template for per-package pages
├── update_package.py                 # Index rebuild script
├── requirements.txt                  # Python deps for update_package.py
├── .github/
│   └── workflows/
│       └── update_packages.yml       # Triggered by dispatch or manually
├── <package-name>/
│   ├── index.html                    # Auto-generated — do not edit by hand
│   └── file_cache.json               # SHA-256 cache — auto-generated — do not edit by hand
├── README.md
├── ARCHITECTURE.md
├── ONBOARDING.md
└── CONTRIBUTING.md
```

**Rule:** Never manually edit `<package-name>/index.html` or `<package-name>/file_cache.json`. Both are overwritten on every workflow run. All changes to package index content must go through `update_package.py`.

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

You need a PAT with `repo` scope on the source repos listed in `PACKAGES`:

```bash
export GITHUB_TOKEN=ghp_your_token_here
python update_package.py
```

Inspect the output — each `<package-name>/index.html` should contain `<a href="...whl#sha256=...">` entries for every release.

### Testing the index with pip

Start a local HTTP server:

```bash
python -m http.server 8080
```

In another terminal:

```bash
pip install <your-package-name> \
  --extra-index-url http://localhost:8080/ \
  --no-cache-dir
```

---

## Modifying `update_package.py`

The script has no test suite. When making changes:

1. Run it locally against the real GitHub API (`GITHUB_TOKEN=... python update_package.py`)
2. Inspect `<package-name>/index.html` — confirm all versions appear with correct SHA-256 hashes
3. Verify the HTML is valid PEP 503: each link must end in `#sha256=<64-char-hex>`
4. Run `python -m http.server 8080` and install a package locally to confirm pip resolves correctly
5. Do **not** commit the generated `<package>/index.html` or `<package>/file_cache.json` changes — the workflow regenerates both; your PR should only contain changes to `update_package.py`, `packages.json`, templates, or root `index.html`

---

## Modifying `pkg_template.html`

The template is rendered by Jinja2. Template variables:

| Variable | Type | Description |
|---|---|---|
| `package_name` | `str` | Normalized package name (e.g. `<package-name>`) |
| `package_files` | `list[dict]` | List of file dicts with keys: `filename`, `url`, `sha256`, `requires_python` |

The rendered output must be valid PEP 503 HTML:
- Each file must be an `<a>` tag whose `href` is `{url}#sha256={sha256}`
- The `data-requires-python` attribute is optional but recommended
- No JavaScript, no CSS, no redirects — just plain HTML

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
