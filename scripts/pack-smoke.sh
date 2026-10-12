#!/usr/bin/env bash
# Packaging smoke: build the wheel, check its file list, install it into a throwaway venv,
# run the console script, prime and the install plan, then complete an MCP stdio initialize
# and one tool call against the installed copy. Everything lives under one tmpdir.
# Never write `check && echo ok`: under `set -e` a failing check in an && list does not abort.
set -euo pipefail
cd "$(dirname "$0")/.."
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
mkdir "$T/home" "$T/cat"

uv build --out-dir "$T/dist" -q
whl=("$T"/dist/*.whl)
files="$(python3 -m zipfile -l "${whl[0]}")"
for want in okf_cli/cli/okf-cli.py okf_cli/cli/okf_install.py okf_cli/cli/_okf okf_cli/cli/embeddings/build_tagvec.py \
            okf_cli/mcp/okf_mcp.py okf_cli/skills/okf/SKILL.md okf_cli/skills/okf/evals/evals.json; do
    grep -q "$want" <<<"$files" || { echo "FAIL: wheel lacks $want" >&2; exit 1; }
done
echo "ok   wheel file list"

uv venv -q "$T/venv" && uv pip install -q --python "$T/venv/bin/python" "${whl[0]}"
cli="$T/venv/bin/okf"
HOME="$T/home" "$cli" --help >/dev/null
echo "ok   okf --help"
HOME="$T/home" "$cli" --root "$T/cat" prime 2>/dev/null | grep -q "agent onboarding"
echo "ok   prime"
HOME="$T/home" "$cli" install --json --only claude,zsh | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["data"]["steps"], d'
echo "ok   install plan"

mcp="$(cd "$T" && "$T/venv/bin/python" -c 'import okf_cli,os; print(os.path.join(os.path.dirname(okf_cli.__file__), "mcp", "okf_mcp.py"))')"
python3 - "$mcp" "$T/cat" <<'EOF'
import json, subprocess, sys
p = subprocess.Popen(["uv", "run", "--with", "mcp<2", sys.argv[1]], stdin=subprocess.PIPE,
                     stdout=subprocess.PIPE, text=True)
def call(m, reply=True):
    p.stdin.write(json.dumps(m) + "\n"); p.stdin.flush()
    return json.loads(p.stdout.readline()) if reply else None
init = call({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
    "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "smoke", "version": "0"}}})
assert init["result"]["serverInfo"]["name"] == "okf", init
call({"jsonrpc": "2.0", "method": "notifications/initialized"}, reply=False)
r = call({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
          "params": {"name": "okf_prime", "arguments": {"root": sys.argv[2]}}})
assert "agent onboarding" in r["result"]["content"][0]["text"], r
p.terminate()
print("ok   MCP stdio initialize + okf_prime")
EOF
