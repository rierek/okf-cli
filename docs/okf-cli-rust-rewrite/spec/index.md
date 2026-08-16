---
type: Spec
title: "index — EARS-Requirements INDEX-1..INDEX-9"
description: "Catalogue table of contents or one bundle's index — the store's structure, not its content search."
tags:
  - okf-cli
  - ears
  - requirements
  - spec
---

# index — EARS-Requirements INDEX-1..INDEX-9

`index` answers "what does the store contain and how is it organised" — the whole catalogue's table of contents, or one bundle's own index.

Die Querschnitts-Regeln gelten unverändert; hier steht nur, was `index` darüber hinaus leistet.

## Requirements

### Scope

| ID | EARS-Requirement |
|----|------------------|
| INDEX-1 | WHERE no bundle is named, THE okf binary SHALL render the store's table of contents as one block per bundle. |
| INDEX-2 | WHERE a bundle is named, THE okf binary SHALL render that bundle's index. |
| INDEX-3 | WHERE the store is a bundle, THE okf binary SHALL treat the store root as the single scope. |

### Existenzprüfung des Bundle-Positionals

| ID | EARS-Requirement |
|----|------------------|
| INDEX-4 | IF the bundle positional names a path that is not an existing directory under the store root, THEN THE okf binary SHALL exit 2. |
| INDEX-5 | WHERE the bundle positional names an existing directory whose name starts with an underscore, THE okf binary SHALL accept that directory as a valid target. |

### `--full`/`--summary`-Trennung

| ID | EARS-Requirement |
|----|------------------|
| INDEX-6 | WHERE no bundle is named, THE okf binary SHALL accept `--full` to add each bundle's used types and tags to its table-of-contents block. |
| INDEX-7 | WHERE a bundle is named, THE okf binary SHALL accept `--summary` to print that bundle's structured summary in place of its raw index page. |

### Ausgabe

| ID | EARS-Requirement |
|----|------------------|
| INDEX-8 | WHERE JSON output is requested and a bundle is named, THE okf binary SHALL emit that bundle's concept list as structured data. |
| INDEX-9 | WHERE JSON output is requested and no bundle is named, THE okf binary SHALL emit every bundle's summary as structured data. |

## Grounding

`cmd_index()` (`cli/okf-cli.py:544-572`) branches on `args.bundle`: with a bundle it prints `INDEX-MAP.md`/`index.md` verbatim or, with `--full`, `render_bundle_block(root, args.bundle, full=True)` (`cli/okf-cli.py:553-568`); without one it renders every bundle via `list_bundles()` (`cli/okf-cli.py:72-79`) and `render_bundle_block()` (`cli/okf-cli.py:570-572`). The JSON branch is `cli/okf-cli.py:545-552`. Parser registration, including the single overloaded `--full`: `cli/okf-cli.py:4214-4222`.

Today `cmd_index()` carries no existence gate on `args.bundle` — a typo prints `# <typo>\n` and exits 0 (AUDIT.md B01, line 61). Branch `fix/b01-b02-bundle-validation` (commit `b5a9f1d`, not yet merged to `main`) adds `require_bundle_dir(root, bundle)` directly below `is_bundle_dir()` (`cli/okf-cli.py:68-71`) and calls it at the top of `cmd_index()`. It tests `os.path.isdir()` only, deliberately not `is_bundle_dir()`: the latter rejects `_`-prefixed names, and `index _archive` names a real, printable directory that the gate must not refuse. That asymmetry is what INDEX-4/INDEX-5 specify.

## Deltas gegenüber heute

| Delta | Deckung |
|---|---|
| Bundle-Positional bekommt eine Existenzprüfung vor der Ausgabe, Exit 2 statt Exit 0 | B01, COM-23 |
| Getippte, aber existierende `_`-Verzeichnisse bleiben adressierbar | B01 |
| Store als Bundle-Modus | D06 |
| `--full` mit Bundle-Argument wird zum eigenen Flag `--summary` | I08, D08 |
| Envelope statt eigenem JSON-Objekt | I04, COM-26 |

## Anmerkungen

**INDEX-4 wiederholt COM-23 absichtlich.** B01 benennt `index` als das Kommando, an dem die fehlende Existenzprüfung tatsächlich beobachtet und gefixt wurde — derselbe Grund, aus dem CHECK-13/CHECK-14 COM-21/COM-22 wiederholen: der Vertrag wird an der Stelle geprüft, an der der reale Bug saß, nicht nur querschnittlich behauptet.

**Die Flag-Namen `--full` und `--summary` sind durch D08 entschieden.** `--full` bleibt für die Katalog-TOC-Anreicherung ohne Bundle-Argument; `--summary` ist die explizite kompakte Ansicht mit Bundle-Argument, während dessen Default die vollständige Bundle-Ansicht bleibt.

## Offene Fragen

Ob das Bundle-Positional künftig auch `<bundle>/<subdir>` adressiert, wie `list`s und `recent`s Target das tun, ist nicht entschieden. Diese SPEC hält an der heutigen bundle-einzigen Granularität fest (`cli/okf-cli.py:4217-4218` kennt keine Subdir-Form).

