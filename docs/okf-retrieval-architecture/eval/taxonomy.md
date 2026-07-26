# Failure taxonomy — residual zero-hits (Task 12)

Based on: `docs/okf-retrieval-architecture/eval/shipped_v2.json`, regenerated
2026-07-26 via `remeasure.py --root ~/Obsidian/Knowledge-Catalogue --queries
queries_v2.json queries_real.json --out shipped_v2.json`, okf-tools git sha
`cdd7a0b4824f7d232fb0b6aa393a9aff8e7e2328`.

`rank` = achieved rank at the shipped default (`--limit 10`) — blank on every
row here, since this table is exactly the 8 queries (of 48) that missed it.
`ranking` vs `synonymy` is decided by a companion `--limit 50` run of the same
shipped `okf-cli find` plus a standalone `semantic_ranking()` full-corpus
call; `note` carries that evidence together with the top-3 actually returned
at `--limit 10`.

| query | expected_path | rank | class | note |
|---|---|---|---|---|
| aufgabenübersicht im notizprogramm ohne eigenentwicklung | agent-memory/po-immersion-beans-via-obsidian-bases-no-custom-tui | – | ranking | top-3@10: replikation, detail-vergleichstabelle-feature-matrix, ki-im-alltag-claude-code-praxis. Semantic arm never fires, even at `--limit 50`: lexical top-1 is wrong but keeps a clear margin (`SEMANTIC_MARGIN_RATIO` gate) past 50 hits. Standalone `semantic_ranking()`: rank 40/2443, cosine 0.46 — close enough to matter, but the fusion gate never lets it run. |
| bots aus hauseigener oberfläche beauftragen | ai-wiki/claude-dispatch | – | ranking | top-3@10: telegram, tools-ki-agenten, ai-agent-tools. Found at rank 27/2443 with `--limit 50` (semantic arm already owns at `--limit 10`) — past the display window only. |
| wer hat Vorrang bei widersprüchlichen Bauplänen | dev-arch-wiki/architecture-methodology/single-source-of-truth-prinzip | – | ranking | top-3@10: adr-0025, adr-0026, adr-0037. Found at rank 35/2443 with `--limit 50`; 34 governance/ADR docs sharing "Architektur" vocabulary outrank the SSoT concept that actually answers the query. |
| Sorten von Algorithmen Aufbau und Aufsicht | ai-wiki/ai-model | – | synonymy | top-3@10: gliederung-der-auditarten, in-memory-rebuild-index, managementbewertung-ablauf-aufbau. Not found at `--limit 50`. Standalone `semantic_ranking()`: rank 90/2443, cosine 0.395. Concept answers the query ("Typen von KI-Modellen" section) but shares zero surface vocabulary with the paraphrase (`queries_v2.json` construction) and the embedding placed it far outside any plausible rescue window. |
| typische Stolperfallen Selbsthosten zuhause | home-lab-wiki/context/lessons/synology-spezifisch | – | ranking | top-3@10: self-hosting, home-lab, vps. Found at rank 11/2443 with `--limit 50` — one position past the default cutoff. |
| metadaten auswerten erweiterung wissensarchiv | general-knowledge-wiki/ai-agentic-coding/dataview | – | synonymy | top-3@10: meta-modell-des-wissensmanagements, external-reception-and-origin-story, catalog-and-okf-synthesis. Not found at `--limit 50`. Standalone `semantic_ranking()`: rank 736/2443, cosine 0.35 — the deepest miss in the set. Dataview (Obsidian metadata-query plugin) answers the query, but "Wissensarchiv"/"Metadaten auswerten" share no vocabulary with the doc body. |
| chatgpt gegenstück konkurrenz vergleich | general-knowledge-wiki/ai-agentic-coding/openai-codex | – | ranking | top-3@10: qwen-3-6-plus-vs-claude-live-test, openai-publishes-system-prompts-vs-anthropic, ai-model-rankings-openrouter. Found at rank 14/2443 with `--limit 50` — 4 positions past the default cutoff. |
| Was sind die Grundbestandteile eines Systems für das Wissensmangement? | km-wiki/bausteine-des-wissensmanagements-probst-2006 | – | ranking | top-3@10: wissenssammlung, kein-backup-oder-wiederherstellungsplan-fuer-wissen, knowledge-management-framework-der-gartner. Found at rank 18/2443 with `--limit 50`; top semantic neighbours are all km-wiki KM concepts (cosine 0.62–0.64) crowding out the exact target (0.586). |

## Counts

| class | count | share |
|---|---|---|
| ranking | 6 | 75% |
| synonymy | 2 | 25% |
| catalogue-gap | 0 | 0% |
| wrong-target | 0 | 0% |
