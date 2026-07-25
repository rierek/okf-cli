---
# okf-cli-wuiv
title: okf-cli/mcp maturity revision
status: in-progress
type: milestone
priority: normal
created_at: 2026-07-25T18:13:09Z
updated_at: 2026-07-25T22:16:14Z
---

Raise okf-cli + okf-mcp maturity at its three weak edges — retrieval semantics, MCP->subprocess correctness, root-safety — with every retrieval change measured as a delta against a keyword baseline frozen BEFORE any optimization.

## Definition of Done (what ships together)
- Keyword baseline frozen (Phase 1) then re-measured after hybrid retrieval; regression gate green.
- B01 fixed + integration-test layer at the MCP->subprocess boundary.
- Hybrid `find` (semantic backstop + filter composition + score breakdown), MCP `okf_tags` parity, root-safety.
- Canonical overview doc de-staled to 20 verbs.

## Plan (source of truth)
`docs/okf-revision/PLAN.md` (ce-plan-reviewer GREEN, PO-approved 2026-07-25).
Think collection: `~/Obsidian/Vault/okf-revision/{DESIGN,EVAL-DESIGN,DECISIONS}.md`.

## Global constraints
- No new runtime deps in `cli/okf-cli.py` (stdlib only; sqlite3 for tagvec reads; embedding production stays offline).
- `find` degrades gracefully to keyword-only when `.tagvec` / embedding backend absent — never hard-fail.
- Conventional Commits, title <=50 chars, no Co-Authored-By.
- Baseline immutability: re-measurement writes a NEW result file.
- Fixtures seeded into the real catalogue (D11), each with reliable teardown.

## Parallelization guidance (added 2026-07-25)

Dispatch ce-implementer agents in waves per the blocked_by graph. Parallel agents MUST run in isolated git worktrees (tools/CLAUDE.md: git checkout/switch in the main workdir is forbidden; concurrent commits to shared HEAD collide). One worktree per concurrent task, then serialize the merges back.

Safe parallel waves:
- Wave A: P1 (okf-cli-83vq) || P2 (okf-cli-ez6f) - okf-cli.py vs new fixtures.py
- Wave B: P6 (okf-cli-asky) || P3 (okf-cli-n9l6) - new test file vs new golden.json
- Wave C: P4 (okf-cli-o7z2) - solo (needs P2+P3)
- BARRIER: P5 (okf-cli-5qmn) FREEZE - solo, blocks all Phase 2 (D09, non-negotiable)
- Wave D: P7 (okf-cli-3geg) || P10 (okf-cli-x0l7) || P11 (okf-cli-1617) - distinct files/regions
- Wave E: P8 (okf-cli-8uaf) - long pole; edits okf-cli.py cmd_find + okf_mcp.py. Dispatch AFTER Wave D lands (P10/P11 small, different regions of the same files) even though its only hard blocked_by is P7.
- Wave F: P12 (okf-cli-6gq6) - solo
- Wave G: P13 (okf-cli-e9hm) || P14 (okf-cli-sjqu) - new md vs catalogue-repo doc

Hard limits (not a cut defect): (1) P5 baseline freeze is a deliberate global barrier. (2) okf-cli.py (P1/P8/P11) and okf_mcp.py (P8/P10) are shared files - worktree isolation is mandatory for concurrent edits.

## PF-1 (PO, 2026-07-25, verbatim + interpretation)

Verbatim: 'ab p12 arbeiten wir in dieser session inline ohne subagents. das ist kritisch'

Interpretation (binding): From P12 (okf-cli-6gq6) onward — P12, P13, P14, P15 — all implementation and review work happens INLINE in the supervisor session itself; no ce-implementer/ce-specs-reviewer dispatches. The P8 cycle (implementer already running + its review) still completes in the old dispatch mode as the last subagent work. Supervisor no-feature-code rule is overridden by PO authority for these tasks. Quality mechanics stay: TDD, RED proof, mutation self-test, full-suite delta rule, catalogue clean.

## Session close 2026-07-25 (realization session, PF-1 inline from P12)

12/14 tasks completed (P1-P8, P10-P12, P14). Open by design: P13 step 3 (separate agentic session, task set ready) and P15 (optional, Q04-gated, draft). Epics: Phase 1 + Phase 2 + Phase 4 tagged to-review; Phase 3 open pending P13 run. Full suite 189 tests, exactly 19F/2E pre-existing (crosslink suites), 0 new. Baseline frozen (baseline-f0714b2.json) + hybrid re-measured (hybrid-39d6c0a.json), gate PASS: paraphrase zero-hit 1.000->0.500, no literal regression. Catalogue + live .tagvec pristine (md5-verified). Open PO questions: Q01 index.md-vs--json eval surface; Q02 --bundle-as-scope-alias semantics; Q03 populate concept_emb for the live catalogue productively (currently the backstop is dormant in production — no concept vectors); Q04 P15 go/no-go.

## Q03 — revised 2026-07-25 (PO-Review, live evidence)

**Frage:** concept_emb produktiv befüllen — und mit welchem Embedding-Design?

**Hintergrund:** Backstop (P8) liest concept_emb; Live-Katalog aktuell 0 Zeilen -> Backstop in Produktion tot. Live-Test während Review: Paraphrase ohne Keyword-Overlap fand mit leerem concept_emb den Zieltreffer gar nicht. Scoped Demo-Befuellung (10 Konzepte devdash-tui/, bge-m3, danach zurueckgerollt) zeigte: Backstop feuert, matcht aber auf falsche Konzepte (cosine 0.40-0.44), Zieltreffer fehlte komplett in der Trefferliste -- reales False-Positive-Muster, gleiche Kategorie wie der bereits gefixte P8-Fund LL-06, jetzt mit echten statt Fixture-Daten reproduziert.

**Root cause (Design-Review im PO-Gate):** concept_emb embedded pro Konzept EIN Vektor aus title+"

"+body (concept_text()) -- ganzes Dokument als ein Punkt. Genau dieses Muster (Titel/Body-Anreicherung ins Embedding mischen) hat das Projekt bei TAG-Embeddings bereits als Kontaminationsquelle dokumentiert und verworfen (cli/embeddings/README.md:27-35: title/description-Anreicherung liess unabhaengige Tags faelschlich aehnlich werden, z.B. task-brief <-> superwhisper 0.92; Fix war Slug-only-Embedding). concept_emb macht fuer Konzepte, was fuer Tags bereits als Fehler identifiziert wurde -- ein ganzer Body verwaessert zu einem Durchschnittspunkt, wodurch thematisch aehnlich strukturierte, aber inhaltlich falsche Konzepte (z.B. andere Entity-Fields-Referenzseiten) naeher an die Query ruecken als der tatsaechliche Treffer.

**Optionen:**
- (a) Jetzt voll produktiv befuellen (--target concepts, alle ~2435 Konzepte), Risiko dokumentiert in Kauf nehmen. Recall fuer echte Paraphrasen steigt, aber belegtes False-Positive-Risiko bleibt ungemindert im Live-Katalog.
- (b) Erst Schwellenwerte/Margin fuer provenance:semantic nachschaerfen (kleiner Rework, gleiche Architektur), dann befuellen.
- (c) Dormant lassen -- Backstop bleibt Feature-ohne-Wirkung bis auf Weiteres.
- (d) NEU, empfohlen: Chunk-Embedding statt Dokument-Embedding. Nicht ein Vektor pro ganzem Konzept, sondern mehrere kleinere Einheiten pro Konzept (Titel separat + Body in Absaetze/Chunks aufgeteilt), je ein Embedding-Vektor; Retrieval matched gegen die spezifischste Chunk statt den verwaesserten Gesamtdurchschnitt. Behaelt Body-Abdeckung (S3-Fixture-Garantie -- Konzept nur ueber Body-Vokabular auffindbar -- bleibt erfuellt, anders als bei Titel-only-Begriffszerlegung, die den bereits verworfenen Tag-only-Rueckschritt wiederholen wuerde). Vermeidet die Verwaesserung, die den heutigen Live-Fehltreffer erklaert. Erfordert eigenen scoped Rework-Task (Schema-Erweiterung concept_emb -> concept_chunk_emb oder aehnlich, Chunking-Strategie, Re-Aggregation im Retrieval) -- kein Threshold-Tweak, ein Architektur-Umbau.

**Empfehlung:** (d) vor (a) -- die 0.40-0.44-Cosine-Fehltreffer sind ein Verwaesserungs-Symptom, kein Schwellenwert-Symptom; ein Threshold-Fix (b) haette die Wurzel nicht behoben. (b) bleibt als guenstiger Zwischenschritt denkbar, falls (d) nicht sofort priorisiert wird.

**Status:** ANSWERED 2026-07-26 by measurement — see "Q03 resolution" below.

## Q03 resolution 2026-07-26 (think session, full-catalogue experiment)

Design collection + evidence: `docs/okf-retrieval-architecture/` (DESIGN.md, REFERENCES R01-R43, eval/).

Experiment: 2437 concepts embedded in 6 arms (bge-m3 and voyage-3-large, each over title / title+body / h2-h3-chunks, 35800 vectors) measured against 48 queries with known targets — 40 written by subagents with 0.6 % vocabulary overlap to their target document, plus 8 real PO queries. The live `.tagvec` was never touched; arms were namespaced through the existing `model` column in a separate eval DB.

Answers, all measured rather than argued:
- **Option (d) chunking is rejected.** With the chosen model it is worse than document embedding (MRR 0.394 vs 0.452); it only compensates a weak model on long texts. Title-only is the worst arm of all, below today's substring scoring — the S3 guarantee is now empirically confirmed.
- **The dilution root cause does not hold.** The original 0.40-0.44 finding was a scope confound: only 10 concepts of one bundle were populated while the counter-test target lived in another.
- **An absolute cosine floor is impossible.** Correct targets and wrong top hits overlap completely (wrong up to 0.813, correct down to 0.494). Cosine ranks, it does not certify.
- **The actual defect is the fusion rule.** The backstop fired on 47 of 48 queries and stayed ineffective: normalised BM25 values at ranks 2-10 sit near 0.9, good cosines near 0.6, and both are interleaved by raw score. Today's rule is second-worst of five tested; conditional handover (lexical owns the ranking only on a clear top-1 margin, otherwise semantic owns it) has the best worst case across query regimes.
- **A lexical upgrade does not replace embeddings.** FTS5+BM25+porter+prefix finds zero of 40 pure paraphrases; it solves morphology, not synonymy. It stays worthwhile for literal queries and latency.
- **Model choice decides usability.** voyage-3-large MRR 0.452 / zero-hit 0.167 against bge-m3 0.150 / 0.646.

PO decision 2026-07-26: populate `concept_emb` productively with **voyage-3-large**, unit **title+body**, network dependency accepted under the existing graceful-degradation rule.

Follow-up work (ordered by leverage, to be operationalised from the plan session): fusion rule first (without it every embedding gain is wasted), then productive population, then producer hardening (see LL-08/LL-09 in docs/LESSONS-LEARNED.md), then the FTS5 lexical path, then versioning the eval assets.

## Q03 — Unterfrage ergaenzt 2026-07-25 (PO)

Zusaetzlich zur Design-Frage (Dokument- vs Chunk-Embedding, siehe oben): PO wirft die vorgelagerte Frage auf, OB Embedding ueberhaupt noetig ist -- gegenueber besserem Keyword-/Lexikal-Retrieval (z.B. echtes FTS5 mit Stemming/BM25/Prefix statt des aktuellen reinen Substring-Scorings). Gegenprobe waehrend Review live gefahren: reale Nutzeranfrage (Tailscale/Mac-Thinkpad/Mockup-HTML-Bereitstellung) gegen den aktuellen keyword-only find, siehe Ergebnis unten. Falls Keyword-Retrieval (ggf. mit FTS5-Aufwertung) das Gros der Faelle bereits loest, waere die Antwort auf Q03 ggf. (c)/(e, neu: FTS5-Aufwertung statt Embedding) statt (d).

## Q03 — Gegenprobe-Ergebnis 2026-07-25

Live-Gegenprobe (PO): find "mockup tailscale" gegen echten Katalog fand serve-excalidraw-drafts.md (dev-wiki/testsystem-vite-tailscale) NICHT -- Konzept nutzt Vokabular Excalidraw/PNG-Vorschau, nie das Wort mockup; nur Browsing (index) fand es. Reales Zero-Hit-Beispiel mit heutigem keyword-only find, spricht FUER Embedding-Notwendigkeit (Antwort auf die ergaenzte Unterfrage 'ist Embedding ueberhaupt noetig' faellt hier zugunsten ja aus) -- unabhaengig von der separaten Chunk-vs-Dokument-Designfrage oben. Nebenbefund: keine der beiden thematisch naechsten Konzepte (serve-excalidraw-drafts.md fuer PNG-Mockups, serve-dev-server-to-tailnet.md fuer generisches HTML-via-tailscale) deckt beide Aspekte (Mockup + HTML) gemeinsam ab -- echte Katalog-Luecke, kein Suchproblem, nicht Teil dieses Reviews.

## Q03 — Nebenbefund Tag-Ebene 2026-07-25 (PO-Gegenprobe Teil 2)

PO testete zusaetzlich: --tag tailscale filtert korrekt, aber 'mockup' kommt in keinem tailscale-getaggten Konzept literal vor (serve-excalidraw-drafts.md ist mit excalidraw/tailscale/export/remote-access getaggt, nicht mockup) -> 0 Treffer trotz Filter. 'mockup' ist zudem gar kein registrierter Tag (okf-cli tags mockup liefert nur entfernte Naeherungen: backup/mcp/molecule/mouse). Das Paraphrase-Problem (mockup vs excalidraw) besteht also auch auf TAG-Ebene, nicht nur in Titel/Body.

Relevant fuer die Design-Entscheidung: die Tag-Embeddings (emb-Tabelle) sind -- anders als concept_emb -- bereits produktiv befuellt (752 bge-m3-Zeilen, diese Session). Ein Tag-Synonym-Backstop (Query-Term gegen Tag-Vektor-Naehe, z.B. mockup~excalidraw) waere ein guenstigerer, sofort einsetzbarer Hebel gegenueber der riskanteren concept_emb/Chunk-Frage oben -- nutzt bereits vorhandene, saubere Infrastruktur (keine Kontaminationsgefahr, da Slug-only-Embedding bereits bewaehrt ist), statt neue Dokument/Chunk-Embeddings einzufuehren. Wert als zusaetzliche Option (e) fuer Q03 pruefen: Tag-Vektor-Expansion der Query VOR dem Keyword-Scoring, orthogonal zur concept_emb-Frage.

## Grilling 2026-07-26 -- Q01/Q02/Q04 entschieden

D01 (Q01) 🟢 -- Eval misst index-walk (S4) nur ueber --json-Surface, keine index.md-Assertion. Fakt: bewusste, bereits dokumentierte Scope-Entscheidung (runner.py:22-24, P3-Review-Prelude 2026-07-25). Keine Aenderung.

D02 (Q02) 🟢 -- --bundle bei find wird ENTFERNT, --scope bleibt einziger Filter-Flag (nicht nur Alias-Beibehaltung -- echte Streichung). Beide Flags loesen identisch ueber resolve_scopes() auf (okf-cli.py:796-798), reine API-Verdopplung. Folge-Task T01: --bundle aus find-Argparse (okf-cli.py:2228) + MCP _FLAGS (okf_mcp.py:21,83) + Test (test_okf_cli.py:1350) + Doku (okf-cli-mcp-overview.md:31,74) entfernen.

D04 (Q04) 🟢 -- P15 (okf-cli-cfgj) gestrichen. P14 ist akzeptierter Endstand (20/20 Verben), kein Beleg fuer wiederkehrende Verb-Drift, die einen Generator rechtfertigt. Folge-Task T02: Bean okf-cli-cfgj auf scrapped setzen.

Q03 bleibt gesondert offen (Design-Groesse Chunk-vs-Dokument-Embedding, nicht Teil dieser Grilling-Runde).
