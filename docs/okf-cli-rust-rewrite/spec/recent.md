---
type: Spec
title: "recent — EARS-Requirements RECENT-1..RECENT-15"
description: "List the most recently created concepts, newest first, dated from git add-history — the one read command the MCP surface does not expose yet."
tags:
  - okf-cli
  - ears
  - requirements
  - spec
---

# recent — EARS-Requirements RECENT-1..RECENT-15

`recent` answers "what was added lately" — a git-dated, newest-first view over a target or the whole store, the only navigation command whose ranking depends on repository history rather than the store's own content.

Die Querschnitts-Regeln gelten unverändert; hier steht nur, was `recent` darüber hinaus leistet.

## Requirements

### Scope

| ID | EARS-Requirement |
|----|------------------|
| RECENT-1 | WHERE a target names a bundle or a subdirectory, THE okf binary SHALL list only the concepts below that target. |
| RECENT-2 | WHERE no target is given, THE okf binary SHALL list concepts across the whole store. |
| RECENT-3 | WHERE the store is a bundle, THE okf binary SHALL treat the store root as the single scope. |

### Filter und Ranking

| ID | EARS-Requirement |
|----|------------------|
| RECENT-4 | WHERE `--type` is given, THE okf binary SHALL include only concepts whose frontmatter `type` equals that value. |
| RECENT-5 | WHERE `--tag` is given, THE okf binary SHALL include only concepts whose tags contain that value. |
| RECENT-6 | THE okf binary SHALL rank matching concepts newest-first by the git commit that added them. |
| RECENT-7 | THE okf binary SHALL sort concepts with no recorded add-commit after every dated concept. |
| RECENT-8 | THE okf binary SHALL report, in plain-text output, the count of listed concepts alongside the total count of matching concepts. |

### Git-Abhängigkeit

| ID | EARS-Requirement |
|----|------------------|
| RECENT-9 | IF the git binary is absent, THEN THE okf binary SHALL exit 3 and SHALL name git as the failing subsystem. |
| RECENT-10 | IF the store root sits outside any git repository, THEN THE okf binary SHALL exit 3 and SHALL name git as the failing subsystem. |
| RECENT-11 | WHERE a scope's repository fails to report its git history, THE okf binary SHALL list that scope's concepts as undated and SHALL announce the failure on stderr. |
| RECENT-12 | WHERE a concept has no recorded add-commit, THE okf binary SHALL list it as undated and SHALL note the count of such concepts on stderr. |
| RECENT-13 | WHERE a scope resolves to a broken symlink, THE okf binary SHALL exclude that scope from the listing and SHALL announce the exclusion on stderr. |

### Ausgabe und MCP

| ID | EARS-Requirement |
|----|------------------|
| RECENT-14 | WHERE JSON output is requested, THE okf binary SHALL emit each concept's add-timestamp in ISO-8601 form alongside the raw unix epoch value. |
| RECENT-15 | THE okf binary SHALL expose `recent` as an MCP tool alongside its command-line form. |

## Grounding

`cmd_recent()` (`cli/okf-cli.py:2394-2463`) resolves scopes via `_recent_scopes()` (`cli/okf-cli.py:2345-2391`), which itself calls `resolve_scopes()` (`cli/okf-cli.py:2940-2959`) and classifies each scope by repository through `_git_toplevel()` (`cli/okf-cli.py:2305-2319`). A missing git binary or a store root outside any repository exits 1 today at `cli/okf-cli.py:2355-2362` — RECENT-9/RECENT-10 keep the check, change the exit code and add the named subsystem. Per-repository history comes from `_git_add_events()` (`cli/okf-cli.py:2322-2342`) and `parse_add_events()` (`cli/okf-cli.py:2206-2225`); a failed `git log` in one repository degrades only that repository's concepts to undated (`cli/okf-cli.py:2400-2404`), matching RECENT-11. Broken-symlink scopes are dropped with a note at `cli/okf-cli.py:2370-2374`. Ranking is `rank_recent()` (`cli/okf-cli.py:2257-2269`), undated-last by design (comment at 2260-2264). The undated-count note is `cli/okf-cli.py:2439-2443`, the JSON branch with `iso_created()`/raw `ts` is `cli/okf-cli.py:2447-2454`, the footer line `cli/okf-cli.py:2461-2463`. Parser registration, including today's `--scope` flag that RECENT-1/RECENT-2 replace with a positional target: `cli/okf-cli.py:4259-4267`.

`recent` has no MCP tool today: `mcp/okf_mcp.py` registers `okf_index`/`okf_list`/`okf_check`/`okf_reindex`/`okf_refs`/`okf_rename`/`okf_wikilinks`/`okf_tags`/`okf_build_index`/`okf_prime`/`okf_info`/`okf_find`/`okf_read`/`okf_toc` (`mcp/okf_mcp.py:103-208`) and no `okf_recent` anywhere in the file — the gap AUDIT.md B06 names.

## Deltas gegenüber heute

| Delta | Deckung |
|---|---|
| `--scope` wird zum optionalen Positional | I02, COM-41 |
| Store als Bundle-Modus | D06 |
| Git-Ausfall: Exit 1 wird zu Exit 3, Subsystem benannt | I09, COM-24 |
| `recent` wird als MCP-Tool exponiert | B06 |
| Envelope statt barem Array | I04, COM-26 |

## Anmerkungen

**RECENT-9/RECENT-10 sind zwei Zeilen, nicht eine.** Fehlender git-Binary und ein Store-Root außerhalb jedes Repositories sind unabhängig auslösbare Bedingungen mit identischer Systemantwort — derselbe Grund, aus dem COM-29 bis COM-31 gesplittet sind.

**RECENT-11/RECENT-12/RECENT-13 sind kommando-spezifische Instanzen des Degradations-Vertrags aus COM-19**, nicht dessen Wiederholung: COM-19 sagt, dass eine Degradation angekündigt wird, diese drei Zeilen sagen, welche der drei `recent`-eigenen Degradationsklassen das sind — derselbe Aufbau wie CHECK-15 gegenüber COM-19.

## Offene Fragen

Ob ein partieller Git-Ausfall (ein Repository unter mehreren scope-tragenden Repositories) künftig den Gesamt-Exit auf 3 zieht, statt wie heute nur eine Degradations-Notiz zu bleiben (RECENT-11), ist nicht separat entschieden. Diese SPEC hält am heutigen Verhalten fest: nur der Totalausfall — kein git-Binary, oder der Store-Root selbst liegt außerhalb jedes Repositories — löst Exit 3 aus (RECENT-9/RECENT-10).
