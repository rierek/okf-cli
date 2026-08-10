---
type: Tasks
title: "Modus B — Agentic Realism Check (Task Set + Rubric)"
description: "Task prompts and scoring rubric for the Modus-B retrieval check, to be run in a separate agentic session with only the okf MCP tools and no repo access."
tags:
  - tpic
  - okf-revision
timestamp: 2026-07-25T21:00:17Z
---
# Modus B — Agentic Realism Check (Task Set + Rubric)

**Execution contract (D12/Q07, bean `okf-cli-e9hm`):** run in a SEPARATE
agentic session, never by the implementer of the retrieval code. The
test-agent gets ONLY the okf MCP tools (`mcp__okf__*`) plus one task prompt
at a time — no repo access, no golden.json, no fixture knowledge. Success is
measured end-to-end (query formulation included). Results are a QUALITATIVE
sanity signal; they are explicitly EXCLUDED from the P12 gate metric.

## Preconditions (session operator, not the test-agent)

1. Seed fixtures: `python3 cli/eval/fixtures.py --root ~/Obsidian/Knowledge-Catalogue --seed`
2. Concept embeddings for S1–S4 present in the live `.tagvec` (swap-in per
   P12 procedure, restore afterwards) — otherwise the backstop cannot fire
   and every paraphrase task degenerates to keyword-only.
3. After the run: `--teardown`, cache restore (md5 vs pristine), catalogue
   `git status --short` clean.

## Task prompts (verbatim to the test-agent)

Each task: hand the agent the prompt, `root=/Users/erik/Obsidian/Knowledge-Catalogue`,
max 5 tool calls. Success = the target concept path appears in the agent's
final answer.

| # | Scenario | Prompt (natural, paraphrase-style — no fixture tokens) | Target | Class |
|---|----------|--------------------------------------------------------|--------|-------|
| T1 | S1 (well-tagged, correct bundle) | "Find the note about the reference calibration benchmark entry in the agent memory area." | `agent-memory/_okfeval-s1` | paraphrase |
| T2 | S2 (misfiled: right content, wrong bundle) | "There is a concept about a misfiled note sitting in an incorrect collection — locate it." | `ai-wiki/_okfeval-s2` | paraphrase |
| T3 | S3 (untagged, body-only) | "Find the concept describing an unmarked item that lacks any classification." | `agent-memory/_okfeval-s3` | paraphrase |
| T4 | S4 (metadata-rich, discoverable by browsing) | "Without searching by its exact words: browse the agent-memory bundle and identify the record that is absent structured labels and only discoverable by browsing." | `agent-memory/_okfeval-s4` | paraphrase/browse |
| T5 | S1 (control, literal) | "Search the catalogue for 'zqxeval ceiling' and name the concept." | `agent-memory/_okfeval-s1` | literal control |

## Rubric (per task, record verbatim)

- **outcome:** success | partial (target seen in tool output but not named) | fail
- **tool calls used:** n/5, sequence (e.g. `okf_find` → `okf_read`)
- **query the agent actually formulated** (the realism datum — copy verbatim)
- **provenance:** did the hit come from keyword rank, semantic backstop
  (`provenance: semantic`), or browsing (`okf_index`/`okf_list`)?
- **friction notes:** wrong root guesses, filter misuse, retries

## Reporting

One markdown table (task | outcome | calls | query | provenance | notes) +
a 3-sentence qualitative verdict appended to bean `okf-cli-e9hm`. Expected
asymmetries worth watching (from P12 data): S2/S4 paraphrase rescue did NOT
work mechanically (cosine too weak) — if the agent still finds them via
reformulation or browsing, that is exactly the Modus-B signal Modus A
cannot measure.
