#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
npx -y skills@latest add "$ROOT/biznews-jayant" -g -y

