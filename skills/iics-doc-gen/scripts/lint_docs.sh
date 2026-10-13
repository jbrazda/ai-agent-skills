#!/usr/bin/env bash
# lint_docs.sh - validate generated IICS asset docs: tab-normalize fenced
# blocks, prettier (fixes GFM table alignment / MD060), then
# markdownlint-cli2.
#
# Usage: lint_docs.sh <file.md> [more.md ...]
#
# Runs on Linux, macOS, and WSL. For native Windows PowerShell (no WSL),
# use lint_docs.ps1 instead - see ../../../docs/INSTALL.md.
#
# Exits non-zero if markdownlint-cli2 reports any remaining issues.
set -euo pipefail

if [ "$#" -eq 0 ]; then
  echo "usage: lint_docs.sh <file.md> [more.md ...]" >&2
  exit 2
fi

PYTHON=python3
command -v python3 >/dev/null 2>&1 || PYTHON=python

if ! command -v npx >/dev/null 2>&1; then
  echo "error: npx not found on PATH. Install Node.js 18+ (see docs/INSTALL.md)." >&2
  exit 3
fi

# Hard tabs can slip into fenced ```xml blocks copied verbatim from XML
# (MD010). Normalize to 4 spaces before linting rather than disabling the
# rule.
for f in "$@"; do
  if command -v "$PYTHON" >/dev/null 2>&1; then
    "$PYTHON" - "$f" <<'PY'
import sys
path = sys.argv[1]
text = open(path, encoding='utf-8').read()
if '\t' in text:
    open(path, 'w', encoding='utf-8').write(text.expandtabs(4))
PY
  fi
done

npx --yes prettier --prose-wrap preserve --write "$@"
npx --yes markdownlint-cli2 "$@"
