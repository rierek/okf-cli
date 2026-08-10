---
# OKFT-cbxu
title: Measure the jargon-paraphrase query class
status: in-progress
type: task
priority: high
created_at: 2026-08-10T12:59:26Z
updated_at: 2026-08-10T12:59:26Z
parent: OKFT-hkze
---

## Objective (User Story)
As the PO, I want to know whether the R1 miss is a single case or a query class, so that nobody tunes fusion parameters against an anecdote.

## Evidence (MODUS-B-REPORT I01)
In run R1 a user-language paraphrase ("selbstgehosteter Login-Dienst", "gerätegebundener Schlüssel") failed to surface a concept whose title carries "Passkey" and whose description says "Passwordloser Login" — literally. Ten plausible neighbours came back instead (Vaultwarden, OAuth2, SSO, SSH, Tailscale); cosine 0.53 for Vaultwarden beat the target. Reformulating with the jargon found it, and then through the LEXICAL arm. The semantic arm missed the exact case that justifies its existence.

## EARS Acceptance
- THE measurement SHALL use targets sampled mechanically BEFORE any query is written, so no target is picked for its expected outcome.
- THE queries SHALL be authored by independent agents that never see the measurement, under the vocabulary rule of `queries_v2.json` plus an absolute ban on the title's distinctive terms.
- THE result SHALL be compared against the shipped baseline on `queries_v2.json` (recall@1 0.25, recall@10 0.825, MRR 0.438, zero-hit 0.175 — `docs/okf-retrieval-architecture/eval/shipped_v2.json`).
- THE live catalogue and both indices SHALL be bitwise unchanged afterwards.

## Success Criteria
- SC-001: query set and raw results committed under `docs/okf-retrieval-architecture/eval/`.
- SC-002: a written verdict — class or anecdote — with the numbers that carry it.

## Note
No fix is in scope. If the class is real, the remedy (fusion parameters, query expansion, or neither) is a separate decision on this evidence.
