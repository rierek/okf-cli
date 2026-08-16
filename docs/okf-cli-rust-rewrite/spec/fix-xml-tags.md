---
type: Spec
title: "fix-xml-tags — EARS-Requirements FIX-XML-TAGS-1..FIX-XML-TAGS-10"
description: "Wrap von Angle-Bracket-Platzhalterketten in Inline-Code gegen Obsidian-Fehlrendering; die zugehörige Regel ist keine OKF-v0.1-Norm und hängt an einem Profil-Schalter."
tags:
  - okf-cli
  - ears
  - requirements
  - spec
---

# fix-xml-tags — EARS-Requirements FIX-XML-TAGS-1..FIX-XML-TAGS-10

`fix-xml-tags` wrapt Angle-Bracket-Platzhalterketten (`<tag>`, `<tag>.<tag2>`, `<tag>.<tag2>.go`) im gewählten Scope in Inline-Code, weil Obsidian sie sonst als unclosed XML/HTML liest und fehlerhaft rendert. Die zugrundeliegende Regel (`xml-like-tags`) ist laut [check.md](./check.md), Abschnitt „Zuordnung zur Norm", **keine** OKF-v0.1-Klausel, sondern eine reine Obsidian-Rendering-Erweiterung dieses Catalogues — sie gehört an einen Schalter, genau wie die gleichnamige `check`-Regel (CHECK-7).

Die Querschnitts-Regeln gelten unverändert; hier steht nur, was `fix-xml-tags` darüber hinaus leistet.

## Requirements

### Umfang des Wraps

| ID | EARS-Requirement |
|----|------------------|
| FIX-XML-TAGS-1 | WHERE no target is given, THE okf binary SHALL wrap placeholder chains in every concept file in the store. |
| FIX-XML-TAGS-2 | WHERE a target names a bundle or a subdirectory, THE okf binary SHALL wrap placeholder chains only in the files below that target. |
| FIX-XML-TAGS-3 | WHERE the store is a bundle, THE okf binary SHALL wrap placeholder chains with the bundle root as the single scope. |
| FIX-XML-TAGS-4 | THE okf binary SHALL wrap no placeholder chain in a reserved file. |

### Norm-Zugehörigkeit

| ID | EARS-Requirement |
|----|------------------|
| FIX-XML-TAGS-5 | THE okf binary SHALL bind placeholder-chain wrapping to a named switch. |
| FIX-XML-TAGS-6 | WHERE the active profile leaves placeholder-chain wrapping disabled, THE okf binary SHALL wrap no file. |

### Kandidaten und Ausnahmen

| ID | EARS-Requirement |
|----|------------------|
| FIX-XML-TAGS-7 | THE okf binary SHALL wrap an angle-bracket placeholder chain outside a fenced or inline code span in inline code. |
| FIX-XML-TAGS-8 | WHERE an angle-bracket chain carries no dot and names a known safe HTML tag, THE okf binary SHALL leave that chain unwrapped. |
| FIX-XML-TAGS-9 | WHERE an angle-bracket chain forms a markdown autolink to a URL scheme, THE okf binary SHALL leave that chain unwrapped. |

### Ausgabe

| ID | EARS-Requirement |
|----|------------------|
| FIX-XML-TAGS-10 | THE okf binary SHALL name, for each wrapped file, the file and the count of chains wrapped. |

## Grounding

Ketten-Grammatik und Ausnahme-Vokabular: `_TAG`/`XML_TAG_CHAIN_RE` (`cli/okf-cli.py:2700-2701`), `SAFE_HTML_TAGS` (`cli/okf-cli.py:2702`, heute `br, hr, sub, sup, kbd, mark, code, wbr`), `AUTOLINK_RE` (`cli/okf-cli.py:2703`). Masking von Fences/Inline-Code (geteilt mit `fix-crosslinks`): `_mask_code_spans()`/`_unmask()` (`cli/okf-cli.py:2706-2723`). Ausnahmelogik (kein Dot + Safe-Tag, oder Autolink): `_is_ignorable_chain()` (`cli/okf-cli.py:2726-2732`). Reine Erkennung (von `check` genutzt): `find_xml_like_tags()` (`cli/okf-cli.py:2735-2739`), `check_xml_like_tags()` (`cli/okf-cli.py:2742-2746`).

Der eigentliche Wrap pro Datei inklusive Scope-Iteration und Reserved-Ausschluss: `fix_xml_like_tags()` (`cli/okf-cli.py:2749-2779`), `RESERVED` (`cli/okf-cli.py:31`). Kommando-Einstieg inkl. Zielpfad-Validierung: `cmd_fix_xml_tags()` (`cli/okf-cli.py:2782-2794`) — validiert heute mit `os.path.isdir` und bricht mit Exit 1 ab; Registrierung: `cli/okf-cli.py:4210-4213` (`--check` als heutige Dry-run-Flagge, kein `--apply`-Gegenstück). Scope-Auflösung `[TARGET]` teilt sich `fix_crosslinks` und `fix_xml_like_tags`: `resolve_scopes()` (`cli/okf-cli.py:2940-2959`).

Für die Norm-Zuordnung: kein heutiges Gegenstück existiert — `cmd_fix_xml_tags()` prüft keinen Schalter und läuft unconditional bei jedem Aufruf.

## Deltas gegenüber heute

| Delta | Deckung |
|---|---|
| `--check` entfällt zugunsten von `--apply`; Dry-run wird Default | I03, COM-29–COM-32 |
| Wrap an einen Profil-Schalter gebunden statt unconditional | D05, vgl. CHECK-7/CHECK-8 |
| Zielpfad-Validierung liefert Exit 2 statt Exit 1 | COM-23, I09 |

## Anmerkungen

**FIX-XML-TAGS-5/6 übertragen CHECK-7/CHECK-8 auf den Fix**, aus demselben Grund wie bei [fix-crosslinks.md](./fix-crosslinks.md): `xml-like-tags` ist als `check`-Regel bereits schalter-gebunden; ohne dieselbe Bindung würde der Fix unter dem `okf`-Profil Dateien anfassen, deren `check`-Lauf im selben Profil die Konvention gar nicht verlangt.

**Kein Unresolved-/Exit-1-Pfad wie bei `fix-crosslinks`.** Anders als ein Crosslink-Ziel kann eine Platzhalterkette nicht „nicht auflösbar" sein — jede erkannte, nicht-ignorierbare Kette wird gewrapt. Es gibt daher keinen Sachbefund, den COM-22 hier zusätzlich zu spezialisieren wäre; COM-21 (Exit 0 ohne Sachbefund) greift ungeändert.

## Offene Fragen

Ob ein expliziter `fix-xml-tags`-Aufruf bei deaktiviertem Schalter still no-opt (FIX-XML-TAGS-6, symmetrisch zu CHECK-8) oder stattdessen mit Exit 2 auf die Deaktivierung hinweist, ist durch D05 nicht entschieden — Teil von T06, siehe dieselbe offene Frage in [fix-crosslinks.md](./fix-crosslinks.md).

Ob `SAFE_HTML_TAGS` (FIX-XML-TAGS-8) eine feste Liste bleibt oder konfigurierbar wird, ist nicht entschieden; diese Datei übernimmt die heutige feste Liste unverändert.

Der Schaltername selbst ist T06 und wird hier bewusst nicht genannt.
