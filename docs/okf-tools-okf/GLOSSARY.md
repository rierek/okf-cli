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
| document-embedding | Embedding a whole concept (title+body) as one vector — the current default; dilutes distinctive terms in a long body into a single averaged point. | Q03, bean `okf-cli-wuiv` |
| chunk-embedding | Embedding a concept as several smaller units (title, per-paragraph body chunks) instead of one whole-document vector, to avoid document-embedding's dilution. | Q03, bean `okf-cli-wuiv` |
| tag-vector expansion | Using already-populated tag-level embeddings to find synonymous tags for a query term, without touching concept-level embeddings. | Q03, bean `okf-cli-wuiv` |
