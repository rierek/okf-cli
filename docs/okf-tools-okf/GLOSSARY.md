---
type: Glossary
title: okf-tools Glossary
description: Ubiquitous language for the okf-tools project — domain terms and definitions.
tags:
  - glossary
timestamp: 2026-07-18T00:00:00Z
---

# Glossary

> Maintained via the `ce-glossary` skill. One row per domain term.

| Term | Definition | Source concept |
|------|------------|----------------|
| semantic backstop | Retrieval fallback that engages only when keyword search returns weak or zero results; never displaces a confident keyword top hit. | P8/8c, bean `okf-cli-8uaf` |
| document-embedding | Embedding a whole concept (title+body) as one vector per concept — the shipped unit. | Q03, bean `okf-cli-wuiv` |
| chunk-embedding | Embedding a concept as several smaller units (one per h2/h3 section) instead of one whole-document vector, scored per concept by the best-matching chunk. | Q03, bean `okf-cli-wuiv` |
| tag-vector expansion | Using already-populated tag-level embeddings to find synonymous tags for a query term, without touching concept-level embeddings. | Q03, bean `okf-cli-wuiv` |
| conditional handover | Fusion rule that decides per query which arm owns the ranking instead of merging both result lists — the lexical arm owns it only when its top-1 leads the runner-up clearly, otherwise the semantic arm owns it and lexical hits are appended behind. | R43, bean `okf-cli-cskz` |
| degradation note | A line the CLI writes to stderr announcing that the current run is degraded rather than failed — a missing or stale lexical index, an unreachable embedding backend — and naming the remedy. It never changes the exit code. Over MCP it is prepended to the returned text for non-JSON commands, since the consumer cannot observe stderr. | D01, beans `okf-cli-2o39` / `okf-cli-4ws6` |
| vocabulary leak | Share of an evaluation query's terms that appear verbatim in its target document — the quality measure of a ground-truth set, since a high share favours lexical retrieval and distorts any lexical-versus-semantic comparison. | R33/R41, bean `okf-cli-cskz` |
| filter residual | The filter dimensions a data source cannot enforce on its own, handed back to whoever queried it so that applying them stays an explicit obligation — the device that turns a skipped filter from a silent omission into a named return value. | I01, concept `filters-constrain-the-answer` |
| assertion coverage | Whether the test named for a criterion actually fails when that criterion breaks, as opposed to merely existing — the question a traceability table cannot answer and mutation does. | `docs/wikilink-awareness/SPEC.md`, Traceability |
| equivalent mutant | A weakening no test can kill because it cannot change an observable outcome, as opposed to a surviving mutant, which marks a real assertion gap — the distinction that keeps a mutation score from being padded by unkillable entries. | `docs/wikilink-awareness/mutants.py` |
