---
type: Spec
title: "visualize — EARS-Requirements VISUALIZE-1..VISUALIZE-6"
description: "Write a self-contained HTML graph of a bundle's concepts and their in-bundle links, guarded against writing into a nonexistent bundle."
tags:
  - okf-cli
  - ears
  - requirements
  - spec
---

# visualize — EARS-Requirements VISUALIZE-1..VISUALIZE-6

`visualize` renders one bundle's concepts and their in-bundle markdown links as a self-contained HTML graph, for a human exploring a bundle's structure visually. It is the one command whose careless argument handling used to mutate the catalogue on a typo — its bundle argument now has to exist before anything else runs (B02).

The cross-cutting rules apply unchanged; this file states only what `visualize` adds on top of them.

## Requirements

### Graph-Aufbau

| ID | EARS-Requirement |
|----|------------------|
| VISUALIZE-1 | THE okf binary SHALL render one graph node for every concept in the named bundle. |
| VISUALIZE-2 | THE okf binary SHALL render one graph edge for every markdown link from one concept to another concept within the same bundle. |

### Zielort und Ausgabe

| ID | EARS-Requirement |
|----|------------------|
| VISUALIZE-3 | WHERE --out names a path, THE okf binary SHALL write the graph to that path. |
| VISUALIZE-4 | WHERE --out is absent, THE okf binary SHALL write the graph to assets/viz.html under the named bundle. |
| VISUALIZE-5 | THE okf binary SHALL report the destination path and the node and edge counts after writing. |

### Vorbedingung (B02)

| ID | EARS-Requirement |
|----|------------------|
| VISUALIZE-6 | IF the named bundle does not exist, THEN THE okf binary SHALL create nothing and SHALL exit 2. |

## Grounding

`visualize` lives in `cmd_visualize()` (`cli/okf-cli.py:1726-1735`). Nodes and edges come from `bundle_graph()` (`cli/okf-cli.py:1693-1723`): one node per concept (`1699-1702`), one edge per in-bundle markdown link resolved against that bundle's concept set (`1703-1722`). The output path defaults to `<bundle>/assets/viz.html` and is overridable via `--out` (`cli/okf-cli.py:1729`); the success line names the path plus node/edge counts (`cli/okf-cli.py:1735`). The parser registers the required `bundle` positional and optional `--out` at `cli/okf-cli.py:4320-4323`.

In this checkout `cmd_visualize` has no existence check on `args.bundle`: it builds the output path from the unvalidated argument and calls `os.makedirs(os.path.dirname(out), exist_ok=True)` unconditionally (`cli/okf-cli.py:1732`), which is exactly B02 — a typo creates `<root>/<typo>/assets/` and writes a 0-node graph into it. The fix exists as commit `b5a9f1d` ("fix(cli): validate the bundle argument of index/visualize", branch `fix/b01-b02-bundle-validation`, not yet merged into this worktree): a new `require_bundle_dir(root, bundle)` helper tests `os.path.isdir(os.path.join(root, os.path.normpath(bundle)))` and, on failure, prints `not a directory: {bundle}` to stderr and exits 1 — still exit 1 there; VISUALIZE-6 unifies it to exit 2 under COM-23/COM-32.

## Deltas gegenüber heute

| Delta | Deckung |
|---|---|
| Existenzprüfung des bundle-Positionals vor jeder Dateisystem-Operation (heute keine) | B02, COM-32 |
| Exit 2 statt Exit 1 für den Nutzungsfehler | I09, COM-23 |

## Anmerkungen

**VISUALIZE-6 wiederholt COM-32 absichtlich.** `visualize` ist das Kommando, an dem B02 verifiziert wurde — ein Verzeichnis entstand für ein Argument, das nie existierte. Die Zeile macht den Vertrag an genau der Stelle prüfbar, an der er verletzt wurde, statt ihn nur querschnittlich zu behaupten. `check.md` begründet dieselbe bewusste Wiederholung an CHECK-13/CHECK-14 mit demselben Argument.

## Offene Fragen

Ob `visualize` unter der einheitlichen Mutations-Polarität (I03, COM-29–31) ein `--apply` bekommt, ist nicht entschieden. AUDITs A3-Verstoßliste nennt es nicht, obwohl es eine Datei schreibt — B02 prüft nur die Existenz des Arguments, nicht die Preview/Perform-Unterscheidung. Diese Datei trifft dazu keine Aussage.
