# Onboarding Guide: Adding a New Package to zeevaro-packages

This guide covers everything needed to register a new internal package in this index. Jump to the relevant section:

- [Registering a Python (PyPI) package](#registering-a-python-pypi-package)
- [Registering an npm package](#registering-an-npm-package)

---

# Registering a Python (PyPI) package

Estimated time: **30–60 minutes** for initial setup, then fully automated on every release.

---

## Prerequisites

Before starting, confirm:

- [ ] The source repo exists on GitHub under the organization
- [ ] The package builds a `.whl` and/or `.tar.gz` via `python -m build`
- [ ] The package uses [Hatchling](https://hatch.pypa.io/latest/) or [setuptools](https://setuptools.pypa.io/) as its build backend (any PEP 517-compliant backend works)
- [ ] You have admin access to both the source repo and `zeevaro/zeevaro-pypi`
- [ ] You have a GitHub PAT with `repo` scope (for creating secrets)

---

## Step 1: Prepare the source package

### 1.1 Required `pyproject.toml` structure

Your package must produce valid artifacts via `python -m build`. A minimal working configuration:

```toml
[build-system]
requires = ["hatchling", "hatch-vcs"]
build-backend = "hatchling.build"

[project]
name = "your-package-name"          # use kebab-case; must be unique on public PyPI too
dynamic = ["version"]
description = "..."
requires-python = ">=3.12"
license = { text = "Proprietary" }

[tool.hatch.version]
source = "vcs"                       # version derived from git tags (e.g. v1.0.0)

[tool.hatch.build.hooks.vcs]
version-file = "src/your_package/_version.py"

[tool.hatch.build.targets.wheel]
packages = ["src/your_package"]
```

**Naming rules:**
- Use an organization-specific prefix for all internal packages (e.g. `zeevaro-auth`, `zeevaro-contracts`)
- This prevents name collisions with public PyPI packages, which eliminates the `--extra-index-url` confused-deputy risk
- The normalized name (hyphens ↔ underscores are equivalent under PEP 503) must be unique

### 1.2 Versioning

Tag releases with `vX.Y.Z` (e.g. `v1.0.0`). With `hatch-vcs`, the version is derived automatically from the latest tag. No manual version editing needed.

### 1.3 Verify the build locally

```bash
pip install build twine
python -m build
twine check dist/*
# Should output: PASSED for both wheel and sdist
```

---

## Step 2: Add a release workflow to the source repo

### 2.1 Create `.github/workflows/release.yml`

```yaml
name: Release

on:
  push:
    tags: ["v*"]

permissions:
  contents: write

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0          # required for hatch-vcs to read full tag history

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Build wheel and sdist
        run: |
          pip install --upgrade build
          python -m build

      - name: Validate artifacts
        run: |
          pip install --upgrade twine
          twine check dist/*

      - name: Create GitHub Release with artifacts
        uses: softprops/action-gh-release@v2
        with:
          files: dist/*
          generate_release_notes: true

      - name: Trigger zeevaro-pypi index update
        env:
          DISPATCH_PAT: ${{ secrets.PYPI_INDEX_DISPATCH_PAT }}
        run: |
          curl -s -o /dev/null -w "%{http_code}" \
            -X POST \
            -H "Authorization: Bearer $DISPATCH_PAT" \
            -H "Accept: application/vnd.github+json" \
            -H "X-GitHub-Api-Version: 2022-11-28" \
            https://api.github.com/repos/zeevaro/zeevaro-pypi/dispatches \
            -d "{\"event_type\": \"new-release\", \"client_payload\": {\"tag\": \"${GITHUB_REF_NAME}\"}}" \
          | grep -qE "^204$" && echo "Dispatch sent" || (echo "Dispatch failed" && exit 1)
```

### 2.2 Add secret to the source repo

In the source repo: **Settings → Secrets and variables → Actions → New repository secret**

| Secret name | Value |
|---|---|
| `PYPI_INDEX_DISPATCH_PAT` | A GitHub PAT with `repo` scope on `zeevaro/zeevaro-pypi` |

You can reuse the same token value across all source repos — one PAT is sufficient if it has `repo` scope on the org.

---

## Step 3: Register the package in this index repo

### 3.1 Add the package directory

Create the per-package directory and placeholder index page:

```bash
mkdir -p <your-package-name>
```

Create `<your-package-name>/index.html`:

```html
<!DOCTYPE html>
<html>
  <head><title>Links for your-package-name</title></head>
  <body><h1>Links for your-package-name</h1></body>
</html>
```

### 3.2 Register the package in `packages.json`

`packages.json` is the registry of all indexed packages. Add your package by appending a new entry:

```json
[
  // existing entries ...
  {
    "repo": "your-org/your-new-package",
    "package_name": "your-package-name",
    "ecosystem": "pypi",
    "requires_python": ">=3.12"
  }
]
```

The `"ecosystem"` field is **required**. `update_package.py` exits with an error if it is missing.

That's the only code change required — `update_package.py` loops over this list automatically and regenerates root `index.html` from `index_template.html`.

### 3.3 Ensure the `PACKAGES_READ_PAT` secret covers the new source repo

The `PACKAGES_READ_PAT` secret in `zeevaro-pypi` is used to download release assets and compute SHA-256 hashes. It must have `repo` scope on every source repo listed in `packages.json`.

**Option A (recommended): Use a single org-level PAT with `repo` scope**
One PAT covers all repos in the org. If your new package is in the same org, no change is needed.

**Option B: Extend the existing PAT's access**
If the new package is in a different org, generate a new PAT with access to both orgs and update the `PACKAGES_READ_PAT` secret value.

---

## Step 4: Backfill existing releases

The new package's `<your-package-name>/index.html` is currently a placeholder. Populate it with all existing releases by triggering the workflow manually:

1. Go to **Actions** → **Update Package Index** → **Run workflow** → **Run workflow**
2. Watch the logs — you should see `Hashing your-package-name-X.Y.Z-py3-none-any.whl ...` for each release (subsequent runs will show `Using cached hash for ...` instead)
3. After the workflow completes, verify: `curl -s https://zeevaro.github.io/zeevaro-pypi/your-package-name/`

---

## Step 5: Update consumer projects

Every project that depends on the new package needs three changes:

### 5.1 `pyproject.toml`

```toml
[project]
dependencies = [
    "your-package-name>=1.0.0",
]

[tool.uv]
extra-index-url = ["https://zeevaro.github.io/zeevaro-pypi/"]
```

If the project already has `extra-index-url` configured, just add the new dependency — no index change needed.

### 5.2 GitHub Actions CI

If the consumer's CI does not already have `.netrc` configured, add this step before `uv sync` or `pip install`:

```yaml
      - name: Configure credentials for private packages
        env:
          PACKAGES_PAT: ${{ secrets.PACKAGES_PAT }}
        run: |
          echo "machine github.com login x-token password $PACKAGES_PAT" >> ~/.netrc
          chmod 600 ~/.netrc
```

Add the secret `PACKAGES_PAT` (a PAT with read access to all private source repos) to the consumer repo's secrets.

### 5.3 Lock file regeneration

```bash
cd <consumer-project>
uv lock
git add uv.lock
git commit -m "chore: add <your-package-name> dependency"
```

### 5.4 Local development

Developers need `~/.netrc` configured with a PAT that has `repo` scope on the source repo. Document this in the consumer project's README.

---

## Step 6: Verify the full pipeline

```bash
# 1. Confirm the package page is live
curl -s https://zeevaro.github.io/zeevaro-pypi/your-package-name/
# Expected: HTML with <a href="...#sha256=..."> links for each release

# 2. Confirm pip can resolve the package
pip index versions your-package-name \
  --extra-index-url https://zeevaro.github.io/zeevaro-pypi/
# Expected: Available versions: 1.0.0, 1.0.1, ...

# 3. Confirm pip install works (requires ~/.netrc)
pip install your-package-name==1.0.0 \
  --extra-index-url https://zeevaro.github.io/zeevaro-pypi/ \
  --no-cache-dir
# Expected: Successfully installed your-package-name-1.0.0

# 4. Confirm uv sync works in the consumer
cd <consumer-project>
uv sync
python -c "import your_package_name; print(your_package_name.__version__)"
# Expected: 1.0.0

# 5. End-to-end pipeline test: cut a release, watch both workflows, verify new version
cd <source-repo>
git tag v1.0.1 && git push origin v1.0.1
# Watch: <source-repo> Actions → Release → should finish in ~2 min
# Watch: zeevaro-pypi Actions → Update Package Index → triggered within 30s of release
# Verify: curl -s https://zeevaro.github.io/zeevaro-pypi/your-package-name/ | grep "1.0.1"
```

---

## Checklist summary

```
Source repo
  [ ] pyproject.toml has correct [build-system] and versioning config
  [ ] python -m build && twine check dist/* passes locally
  [ ] .github/workflows/release.yml created with dispatch step
  [ ] PYPI_INDEX_DISPATCH_PAT secret added to source repo

zeevaro-pypi repo
  [ ] <package-name>/index.html placeholder created (optional — generated on first run)
  [ ] Package added to packages.json with ecosystem: "pypi" and requires_python
  [ ] PACKAGES_READ_PAT secret covers the new source repo
  [ ] Backfill workflow run triggered and completed successfully
  [ ] Root index.html regenerated and shows new package card with PyPI badge

Consumer projects (for each consumer)
  [ ] pyproject.toml dep added with version constraint
  [ ] [tool.uv] extra-index-url set (if not already present)
  [ ] uv.lock regenerated and committed
  [ ] CI workflow has .netrc setup step
  [ ] PACKAGES_PAT secret added to consumer repo (if not already present)
  [ ] Local ~/.netrc documented in consumer README
```

---

## Troubleshooting

### `pip` can't find the package

```
ERROR: Could not find a version that satisfies the requirement your-package-name
```

- Confirm the package page exists: `curl https://zeevaro.github.io/zeevaro-pypi/your-package-name/`
- Check that `--extra-index-url https://zeevaro.github.io/zeevaro-pypi/` is being passed
- If the page returns 404, GitHub Pages may not have deployed yet — wait 60 seconds and retry

### `pip` finds the package but download fails with 404

```
ERROR: HTTP error 404 while getting https://github.com/...
```

- The release asset URL in the index is stale or wrong — re-run the backfill workflow
- Confirm the release exists on the source repo's GitHub Releases page

### `pip` download fails with 401 or 403

```
ERROR: HTTP error 401 while getting https://github.com/...
```

- `.netrc` is missing or has wrong credentials
- Check `~/.netrc` has `machine github.com login x-token password <PAT>`
- Confirm the PAT has not expired and has `repo` scope on the source repo

### SHA-256 mismatch

```
ERROR: RECORD file has an invalid hash for ...
```

- The artifact was re-uploaded or replaced after the index was built — re-run the backfill workflow to recompute hashes

### `update_package.py` fails with `GITHUB_TOKEN` error

- The `PACKAGES_READ_PAT` secret is missing or expired in `zeevaro-pypi`
- Go to **Settings → Secrets → Actions** and update the value

### Dispatch step fails in source repo release.yml

```
Dispatch failed
```

- The `PYPI_INDEX_DISPATCH_PAT` secret is missing or expired in the source repo
- The PAT may not have `repo` scope on `zeevaro/zeevaro-pypi`
- Check: does the PAT owner have write access to `zeevaro/zeevaro-pypi`?

---

# Registering an npm package

Estimated time: **20–40 minutes** for initial setup, then fully automated on every release.

**Important:** This index is download-only for npm packages. GitHub Pages cannot serve the npm registry protocol, so packages cannot be installed with `npm install --registry ...`. Users browse the package page, download the `.tgz`, and verify the SHA-256 checksum.

---

## Prerequisites

Before starting, confirm:

- [ ] The source repo exists on GitHub under the organization
- [ ] The package has a valid `package.json` and can be packed with `npm pack`
- [ ] You have admin access to both the source repo and `zeevaro/zeevaro-pypi`
- [ ] You have a GitHub PAT with `repo` scope

---

## Step 1: Prepare the source package

### 1.1 Required `package.json` structure

```json
{
  "name": "@zeevaro/your-package-name",
  "version": "1.0.0",
  "description": "...",
  "main": "dist/index.js",
  "files": ["dist"],
  "scripts": {
    "build": "tsc"
  },
  "devDependencies": {
    "typescript": "^5.0.0"
  }
}
```

**Naming rules:**
- Use a scoped name (`@zeevaro/<name>`) to avoid collisions with public npm packages
- The sanitized directory name in this index is derived by stripping `@` and replacing `/` with `-`: `@zeevaro/my-pkg` → directory `zeevaro-my-pkg`

### 1.2 Versioning

Tag releases with `vX.Y.Z`. The release workflow reads the tag to set the version.

### 1.3 Verify the build locally

```bash
npm install
npm run build
npm pack --dry-run
# Should list the files that will be included in the .tgz
```

---

## Step 2: Add a release workflow to the source repo

### 2.1 Create `.github/workflows/release.yml`

```yaml
name: Release

on:
  push:
    tags: ["v*"]

permissions:
  contents: write

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: "20"

      - name: Install dependencies
        run: npm ci

      - name: Build
        run: npm run build

      - name: Pack
        run: npm pack

      - name: Create GitHub Release with artifact
        uses: softprops/action-gh-release@v2
        with:
          files: "*.tgz"
          generate_release_notes: true

      - name: Trigger zeevaro-pypi index update
        env:
          DISPATCH_PAT: ${{ secrets.PYPI_INDEX_DISPATCH_PAT }}
        run: |
          curl -s -o /dev/null -w "%{http_code}" \
            -X POST \
            -H "Authorization: Bearer $DISPATCH_PAT" \
            -H "Accept: application/vnd.github+json" \
            -H "X-GitHub-Api-Version: 2022-11-28" \
            https://api.github.com/repos/zeevaro/zeevaro-pypi/dispatches \
            -d "{\"event_type\": \"new-release\", \"client_payload\": {\"tag\": \"${GITHUB_REF_NAME}\"}}" \
          | grep -qE "^204$" && echo "Dispatch sent" || (echo "Dispatch failed" && exit 1)
```

### 2.2 Add secret to the source repo

In the source repo: **Settings → Secrets and variables → Actions → New repository secret**

| Secret name | Value |
|---|---|
| `PYPI_INDEX_DISPATCH_PAT` | A GitHub PAT with `repo` scope on `zeevaro/zeevaro-pypi` |

---

## Step 3: Register the package in this index repo

### 3.1 Register the package in `packages.json`

Add your npm package entry. The `ecosystem` field is **required** and must be `"npm"`. No `requires_python` field:

```json
[
  // existing entries ...
  {
    "repo": "zeevaro/your-npm-repo",
    "package_name": "@zeevaro/your-package-name",
    "ecosystem": "npm"
  }
]
```

`update_package.py` automatically creates the directory `zeevaro-your-package-name/` (sanitized from `@zeevaro/your-package-name`) and generates all index pages.

### 3.2 Ensure the `PACKAGES_READ_PAT` secret covers the new source repo

See the PyPI section above — the same PAT is used for both ecosystems.

---

## Step 4: Backfill existing releases

Trigger the workflow manually to populate the index with all existing releases:

1. Go to **Actions** → **Update Package Index** → **Run workflow** → **Run workflow**
2. Watch the logs — you should see `Hashing your-package-name-X.Y.Z.tgz ...` for each release
3. After the workflow completes, verify the page: `curl -s https://zeevaro.github.io/zeevaro-pypi/zeevaro-your-package-name/`

---

## Step 5: Verify

```bash
# 1. Confirm the package page is live and shows download links
curl -s https://zeevaro.github.io/zeevaro-pypi/zeevaro-your-package-name/
# Expected: HTML with .tgz download links and SHA-256 hashes for each release

# 2. Download a specific release manually
curl -L -o your-package-1.0.0.tgz \
  https://github.com/zeevaro/your-npm-repo/releases/download/v1.0.0/zeevaro-your-package-name-1.0.0.tgz

# 3. Verify the SHA-256 checksum against what the index page shows
sha256sum your-package-1.0.0.tgz

# 4. Install locally
npm install ./your-package-1.0.0.tgz
```

---

## Checklist summary (npm)

```
Source repo
  [ ] package.json has correct name, version, files
  [ ] npm pack --dry-run passes locally
  [ ] .github/workflows/release.yml created with dispatch step
  [ ] PYPI_INDEX_DISPATCH_PAT secret added to source repo

zeevaro-pypi repo
  [ ] Package added to packages.json with ecosystem: "npm" (no requires_python)
  [ ] PACKAGES_READ_PAT secret covers the new source repo
  [ ] Backfill workflow run triggered and completed successfully
  [ ] Root index.html regenerated and shows new package card with npm badge
  [ ] Package page shows .tgz download links with SHA-256 hashes
```
