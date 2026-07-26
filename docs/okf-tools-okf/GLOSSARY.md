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
