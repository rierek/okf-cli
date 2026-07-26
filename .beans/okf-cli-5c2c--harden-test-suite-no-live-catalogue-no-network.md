---
# okf-cli-5c2c
title: 'Harden test suite: no live catalogue, no network'
status: todo
type: task
priority: normal
created_at: 2026-07-26T06:43:49Z
updated_at: 2026-07-26T06:43:49Z
parent: okf-cli-wuiv
---

Structural weakness surfaced during T07 (`okf-cli-8j7l`), 2026-07-26.

`cli/test_eval_fixtures.py` sets `CATALOGUE_ROOT = fixtures.DEFAULT_ROOT` (`:31`) and runs
`okf.cmd_find` against the **live** Knowledge Catalogue. While `concept_emb` was empty this was
inert. The moment the semantic arm became real (voyage rows from T03 + `SEMANTIC_MODEL` switched
in T07), the same test started issuing real Voyage API calls during `unittest discover` and
began failing — a nonsense seed token now returns 50 nearest neighbours instead of `[]`.

T07 neutralised that one test. This bean owns the general question.

### Requirement 1: Unit tests reach neither the live catalogue nor the network

**Objective:** As a maintainer running the suite, I want tests to be hermetic, so that a run
costs nothing, leaks no credential, and cannot be perturbed by whatever the real catalogue
happens to contain today.

#### Acceptance Criteria

1. THE test suite SHALL be auditable for tests that resolve a catalogue root outside a
   temporary directory, and every such test SHALL be listed with its justification.
2. WHERE a test legitimately needs the real catalogue THE suite SHALL make that dependency
   explicit rather than implicit through a module-level default.
3. THE suite SHALL fail loudly IF any test performs an outbound network call, rather than
   performing it silently.
4. THE audit SHALL cover the embedding call sites in both the query path and the producer.

#### Success Criteria

- SC-01: an inventory of every test touching a non-temporary catalogue root exists, each row
  marked keep-with-reason or convert-to-tmp.
- SC-02: a full `python3 -m unittest discover -s cli -p 'test_*.py'` run makes zero outbound
  network calls, demonstrated by a guard that turns an attempted call into a test failure.
- SC-03: the baseline failure count after the change is stated explicitly and is not worse
  than the count at the time this bean starts.

_Requirements: PLAN.md Global Constraints ("no network at import time and none under test") ·
surfaced by okf-cli-8j7l · related SC-NET on okf-cli-pean/2a1w/8j7l/ftri_

## Notes

Not urgent, and deliberately NOT part of the retrieval feature: it is test-infrastructure
hygiene, and folding it into the architecture chain would widen a scope that is already
13 tasks long. Schedule after `okf-cli-cskz` closes.
