#!/usr/bin/env bash
# Build wheel + sdist, validate metadata, install the wheel into a clean venv, run the console script.
# Output lands in a fresh tmpdir; the working tree stays clean (CI checks that).
set -euo pipefail
cd "$(dirname "$0")/.."

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

uv run --no-project --with build python -m build --outdir "$tmp/dist"
uvx twine check --strict "$tmp"/dist/*
uv venv -q "$tmp/venv"
uv pip install -q --python "$tmp/venv/bin/python" "$tmp"/dist/*.whl
"$tmp/venv/bin/okf-cli" --help >/dev/null
echo "pack-check ok: $(ls "$tmp/dist" | tr '\n' ' ')"
