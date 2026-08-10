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

## Revision 2026-08-10 — real concepts instead of seeded fixtures (SUPERSEDES the table above)

The fixture table above is kept as the record of what P13 steps 1-2 froze on 2026-07-25; it is no longer the executed contract. Two things changed under it: `find` now ranks through an FTS5/BM25 lexical arm plus a voyage-3-large semantic arm (`concept_emb` productively filled, 2989 rows), and `okf-tools/CLAUDE.md` rule 1 forbids test runs writing into `~/Obsidian/Knowledge-Catalogue`. Seeding `_okfeval-*` files today would reach neither arm without also rebuilding the live `.fts` index and producing embeddings for the fixtures — three mutations of live state to measure four synthetic documents.

PO decision 2026-08-10: run the realism check against REAL catalogue concepts with known targets. No seeding, no index rebuild, no network, no catalogue mutation. The scenario classes S1-S4 are preserved as analogues; the targets are chosen by the session operator and never shown to the test-agent.

Each task: hand ONE agent ONE prompt, `root=/Users/erik/Obsidian/Knowledge-Catalogue`, only `mcp__okf__*` tools, no repo access, max 5 tool calls. Success = the target concept path appears in the agent's final answer.

| # | Scenario analogue | Prompt (verbatim to the test-agent) | Target | Class |
|---|-------------------|-------------------------------------|--------|-------|
| R1 | S1 — well-tagged, canonical bundle | "Ich möchte mich an meinem selbstgehosteten Login-Dienst künftig ohne Passwort anmelden, nur über den gerätegebundenen Schlüssel meines Laptops. Gibt es dazu eine Notiz im Katalog, und zu welchem Ergebnis kommt sie?" | `home-lab-wiki/notes/authelia-passkey-authentication` | paraphrase |
| R2 | S2 — right content, surprising location | "Ich habe lokal ein Diagramm erzeugt, einmal als Bilddatei und einmal als bearbeitbares Original. Beides soll ein Nutzer auf seinem Handy im eigenen privaten Netz ansehen können. Beschreibt der Katalog dafür ein Vorgehen?" | `dev-wiki/testsystem-vite-tailscale/serve-excalidraw-drafts` | paraphrase |
| R3 | S3 — findable through body vocabulary only | "Welches Konzept erklärt die Arten, auf die getrennte Software-Dienste aneinander angeschlossen werden — über HTTP-Schnittstellen, ereignisgesteuerte Rückrufe, eingebettete Erweiterungen — und woran solche Vorhaben typischerweise scheitern?" | `general-knowledge-wiki/ai-agentic-coding/integration` | paraphrase |
| R4 | S4 — sparse metadata, browse-discoverable | "Nutze zum Auffinden vorrangig die Navigation über Bundles und Verzeichnisse, nicht die Volltextsuche: Welches Dokument hält die Entscheidung fest, den globalen Gedächtnisspeicher des Agenten und die projektbezogenen Notizen auf einer einzigen Datenbank auf dem Heimserver zusammenzuführen?" | `memory-layer-wiki/memory-analyses/2026-06-02-mem-27-sprint-plan-backend-consolidation` | paraphrase/browse |
| R5 | control, literal | "Suche im Katalog nach 'ralph wiggum loop' und nenne das Konzept." | `ai-wiki/ralph-wiggum-loop` | literal control |

R2 is the PO's own documented zero-hit from 2026-07-25 (`find "mockup tailscale"` missed this concept under keyword-only retrieval), re-run here against the shipped architecture. R3 carries an ambiguity risk the fixture version did not have: several concepts describe system coupling, so a near-miss is scored `partial`, not `success`.

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
