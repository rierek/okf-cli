---
type: DesignSpec
title: "SPEC — okf-archive-lifecycle"
description: "Die Archiv-Fähigkeit der okf-cli: eine archive-Operation als Wrapper um rename, Wikilink-Auflösung ins Archiv mit Vorrang für Aktives, und --include-archive als vierte Dimension von FindFilters."
tags:
  - tpic
  - okf-archive-lifecycle
timestamp: 2026-08-09T19:06:56Z
---

# SPEC — Archiv-Fähigkeit der okf-cli

## Herkunft

Die Konvention steht fest und wird hier nicht neu verhandelt: `lean-stack/docs/okf-knowledge-lifecycle/taxonomy-and-lifecycle/DESIGN.md`, Abschnitte 4 und 7, getragen von D05, D06, D07, D08, D13, D14, D21. Das Archiv ist ein Ordner und kein Boolean, es liegt katalogweit als `_archive/<bundle>/<concept-id>.md`, es ist aus dem Default-Retrieval ausgeschlossen und über `--include-archive` bei `find` und `list` erreichbar. Diese SPEC ist die CLI-Seite davon — T09, T11 und T12 des dortigen TASKS.

**T15 gehört nicht hierher.** Der gemessene Blind Spot (`iter_concepts` prunt `_`-Ordner nicht, `iter_all_md` schon) betrifft in-Bundle-Staging und ist von der Archiv-Topologie unabhängig, weil das Archiv auf Katalog-Ebene liegt. Er läuft als eigenes bean.

## Nicht-Ziele

- Kein Batch-Archivieren. Eine Operation, ein Konzept.
- Keine Retention-Automatik und keine Frist (D19).
- Kein `archived:`-Feld im Frontmatter (D06) — der Ort ist die Aussage.
- Keine `check`-Regel gegen Verweise aus dem aktiven Bestand ins Archiv. Ein solcher Verweis ist nicht kaputt, sondern historisch; eine Regel dagegen machte aus jeder Archivierung eine Aufräumkette.
- Kein Autoritätsrang im Ranking (D18). Typ bleibt Filter, Änderungsdatum bleibt Anzeige.
- Keine Umstellung von `cmd_list` auf `FindFilters` über das hinaus, was die geteilte Scope-Auflösung verlangt.

## 1. Das `archive`-Kommando

Signatur: `okf-cli.py archive <bundle>/<concept>[.md]` und `okf-cli.py archive --restore _archive/<bundle>/<concept>[.md]`. Dry-run ist der Default, `--apply` führt aus, `--force` verhält sich wie bei `rename` (Zielkollision, Ambiguitäts-Guard). Beide Formen nehmen genau einen Pfad; das Ziel wird abgeleitet und nie getippt.

| Richtung | Quelle | Ziel |
|---|---|---|
| archivieren | `<bundle>/<cid>.md` | `_archive/<bundle>/<cid>.md` |
| zurückholen | `_archive/<bundle>/<cid>.md` | `<bundle>/<cid>.md` |

Eine mehrstufige concept-id behält ihre Substruktur: `dev-wiki/patterns/retry.md` wird zu `_archive/dev-wiki/patterns/retry.md` und zurück.

Guards zusätzlich zu denen, die `rename` schon trägt:

- `archive` ohne `--restore` verweigert eine Quelle, die bereits unter `_archive/` liegt — sonst entsteht `_archive/_archive/…`.
- `archive --restore` verweigert eine Quelle, die **nicht** unter `_archive/` liegt — sonst berechnet die Ableitung ein Ziel, das die Quelle selbst ist, und `rename` stirbt an "source and destination are identical" mit einer Meldung, die den Fehler nicht erklärt.
- `--restore` verweigert einen Archivpfad ohne Bundle-Segment (`_archive/x.md`): das Ziel wäre nicht ableitbar.

Der Report nennt zusätzlich zur Move-Zeile die Zahl der aktiven Konzepte, die per Markdown-Crosslink weiterhin auf das Konzept verweisen — die kennt `plan_rename` als `inbound` bereits. Damit ist die Archivierung nicht stumm gegenüber dem, was sie hinterlässt.

## 2. `perform_rename` — der Refactor, der den Wrapper dünn macht

`cmd_rename` (`cli/okf-cli.py:3846`) ist heute Validierung, Planung und Anwendung in einem Handler, der seine Parameter aus einem argparse-Namespace liest (`args.apply`, `args.force`, `args.old`, `args.new`). Ein Wrapper, der sich einen Namespace zusammensteckt, wäre an jede spätere Flag-Änderung gekoppelt, ohne dass ein Test das zeigt.

Der Rumpf wandert deshalb nach `perform_rename(root, old_abs, new_abs, apply, force, verb="rename")`. `cmd_rename` löst seine beiden Pfade auf und ruft dort hinein; `cmd_archive` leitet das Ziel ab und ruft dieselbe Funktion. `verb` steuert ausschließlich die Wortwahl der Ausgabe ("would move" bleibt "would move"; der Präfix der Fehlermeldungen wird `rename:` bzw. `archive:`).

Alles, was `archive` damit erbt, ohne es zu duplizieren: `git mv -f` mit fs-Fallback und expliziter Meldung des genommenen Weges (`_git_mv`, :3832), Inbound-/Outbound-Link-Rewrite (`plan_rename`, :3695), Wikilink-Rewrite samt Ambiguitäts-Guards (`plan_wikilink_rewrites`, :3596), Reindex der betroffenen Bäume (`reindex_tree`, :3810), Reserved-Name- und Zeichen-Validierung.

Verhalten von `rename` bleibt byte-identisch. Das ist prüfbar: die bestehende `rename`-Testmenge läuft unverändert.

## 3. Wikilink-Auflösung ins Archiv

`build_concept_basename_index` (`cli/okf-cli.py:3208`) traversiert heute `list_bundles(root)`, und `is_bundle_dir` (:69) schließt `_`-Präfixe aus. Ein archiviertes Konzept ist damit kein Auflösungsziel mehr, jeder Inbound-Wikilink `[[x]]` wird unresolved, und in den fünf per `.okf.toml` opt-in geschalteten Bundles meldet `check_wikilink_resolvable` (:3326) das als Violation — in Dateien, die der Archivierende nie angefasst hat. Der Kommentar im `.okf.toml` des Katalogs erklärt jede Warnung von dort ausdrücklich zur echten Regression.

Deshalb nimmt der Index `_archive/<bundle>/**` mit auf, mit einer Vorrangregel:

> Existiert zu einem Basename mindestens ein **aktiver** Kandidat, zählen ausschließlich die aktiven Kandidaten. Nur wenn kein aktiver existiert, löst der Link auf den oder die archivierten auf.

Ohne diese Regel würde archivieren-und-unter-gleichem-Namen-neu-anlegen jedes `[[x]]` ambiguous machen. Die bestehende Ambiguitäts-Semantik unter aktiven Konzepten bleibt davon unberührt: zwei aktive Kandidaten sind weiterhin `ambiguous`, zwei archivierte ohne aktives ebenfalls.

`_index_after_move` (:3670) muss dieselbe Regel anwenden. Es simuliert den Index nach dem Move, um `turns_ambiguous` zu bestimmen; ohne die Regel meldete der Dry-Run von `archive` Ambiguität für Links, die in Wahrheit sauber auflösen, und verweigerte ohne `--force` den Dienst.

Markdown-Crosslinks brauchen nichts: `plan_rename` schreibt sie auf den `_archive/`-Pfad um, das Ziel existiert, der Link bleibt gültig.

Zwei Nebenwirkungen des Moves sind geprüft und in Ordnung, damit der Plan sie nicht neu herleiten muss. `bundle_of` (:3470) liefert für einen Archivpfad `_archive`, also gilt der Move als bundle-übergreifend und der Outbound-Pass läuft — er ändert aber nichts, weil `link_expr` (:3476) katalogroot-absolute Links erzeugt, die ortsunabhängig sind. Und `plan["bundles"]` enthält `_archive` neben dem Herkunfts-Bundle; `reindex_tree` läuft folglich über beide, findet unter `_archive/` kein `index.md` und tut dort nichts, während der `index.md` des Herkunfts-Bundles den Eintrag korrekt verliert.

## 4. Retrieval — `include_archive` als vierte Dimension von `FindFilters`

`FindFilters` (`cli/okf-cli.py:761`) dokumentiert an seinem eigenen Kopf den Befund I01: dieselbe Filterdimension war dreimal implementiert, reiste als loses Argument durch fünf Signaturen und fehlte im semantischen Arm ganz, weshalb eine gescopte Query Konzepte aus fremden Bundles zurückgab. Eine vierte Dimension daneben durchzureichen wiederholte diesen Fehler. Sie wird deshalb das vierte Feld des Wertobjekts, Default `False`.

`path_in_scope` trägt beide Regeln, weil sie dieselbe sind:

- Ein Pfad, der mit `_archive/` beginnt, ist unsichtbar, solange `include_archive` nicht gesetzt ist.
- Der Scope-Vergleich läuft gegen den Pfad **ohne** das führende `_archive/`-Segment. `--scope okf-meta-wiki --include-archive` liefert damit aktive und archivierte Konzepte dieses Bundles — der Bundle-Name bleibt im Archivpfad genau dafür erhalten (D14). Ohne das Flag ändert sich nichts.

`sql_where` (:800) bildet beides in SQL ab. Die Scope-Bedingung deckt zusätzlich `_archive/<scope>` und `_archive/<scope>/%` ab; ohne gesetztes Flag kommt `AND path NOT LIKE '\_archive/%' ESCAPE '\'` hinzu. Das `ESCAPE` ist nicht optional: `_` ist in SQL LIKE ein Einzelzeichen-Wildcard, und ohne Maskierung schlösse das Prädikat auch ein Bundle namens `xarchive` aus.

Die Dimension gilt als von SQL abgedeckt, sobald die Tabelle eine `scope`-Spalte führt — für `FTS_FILTER_COLUMNS` und `EMB_FILTER_COLUMNS` (:873) ist das jeweils `path`. Das `residual`-Protokoll bleibt unverändert gültig.

### 4.1 Der FTS-Index muss das Archiv kennen

`build_fts_index` (:676) indiziert zusätzlich `_archive/<bundle>/<cid>` unter genau diesem Pfad. Ohne das wäre `--include-archive` eine Attrappe: der Default-Arm ist FTS, und was der Index nicht kennt, kann kein Prädikat wieder sichtbar machen.

`_fts_index_stale` (:717) braucht dafür **zwei getrennte Zähler** in `fts_meta` — aktiv und archiviert —, die beide verglichen werden. Die Begründung ist ein Fehlerpfad, kein Stilfrage:

- Zählt der Index beide Mengen, der Staleness-Test aber nur die aktive, ist der Index ab dem ersten Archiveintrag dauerhaft stale und jeder `find` baut ihn neu.
- Zählt beides als eine Summe, bleibt diese beim Archivieren konstant, und `git mv` erhält die mtime der Datei. Die Verschiebung wäre unsichtbar, der Index führte das Konzept weiter unter seinem aktiven Pfad, und `find` zeigte Archiviertes im Default an — genau der Zustand, den D05 ausschließt.

Mit zwei Zählern weichen beim Verschieben beide ab, und die Erkennung bleibt stat-only.

### 4.2 Substring-Arm und `list`

`_substring_ranking` (:969) und `cmd_list` (:582) traversieren beide über `resolve_scopes` (:2940). Sie teilen sich künftig eine Funktion, die zusätzlich zu den aktiven Scopes die Archiv-Scopes liefert, wenn das Flag gesetzt ist. Der Pfad-Präfix eines Treffers ist dabei seine Position unter root, also `_archive/<bundle>/…` — B04 bleibt gewahrt, ein `okf-cli read` auf den ausgegebenen Pfad muss auflösen.

`_substring_ranking` prüft zusätzlich weiterhin `matches_loaded` über den zusammengesetzten Pfad. Diese doppelte Durchsetzung ist beabsichtigt (I01) und gilt für die neue Dimension genauso.

### 4.3 Semantischer Arm

Unverändert. Der Embedding-Build (`cli/embeddings/build_tagvec.py:174`) bleibt auf dem aktiven Katalog: Embeddings kosten API-Aufrufe für Material, das per Default nie erscheint, und "ich weiß, dass es das mal gab" (D21) ist eine lexikalische Suche.

Damit das keine stille Lücke wird: steuert der semantische Arm bei gesetztem `--include-archive` Treffer bei, schreibt `cmd_find` genau eine Zeile auf stderr, dass das Flag nur den lexikalischen Arm deckt. Eine Note pro Arm pro Aufruf, nach der Regel der bestehenden Degradations-Noten (PF-4). Ohne sie sucht der Nutzer in einem Archiv, das der antwortende Arm nie gesehen hat, und liest das leere Ergebnis als Auskunft.

## 5. MCP

`include_archive` kommt in `_BOOL_FLAGS` (`mcp/okf_mcp.py:27`) und als Parameter an `okf_find` und `okf_list` — und nur dort. Ein Kommando, das das Flag nicht kennt, quittiert es mit einem argparse-Fehler; die Tool-Signatur ist die Stelle, an der das entschieden wird.

## 6. Akzeptanz

Jede Zeile ist ein ausführbarer Nachweis, nicht eine Absicht.

| # | Kriterium |
|---|---|
| A01 | `archive <bundle>/<cid>` ohne `--apply` gibt den Plan aus und verändert keine Datei. |
| A02 | `archive <bundle>/<cid> --apply` legt die Datei unter `_archive/<bundle>/<cid>.md` ab, git-getrackt (`git mv`), und meldet den genommenen Weg. |
| A03 | `archive --restore _archive/<bundle>/<cid>.md --apply` stellt den Ausgangspfad wieder her; ein Vergleich des Dateiinhalts vor der Archivierung und nach dem Restore ist byte-gleich. |
| A04 | `archive` auf eine Quelle unter `_archive/` bricht mit erklärender Meldung ab; `--restore` auf eine Quelle außerhalb ebenso. |
| A05 | Ein Inbound-Wikilink `[[x]]` in einem aktiven Konzept löst nach der Archivierung von `x` weiterhin auf; `check` auf den fünf Opt-in-Bundles bleibt violationsfrei. |
| A06 | Existiert ein aktives **und** ein archiviertes Konzept desselben Basenames, löst `[[x]]` eindeutig auf das aktive auf — nicht `ambiguous`. |
| A07 | Zwei aktive Kandidaten desselben Basenames bleiben `ambiguous` (bestehendes Verhalten unverändert). |
| A08 | `find <term>` ohne Flag liefert ein archiviertes Konzept nicht, obwohl es im FTS-Index steht. |
| A09 | `find <term> --include-archive` liefert es, mit `_archive/<bundle>/<cid>` als Pfad. |
| A10 | `find <term> --scope <bundle> --include-archive` liefert archivierte Konzepte **dieses** Bundles; ein Bundle-fremdes Archivkonzept erscheint nicht. |
| A11 | Ein Bundle namens `xarchive` wird vom Default-Prädikat nicht ausgeschlossen (ESCAPE-Nachweis). |
| A12 | `list --type X` ohne Flag zeigt kein Archiviertes, mit Flag schon. |
| A13 | Nach einer Archivierung meldet `_fts_index_stale` den Index als stale. |
| A14 | Ein `find --include-archive`, dessen Antwort semantische Treffer enthält, schreibt die Arm-Note auf stderr; ohne das Flag schreibt es sie nicht. |
| A15 | Die bestehende `rename`-Testmenge läuft nach dem `perform_rename`-Refactor unverändert grün. |
| A16 | `okf_find`/`okf_list` reichen `include_archive` durch; `build_argv` setzt das Flag für kein anderes Kommando. |

### Guard-Umkehrproben

Zu jeder Mutation gegen das Geschützte gehört die Umkehrmutation gegen den Schutz. Zwei Stellen tragen hier den stillen Fehler, also müssen zwei Tests nachweislich rot werden, wenn die Durchsetzungszeile fällt:

- Entfernt man das Default-Ausschluss-Prädikat aus `sql_where`/`path_in_scope`, muss A08 rot werden.
- Entfernt man die Aktiv-vor-archiviert-Regel aus `build_concept_basename_index`, muss A06 rot werden.

Beide Proben bleiben als Tests im Repo, nicht als vorgeführter Zustand.

### Lauf gegen den echten Katalog

Nach grüner Suite einmal gegen `~/Obsidian/Knowledge-Catalogue`: ein Konzept archivieren, A05 und A08 bis A10 dort nachfahren, mit `--restore` zurückrollen, `git status` muss sauber sein. Der Katalog hat heute kein `_archive/` — dieser Lauf legt es an und entfernt es wieder.

## 7. Kopplung nach außen

`just okf-archive-exclusion` in lean-stack endet mit Exit 1, sobald okf-cli von R09 abweicht. Dieses Vorhaben ändert R09 nicht: der Guard misst ein `_archive/` **innerhalb** eines Bundles, gebaut wird auf Katalog-Ebene. Der separat zu fixende T15 wird ihn auslösen, und das ist gewollt — er meldet dann, dass DESIGN Abschnitt 4 nachzulesen ist.
