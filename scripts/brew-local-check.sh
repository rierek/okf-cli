#!/usr/bin/env bash
# Local check of packaging/homebrew/okf-cli.rb (OKFT-qg0o, D11): build the formula from source in a
# throwaway local tap, run `brew test`, and prove the installed binary without Python or uv.
# Nothing goes to a public tap, no tag is made or read, the real HOME is not written by okf itself.
# The formula has only `head` until a release carries the Go sources, so the local-only url, sha256
# and version are substituted here, never in the checked-in file. The check names the formula
# okf-cli-check and makes it keg-only: an installed okf-cli of the same machine stays untouched
# (same Cellar name would replace it, same bin/okf link would clash).
# Source = `git archive HEAD` of this checkout (commit first); the formula = the working-tree file.
# Needs brew with go, just and uv installed. `--ignore-dependencies` keeps brew from upgrading them: this
# check changes no installed formula besides its own throwaway keg. Run: just brew-local-check
set -euo pipefail
cd "$(dirname "$0")/.."
export HOMEBREW_NO_INSTALL_UPGRADE=1 HOMEBREW_NO_AUTO_UPDATE=1 HOMEBREW_NO_INSTALL_CLEANUP=1 HOMEBREW_NO_ANALYTICS=1 HOMEBREW_NO_ENV_HINTS=1
TAP=okf-check/local NAME=okf-cli-check FORMULA=packaging/homebrew/okf-cli.rb
T="$(mktemp -d)"
fail() { echo "FAIL: $*" >&2; exit 1; }
ok() { echo "ok   $*"; }
cleanup() {
    brew uninstall --force "$NAME" >/dev/null 2>&1 || true
    brew untap "$TAP" >/dev/null 2>&1 || true
    rm -rf "$T"
}
trap cleanup EXIT
taps_before="$(brew tap)"; tags_before="$(git tag -l)"

# AC-01: the checked-in formula
if grep -Eiq 'resource |Language::Python|python|virtualenv' "$FORMULA"; then fail "$FORMULA names Python"; fi
grep -q 'depends_on "uv"' "$FORMULA" || fail "no depends_on uv"
ok "formula: no resource, virtualenv or python; uv kept"

git archive --format=tar.gz --prefix=okf-cli-local/ -o "$T/src.tar.gz" HEAD
sha="$(shasum -a 256 "$T/src.tar.gz" | cut -d' ' -f1)"
brew tap-new --no-git "$TAP" >/dev/null
dest="$(brew --repository "$TAP")/Formula/$NAME.rb"
# `brew test` refuses a formula whose runtime dependency is outdated, and the install above must not upgrade
# anything: with an outdated uv the throwaway copy drops that one line (AC-01 already checked it above).
dropuv=0
if [ -n "$(brew outdated --quiet uv)" ]; then dropuv=1; echo "note: uv is outdated here; the throwaway formula omits depends_on uv"; fi
awk -v t="$T" -v sha="$sha" -v dropuv="$dropuv" '
    /^  depends_on "uv"/ && dropuv == 1 { next }
    /^class OkfCli < Formula/ { print "class OkfCliCheck < Formula"; next }
    /^  head / { print "  url \"file://" t "/src.tar.gz\""; print "  sha256 \"" sha "\""; print "  version \"0.0.0-local\""
                 print "  keg_only \"throwaway check, never linked\""; print "  env :std"; next }
    { print }' "$FORMULA" > "$dest"

# AC-02, AC-03
PATH="$(brew --prefix)/bin:/usr/bin:/bin" brew install --ignore-dependencies --build-from-source "$TAP/$NAME"
keg="$(brew --prefix "$NAME")"
test -x "$keg/bin/okf" || fail "no $keg/bin/okf"
ok "built from source: $keg/bin/okf"
brew test "$NAME"
ok "brew test"

# AC-04: throwaway HOME, package root next to the binary, the applied MCP registration points at an existing file
# `okf install` plans the MCP step only when `uv` is on PATH; a stub makes it present and is never run
mkdir "$T/home" "$T/stub"
printf '#!/bin/sh\nexit 0\n' > "$T/stub/uv"
chmod +x "$T/stub/uv"
env -i HOME="$T/home" PATH="$keg/bin:$T/stub" "$keg/bin/okf" install --apply --only claude >/dev/null
mcp="$(grep -Eo '[^" ]*/mcp/okf_mcp\.py' "$T/home/.claude.json" | head -n 1)"
test -f "$mcp" || fail "MCP registration points at a missing file: $mcp"
test -f "$keg/skills/okf/SKILL.md" || fail "no skills/okf/SKILL.md in the keg"
ok "the MCP registration runs $mcp"

# AC-05: find with a PATH that holds only the keg bin
hits="$(env -i PATH="$keg/bin" "$keg/bin/okf" --root tests/golden/catalogue find recipe)"
grep -q "^rank: 1" <<<"$hits" || fail "okf find printed no hits: $hits"
ok "okf find recipe: $(grep -c "^rank: " <<<"$hits") hits, exit 0"

# AC-06
cleanup
trap - EXIT
test "$taps_before" = "$(brew tap)" || fail "tap list changed"
test "$tags_before" = "$(git tag -l)" || fail "tags changed"
ok "taps and tags unchanged; throwaway tap and keg removed"
