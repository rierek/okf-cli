# Migrate a bundle to OKF v0.2

Goal: every concept of `<bundle>` uses the OKF v0.2 frontmatter (`generated` instead of `timestamp`, `sources` instead of a `# Citations` list, plus `status`, `verified` and `stale_after` where the facts exist), the bundle uses managed listings and catalogue-root-absolute links, and `check` stays clean at every phase.

Normative source: OKF v0.2, https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md, sections "Provenance, trust, and lifecycle", "Actor convention", "Conformance", "Versioning" and "Changes from v0.1". Field rules (shapes, actors, time format): write-concepts.md, section 4; load it together with this file.

Needs git, grep and find: `command -v git grep find`.

## Contents

- Checklist
- What v0.2 adds
- What okf-cli checks, and what it does not
- Mapping from v0.1 and ad-hoc frontmatter
- Deciding values
- Procedure: phases 0 to 6
- Failure modes

## Checklist

Copy into your task list (todo tool or scratch list), tick one by one. Each phase ends at a review point: show the user `git diff --stat`, and commit only when the user asked for commits.

- [ ] Phase 0: baseline -> done when the outputs of `check`, `reindex --check` and both `grep` calls are saved as the work list, and the user agreed to the planned mapping
- [ ] Phase 1: structure -> done when `reindex <bundle> --check` reports `0 stale, 0 uncovered` and `check <bundle>` ends `OK — 0 violations` -> on failure: create missing index files or convert listings by hand, rerun phase 1
- [ ] Phase 2: normalisation -> done when `fix-crosslinks --check` reports `0 unresolved link(s)` and `check` shows no `tags-block-form` or `xml-like-tags` warning -> on failure: fix links by hand, rerun phase 2
- [ ] Phase 3: vocabulary -> done when `check` shows no `type-registered`, `tag-registered` or `english-keys` warning -> on failure: register or rename, rerun `check`
- [ ] Phase 4: frontmatter fields -> done when the phase 0 `grep` calls print nothing, except keys kept on purpose -> on failure: edit the listed files, rerun the `grep` calls
- [ ] Phase 5: trust and lifecycle -> done when every `status`, `verified` and `stale_after` value traces to a user statement or a record -> on failure: remove the value or ask the user
- [ ] Phase 6: verify -> done when every criterion in phase 6 holds -> on failure: back to the phase that owns the finding, rerun phase 6 until clean

## What v0.2 adds

- `generated: { by, at }`: author and time of the last meaningful content change. Replaces v0.1 `timestamp`.
- `sources`: list of materials the concept derives from, cited in the body by footnotes `[^<id>]`. Replaces the v0.1 body `# Citations` list.
- `verified`: confirmation events, independent of `generated`.
- `status`: `draft`, `stable` (default) or `deprecated`.
- `stale_after`: absolute time from which the content counts as stale.
- `okf_version: "0.2"`: optional, only in the frontmatter of the bundle-root `index.md`.
- Also new, not needed for a plain migration: `type: Attested Computation` with `runtime`, `parameters`, `computation`, `executor`, `attester`.

Unchanged from v0.1: required `type`, recommended `title`, `description`, `resource`, `tags`, reserved `index.md` and `log.md`, markdown links. Extra keys are allowed.

## What okf-cli checks, and what it does not

- No migrator exists. Every frontmatter change below is a manual edit; okf-cli handles only the structural steps.
- `check` enforces the v0.2 hard rules (frontmatter block present, non-empty `type`, no `type` in reserved files) plus local rules: tag block form, link form, registered types and tags, file names, asset placement, canon and ctx integrity.
- `check` does not validate `generated`, `sources`, `verified`, `status`, `stale_after` or `okf_version`, and does not parse YAML. A misspelled or malformed v0.2 field passes `check`. Verify those fields with the `grep` and `read` steps of phase 6.

## Mapping from v0.1 and ad-hoc frontmatter

| Old | v0.2 | Rule |
|---|---|---|
| `timestamp: <t>` | `generated: { by: <actor>, at: <t> }` | Keep the instant. Add an offset when missing (a bare date becomes `<date>T00:00:00Z`). |
| `date`, `created`, `updated`, `modified` | `generated.at` | Use the last meaningful content change. |
| `author: <name>` | `generated.by: human:<id>` | Only when the user confirms that person wrote the current text: the key alone does not prove it. Otherwise (no confirmation, or you cannot ask) keep `author` as an extra key and name the concept in your report. |
| `source`, `url`, `link`, `references` | `sources` entries | One entry per material: `resource` required, `id` when cited, `title` when known. |
| Body section `# Citations` | `sources` entries plus `[^<id>]` footnotes | Move every item, footnote the claims it supports, then delete the section. |
| `summary`, `excerpt`, `abstract` | `description` | One sentence. |
| `keywords`, `categories` | `tags` | Block list, registered tags. |
| `kind` or `category` used as the concept kind | `type` | A value from `TYPES.md`. |
| `name` | `title` | |
| `draft: true` | `status: draft` | |
| `deprecated: true`, `obsolete: true` | `status: deprecated` | Or `archive` the concept. |
| `review_by`, `expires`, `valid_until` | `stale_after` | Absolute time with offset. |
| `reviewed_by` plus `reviewed_at`, `approved_by` | `verified: { by: human:<id>, at: <t> }` | Only for a review that happened. |
| Keys flagged by warning `english-keys` | English equivalents | `title`, `description`, `type`, `tags`, `generated.at`. |
| `superseded_by`, `resource`, other keys | keep | `superseded_by` only on `type: Decision`. |

## Deciding values

- `generated.by`: the author of the current text. Unknown: ask the user. No answer possible: leave `generated` out of that concept (`by` is required), keep its old `author` and date keys (`timestamp`, `created`, `date`, ...) unchanged (extra keys are allowed) and list the concept in your report; never write a placeholder such as `human:unknown`. Never put your own actor there unless you rewrote the content.
- `generated.at`: from the old key; otherwise the date of the last commit that changed the file: `git -C <catalogue>/<bundle> log -1 --format=%cI -- <path below the bundle>.md`.
- `verified`: only real confirmation events. A person who checked the content against its sources: `human:<id>`. An automated check (CI job, test, link checker): `process:<id>`. Migration is not verification; without evidence, omit the field. Unverified is an honest state.
- `status`: omit for current content. `draft` for incomplete or unreviewed content. `deprecated` for content kept only for history and inbound links.
- `stale_after`: only for facts that expire: versions, prices, limits, contacts, external API behaviour, definitions on a review cycle. Value = last verification (or `generated.at`) plus the review interval the user names, as an absolute time. Omit for timeless content such as principles or historical decisions.
- `sources`: every material the text was derived from. `id` in kebab-case, stable when the list is reordered. `author`, `usage_count`, `last_modified` only when known.

## Procedure: phases 0 to 6

Work in the repository that holds the bundle: `git -C <catalogue>/<bundle> rev-parse --show-toplevel`. Start from a clean working tree. Move to the next phase only when `check <bundle>` ends `OK — 0 violations`.

### Phase 0: baseline

```bash
git -C <catalogue>/<bundle> status --short
okf-cli --root <catalogue> check <bundle>
okf-cli --root <catalogue> reindex <bundle> --check
grep -rlE --include='*.md' '^(timestamp|date|created|updated|author|source|url|draft):' <catalogue>/<bundle>
grep -rl --include='*.md' '^# Citations' <catalogue>/<bundle>
```

Keep the output: it is the work list and the comparison point. Show the user the planned mapping before editing many files.

### Phase 1: structure

1. Every directory that holds concepts needs an `index.md`. List directories with `find <catalogue>/<bundle> -type d`; for each without `index.md`: `okf-cli --root <catalogue> reindex <bundle>/<subdir> --init`, then add an intro line under its H1.
2. Convert hand-written listings. Preview, then run:

   ```bash
   okf-cli --root <catalogue> reindex <bundle> --init --check
   okf-cli --root <catalogue> reindex <bundle> --init
   okf-cli --root <catalogue> reindex <bundle>
   ```

   `--init` replaces a single-section bullet list with an empty marker block; the listing is then generated from each concept's `title` and `description`. Move information that exists only in the old list into the concepts first. Multi-section indexes are skipped and flagged; convert them by hand, or with `--force` when they hold only headings and bullets.
3. `okf-cli --root <catalogue> check <bundle>`, review `git diff`.

### Phase 2: mechanical normalisation

```bash
okf-cli --root <catalogue> normalize-tags --scope <bundle>
okf-cli --root <catalogue> normalize-tags --scope <bundle> --apply
okf-cli --root <catalogue> fix-crosslinks <bundle> --check
okf-cli --root <catalogue> fix-crosslinks <bundle>
okf-cli --root <catalogue> fix-xml-tags <bundle> --check
okf-cli --root <catalogue> fix-xml-tags <bundle>
okf-cli --root <catalogue> check <bundle>
```

Fix every `unresolved` link that `fix-crosslinks` reports by hand.

### Phase 3: vocabulary

- `type-registered` warnings: add the type to `TYPES.md`, or change the concept to an existing type.
- `tag-registered` warnings (closed vocabulary): `tags <candidate>` to find the existing tag, then `merge-tags <old> --into <existing> --scope <bundle> --apply`, or `tags --register <tag> "<description>"` (writes at once).
- `english-keys` warnings: rename the keys.

Run `check <bundle>`.

### Phase 4: frontmatter fields (batches per subdirectory for large bundles)

For each file in the phase 0 work list, edit the frontmatter per the mapping table. Example, v0.1:

```markdown
---
type: Metric
title: Revenue
tags: [finance]
timestamp: '2026-05-28T22:53:05+00:00'
author: alice
---

Revenue sums amount per fiscal year.

# Citations

- https://wiki.example/finance/revenue-recognition
```

v0.2, with `alice` confirmed by the user as the author of the current text:

```markdown
---
type: Metric
title: Revenue
tags:
  - finance
generated: { by: human:alice, at: 2026-05-28T22:53:05+00:00 }
sources:
  - id: revenue-recognition
    resource: https://wiki.example/finance/revenue-recognition
    title: Revenue recognition policy
---

Revenue sums amount per fiscal year.[^revenue-recognition]

[^revenue-recognition]: Revenue recognition policy
```

After each batch: `okf-cli --root <catalogue> check <bundle>`, review `git diff`.

### Phase 5: trust and lifecycle

Add `status`, `verified` and `stale_after` only where the user or the records supply the facts (see "Deciding values"). Optionally declare the version in the bundle-root `index.md`:

```markdown
---
okf_version: "0.2"
---
# <Bundle title>
```

Never add `type` there.

### Phase 6: verify

```bash
okf-cli --root <catalogue> check <bundle> --strict
okf-cli --root <catalogue> reindex <bundle> --check
grep -rlE --include='*.md' '^(timestamp|date|created|updated|author|source|url|draft):' <catalogue>/<bundle>
grep -rl --include='*.md' '^# Citations' <catalogue>/<bundle>
grep -rL --include='*.md' '^generated:' <catalogue>/<bundle>
okf-cli --root <catalogue> read <bundle>/<concept-id>
okf-cli --root <catalogue> build-index --if-stale
okf-cli --root <catalogue> find "<term>" --scope <bundle>
```

Done when:

- `check --strict` ends `OK — 0 violations` and `reindex --check` reports `0 stale, 0 uncovered`.
- The first two `grep` calls print nothing, except keys you kept on purpose as extra keys.
- The third `grep` lists reserved files only (`index.md`, `INDEX-MAP.md`, `log.md`, `readme.md`).
- `read` on two or three samples shows well-formed `generated`, `sources` and footnotes.

## Failure modes

| Symptom | Cause | Fix |
|---|---|---|
| Hand-written index text lost | `reindex --init` replaced the old list | Restore from git; move the text into concepts or into prose above `## Contents`; run `--init` again |
| Concepts of a subdirectory missing from listings | Subdirectory without `index.md` | Phase 1, step 1 |
| `ERROR reserved-no-type` on `index.md` | `type` added next to `okf_version` | Remove `type` |
| `generated` without `by` | Author unknown | Ask the user; never fill in your own actor for text you did not write |
| `verified` added during migration | Migration mistaken for review | Remove it unless a real check happened |
| `check` clean but another OKF reader fails | Invalid YAML (for example an unquoted `: `) | Quote the value; `check` does not parse YAML |
| Footnote points nowhere | `[^<id>]` without a matching `sources` id or footnote line | Align the label, the `sources` id and the footnote definition |
| Diff contains unrelated changes | The working tree was not clean at phase 0 | Start clean; stage explicit paths only |
