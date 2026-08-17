---
type: Concept
title: The search corpus is the declared bundles, resolution stays wide
description: okf-cli's index and search corpus is the set of bundles a root declares via the .okf.toml `bundle` key, while resolution, rename and wikilink integrity keep the wide bundle set — the narrowing is an opt-in at the one call site that owns the corpus, never a new default in the shared traversal.
tags:
  - okf-cli
  - retrieval
  - okf-format
timestamp: 2026-08-16T00:00:00Z
---

# The search corpus is the declared bundles, resolution stays wide

Quelle: Epos `OKFT-wmbu` „Index corpus: canon must outweigh scaffolding", realisiert 2026-08-13, PO-accepted 2026-08-16 nach unabhängiger Nachmessung.

Ein OKF-Root kann mehr Markdown enthalten als sein Kanon. `LES_lean_stack/repo/docs` trägt neben dem Bundle `lean-stack-okf` die TPIC-Arbeitsordner der laufenden Themen (`aca_capability-mcp/`, Pläne, Referenzen, Eval-Rohdaten). Vor diesem Epos indizierte `build-index` alles davon: 197 Dokumente, von denen 145 Gerüst waren. Der messbare Schaden lag nicht in der Größe, sondern im Ranking — auf die Query `dev-CLI Kanon Entrypoint Wrapper Shims` lieferte `find` acht von neun Treffern aus Themen-Ordnern und das kanonische Konzept `lean-stack-okf/dev-cli-canon` auf Rang 4. Gerüst-Prosa zitiert den Kanon und schlägt ihn deshalb bei BM25.

## Der Mechanismus

`.okf.toml` trug den Schlüssel `bundle` schon länger; `okf-cli` hat ihn nie gelesen. `list_indexable_bundles(root, config_root=None)` (`cli/okf-cli.py:81`) liest ihn und fällt auf `list_bundles()` zurück, wenn er fehlt — deshalb ist die Änderung für den zentralen Katalog, der keinen `bundle`-Schlüssel trägt, per Konstruktion rückwärtskompatibel.

Eingesetzt wird die schmale Menge ausschließlich dort, wo der Korpus entsteht:

- `build_fts_index()` über `list_search_bundles(root, include_topics)` (`:119`, `:809`) plus den `_archive/`-Zweig (`:814`)
- die semantische Coverage-Zählung (`:920`)
- genau **ein** `resolve_scopes()`-Aufruf: der, der `find` den Korpus liefert (`:1268`, `indexable_only=True`)

`is_bundle_dir` ist unverändert. Auflösung, `rename`, Wikilink-Integrität und jedes schreibende Kommando behalten die breite Menge.

## Die Regel, die daraus folgt

Eine Verengung gehört an den Aufrufer, nicht in die geteilte Traversierung. `resolve_scopes(..., indexable_only=False)` (`:3348`) und `iter_concepts(..., prune_staging=True)` (`:122`) tragen beide einen Default, der nichts wegnimmt, und einen benannten Opt-in für die Aufrufer, die die schmale Menge wirklich wollen. Der Grund steht als Kommentar am Default und ist der Kern der Lehre: **ein verengter Read ist laut, ein verengter Write ist still.** Ein Tag-Kommando, das plötzlich nur noch deklarierte Bundles anfasst, reparariert lautlos weniger als vorher, und niemand sieht es.

Dreimal ist in diesem Epos genau das aufgefallen, jedes Mal an einer Aufrufstelle, die eine per Hand geschriebene Zählung nicht kannte: drei fehlende `_archive/`-Zweige, `resolve_scopes` mit zehn Kommandos statt nur `find` (unscoped `check` meldete `0 violations`, während 33 reale existierten), `iter_concepts` mit drei schreibenden Tag-Kommandos unter neunzehn Aufrufern. Methodisch verdichtet in `docs/LESSONS-LEARNED.md` LL-35/LL-36.

## Was das für einen Root bedeutet, der indiziert werden will

Wer einen Suchkorpus deklarieren will, setzt `bundle` in seiner `.okf.toml`. Wer nichts setzt, bekommt weiter alles. Themen-Ordner absichtlich mitzusuchen ist ein bewusster Opt-in — `list_search_bundles(root, include_topics)` trägt den Parameter bereits, das CLI-Flag dazu ist als `OKFT-epil` gefilet.

Zwei Stellen bleiben offen und sind als Bugs erfasst, nicht als Design:

- Ein repo-lokaler docs-Root hat **keinen** automatischen Rebuild-Trigger. Der `SessionStart`-Hook `~/.claude/hooks/fts-rebuild-if-stale.sh` rebuildet ausschließlich `kc_root`; `find` gegen `lean-stack/docs` druckt entsprechend `note: lexical index is stale`. Bean `OKFT-rdt8`.
- `docs/.okf.toml` dieses Repos trägt kein `wikilink_checked_bundles`, womit `check` hier für genau die Fehlerklasse blind ist, die dieses Epos bewacht hat. Bean `OKFT-uctf`.

## Beweislage der Abnahme

Gegen `HEAD 98d3bf6`, zwei Commits nach dem Epos-Tip, weil `bac586a` danach einen korrupten Kontrollfluss in `build_fts_index()` reparierte:

- Read-only-SQLite gegen den ausgelieferten `docs/.fts/fts.sqlite`: 52 Zeilen, erstes Pfadsegment durchgehend `lean-stack-okf`, `fts_meta n_concepts=52 n_archived=0`, kein Themen-Ordner-Dokument.
- `find "dev-CLI Kanon Entrypoint Wrapper Shims" --limit 10 --breakdown`: `lean-stack-okf/dev-cli-canon` auf `rank: 1`, `score: 100/100`, `provenance: lexical`, alle zehn Treffer unter `lean-stack-okf`.
- `just test`: `Ran 701 tests`, `failures=3` — die drei vorbestehenden `RunnerAgainstRealCatalogueTest`-Fehler aus `OKFT-5c2c`, kein vierter.
