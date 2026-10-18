---
title: "Conformance checks"
description: "Validate markdown frontmatter and links: okf check scans a catalogue against the OKF v0.2 hard rules and local invariants."
---

## Conformance checks: validate markdown frontmatter and links

**Run `okf check` to see which concepts break the OKF rules, then fix them before they reach readers or CI.**

All outputs on this page come from okf 0.2.4 (`rel-0-2-4-115-g91f54bf`), run against a copy of the test catalogue.

## How it looks

```text title="okf --root <catalogue> check recipes"
ERROR    okf/type/reserved-no-type recipes/readme.md  (reserved file must not carry `type`)
ERROR    kc/supersede/resolves recipes/salad.md  (superseded_by target does not resolve: recipes/soup)
ERROR    kc/asset/placement   recipes/shopping.txt  (non-md file outside assets/)
ERROR    kc/supersede/resolves recipes/stew.md  (superseded_by target does not resolve: handbook/ops/deploy)
WARNING  kc/link/crosslink-format recipes/bread.md  (non catalogue-absolute link(s) (use /bundle/…): pasta.md)
WARNING  kc/link/crosslink-format recipes/drafts/ideas.md  (non catalogue-absolute link(s) (use /bundle/…): pie.md)
WARNING  kc/link/crosslink-format recipes/overview.md  (non catalogue-absolute link(s) (use /bundle/…): pasta.md, soup.md)
WARNING  kc/frontmatter/tags-block-form recipes/overview.md  (tags field uses inline form — local convention requires YAML block-list)
WARNING  kc/link/crosslink-format recipes/salad.md  (non catalogue-absolute link(s) (use /bundle/…): soup.md)
WARNING  kc/supersede/scope   recipes/salad.md  (superseded_by used on non-Decision concept (type=Recipe))
WARNING  kc/frontmatter/tags-block-form recipes/soup.md  (tags field uses inline form — local convention requires YAML block-list)
WARNING  kc/markup/xml-like-tags recipes/soup.md  (angle-bracket placeholder(s) not in code-fence: <size>)
WARNING  kc/tag/registered    recipes/stew.md  (tag `misc` not registered in TAGS.md)
WARNING  kc/frontmatter/english-keys recipes/stew.md  (German frontmatter key(s): beschreibung, titel)
WARNING  kc/supersede/scope   recipes/stew.md  (superseded_by used on non-Decision concept (type=Recipe))
4 VIOLATIONS
[exit 4]
```

Each line has the form `SEVERITY  rule-id  path  (message)`. The last line counts the violations. Here the count is 4: only the `ERROR` lines count.

## Why it matters

**One command names every concept that breaks the rules, with the rule ID and the file.**

## What you get

- **A finding per rule and file.** Pass `<bundle>` or `<bundle>/<subdir>` to limit the scan. Without a target, `okf check` scans the whole catalogue.
- **Tuning.** `--ignore PATTERN` suppresses a rule: an exact rule ID or a prefix ending in `*` (`kc/*`, `okf/link/*`). The option is repeatable. Suppressed findings neither print nor count. `--strict` counts warnings toward the exit code.
- **A JSON envelope for CI.** `--json` prints one envelope. The findings are in `data.findings`, each with `rule`, `severity`, `path` and `message`. When findings exist, the envelope has `ok: false` and the same data rides in the error (`error.kind` is `non_conformant`).
- **Verification dates.** `okf verify --by ACTOR <bundle>/<concept-id>` records that a person or process checked a concept against its sources. It appends `{by, at}` to the `verified` list in the frontmatter. It writes at once, without a preview.
- **A wikilink report.** `okf wikilinks` lists every Obsidian `[[…]]` link with its status: `resolved`, `ambiguous` or `unresolved`.

```text title="okf --root <catalogue> verify --by human:erik handbook/glossary"
verified handbook/glossary by human:erik at 2026-10-18T19:48:00Z
```

```yaml title="handbook/glossary.md, frontmatter after verify"
verified:
  - by: human:erik
    at: 2026-10-18T19:48:00Z
```

```text title="okf --root <catalogue> wikilinks (excerpt)"
resolved   body        handbook/getting-started.md  [[glossary]]
resolved   body        handbook/getting-started.md  [[deploy|the deploy page]]
unresolved body        handbook/getting-started.md  [[does-not-exist]]
```

`okf wikilinks` exits 0 even when links are unresolved. Use `--unresolved` to list only the broken ones. The rule `kc/link/wikilink-resolvable` raises them as warnings in `okf check`.

## Details

- **Two rule families.** Rule IDs that start with `okf/` are the OKF hard rules (SPEC §9). IDs that start with `kc/` are local invariants of the catalogue, such as link format, registered tags and types, and ctx bundle health.
- **Severity.** `ERROR` sets the exit code. `WARNING` prints, but changes the exit code only with `--strict`.
- **Provenance fields.** The hard rules check the trust fields in the frontmatter: `generated`, `sources`, `verified` and `stale_after`. Example: `okf/trust/generated` reports a `generated` field without a non-empty `by`. See [Frontmatter and types](/okf-cli/reference/frontmatter-and-types/).
- **Exit code.** Findings give exit 4 (`NonConformant`). A target that is not a directory gives exit 3. See [JSON output and exit codes](/okf-cli/reference/json-output-and-exit-codes/).
- **No git, no drift check.** Outside a git repository, `okf check` prints `note: drift check skipped: the catalogue root is not inside a git repository` on stderr and runs the other rules.

## Limits

- The v0.2 rules apply only to bundles whose root `index.md` declares `okf_version: "0.2"`. Test: after the line `okf_version: "0.2"` was removed from `handbook/index.md`, `okf check handbook` no longer reported `okf/trust/generated` for `handbook/wiki-notes.md`.
- `okf check` is read-only. It reports problems and does not fix them.

## Reference

- [`okf check`](/okf-cli/reference/commands/okf-check/)
- [`okf verify`](/okf-cli/reference/commands/okf-verify/)
- [`okf wikilinks`](/okf-cli/reference/commands/okf-wikilinks/)
- [`okf ctx check`](/okf-cli/reference/commands/okf-ctx-check/)
- [JSON output and exit codes](/okf-cli/reference/json-output-and-exit-codes/)
