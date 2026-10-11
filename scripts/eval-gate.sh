#!/usr/bin/env bash
# Offline eval gate (OKFT-cuj7): fixtures seeded into a throwaway catalogue, lexical re-measurement,
# compared with the frozen baseline. Only the literal S1 guard applies: the paraphrase guard needs the
# semantic arm (Voyage network + populated index), which CI has not.
set -euo pipefail
cd "$(dirname "$0")/.."

# the eval modules import okf.*; the PEP 723 header of okf-cli.py is the one place that declares its dependencies
py=(uv run --no-project --with-requirements cli/okf-cli.py python)

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

# the fixtures pin two bundle names; read them from the one place that defines them
for b in $("${py[@]}" -c "import sys; sys.path.insert(0, 'cli/eval'); import fixtures as f; print(f.CORRECT_BUNDLE, f.WRONG_BUNDLE)"); do
    mkdir -p "$tmp/catalogue/$b"
done
"${py[@]}" cli/eval/fixtures.py --root "$tmp/catalogue" --seed >/dev/null
"${py[@]}" cli/eval/runner.py --root "$tmp/catalogue" --golden cli/eval/golden.json --out "$tmp/lexical.json" >/dev/null
"${py[@]}" cli/eval/gate.py --literal-only --baseline "${1:-cli/eval/results/baseline-f0714b2.json}" --hybrid "$tmp/lexical.json"
