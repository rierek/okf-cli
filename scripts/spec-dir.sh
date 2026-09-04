#!/usr/bin/env bash
# Resolve the Rust-rewrite SPEC directory worktree-agnostically (D-siyu-07).
#
# `git rev-parse --git-common-dir` returns relative ("`.git`") from the
# main checkout (`repo/`) but absolute (`/…/repo/.git`) from a linked
# worktree -- verified both ways. Any fixed dirname-step-count on top of
# that is itself the same unspoken-assumption failure class this gate
# exists to close: it would invert the original defect (green only from
# `repo/`) into its mirror (green only from the worktree) instead of
# fixing it. So: absolutize first, then walk upward by CRITERION (a
# directory carrying both `repo/` and `docs/`), not by a fixed step count.
#
# Prints the resolved SPEC directory on stdout and exits 0 on success.
# Four failure classes, all Exit 3 (COM-24, `_common.md:70`; precedent
# `spec/log.md:54`, `spec/recent.md:67` -- both require exit 3 for a
# failing git subprocess), each with its OWN message naming subsystem
# "spec-dir" plus the checked path, so the reader knows WHICH unspoken
# assumption broke without opening this file (D-siyu-08):
#   1. not inside a git checkout at all;
#   2. the directory containing the git common dir cannot be resolved
#      (it vanished or became unreadable between discovery and use);
#   3. no ancestor directory carries both `repo/` and `docs/`;
#   4. that ancestor exists, but the SPEC subdirectory under `docs/` is
#      itself missing (renamed/moved/dissolved topic) -- checked BEFORE
#      printing, so a caller never receives a path that doesn't exist.
set -euo pipefail

gcd="$(git rev-parse --git-common-dir 2>/dev/null || true)"
if [ -z "$gcd" ]; then
  echo 'spec-check: subsystem "spec-dir" unavailable -- not inside a git checkout' >&2
  exit 3
fi

dparent="$(dirname "$gcd")"
if ! d="$(cd "$dparent" 2>/dev/null && pwd)"; then
  echo "spec-check: subsystem \"spec-dir\" unavailable -- could not enter $dparent, derived from git common dir $gcd" >&2
  exit 3
fi
start="$d"
while [ "$d" != "/" ]; do
  if [ -d "$d/repo" ] && [ -d "$d/docs" ]; then
    spec="$d/docs/topics/okf-cli-rust-rewrite/spec"
    if [ ! -d "$spec" ]; then
      echo "spec-check: subsystem \"spec-dir\" unavailable -- hull found at $d, but SPEC directory missing at $spec" >&2
      exit 3
    fi
    printf '%s\n' "$spec"
    exit 0
  fi
  d="$(dirname "$d")"
done

echo "spec-check: subsystem \"spec-dir\" unavailable -- no hull (repo/+docs/) found walking up from $start" >&2
exit 3
