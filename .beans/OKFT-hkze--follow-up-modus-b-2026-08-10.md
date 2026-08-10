---
# OKFT-hkze
title: Follow-up Modus B 2026-08-10
status: completed
type: epic
priority: normal
created_at: 2026-08-10T12:58:26Z
updated_at: 2026-08-10T15:11:51Z
parent: OKFT-wuiv
---

Findings carried out of the Modus-B agentic realism check (2026-08-10). Full evidence: `docs/okf-revision/MODUS-B-REPORT.md`.

Five fresh agents with only the okf MCP tools solved five retrieval tasks against real catalogue concepts, 5/5 found, four of them on a single search call. Retrieval quality itself is not the problem the run exposed; output attribution, score presentation and catalogue hygiene are.

## Shared context for children
- The run is qualitative sanity by contract (D12) and is excluded from the P12 gate metric. These children inherit that: none of them is gated on a metric delta unless it says so.
- Report IDs map to beans one-to-one: B01, B02, I01, I02, I03, I04, Q01.
- The catalogue was bitwise unchanged across the run and must stay that way for any measurement child.


## Realisiert 2026-08-10

Alle sieben Report-IDs sind abgearbeitet, die Eins-zu-eins-Abbildung Report-ID auf bean hat gehalten.

B01 → `OKFT-wvgb` (jede Trefferzeile nennt ihren Arm) · B02 → `OKFT-hjqp` (Hypothese gemessen und **widerlegt**) · I01 → in der Session vom 2026-08-10 gemessen und als Abdeckungslücke entlarvt, daraus `OKFT-wsne` · I02 → `OKFT-3rb6` (eine Ranking-Skala) · I03 → `OKFT-t2w8` (kompakter Katalog-Index) · I04 → `OKFT-idch` (Typ/Ablageort im `memory-layer-wiki`) · Q01 → `OKFT-gpcx` (`superseded_by` als Frontmatter-Relation).

Zwei PO-Entscheidungen in dieser Realisierung. **D01** — die Kopfzahl einer `find`-Trefferzeile ist `rank: N`, die 1-basierte Position in der ausgelieferten Liste; der arm-eigene Rohwert wandert in `--breakdown`. Rang ist die einzige Zahl, die per Konstruktion mit der Listenordnung übereinstimmt, ohne eine armübergreifende Score-Vergleichbarkeit zu behaupten, die es nach D12 nicht gibt. **D02** — Superseding wird eine optionale Frontmatter-Relation `superseded_by` auf `type: Decision`, katalogwurzel-absoluter Pfad, kein Status-Feld und kein Zustandsautomat; ein totes Ziel ist eine `check`-Violation, das Feld auf einem Nicht-Decision eine WARNING.

**Drei Befunde gingen über den Report hinaus und liegen als eigene beans am Milestone**, nicht hier: `OKFT-mac3` — der Duplikat-Scan fand 105 Gruppen statt der zwei aus B02, 66 davon auf der Achse `ai-wiki` gegen `general-knowledge-wiki`; das braucht eine Richtungsentscheidung, keine 105 Einzelurteile. `OKFT-8l96` — `_keyword_top1_is_confident` feuert auf dem realen Korpus praktisch nie, der lexikalische Arm besitzt über 48 Eval-Queries genau einmal das Ranking und das nur über `len(hits) == 1`. `OKFT-rx72` — der Eval-Runner ist am Tie-Break nicht deterministisch, zwei Läufe desselben Codes liefern denselben 8/9-Flip und zwei verschiedene MRR-Werte.

Beweislage: `just test` → `Ran 669 tests in 44.768s … OK` (Baseline bei Session-Start 637). Beide Arbeitsbäume clean. Repo-Commits `c9ffd21` bis `39e0891`, Katalog-Commits `9f95a27`, `bbccab3`, `ec5cc72`. `okf-cli check` gegen den echten Katalog: `OK — 0 violations`. Semantischer Index nach den drei Moves wieder `complete — all 2590 concept(s) embedded`, ausgelöst durch das neue `build-semantic-index --if-stale`, das jetzt auch als SessionStart-Hook registriert ist.
