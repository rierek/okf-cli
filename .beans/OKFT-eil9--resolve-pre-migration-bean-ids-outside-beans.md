---
# OKFT-eil9
title: resolve pre-migration bean ids outside .beans
status: todo
type: task
priority: normal
created_at: 2026-08-10T11:59:12Z
updated_at: 2026-08-10T11:59:12Z
---

The bean id prefix of this repo changed from `okf-cli-` to `OKFT-` on 2026-08-10. Everything inside `.beans/` was migrated in commit `f7433bb`. Every citation outside `.beans/` still names the old ids and is therefore wrong.

## Origin

The rename arrived in the working tree from outside the PO-review session that found it — 91 files renamed, the `id` header line rewritten, `.beans.yml` switched to `prefix: OKFT-`, all uncommitted, while the review of `OKFT-0xkj` was running. The most likely source is the `beans-tui` instance running on the machine at the time. The PO decided to accept and complete the migration rather than roll it back.

Completion covered `.beans/` only: 333 references across 64 files, restricted to `okf-cli-<id>` where `<id>` matches an existing bean file, so the product name `okf-cli`, the `okf-cli.py` path and command examples such as `okf-cli find` stayed untouched.

## What is still wrong, and where

Four sinks carry old ids. They differ in whether they can be fixed at all.

**Fixable by editing:**

- `docs/LESSONS-LEARNED.md` — entries LL-24 through LL-33 cite leaf and epic ids throughout, e.g. `okf-cli-fv7y`, `okf-cli-pnyf`, `okf-cli-fu7o`, `okf-cli-0xkj`, `okf-cli-mk7m`.
- `docs/SSTD.md` — the current entry point and several previous ones cite `okf-cli-huow`, `okf-cli-0xkj` and every leaf of the follow-up epic.
- `~/dev/lean-stack/docs/lean-stack-okf/autonome-agent-kette.md` — the section "Drei blinde Flecken der Mutationsprobe" cites `okf-cli-0xkj` as its evidence epic (commit `1e0665f`, a different repository reached through a symlinked bundle).

**Not fixable, and must not be:**

- The commit history of this repo. Roughly 30 commit messages of the 2026-08-10 realization carry `Refs: okf-cli-<id>` footers, plus the bodies of several. Rewriting published history to repair a citation is not worth it, and the history is the one sink where the old ids are still *correct* — they name what those ids were at the time.

## The decision this needs

Two readings, and they are not equivalent:

1. **Rewrite the doc citations to the new ids.** The documents then agree with `beans list`, which is what a reader does next after reading them. The cost is that the documents no longer match the commit history they describe — a reader following `LL-31` to its commits finds `Refs: okf-cli-mk7m` in a repo where no such bean exists.
2. **Add a one-line mapping note to each affected document instead**, stating that ids of the form `okf-cli-<suffix>` in that file are the pre-2026-08-10 spelling of `OKFT-<suffix>`. Nothing is rewritten, every existing citation stays literally true of its own time, and the reader gets the rule once rather than a silent inconsistency.

Reading 2 is the recommendation. A prefix migration is exactly the case the "retire ids, never renumber them" rule exists for: the ids are cited in commit bodies and reviews that cannot be updated, so a mapping rule is cheaper and more honest than a sweep that can only ever be partial.

### Requirement 1: A reader can resolve an old id without guessing

**Objective:** As someone reading a lesson or a status document written before the migration, I want to be able to resolve the bean ids it names, so that a citation from before 2026-08-10 still leads me to the bean it means.

#### Acceptance Criteria

1. THE repository SHALL make the mapping from `okf-cli-<suffix>` to `OKFT-<suffix>` discoverable from every document that cites pre-migration ids.
2. THE repository SHALL NOT rewrite git commit messages to the new prefix.
3. IF a document is rewritten to the new ids THEN THE document SHALL still allow a reader to reach the corresponding commits, whose footers name the old ids.

#### Success Criteria

- SC-01: Starting from a pre-migration id in `docs/LESSONS-LEARNED.md`, a reader reaches the bean it names using only what the repository states.
- SC-02: `docs/SSTD.md` and the OKF concept in `~/dev/lean-stack` are covered by the same rule, whichever form it takes.

_Requirements: PO decision 2026-08-10 to accept and complete the prefix migration_

## Note on the two orphan ids

`okf-cli-capa` (15 references) and `okf-cli-p9h5` (2) have no bean file and were left untouched by the migration. Determine whether they are scrapped beans, beans from another store, or typos, before anyone concludes the migration missed them.
