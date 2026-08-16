---
type: Spec
title: "build-index — EARS-Requirements BUILD-INDEX-1..BUILD-INDEX-13"
description: "(Re)Aufbau des FTS5-Index, der find's lexikalischen Arm trägt: Umfang, Tokenizer, Staleness, atomarer Austausch."
tags:
  - okf-cli
  - ears
  - requirements
  - spec
---

# build-index — EARS-Requirements BUILD-INDEX-1..BUILD-INDEX-13

`build-index` erzeugt das Artefakt, ohne das `find`'s lexikalischer Arm auf den Substring-Scan zurückfällt (FIND-14): den FTS5-Index. Es ist ein lokales, optionales, jederzeit reproduzierbares Nebenprodukt des Stores — kein Store-Inhalt, sondern ein Cache über ihm.

Die Querschnitts-Regeln gelten unverändert; hier steht nur, was `build-index` darüber hinaus leistet.

## Requirements

### Umfang und Ziel

| ID | EARS-Requirement |
|----|------------------|
| BUILD-INDEX-1 | THE okf binary SHALL build the FTS5 lexical index from every concept file in scope. |
| BUILD-INDEX-2 | WHERE the store is a bundle, THE okf binary SHALL build the index from that bundle's concepts alone. |
| BUILD-INDEX-3 | THE okf binary SHALL write the index to `.fts/fts.sqlite` under the store root. |
| BUILD-INDEX-4 | THE okf binary SHALL fold diacritics and stem English morphology in the text it indexes. |
| BUILD-INDEX-12 | THE okf binary SHALL build the index using local file reads alone. |

### Staleness

| ID | EARS-Requirement |
|----|------------------|
| BUILD-INDEX-5 | WHILE the store's concept count differs from the count recorded at the last build, or a concept file changed since that build, THE okf binary SHALL treat the index as stale. |
| BUILD-INDEX-6 | IF the existing index is unreadable, THEN THE okf binary SHALL treat it as stale. |

### `--if-stale`

| ID | EARS-Requirement |
|----|------------------|
| BUILD-INDEX-7 | WHERE '--if-stale' is absent, THE okf binary SHALL rebuild the index regardless of its current state. |
| BUILD-INDEX-8 | WHERE '--if-stale' is given and the existing index is current, THE okf binary SHALL skip the rebuild. |
| BUILD-INDEX-9 | WHERE '--if-stale' is given and the existing index is absent or stale, THE okf binary SHALL rebuild it. |

### Atomarer Austausch und Bericht

| ID | EARS-Requirement |
|----|------------------|
| BUILD-INDEX-10 | THE okf binary SHALL build the new index into a temporary location and SHALL replace the existing index only once the build completes without error. |
| BUILD-INDEX-11 | IF the build is interrupted before it completes, THEN THE okf binary SHALL leave the previous index file in place. |
| BUILD-INDEX-13 | THE okf binary SHALL report the count of concepts indexed and the index's path. |

## Grounding

Umfang und Aufbau: `build_fts_index()` `cli/okf-cli.py:676-714`, aufgerufen von `cmd_build_index()` `cli/okf-cli.py:739-758`. Zielpfad und Dateinamen: `FTS_DIRNAME`/`FTS_FILENAME`/`_fts_db_path()` `cli/okf-cli.py:657-658, 672-673`. Tokenizer: `FTS_TOKENIZER`/`FTS_SCHEMA` `cli/okf-cli.py:659-666`. Kein Netzwerkzugriff: die Dokstring-Zeile der Kommando-Registrierung, „local only, no network" `cli/okf-cli.py:4175-4176`, und `build_fts_index()` liest ausschließlich über `read_file()`/`os.path.getmtime()` vom lokalen Dateisystem.

Staleness-Kriterium und der Unreadable-Fall: `_fts_index_stale()` `cli/okf-cli.py:717-736`, insbesondere der `except`-Zweig `cli/okf-cli.py:722-727`, der ein fehlendes oder kaputtes `fts_meta` als stale zählt.

`--if-stale`-Verzweigung: `cmd_build_index()` `cli/okf-cli.py:739-758`, konkret die drei Pfade — Flag abwesend (unbedingter Rebuild, `cli/okf-cli.py:746-757`), Flag gesetzt und Index aktuell (Skip mit Meldung, `cli/okf-cli.py:754-756`), Flag gesetzt und Index abwesend/stale (Rebuild fällt durch bis `cli/okf-cli.py:757`).

Atomarer Austausch: `build_fts_index()` `cli/okf-cli.py:681-685` (Tmp-Datei, existierende Tmp-Reste vor dem Build entfernt) und `cli/okf-cli.py:713` (`os.replace()` erst nach erfolgreichem `conn.commit()`/`conn.close()`). Ein Build, der vor `os.replace()` abbricht, hinterlässt die Tmp-Datei und lässt `db_path` unverändert — das ist BUILD-INDEX-11.

Bericht: `cli/okf-cli.py:755` (Skip-Zweig) und `cli/okf-cli.py:758` (Rebuild-Zweig).

Bundle-Modus (BUILD-INDEX-2) existiert im heutigen Code nicht — `build_fts_index()` iteriert `list_bundles(root)` über den ganzen Catalogue; er ist D06.

## Deltas gegenüber heute

| Delta | Deckung |
|---|---|
| Bundle-Modus: Index nur über die Concepts des einen Bundles | D06 |
| Envelope statt reiner Text-Meldung, wenn JSON angefragt ist | I04, COM-26 |

## Anmerkungen

**BUILD-INDEX-7 bis BUILD-INDEX-9 sind drei Zeilen, nicht eine**, aus demselben Grund wie COM-29 bis COM-31: `--if-stale` hat zwei Eingänge (gesetzt/nicht gesetzt) und der gesetzte Fall verzweigt selbst noch einmal nach dem Zustand des vorhandenen Index. Eine einzelne Zeile könnte nur einen der drei Wege abdecken und ließe die anderen beiden unausgesprochen.

**BUILD-INDEX-10 hält an derselben Zweizeiligkeit fest wie COM-19**, weil das Bauen ins Temp und das Ersetzen erst nach Erfolg zwei Hälften desselben Mechanismus sind — der atomare Austausch ist erst durch beide zusammen bewiesen, nicht durch eine der beiden Handlungen allein.

**BUILD-INDEX-7 bis BUILD-INDEX-9 zitieren `--if-stale` in einfachen statt in Backtick-Anführungszeichen.** Der Flag-Name trägt das EARS-Keyword `if` als Substring; der Validator blendet nur `"…"`/`'…'` aus, keine Backticks, also ist die Anführung hier funktional, nicht nur stilistisch — ohne sie meldet der Gate ein `if` in Kleinschreibung, obwohl kein EARS-`IF` gemeint ist.

## Offene Fragen

Ob `.fts/fts.sqlite` als konkreter Pfad im Rust-Rewrite Bestand hat oder Teil des noch offenen Store-Layouts (T06/T07) wird, ist nicht entschieden; BUILD-INDEX-3 hält den heutigen Pfad fest, weil keine Decision einen anderen nennt.

Ob der Index als Store-Artefakt der Mutations-Polarität aus COM-29 bis COM-32 unterliegt (also erst mit `--apply` schreibt), ist offen. Heute baut `build-index` unbedingt, ohne Vorschau-Modus, und der Audit-Katalog (I03) zählt `build-index` nicht zu den Verstößen gegen die Mutations-Polarität — der Index ist ein Cache über dem Store, kein Store-Inhalt. Diese Datei übernimmt deshalb bewusst kein `--apply`-Requirement.
