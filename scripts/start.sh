#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

PORT="${PORT:-8080}"
PYTHON="${PYTHON:-python3}"

if ! command -v "$PYTHON" &>/dev/null; then
  echo "Error: $PYTHON not found." >&2
  exit 1
fi

echo "==> Serving Zeevaro PyPI at http://localhost:$PORT"
echo "     Press Ctrl+C to stop."
echo ""

# Open browser after a short delay to let the server start
(sleep 0.5 && open "http://localhost:$PORT") &

"$PYTHON" -m http.server "$PORT" --bind 127.0.0.1
