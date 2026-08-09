---
type: Spec
title: "fix-crosslinks — EARS-Requirements FIX-CROSSLINKS-1..FIX-CROSSLINKS-13"
description: "Rewrite von Markdown-Crosslinks in catalogue-root-absolute Form; die zugehörige Regel ist keine OKF-v0.1-Norm und hängt an einem Profil-Schalter."
tags:
  - okf-cli
  - ears
  - requirements
  - spec
---

# fix-crosslinks — EARS-Requirements FIX-CROSSLINKS-1..FIX-CROSSLINKS-13

`fix-crosslinks` rewritet Markdown-Links (`[label](target.md)`) im gewählten Scope in die kanonische catalogue-root-absolute Form (`/bundle/subdir/concept.md`). Die zugrundeliegende Konvention (`crosslink-format`) ist laut [check.md](./check.md), Abschnitt „Zuordnung zur Norm", **keine** OKF-v0.1-Klausel — §9 untersagt Ablehnung wegen kaputter Links, §5.1 verlangt sogar bundle-relative statt catalogue-root-absolute Form. Der Rewrite ist eine Erweiterung dieses Catalogues und gehört an einen Schalter, genau wie die gleichnamige `check`-Regel (CHECK-7).

Die Querschnitts-Regeln gelten unverändert; hier steht nur, was `fix-crosslinks` darüber hinaus leistet.

## Requirements

### Umfang des Rewrites

| ID | EARS-Requirement |
|----|------------------|
| FIX-CROSSLINKS-1 | WHERE no target is given, THE okf binary SHALL rewrite crosslinks in every concept file in the store. |
| FIX-CROSSLINKS-2 | WHERE a target names a bundle or a subdirectory, THE okf binary SHALL rewrite crosslinks only in the files below that target. |
| FIX-CROSSLINKS-3 | WHERE the store is a bundle, THE okf binary SHALL rewrite crosslinks with the bundle root as the single scope. |
| FIX-CROSSLINKS-4 | THE okf binary SHALL rewrite no crosslink in a reserved file. |

### Norm-Zugehörigkeit

| ID | EARS-Requirement |
|----|------------------|
| FIX-CROSSLINKS-5 | THE okf binary SHALL bind crosslink rewriting to a named switch. |
| FIX-CROSSLINKS-6 | WHERE the active profile leaves crosslink rewriting disabled, THE okf binary SHALL rewrite no file. |

### Kandidaten und Kanonisierung

| ID | EARS-Requirement |
|----|------------------|
| FIX-CROSSLINKS-7 | THE okf binary SHALL rewrite into catalogue-root-absolute form a markdown link whose target ends `.md`, is not an `http://`, `https://` or `mailto:` address, and resolves to an existing file. |
| FIX-CROSSLINKS-8 | WHERE a link target is already in catalogue-root-absolute form, THE okf binary SHALL leave that link unchanged. |
| FIX-CROSSLINKS-9 | THE okf binary SHALL leave a markdown link inside a fenced or inline code span unmodified. |

### Unresolved Links

| ID | EARS-Requirement |
|----|------------------|
| FIX-CROSSLINKS-10 | WHERE a markdown link target does not resolve to an existing file, THE okf binary SHALL leave that link unchanged. |
| FIX-CROSSLINKS-11 | WHERE a markdown link target does not resolve to an existing file, THE okf binary SHALL report the file and the target as unresolved. |
| FIX-CROSSLINKS-12 | WHERE the rewrite leaves at least one unresolved crosslink, THE okf binary SHALL exit 1. |

### Ausgabe

| ID | EARS-Requirement |
|----|------------------|
| FIX-CROSSLINKS-13 | THE okf binary SHALL name, for each rewritten file, the file and the count of links changed. |

## Grounding

Link-Erkennung: `CROSSLINK_RE` (`cli/okf-cli.py:2828`). Zielauflösung inklusive der drei Interpretationsversuche (legacy bundle-root, bereits catalogue-root, bundle-relativ) und der Existenz-Anker: `resolve_crosslink_target()` (`cli/okf-cli.py:2831-2859`). Der eigentliche Rewrite pro Body inklusive Masking von Fences/Inline-Code: `rewrite_crosslinks_in_body()` (`cli/okf-cli.py:2862-2895`), Masking-Helfer `_mask_code_spans()`/`_unmask()` (`cli/okf-cli.py:2706-2723`, geteilt mit `fix-xml-tags`).

Datei-Iteration über den Scope, reservierte Dateien ausgeschlossen: `fix_crosslinks()` (`cli/okf-cli.py:2898-2920`), `RESERVED` (`cli/okf-cli.py:31`). Scope-Auflösung `[TARGET]` -> `[(bundle, bundle_path), ...]`: `resolve_scopes()` (`cli/okf-cli.py:2940-2959`), heute ohne eigenen Bundle-Einzelmodus (D06 fehlt dort). Kommando-Einstieg inkl. Zielpfad-Validierung: `cmd_fix_crosslinks()` (`cli/okf-cli.py:2923-2937`) — validiert heute mit `os.path.isdir` und bricht mit Exit 1 ab; Registrierung: `cli/okf-cli.py:4206-4209` (`--check` als heutige Dry-run-Flagge, kein `--apply`-Gegenstück).

Für die Norm-Zuordnung: kein heutiges Gegenstück existiert — `cmd_fix_crosslinks()` prüft keinen Schalter und läuft unconditional bei jedem Aufruf.

## Deltas gegenüber heute

| Delta | Deckung |
|---|---|
| `--check` entfällt zugunsten von `--apply`; Dry-run wird Default | I03, COM-29–COM-32 |
| Rewrite an einen Profil-Schalter gebunden statt unconditional | D05, vgl. CHECK-7/CHECK-8 |
| Exit-Code spiegelt unresolved Links statt immer 0 | COM-22, I09 |
| Zielpfad-Validierung liefert Exit 2 statt Exit 1 | COM-23, I09 |

## Anmerkungen

**FIX-CROSSLINKS-5/6 übertragen CHECK-7/CHECK-8 auf den Fix.** `crosslink-format` ist als `check`-Regel bereits an einen Schalter gebunden (D05, CHECK-7). Der Fix implementiert exakt diese Konvention gegen den Store — ohne dieselbe Bindung würde der Rewrite unter dem `okf`-Profil Dateien anfassen, deren `check`-Lauf im selben Profil dieselbe Form gar nicht verlangt. Die beiden Zeilen halten Fix und Check konsistent, analog zur bereits im Code erprobten bundle-granularen `wikilink_checked_bundles`-Bindung.

**FIX-CROSSLINKS-11/12 spezialisieren COM-22, wiederholen es nicht.** COM-22 sagt nur „ein Sachbefund über den Store löst Exit 1 aus" — ohne festzulegen, was für `fix-crosslinks` als Sachbefund zählt. Ein Link, der nach dem Rewrite unresolved bleibt, ist ein Defekt im Store, den das Kommando selbst aufgedeckt hat; die beiden Zeilen benennen diesen konkreten Fall, den COM-22 offenlässt.

## Offene Fragen

Ob ein expliziter `fix-crosslinks`-Aufruf bei deaktiviertem Schalter still no-opt (FIX-CROSSLINKS-6, symmetrisch zu CHECK-8) oder stattdessen mit Exit 2 auf die Deaktivierung hinweist, ist durch D05 nicht entschieden — die konkrete Schalter-Semantik für explizit aufgerufene Mutations-Kommandos (statt passiv gescannter `check`-Regeln) ist Teil von T06.

Der Schaltername selbst ist T06 und wird hier bewusst nicht genannt.
