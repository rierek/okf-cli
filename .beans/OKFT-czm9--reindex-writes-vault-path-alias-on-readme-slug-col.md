---
# OKFT-czm9
title: reindex writes vault-path alias on README slug collision
status: todo
type: bug
priority: low
created_at: 2026-07-26T13:58:55Z
updated_at: 2026-07-26T13:58:55Z
---

Found while ingesting into `sproutling-okf` on 2026-07-26.

## Symptom

`okf-cli reindex <bundle>` rewrites crosslinks of files it was not asked to touch, and when two `README.md` files exist in different subdirs of one bundle it emits a **vault-style absolute path alias** instead of the plain bundle-relative slug.

Observed in `/Users/erik/dev/sproutling/docs/sproutling-okf`:

- `e2e-tests/FLOW-PREFLIGHT.md`, `e2e-tests/GUARDRAILS.md`, `e2e-tests/index.md` were modified although the ingest touched none of them.
- The rewrite turned `README.md` into `SPF_Sproutling/docs/sproutling-okf/e2e-tests/README.md` — a vault path, not a bundle-relative link.
- `index.md` already carried the same artifact in its legacy table (`README` -> `SPF_Sproutling/docs/sproutling-okf/README`), so this has happened before and was committed unnoticed.

## Why it matters

Two separate problems, and the second is the worse one:

1. **Blast radius:** an ingest into one subdir silently dirties unrelated files. An agent that stages with `git add -A` (or a human who does not read the diff) commits foreign rewrites. The `sproutling-okf` ingest only stayed clean because the agent reverted them by hand.
2. **Wrong link form:** the emitted path is a vault path. Per OKF invariant 4 crosslinks are bundle-relative (`/subdir/concept.md`), so these links are non-conformant and will not resolve after a move — the exact failure mode the bundle-relative form exists to prevent.

## Reproduce
- [ ] Bundle with `README.md` in two different subdirs (or root + subdir).
- [ ] Run `okf-cli --root <docs> reindex <bundle>`.
- [ ] `git status` — expect unrelated files modified; grep the diff for a path containing the vault folder name.

## Acceptance
- [ ] Slug resolution disambiguates same-named files without falling back to an absolute vault path.
- [ ] `reindex <bundle>/<subdir>` does not modify files outside that target.
- [ ] Existing artifacts in `sproutling-okf` (`index.md` legacy table, `e2e-tests/*`) are repaired — they are committed and currently wrong.
- [ ] A test covers the two-README collision.

## Note

`fix-crosslinks` claims it only rewrites when the target provably exists. Worth checking whether that guard shares the resolution code path with `reindex`, since the emitted target here does not exist in bundle-relative form.
