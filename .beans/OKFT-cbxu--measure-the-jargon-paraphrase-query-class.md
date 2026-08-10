---
# OKFT-cbxu
title: Measure the jargon-paraphrase query class
status: completed
type: task
priority: high
created_at: 2026-08-10T12:59:26Z
updated_at: 2026-08-10T13:11:08Z
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


## Result 2026-08-10 — hypothesis REFUTED, real cause found

Twelve targets sampled mechanically before any query existed (`random.seed(20260810)`, title carries a term rare across catalogue titles, body 1200-20000 chars); three independent agents wrote four queries each under an absolute ban on the title terms. Content-word leak against the target document: 1 of 111 words.

The jargon-paraphrase class performs BETTER than the general unbiased paraphrase set, not worse: recall@1 0.583 vs 0.25, MRR 0.694 vs 0.438, zero-hit 0.167 vs 0.175. There is no class defect. Tuning the fusion rule on the R1 anecdote would have altered a healthy mechanism.

The R1 miss has a different cause: `home-lab-wiki/notes/authelia-passkey-authentication` had NO row in `concept_emb`. The semantic arm could not find it because it did not know it. Catalogue-wide 115 of 2589 concepts (4.4 %) had no vector, every one of them added after the one-shot population run, plus 74 orphan rows for deleted files. Carried into its own bean.

After running the producer (166 concepts): the R1 query returns the target at rank 1 instead of not at all; on the I01 set MRR 0.694 -> 0.771 and zero-hit 0.167 -> 0.083. Controlled A/B on the same catalogue state shows the price on the canonical 48-query set: MRR 0.450 -> 0.432, recall@1 0.271 -> 0.250, recall@10 and zero-hit unchanged — noise of about one query at n=48.

Artefacts: `docs/okf-retrieval-architecture/eval/{queries_i01.json,i01_jargon.json,i01_jargon_after.json,shipped_2026-08-10.json}`. Evidence and numbers: `docs/okf-revision/MODUS-B-REPORT.md`, section "Nachtrag 2026-08-10".
