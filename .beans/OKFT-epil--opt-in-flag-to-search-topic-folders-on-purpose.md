---
# OKFT-epil
title: Opt-in flag to search topic folders on purpose
status: completed
type: feature
priority: low
created_at: 2026-08-13T11:25:38Z
updated_at: 2026-08-13T17:37:27Z
---

Deferred by D16 itself: `lean-stack/docs/aca_capability-mcp/DECISIONS.md:31` chooses the declaration rule for the index corpus and adds "Zusätzlich Opt-in-Flag für Themen-Ordner als eigene, zweite Frage ('was haben wir damals gedacht?')".

OKFT-n8xz removes topic folders from the default corpus. That is right for the default case — canon should outweigh scaffolding — but it also removes the only way to search a think session's own DECISIONS/QUESTIONS/REFERENCES through okf-cli. The question this flag answers is a real one and different from the default: "what did we think back then?"

Deliberately NOT part of epic OKFT-wmbu. Filed only so the deferral stays referenceable — before this bean it existed as one clause in a table row of a neighbouring repo's DECISIONS.md, which is how deferrals get silently forgotten. Raised by ce-verify-operationalization at Gate B, 2026-08-13.

Open when picked up: flag name and shape, whether it widens the corpus or searches a second one, and whether it belongs on `find` only or on `build-index` too.
