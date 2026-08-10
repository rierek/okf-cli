---
# OKFT-mac3
title: Consolidate duplicates across ai-wiki and general-knowledge-wiki
status: completed
type: task
priority: normal
created_at: 2026-08-10T14:21:48Z
updated_at: 2026-08-10T16:52:34Z
parent: OKFT-wuiv
---

## Objective (User Story)
As the catalogue owner, I want one canonical concept per topic across `ai-wiki` and `general-knowledge-wiki`, so that a reader does not have to guess which of two copies is current.

## Evidence (docs/okf-revision/B02-DUPLICATE-MARGIN.md)
The near-duplicate scan of 2026-08-10 found 105 duplicate groups — 88 by concept slug, 17 more by identical `title:` — spanning 222 concept files. 66 of those groups (132 files) lie exclusively on the axis `ai-wiki` against `general-knowledge-wiki`. Six groups are `qm-wiki`-internal and deliberate (checklist, norm-reference, story-line, knowledge-blocks as different views of one norm clause); one group (`GLOSSARY`, 5x) is a scan artefact from the repo bundles.

The merge is catalogue hygiene, NOT a retrieval fix. `OKFT-hjqp` measured the margin hypothesis and refuted it: removing copies did not hand the ranking back to the lexical arm, and in the `integration` case it made the margin worse. Any acceptance criterion of the form "after the merge the lexical arm wins" is known to be unreachable and must not be written.

## Open decision (PO)
The 66 cross-bundle groups need ONE direction decision — does `ai-wiki` fold into `general-knowledge-wiki/ai-agentic-coding/`, the other way round, or does each group get judged on its own? 105 individual judgements is not a plan. The richest copy per group is known for the two originally reported cases (`general-knowledge-wiki/ai-agentic-coding/ralph-wiggum-loop.md` with 3 outbound path links against 2 and 0; `general-knowledge-wiki/ai-agentic-coding/integration.md` with 11 against 2), not for the other 103.

## EARS Acceptance
- THE direction decision SHALL be recorded before any concept is moved or deleted.
- WHERE a group is merged, THE surviving concept SHALL be the one carrying the richer body and link set, and every inbound reference SHALL follow through `okf-cli rename` or `reindex`.
- THE deliberate `qm-wiki` groups SHALL be left untouched.

## Success Criteria
- SC-001: direction decision written down.
- SC-002: after the merge, the scan reports no unintended duplicate group; `okf-cli check` clean, no new unresolved wikilinks.

## Note
11 of the 48 canonical eval queries have a target inside a duplicate group — re-measure after the merge, since the surviving path may differ from the recorded target.


## Done 2026-08-10 (catalogue commit 5ada24b)

Richtungsentscheidung des PO: **`ai-wiki` geht in `general-knowledge-wiki` auf.** Ausgeführt für die gesamte Achse — 75 Paare, 62 mit identischem Slug und 13 mit identischem `title:` unter englischem gegen deutschen Slug. Die `general-knowledge-wiki`-Kopie überlebt an ihrem Pfad, die `ai-wiki`-Kopie liegt in `_archive/ai-wiki/`.

**Die Annahme „die dünnere Kopie fällt weg" hat der Vorlauf widerlegt, bevor sie Schaden anrichten konnte.** Ein mechanischer Zeilenvergleich beider Kopien je Gruppe zeigte, dass 42 der 62 Slug-Gruppen in der `ai-wiki`-Kopie Aussagen tragen, die der `gnw`-Kopie fehlen — und dass in mehreren Fällen die `ai-wiki`-Kopie die reichere ist (`mcp` 1925 gegen 832 Bytes bei 15 exklusiven Inhaltszeilen, `token`, `claude-dispatch`, `saas`, `halluzinationen`, `n8n`, `cron-job`). Drei überlebende `gnw`-Dateien — `rag-anything`, `lightrag`, `nanoclaw` — hatten **überhaupt keinen Body**, nur Frontmatter: ein Löschen der `ai-wiki`-Kopie hätte den gesamten Inhalt dieser drei Konzepte vernichtet. Deshalb wurde je Paar redaktionell zusammengeführt statt verworfen, in sieben parallelen Durchgängen, jeder mit Tag-Validierung gegen das geschlossene Vokabular und Existenzprüfung jedes übernommenen Links.

**Mechanischer Nachlauf:** 102 eingehende Verweise auf die `ai-wiki`-Pfade wurden in einem Durchlauf auf den überlebenden Pfad umgeschrieben (23 Dateien; der Obsidian-Plugin-Cache unter `.obsidian/` blieb ausgenommen, er ist Werkzeugzustand, kein Kataloginhalt), danach 75 `archive --apply`, dann `reindex` beider Bundles.

**Beweislage:** `okf-cli check` → `OK — 0 violations`. `wikilinks` → 2123 Links, 271 aufgelöst, **0 mehrdeutig**, 1852 unaufgelöst — Zahl für Zahl der Stand vor dem Merge, die `wikilink-collision`-Warnungen des Archivlaufs haben also keine Mehrdeutigkeit erzeugt (aktiv schlägt archiviert). `ai-wiki` 180 auf 105 aktive Konzepte, `_archive/ai-wiki/` 75. Ein erneuter Duplikat-Scan meldet auf dieser Achse **0** verbliebene Gruppen. Katalog gepusht.

## Offen, bewusst nicht mitgemacht

- **Das Bundle `ai-wiki` besteht weiter** mit 105 Konzepten ohne Gegenstück. Die Entscheidung galt der Doppelablage, nicht der Auflösung des Bundles; das wäre ein eigenes Vorhaben mit 105 Pfadwechseln.
- **33 Duplikatgruppen mit 71 Dateien bleiben katalogweit** — auf anderen Achsen (`claude-code-wiki` gegen `general-knowledge-wiki`, `obsidian-vault-mgmt-wiki` gegen `general-knowledge-wiki`), plus die gewollten `qm-wiki`-internen Sichten und die fünf Repo-`GLOSSARY.md`, die ein Scan-Artefakt sind. Jede weitere Achse braucht ihre eigene Richtungsentscheidung.
- **Neue bundle-interne Doppelung:** `general-knowledge-wiki/ai-agentic-coding/mcp.md` und `.../model-context-protocol.md` tragen nach der Faltung denselben Hermes-Text. Das ist eine Folge dieses Merges und gehört entschieden.
- **Vault-Migrationsartefakte** der Form `[800 Bank/API]()` und `[750 PERSISTENTS/.../LibreChat]()` stehen weiter in `custom-endpoint.md`, `plan.md`, `tools-ki-agenten.md`. Leer-Links mit Vault-Pfad als Label, älter als dieser Merge — katalogweit auf Klartext normalisieren, nicht im Merge-Commit vermischt.
- **`.tagvec` ist für die zusammengeführten Konzepte inhaltlich veraltet.** `build-semantic-index` füllt nur fehlende Pfade, keine inhaltlich geänderten; die Abdeckung meldet `complete`, obwohl der Vektor den alten Text beschreibt. Das ist `OKFT-3520`.
