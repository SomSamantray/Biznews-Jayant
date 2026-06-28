#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 -m py_compile "$ROOT/biznews-jayant/scripts/biznews_jayant.py" "$ROOT/biznews-jayant/scripts/lib/biznews_core.py"
python3 "$ROOT/biznews-jayant/scripts/biznews_jayant.py" --diagnose >/tmp/biznews-jayant-diagnose.json || true
if command -v uv >/dev/null 2>&1; then
  (cd "$ROOT" && uv run pytest)
else
  (cd "$ROOT" && python3 -m pytest)
fi
python3 /Users/apple/.codex/skills/.system/skill-creator/scripts/quick_validate.py "$ROOT/biznews-jayant"

