---
type: Spec
title: "find — EARS-Requirements FIND-1..FIND-27"
description: "Hybride Suche: lexikaler FTS5/BM25-Arm und optionaler semantischer Arm, conditional Handover statt Blending, eigene Score-Skalen je Arm, definierte Degradation je Ausfall."
tags:
  - okf-cli
  - ears
  - requirements
  - spec
---

# find — EARS-Requirements FIND-1..FIND-27

`find` beantwortet eine Ranking-Frage über den ganzen Store (oder einen Scope darin): welche Concepts passen zur Anfrage, in welcher Reihenfolge. Zwei Arme tragen die Antwort — ein lexikaler (FTS5/BM25, mit Substring-Scan als Fallback) und ein semantischer (Embeddings) — und genau ein Arm übernimmt pro Anfrage die Rangfolge; sie werden nie score-gewichtet gemischt. Der semantische Arm hängt an einem Schalter (D05) und ist damit optional; sein Ausbleiben — ob abgeschaltet oder degradiert — darf die lexikalische Antwort nie verhindern.

Die Querschnitts-Regeln gelten unverändert; hier steht nur, was `find` darüber hinaus leistet.

## Requirements

### Arme und Schalter

| ID | EARS-Requirement |
|----|------------------|
| FIND-1 | THE okf binary SHALL rank a query with a lexical arm that reads the FTS5 index built by `build-index`. |
| FIND-2 | THE okf binary SHALL weight a lexical hit's title contribution above its tag contribution, and its tag contribution above its body contribution. |
| FIND-3 | WHERE the switch governing the semantic arm is inactive, THE okf binary SHALL rank every query with the lexical arm alone. |
| FIND-27 | WHERE the semantic-arm switch is not explicitly set, THE okf binary SHALL activate it under the `catalogue` profile and deactivate it under the `okf` profile. |

### Rankverfahren: Handover statt Blend

| ID | EARS-Requirement |
|----|------------------|
| FIND-4 | WHILE the switch governing the semantic arm is active, WHEN the lexical arm's top hit has no clear lead over the runner-up hit, THE okf binary SHALL run the semantic arm. |
| FIND-5 | WHILE the switch governing the semantic arm is active, WHEN the lexical arm returns fewer hits than the requested limit, THE okf binary SHALL run the semantic arm. |
| FIND-6 | WHEN the lexical arm's top hit leads the runner-up hit by the measured margin, THE okf binary SHALL let the lexical arm own the ranking. |
| FIND-7 | WHEN the lexical arm's top hit has no such lead, THE okf binary SHALL let the semantic arm own the ranking. |
| FIND-8 | THE okf binary SHALL list the owning arm's hits ahead of the non-owning arm's hits in the final ranking. |
| FIND-9 | WHERE a concept appears in both arms' hits, THE okf binary SHALL keep only the owning arm's entry for it. |

### Score-Skalen

| ID | EARS-Requirement |
|----|------------------|
| FIND-10 | THE okf binary SHALL report a lexical hit produced by the FTS5 index on a scale of 0 to 100, relative to that run's own top hit. |
| FIND-11 | WHERE the lexical arm falls back to the substring scan, THE okf binary SHALL report a lexical hit on a scale of six times the query's term count. |
| FIND-12 | THE okf binary SHALL report a semantic hit's score as its raw cosine similarity, on a scale separate from the lexical arm's score. |
| FIND-13 | THE okf binary SHALL name, for every hit, the arm that produced it. |

### Degradation je Ausfall

| ID | EARS-Requirement |
|----|------------------|
| FIND-14 | WHERE the FTS5 index is absent or unusable, THE okf binary SHALL rank the query with the substring scan instead of the FTS5 index. |
| FIND-15 | WHERE the FTS5 index is stale, THE okf binary SHALL still rank the query with that index instead of falling back to the substring scan. |
| FIND-16 | WHERE the semantic arm's embedding cache is absent or holds no vector for the active model, THE okf binary SHALL answer with the lexical arm's hits alone. |
| FIND-17 | WHERE the query embedding call fails, THE okf binary SHALL answer with the lexical arm's hits alone. |
| FIND-18 | WHERE the semantic arm's embedding cache holds no vector inside the requested scope, THE okf binary SHALL return no semantic hit and SHALL emit no note about it. |
| FIND-19 | WHERE a query produces no hit and the store has registered tags near the query's terms, THE okf binary SHALL name those tags. |

### Filter und Scope

| ID | EARS-Requirement |
|----|------------------|
| FIND-20 | WHERE `--tag` is given, THE okf binary SHALL match the whole tag value, not a substring of it. |
| FIND-21 | WHERE `--type` is given, THE okf binary SHALL restrict hits to concepts whose frontmatter type equals that value exactly. |
| FIND-22 | WHERE the store is a bundle, THE okf binary SHALL search the bundle root as the single scope. |

### Fehlerfälle und Flags

| ID | EARS-Requirement |
|----|------------------|
| FIND-23 | IF the query is empty after tokenization, THEN THE okf binary SHALL exit 2. |
| FIND-24 | WHERE `--breakdown` is given, THE okf binary SHALL name, for each lexical hit, which field or term contributed to its score. |
| FIND-25 | WHERE `--expand-tags` is given and the lexical arm does not own the ranking, THE okf binary SHALL widen the query with semantically near registered tags and SHALL rank again with the lexical arm. |
| FIND-26 | WHERE JSON output is requested, THE okf binary SHALL carry, in each hit's data object, its path, title, type, description, snippet, provenance, and either its lexical score or its cosine score. |

## Grounding

**Lexikaler Arm.** Schema, Tokenizer und BM25-Gewichte: `FTS_TOKENIZER`/`FTS_SCHEMA`/`FTS_BM25_WEIGHTS` `cli/okf-cli.py:662-669`. Query-Ranking gegen den Index: `_fts_ranking()` `cli/okf-cli.py:877-943`. Substring-Fallback mit den 3/2/1-Feldgewichten: `_substring_ranking()` `cli/okf-cli.py:969-1022` (Gewichtung `cli/okf-cli.py:1004-1012`). Skalenwahl zwischen beiden: `_rank_lexically()` `cli/okf-cli.py:1025-1043`.

**Semantischer Arm.** Vektor-Cache-Lookup: `_load_concept_vectors()` `cli/okf-cli.py:1091-1134`. Query-Embedding: `_query_vector()`/`_embed_query_voyage()` `cli/okf-cli.py:1142-1174`. Kosinus: `_cosine()` `cli/okf-cli.py:1177-1183`. Ranking-Zusammenbau: `semantic_ranking()` `cli/okf-cli.py:1249-1289`, hydriert zu Hit-Dicts in `_semantic_hit_dicts()` `cli/okf-cli.py:1291-1304`. Ein Schalter, der den Arm ganz abschaltet (FIND-3), existiert im heutigen Code nicht — der Arm läuft immer, wenn er gebraucht wird, und degradiert nur bei Cache-/Netzwerk-Ausfall. Der Schalter selbst ist Task T06.

**Gate/Handover.** Konfidenz des lexikalischen Top-Treffers: `_keyword_top1_is_confident()` `cli/okf-cli.py:1228-1246`. Trigger für den semantischen Lauf: `cmd_find()` `cli/okf-cli.py:1373` (provisorische Konfidenz) und `cli/okf-cli.py:1395-1400` (Bedingung: nicht konfident, oder zu wenige Treffer für `--limit`). Fusion: `fuse_conditional()` `cli/okf-cli.py:1307-1330`.

**Score-Zeilen.** Druckschleife mit den drei Skalen: `cmd_find()` `cli/okf-cli.py:1414-1439`. Dieselbe Erklärung steht im `--help`-Epilog: `_FIND_EPILOG` `cli/okf-cli.py:4136-4177`.

**Degradations-Notizen.** Index abwesend: `cli/okf-cli.py:897-901`. Index veraltet (kein Fallback, nur Notiz): `cli/okf-cli.py:933-935`. Index korrupt: `cli/okf-cli.py:938-942`. Semantischer Cache/Modellzeilen abwesend: `cli/okf-cli.py:1264-1269`. Embedding-Backend nicht erreichbar: `cli/okf-cli.py:1272-1277`. Cache leer nur innerhalb des angefragten Scope — bewusst KEINE Notiz, weil das eine korrekte leere Antwort ist, keine Degradation: `cli/okf-cli.py:1113-1125`.

**Zero-hit-Vorschläge.** `_zero_hit_suggestions()` `cli/okf-cli.py:1333-1345`, Aufrufstelle `cli/okf-cli.py:1407-1413`.

**Filter.** `FindFilters` `cli/okf-cli.py:761-868`; Whole-tag-Prüfung `cli/okf-cli.py:848`; Scope-Prädikat `path_in_scope()` `cli/okf-cli.py:836-838`, wiederverwendet von `resolve_scopes()` `cli/okf-cli.py:2940`ff. Der Bundle-Modus (FIND-22) existiert im heutigen Code nicht — dort gibt es nur den Catalogue; er ist D06.

**Leere Anfrage.** Heute stdout + Exit 0: `cmd_find()` `cli/okf-cli.py:1349-1352` — genau B04.

**`--breakdown`.** Druckblock `cli/okf-cli.py:1432-1439`, Formatierer `_format_contrib()` `cli/okf-cli.py:617-624`.

**`--expand-tags`.** `cli/okf-cli.py:1380-1393`, Kandidatenermittlung `_expand_query_tags()` `cli/okf-cli.py:1207-1225`.

**JSON.** `find` fehlt heute `--json` in der Parser-Registrierung `cli/okf-cli.py:4186-4199` und trägt `supports_json=False` im MCP-Dispatch `mcp/okf_mcp.py:8`. Das Hit-Dict, dessen Felder das neue JSON-`data`-Objekt übernimmt, ist `_hydrate_hit()` `cli/okf-cli.py:946-966`.

## Deltas gegenüber heute

| Delta | Deckung |
|---|---|
| Semantischer Arm hinter einem Schalter statt immer aktiv versucht | D05 (COM-9) |
| `--json` und Envelope-`data` mit strukturierten Hit-Feldern statt reinem Text | I04, B03 |
| Leere Anfrage: Exit 2 statt Exit 0, Meldung auf stderr statt stdout | B04 |
| Scope über optionales Positional statt `--scope`-Flag | I02, COM-41 |
| Bundle-Modus als Scope | D06 |

## Anmerkungen

**FIND-15 hält bewusst fest, was NICHT passiert.** Anders als beim abwesenden oder korrupten Index fällt `find` bei einem veralteten Index nicht auf den Substring-Scan zurück — es rankt mit dem vorhandenen Index weiter und meldet nur die Staleness. Ohne diese Zeile wäre der Unterschied zu FIND-14 aus der Tabelle nicht ablesbar, obwohl beide unter COM-19 als „Degradation" fallen.

**FIND-18 ist das Gegenstück dazu:** ein leerer semantischer Cache innerhalb eines Scope ist keine Degradation, sondern eine korrekte leere Antwort. Die Zeile verhindert, dass COM-19 hier fälschlich eine Notiz erzwingt, die den Nutzer bei jeder scope-gebundenen Anfrage ohne Embeddings in diesem Scope beunruhigen würde.

**FIND-4/FIND-5 und FIND-16/FIND-17/FIND-18 wiederholen COM-19 nicht wörtlich.** Die stderr-Notiz selbst ist bereits durch COM-19 verlangt; diese Zeilen legen nur fest, WELCHES reduzierte Ergebnis bei welchem Ausfall entsteht — das war der Auftrag an diese Datei, nicht die COM-Mechanik ein zweites Mal zu behaupten.

## Offene Fragen

Ob `--expand-tags` an denselben Schalter wie der semantische Arm gebunden wird (beide brauchen dieselbe Embedding-Infrastruktur) oder einen eigenen trägt, ist nicht entschieden. Diese Datei nennt bewusst keinen Mechanismus dafür und lässt FIND-25 ungated — das ist der heutige Stand, kein Beschluss.

Der Name des Schalters aus FIND-3/FIND-4/FIND-5 ist Task T06 (siehe `_common.md`, Offene Fragen).

Ob `--expand-tags` angesichts der im Code selbst dokumentierten Wirkungslosigkeit (Q05/D17: "found ineffective for the vocabulary-mismatch class it was built for") im Rewrite überhaupt erhalten bleibt, ist keine Frage dieser Datei — mangels Decision/Finding dafür bleibt FIND-25 am heutigen Verhalten.
