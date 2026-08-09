---
type: Spec
title: "prime — EARS-Requirements PRIME-1..PRIME-5"
description: "One-shot agent onboarding: usage guide, command directory, live catalogue state and bundle TOC in a single report."
tags:
  - okf-cli
  - ears
  - requirements
  - spec
---

# prime — EARS-Requirements PRIME-1..PRIME-5

`prime` answers the question an agent asks before its first call into a store it has not worked with this session: what is this store, how do I retrieve from it, and is it in a state where retrieval actually works. It is a report, not a query — no filter, no target, one invocation.

The cross-cutting rules apply unchanged; this file states only what `prime` adds on top of them.

## Requirements

### Umfang des Reports

| ID | EARS-Requirement |
|----|------------------|
| PRIME-1 | THE okf binary SHALL combine a usage guide, the command directory, catalogue state and the bundle TOC into one report. |
| PRIME-2 | THE okf binary SHALL name in the catalogue state the bundle count, the concept count, the lexical index availability and the tag vocabulary state. |

### Darstellungsmodi

| ID | EARS-Requirement |
|----|------------------|
| PRIME-3 | WHERE --compact is given, THE okf binary SHALL render the bundle TOC as one name-and-count line per bundle in place of full bundle blocks. |
| PRIME-4 | WHERE --full is given, THE okf binary SHALL add each bundle's types and tags used to its TOC block. |

### Store-Modell (D06)

| ID | EARS-Requirement |
|----|------------------|
| PRIME-5 | WHERE the store is a bundle, THE okf binary SHALL report the store itself as the sole scope in place of a bundle TOC. |

## Grounding

`prime` lives in `cmd_prime()` (`cli/okf-cli.py:1633-1673`). The report assembly: intro prose `_PRIME_INTRO`/`_PRIME_INTRO_COMPACT` (`cli/okf-cli.py:1510`, `1553`), the command directory via `command_overview()` (called at `cli/okf-cli.py:1645` and `1650`; the registration it renders from is COM-33's concern, not repeated here), live catalogue state via `render_catalogue_state()` (`cli/okf-cli.py:1605-1630` — bundle/concept counts at `1610-1614`, lexical-index check at `1615-1619`, tag-vocabulary check at `1620-1625`), and the bundle TOC via `render_bundle_line()` (compact, `cli/okf-cli.py:494-498`) and `render_bundle_block()` (full, `cli/okf-cli.py:501-517`, the `types`/`tags` lines gated by its `full` parameter at `513-516`).

The `--full`/`--compact` flags are registered at `cli/okf-cli.py:4249-4256`. Today's `cmd_prime` branches on `args.compact` first (`cli/okf-cli.py:1643`) and only reads `args.full` in the non-compact branch (`1669`) — the two flags are not evaluated against each other, see Offene Fragen.

Today's store model is catalogue-only (per `_common.md`'s Grounding); PRIME-5 has no counterpart in the current code because the bundle store model does not exist yet.

## Deltas gegenüber heute

| Delta | Deckung |
|---|---|
| Bundle-Modus-Verhalten für `prime` (heute nicht existent — Catalogue ist die einzige Form) | D06 |

## Anmerkungen

**PRIME-5 ist die T07-Antwort für dieses Kommando.** Im Bundle-Modus (D06) gibt es keine Unter-Bundles zu listen — COM-6 macht den Store selbst zum einzigen Scope, also kollabiert das TOC auf genau diesen einen Eintrag statt auf eine Liste.

## Offene Fragen

Ob `--compact` und `--full` gleichzeitig übergeben werden dürfen und was in dem Fall gerendert wird, ist heute implizit (compact gewinnt, full wird stillschweigend ignoriert) und durch kein Finding gedeckt. Diese Datei trifft dazu keine Aussage.
