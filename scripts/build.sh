#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

# ── Validate environment ──────────────────────────────────────────────────────
if [[ -z "${GITHUB_TOKEN:-}" ]]; then
  echo "Error: GITHUB_TOKEN is not set." >&2
  echo "Usage: GITHUB_TOKEN=ghp_... ./build.sh" >&2
  exit 1
fi

# ── Python interpreter ────────────────────────────────────────────────────────
PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" &>/dev/null; then
  echo "Error: $PYTHON not found." >&2
  exit 1
fi

# ── Dependencies ──────────────────────────────────────────────────────────────
echo "==> Installing dependencies..."
"$PYTHON" -m pip install --quiet -r requirements.txt

# ── Generate package index pages ─────────────────────────────────────────────
echo "==> Rebuilding package index pages..."
"$PYTHON" update_package.py

echo "==> Done."
