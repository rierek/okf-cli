---
type: Report
title: "Q01-SUPERSEDED-DECISIONS — okf-revision"
description: "PO-Entscheidung D01 umgesetzt: superseded_by-Schema, find/check-Erweiterung, und die Anwendung auf memory-layer-wiki/decisions gegen den Teardown."
tags:
  - tpic
  - okf-revision
timestamp: 2026-08-10T15:03:32Z
---
# Q01 — Superseded Decisions, Umsetzung von D01

## PO-Entscheidung (D01, 2026-08-10)

Supersession ist eine explizite Frontmatter-Relation `superseded_by`, ausschließlich auf Konzepten mit `type: Decision`. Wert ist ein katalogwurzel-absoluter Pfad (`/bundle/subdir/concept.md`), dieselbe Form wie ein Crosslink. Kein `status`-Feld, kein Workflow-Automat, kein Pflichtfeld — ein optionaler Zeiger, sichtbar beim Retrieval. Details: bean `OKFT-gpcx`.

## Schema

`superseded_by` ist in `PROPERTIES.md` (`~/Obsidian/Knowledge-Catalogue/PROPERTIES.md`, Abschnitt „Kern-Properties") dokumentiert. Die Datei ist über `~/Obsidian/Vault/PROPERTIES.md` (Symlink) auch im Vault sichtbar, wie in der Datei selbst vermerkt.

## Codeänderungen (`okf-tools`)

`find` gibt `superseded_by` in der Trefferzeile aus, wenn das Konzept es trägt — zwischen `type` und `path`. Ein Treffer ohne das Feld ist byte-identisch zur bisherigen Ausgabe (`FindSupersededByField.test_hit_without_superseded_by_is_byte_identical`, `cli/test_okf_cli.py`).

`check` prüft zwei neue Regeln: `superseded-by-resolves` (ERROR — Ziel löst nicht auf ein existierendes Konzept auf, dieselbe Klasse wie ein toter Crosslink) und `superseded-by-scope` (WARNING — `superseded_by` auf einem Konzept, dessen `type` nicht `Decision` ist).

Jede der drei Änderungen wurde per TDD gebaut (RED vor GREEN) und per Gegenmutation im Produktionscode belegt, dass genau ein Test rot wird — Details im Abschluss-Report an das bean.

## Anwendung auf den realen Fall

`memory-layer-wiki/decisions/memory-db-layer-teardown.md` erklärt den lokalen SQLite-vec-Memory-Layer für ersatzlos abgebaut (2026-07-27) und macht das Bundle zur historischen Dokumentation — mit einer expliziten Ausnahme: „Analyse- und Entscheidungs-Seiten, deren Aussagen über Senken-Design und Migrationsverluste unabhängig vom abgebauten Code gelten" bleiben gültig. Diese Ausnahme ist der Maßstab für die folgenden Urteile, nicht eine Pauschalregel.

### Markiert (superseded_by = Teardown)

**`memory-layer-wiki/decisions/evaluation-and-decision-path.md`** — „Evaluation and Decision Path" dokumentiert den Entscheidungsweg zu SQLite-vec und behauptet im Fließtext, das daraus entstandene Schema sei „seitdem aktiv". Genau diese Aktualitätsbehauptung ist durch den Teardown falsch: `~/.claude/memory.db` existiert nicht mehr. Das ist exakt der Fehlermodus aus der bean-Evidenz (R4: eine überholte Entscheidung als aktuell gemeldet) — markiert.

**`memory-layer-wiki/decisions/upgrade-memory-system-level-6.md`** — Migrationsplan von SQLite-vec (Level 3) auf PostgreSQL+pgvector (Level 6). Die „Ausgangslage" setzt das inzwischen gelöschte `~/.claude/memory.db` voraus, alle „Nächsten Schritte" sind unausgeführt (offene Checkboxen). Der Plan zielt auf eine Infrastruktur, die es nicht mehr gibt — markiert.

**`memory-layer-wiki/decisions/2026-06-02-mem-27-sprint-plan-backend-consolidation.md`** — „MEM-27 Sprint Plan — Backend Consolidation": konsolidiert `~/.claude/memory.db` und `project_memories` auf **eine** `devd.db`. Das ist die Entscheidung, auf die sich die bean-Evidenz wörtlich bezieht („a decision to consolidate the memory layer onto one database"). Statt der geplanten Konsolidierung in `devd.db` wurde der gesamte Layer ersatzlos gelöscht — der Sprint-Plan wurde nie ausgeführt und ist durch den Teardown gegenstandslos. Markiert.

### Nicht markiert

**`memory-layer-wiki/decisions/decision-against-neo4j-graph.md`** — Begründet, warum Neo4j aus der Architektur gestrichen wurde (Aufwand/Nutzen, YAGNI, Vektorsuche deckt 95% ab). Das ist eine Analyse-Seite im Sinn der Teardown-Ausnahme: ihre Kernaussage (ein Graph lohnt sich für ein Wissenssystem dieser Größenordnung nicht) ist unabhängig vom konkreten, inzwischen gelöschten SQLite-vec-Code — nichts hat die Anti-Neo4j-Position seither revidiert. Dass der einzige im Dokument genannte Nachfolger (die lokale Vektorsuche) selbst nicht mehr existiert, macht die Seite historisch, aber nicht überholt im Sinn von D01: kein späteres Konzept widerspricht ihrer Schlussfolgerung. Nicht markiert.

**`memory-layer-wiki/decisions/index.md`** — reserved-Datei (kein `type`-Frontmatter, § OKF 3.1), fällt nicht unter „Decision"-Konzepte und wurde nicht bewertet.

## Katalogweite Kandidaten (nur benannt, nicht bearbeitet)

`okf-cli.py list --type Decision` gegen den realen Katalog liefert 40 Treffer. Zwei davon lesen sich als plausibel ebenfalls überholt, liegen aber außerhalb des Scopes dieser Aufgabe (nicht `memory-layer-wiki/decisions/`) und wurden nicht angefasst:

- `memory-layer-wiki/memory-analyses/p-review-memory-system/2026-05-26-context-management-foundation-plan-and-decisions` — Plan/Entscheidungen zur Context-Management-Foundation (SSTD-Slots, project-memory-Routing), voraussichtlich vom selben Teardown betroffen wie die drei markierten Entscheidungen — liegt aber außerhalb `decisions/` und wurde in dieser Aufgabe nicht einzeln geprüft.
- `devd2-okf/decisions/context-engineering-status` — Standortbestimmung der DD2-Wissensarchitektur; plausibel überholt durch `agent-memory/devd2-archived-devd-mcp-unwired` (DevD 2.0 seit 2026-07-26 archiviert), aber ein anderes Bundle/Thema als der Memory-Layer-Teardown und nicht Teil dieses Tasks.

## Bekannte Lücke

`okf-cli.py build-index` wurde nach den Frontmatter-Änderungen neu gebaut (lexikalischer FTS-Index). Der semantische Index (`.tagvec`) ist davon **nicht** abgedeckt — `build-semantic-index` befüllt nur fehlende Pfade, keine inhaltlich geänderten Konzepte. Das ist der bekannte Bug `OKFT-3520` und bleibt offen; die drei markierten Konzepte tragen bis zu dessen Fix eine veraltete Embedding-Repräsentation im semantischen Arm (ihr Text hat sich nur um die Frontmatter-Zeile geändert, der Effekt auf die Embedding-Qualität ist vernachlässigbar, aber die Lücke besteht formal).
