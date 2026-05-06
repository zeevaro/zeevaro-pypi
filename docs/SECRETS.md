# Secrets & Authentication Setup

This document covers every GitHub secret and PAT required to run the full pipeline — index automation, source repo releases, and consumer project CI.

---

## Naming convention

**Dispatch tokens (PAT A):** one per source repo, named `<source-repo>-pypi-dispatch`.
This lets you revoke a single package's ability to update the index without affecting any other package.

**Read tokens (PAT B):** one per source repo, named `<package-name>-packages-read` and stored in consumer repos as `<PACKAGE_NAME>_READ_PAT`.

```
zeevaro-middleware-pypi-dispatch  →  PYPI_INDEX_DISPATCH_PAT  in zeevaro/zeevaro-middleware
zeevaro-auth-pypi-dispatch        →  PYPI_INDEX_DISPATCH_PAT  in zeevaro/zeevaro-auth (example)

zeevaro-middleware-packages-read  →  PACKAGES_READ_PAT              in zeevaro/zeevaro-pypi
                                  →  ZEEVARO_MIDDLEWARE_READ_PAT    in consumer repos
```

---

## Overview

```
Per-source-repo PAT A  ──►  zeevaro/zeevaro-pypi         secret: PACKAGES_READ_PAT
PAT B (one per pkg)    ──►  zeevaro/zeevaro-pypi         secret: PACKAGES_READ_PAT

zeevaro-middleware-pypi-dispatch  ──►  zeevaro/zeevaro-middleware   secret: PYPI_INDEX_DISPATCH_PAT
zeevaro-middleware-packages-read  ──►  zeevaro/zeevaro-pypi         secret: PACKAGES_READ_PAT
zeevaro-middleware-packages-read  ──►  tradex-core                  secret: ZEEVARO_MIDDLEWARE_READ_PAT
zeevaro-middleware-packages-read  ──►  tradex-admin                 secret: ZEEVARO_MIDDLEWARE_READ_PAT
                                       tradex                        (reuses existing GH_PAT)
```

---

## PAT types at a glance

| PAT | One per | Scoped to | Permission | Used for |
|---|---|---|---|---|
| **Dispatch (PAT A)** | Source repo | `zeevaro/zeevaro-pypi` | Contents: Read and write | Firing `repository_dispatch` after a release |
| **Read (PAT B)** | Source repo | That source repo | Contents: Read-only | Downloading release assets for hashing + consumer CI installs |

---

## Creating PATs

Navigate to:
**github.com → Profile picture → Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**

---

### PAT A — Dispatch token (one per source repo)

Create a separate token for **each** source repo whose packages are indexed here. If you revoke one, only that package loses the ability to trigger index updates.

#### Example: for `zeevaro-middleware`

**Settings**

| Field | Value |
|---|---|
| **Token name** | `zeevaro-middleware-pypi-dispatch` |
| **Expiration** | 1 year |
| **Resource owner** | `zeevaro` |

**Repository access**

Select **Only select repositories** → choose `zeevaro-pypi`

**Permissions** — Repository permissions:

| Permission | Level |
|---|---|
| **Contents** | Read and write |

Leave all other permissions at **No access**.

> Repeat this process for every source repo, changing only the token name. The repo access and permission level are identical for all dispatch tokens.

---

### PAT B — Read token (one per source repo)

Create a separate token for **each** source repo. This token is used by the index script to hash release assets, and by consumer CI to download wheels.

#### Example: for `zeevaro-middleware`

**Settings**

| Field | Value |
|---|---|
| **Token name** | `zeevaro-middleware-packages-read` |
| **Expiration** | 1 year |
| **Resource owner** | `zeevaro` |

**Repository access**

Select **Only select repositories** → choose `zeevaro-middleware`

**Permissions** — Repository permissions:

| Permission | Level |
|---|---|
| **Contents** | Read-only |

Leave all other permissions at **No access**.

> Repeat this process for every source repo, changing the token name and the selected repository. The permission level is identical for all read tokens.

---

> Copy each token value immediately — GitHub only shows it once.

---

## Step 2: Add secrets to each repo

For each repo: **Settings → Secrets and variables → Actions → New repository secret**

---

### `zeevaro/zeevaro-pypi` (this repo)

One secret per indexed package — each holds a different PAT B value:

| Secret name | Token | Purpose |
|---|---|---|
| `PACKAGES_READ_PAT` | `zeevaro-middleware-packages-read` | Used by `update_package.py` to list releases and download assets for SHA-256 hashing |

> When multiple packages from different private repos are indexed, each needs its own read token. See [Adding a new package](#adding-a-new-package) below.

---

### Source repos — dispatch secret

The secret name is the same in every source repo; only the PAT value differs:

| Repo | Secret name | Token |
|---|---|---|
| `zeevaro/zeevaro-middleware` | `PYPI_INDEX_DISPATCH_PAT` | `zeevaro-middleware-pypi-dispatch` |
| `zeevaro/zeevaro-auth` _(example)_ | `PYPI_INDEX_DISPATCH_PAT` | `zeevaro-auth-pypi-dispatch` |

---

### Consumer repos — read secret

| Repo | Secret name | Token | Purpose |
|---|---|---|---|
| `tradex-core` | `ZEEVARO_MIDDLEWARE_READ_PAT` | `zeevaro-middleware-packages-read` | Written to `~/.netrc` so CI can download private `.whl` assets |
| `tradex-admin` | `ZEEVARO_MIDDLEWARE_READ_PAT` | `zeevaro-middleware-packages-read` | Written to `~/.netrc` so CI can download private `.whl` assets |
| `tradex` | _(reuse existing `GH_PAT`)_ | — | Already present |

---

## Adding a new package

When a new package is registered in this index:

1. Create a new **PAT A** (`<new-package>-pypi-dispatch`) scoped to `zeevaro-pypi` with `Contents: Write`
2. Create a new **PAT B** (`<new-package>-packages-read`) scoped to the new source repo with `Contents: Read`
3. Add `PYPI_INDEX_DISPATCH_PAT` secret to the new source repo (PAT A value)
4. Add or update `PACKAGES_READ_PAT` in `zeevaro/zeevaro-pypi` — if the index script needs to read multiple private repos, the PAT must cover all of them (regenerate with both repos selected, or use separate secrets per package and update `update_packages.yml` accordingly)
5. Add `<PACKAGE_NAME>_READ_PAT` to every consumer repo that depends on the new package (PAT B value)

---

## PAT rotation

When a PAT expires or is revoked, regenerate it and update every secret that holds its value.

**Rotating a dispatch token (PAT A):**
1. Regenerate the specific `<package>-pypi-dispatch` token with the same settings
2. Update `PYPI_INDEX_DISPATCH_PAT` in that source repo only — other source repos are unaffected

**Rotating a read token (PAT B):**
1. Regenerate `<package>-packages-read` with the same settings
2. Update `PACKAGES_READ_PAT` in `zeevaro/zeevaro-pypi`
3. Update `<PACKAGE_NAME>_READ_PAT` in every consumer repo

**Revoking a single package's dispatch access:**
Simply revoke the `<package>-pypi-dispatch` token. That package can no longer trigger index updates. All other packages are unaffected.

---

## Local development

Developers running `uv sync` or `pip install` locally need credentials to download private release assets. Add to `~/.netrc`:

```
machine github.com login <your-github-username> password <your-fine-grained-pat>
```

Each developer creates their own fine-grained PAT with **Contents: Read-only** scoped to the specific source repo. Do not share service account tokens with individuals.

---

## Security notes

- **Never commit PAT values** to any repository, even in `.env` files
- **Never log PAT values** — the `.netrc` step writes to a file, not stdout
- Per-package PATs mean a compromised token has the **smallest possible blast radius** — one token can only affect one package
- Fine-grained PATs are scoped to specific repos, not your entire account
- If a PAT is accidentally exposed, revoke it at **Settings → Developer settings → Personal access tokens** and rotate the affected secrets only
