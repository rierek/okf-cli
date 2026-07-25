# REFERENCES — okf-retrieval-architecture

Belege, auf die sich Aussagen dieser Sammlung stützen. Jede Zeile verifiziert (nicht aus dem Bean übernommen, sondern live nachgeprüft), Datum wo relevant.

## R — Code

| ID | Fundstelle | Aussage |
|----|-----------|---------|
| R01 | `cli/okf-cli.py:812-827` | Keyword-Scoring ist reines **Substring-Matching** (`term in hay_title/hay_tags/hay_body`), Gewichte title 3 / tags 2 / body 1. Kein Stemming, keine Tokenisierung des Haystacks, kein Prefix, kein IDF, keine Feldlängen-Normalisierung. |
| R02 | `cli/okf-cli.py:801-802` | `find` iteriert bei jeder Query über **alle** Bundles/Konzepte und liest sie von Platte — Full Scan, kein persistenter Index. |
| R03 | `cli/okf-cli.py:836-837` | Sortierung nach absolutem Score; `max_score = 6 * len(terms)` als Normalisierungsbasis. |
| R04 | `cli/okf-cli.py:647-672, 839-855` | Semantischer Backstop feuert **nur** als Fallback: Zero-Hit ODER Top-1 ohne klare Marge (`SEMANTIC_MARGIN_RATIO = 0.5`) ODER Top-1 unter Rauschgrenze (`SEMANTIC_NOISE_RATIO = 0.25`). Keyword-Top-1 bleibt geschützt. |
| R05 | `cli/okf-cli.py:742-762` | Backstop liest `concept_emb` aus `.tagvec`; fehlende Datei/Tabelle oder fehlendes Embedding-Backend → `note: semantic backstop skipped`, nie Hard-Fail. Query-Embedding per lokalem Ollama-Call (`bge-m3`, `SEMANTIC_MODEL`). |
| R05b | `cli/okf-cli.py:758-762` | **Kein absoluter Cosine-Floor**: `semantic_backstop` sortiert alle Kandidaten und schneidet nach `limit` ab. Was auch immer vorhanden ist, wird zurückgegeben — bei 10 befüllten Vektoren also zwangsläufig 10 „Treffer", unabhängig von deren Güte. |
| R05c | `cli/okf-cli.py:781` | Semantik-Score = `round(cosine * max_score)` — direkte Umrechnung ohne Kalibrierung; ein Cosine von 0.44 wird damit zu einem Score, der neben Keyword-Scores gerankt wird. |
| R06 | `cli/embeddings/README.md:27-35` | **Präzedenzfall Kontamination:** frühere Tag-Embeddings mit Titel/Description-Anreicherung ließen unabhängige Tags ~0.9 scoren (`task-brief ↔ superwhisper` 0.92) — gemessen wurde Ko-Okkurrenz, nicht Label-Bedeutung. Fix: Slug-only. |
| R07 | `cli/embeddings/README.md` (Teil 2, „since P8/8c") | `concept_emb(key, path, model, dim, vec)` embeddet **ein** Vektor pro Konzept aus `title + "\n\n" + body` (`concept_text()`). |
| R08 | `cli/embeddings/README.md` (Teil 2, Begründung) | Fixture **S3** ist die Existenzberechtigung von `concept_emb`: Konzept mit `tags=[]`, Query-Token nur im Body — strukturell unauffindbar für einen tag-gekeyten Backstop. |

## R — Live-Katalog (gemessen 2026-07-25, `~/Obsidian/Knowledge-Catalogue`)

| ID | Messung | Wert |
|----|---------|------|
| R09 | `.tagvec/tag_vectors.sqlite` → `emb` | 752 Zeilen `bge-m3`, 650 `voyage-3-large` — Tag-Embeddings **produktiv befüllt**. |
| R10 | `.tagvec/tag_vectors.sqlite` → `concept_emb` | **0 Zeilen**. Backstop in Produktion wirkungslos. |
| R11 | `find . -name "*.md"` | 2581 Markdown-Dateien im Katalog (Größenordnung des Full-Scan-Suchraums, R02). |

## R — PO-Gegenproben (Bean `okf-cli-wuiv`, 2026-07-25)

| ID | Beobachtung | Quelle |
|----|-------------|--------|
| R12 | `find "mockup tailscale"` findet `dev-wiki/testsystem-vite-tailscale/serve-excalidraw-drafts.md` **nicht** — Konzept nutzt Excalidraw/PNG-Vokabular, nie „mockup". Nur Browsing (`index`) fand es. | Bean, Abschnitt „Q03 — Gegenprobe-Ergebnis" |
| R13 | Scoped Demo-Befüllung (10 Konzepte `devdash-tui/`, bge-m3, zurückgerollt): Backstop feuert, matcht auf **falsche** Konzepte bei cosine 0.40–0.44, Zieltreffer fehlt komplett. | Bean, Abschnitt „Q03 — revised" |
| R14 | `--tag tailscale` filtert korrekt, aber „mockup" kommt in keinem tailscale-getaggten Konzept literal vor → 0 Treffer trotz korrektem Filter. `mockup` ist zudem kein registrierter Tag (`tags mockup` → backup/mcp/molecule/mouse). | Bean, Abschnitt „Q03 — Nebenbefund Tag-Ebene" |
| R15 | Eval-Gate der Revision: Paraphrase-Zero-Hit-Rate 1.000 → 0.500 (baseline-f0714b2 → hybrid-39d6c0a), keine literale Regression. Gemessen mit **Fixtures**, nicht mit dem Live-Katalog. | Bean, „Session close 2026-07-25" |

## R — Experiment (Session 2026-07-25/26, Scratchpad — Wegwerf-Code, Ergebnisse werden hierher übernommen)

| ID | Artefakt | Inhalt |
|----|----------|--------|
| R20 | `scratchpad/embed_arms.py` | Befüllt `eval.sqlite` in drei Armen (`bge-m3+title`, `bge-m3+titlebody`, `bge-m3+chunk`). `--ollama-host` verlagert Calls, `--reverse` für den Gegenläufer. |
| R21 | `scratchpad/gen_queries.py` | Erzeugt Paraphrase-Queries mit qwen3.5:9b, Vokabular-Sperre + bis zu 3 Versuche, Leaks markiert. |
| R22 | `scratchpad/eval_arms.py` | Misst K/A/B/C: Recall@1/5/10, MRR, Zero-Hit + Cosine-Trennung Ziel vs. bestes Nicht-Ziel. |
| R23 | `scratchpad/queries_generated.json` | 50 generierte Queries, davon **23 mit Vokabular-Leak** (46 %) — dienen als keyword-freundliche Kontrollgruppe, nicht als Ausschuss. |
| R24 | `scratchpad/queries_real.json` | 8 reale PO-Queries mit verifiziertem Zielkonzept (alle 8 Pfade im Katalog vorhanden). Spannweite von wörtlich (`data-ui konvention namensschema`) bis rein semantisch (`mockup tailscale`, `service home-lab photos`). |
| R25 | Mac Mini `100.85.223.39:11434` (Tailscale) | Zweiter Ollama-Host mit identischen Modellen (`bge-m3`, `nomic-embed-text`, `qwen3.5:9b`). Fedora (`100.127.119.116`) hat keinen Ollama. |

## R — Messergebnis (2026-07-26, n=58 Queries, Live-Katalog 2437 Konzepte)

R26 — **Voyage-Arme, alle drei vollständig befüllt, damit modellintern voll belastbar** (`eval_partial.json`):

| Arm | R@1 | R@5 | R@10 | MRR | Zero-Hit |
|-----|-----|-----|------|-----|----------|
| `voyage-3-large+titlebody` | 0.638 | 0.914 | 0.983 | 0.744 | 0.017 |
| `voyage-3-large+chunk` | 0.586 | 0.879 | 0.897 | 0.692 | 0.103 |
| `voyage-3-large+title` | 0.241 | 0.414 | 0.534 | 0.334 | 0.466 |
| `K` (heutiges Keyword) | 0.241 | 0.483 | 0.534 | 0.336 | 0.466 |

R27 — Teilmenge **saubere Paraphrasen** (n=27, kein Vokabular-Leak): `voyage+titlebody` R@10 = **1.000**, Zero-Hit = **0.000**; `voyage+chunk` 0.852; `bge+titlebody` 0.852; `K` 0.333.

R28 — Kontrollgruppe **geleakte Queries** (n=23, Titelwörter enthalten): `K` R@1 0.478 / Zero-Hit 0.087 — Keyword verhält sich dort erwartungsgemäß stark, das Messdesign trägt. `voyage+titlebody` schlägt es dennoch (R@1 0.783).

R29 — **Reale PO-Queries** (n=8): `K` Zero-Hit **0.875** (7 von 8 gar nicht gefunden), `voyage+chunk` 0.125, `voyage+titlebody` 0.125.

R30 — Einschränkung zum Zeitpunkt der Messung: `bge-m3+chunk` war erst zu ~60 % befüllt, seine Zahlen sind untere Schranken. Der Abstand bge↔voyage ist deshalb überzeichnet; der **modellinterne** Vergleich (Voyage: titlebody vs chunk vs title) ist davon unberührt.

R31 — Betriebsbeleg zu LL-08: der abgesicherte bge-titlebody-Lauf protokollierte **4 Retries** und lief vollständig durch (2437/2437), wo der ungeschützte Lauf bei ~550 abgebrochen war.

R32 — **Lexikaler Arm (FTS5 + BM25, Feldgewichte 3/2/1 wie heute), `fts_arm.py`**, n=58:

| Variante | R@1 | R@5 | R@10 | MRR | Zero-Hit |
|----------|-----|-----|------|-----|----------|
| heutiges Substring-Scoring (`K`) | 0.241 | 0.483 | 0.534 | 0.336 | 0.466 |
| FTS5 plain | 0.534 | 0.776 | 0.862 | 0.639 | 0.138 |
| FTS5 plain + Prefix | 0.552 | 0.810 | 0.879 | 0.664 | 0.121 |
| FTS5 porter | 0.569 | 0.793 | 0.862 | 0.669 | 0.138 |
| **FTS5 porter + Prefix** | **0.638** | 0.845 | 0.879 | 0.720 | 0.121 |

R33 — **Messfehler im generierten Query-Satz (wichtig für jede Interpretation):** die Vokabular-Sperre des Generators umfasste nur Titel + Tags, nicht den Body — und der Generator sah einen Body-Auszug. Gemessen: **75 %** der Terme der „sauberen" generierten Queries stehen wörtlich im Ziel-Body (real: 47 %). Der generierte Satz bevorzugt daher systematisch lexikale Verfahren. Vergleiche Lexikal↔Semantik sind nur auf dem realen Satz unverzerrt — dort ist n=8.

R34 — **Kein absoluter Cosine-Floor möglich** (widerlegt die Fix-Idee zu Q12): korrekte Rang-1-Treffer und falsche Top-Treffer überlappen vollständig. `voyage+titlebody`: korrekte Ziele Median 0.604 / Min 0.494, bester Fehltreffer 0.644. `bge+title`: korrekte Median 0.686, Fehltreffer bis **0.813**. Cosine ist ein Rang-, kein Konfidenzsignal.

R35 — **Architektur-Messung (`hybrid_eval.py`), n=58**: FTS5(porter+prefix) als Primärpfad, `voyage-3-large+titlebody` als Backstop.

| Variante | R@1 | R@5 | R@10 | MRR | Zero-Hit |
|----------|-----|-----|------|-----|----------|
| nur FTS5 | 0.638 | 0.845 | 0.879 | 0.720 | 0.121 |
| nur Embedding | 0.638 | 0.914 | 0.983 | 0.744 | 0.017 |
| Hybrid **wie okf-cli heute fusioniert** (Top-1-Pin + Score-Mischung) | 0.638 | 0.845 | 0.897 | 0.723 | 0.103 |
| Hybrid mit **Reciprocal Rank Fusion** | 0.672 | 0.914 | 0.966 | 0.774 | 0.034 |

R36 — **Die heutige Fusion neutralisiert den Backstop.** Der Backstop feuerte bei allen 8 realen Queries, der Hybrid blieb dabei exakt auf dem Ergebnis des lexikalen Arms (MRR 0.344 = identisch). Ursache ist eine Skalenverwechslung: normalisierte BM25-Werte der Plätze 2–10 liegen bei ~0.9, gute Cosines bei ~0.6 — semantische Kandidaten werden hinter **jeden** falschen Keyword-Treffer sortiert (`cli/okf-cli.py:872-878`, Interleaving nach `score`). Positionsbasierte Fusion (RRF) behebt das ohne jede Schwellenwert-Justage.

R37 — Alle sechs Vektor-Arme vollständig: `{bge-m3, voyage-3-large}` × `{title 2437, titlebody 2437, chunk 12967}`.

R38 — **Vollständige Sechs-Arm-Matrix** (alle Arme 100 % befüllt, n=58, `eval_full6.json`):

| Arm | R@1 | R@5 | R@10 | MRR | Zero-Hit |
|-----|-----|-----|------|-----|----------|
| `voyage-3-large+titlebody` | 0.638 | 0.914 | 0.983 | 0.744 | 0.017 |
| `voyage-3-large+chunk` | 0.569 | 0.879 | 0.897 | 0.683 | 0.103 |
| `bge-m3+chunk` | 0.466 | 0.759 | 0.810 | 0.583 | 0.190 |
| `bge-m3+titlebody` | 0.379 | 0.793 | 0.897 | 0.559 | 0.103 |
| `voyage-3-large+title` | 0.241 | 0.414 | 0.534 | 0.334 | 0.466 |
| `K` (Substring, heute) | 0.241 | 0.483 | 0.534 | 0.336 | 0.466 |
| `bge-m3+title` | 0.138 | 0.414 | 0.500 | 0.248 | 0.500 |

R39 — **Chunking ist modellabhängig, nicht generell unterlegen** (differenziert R26): beim schwächeren `bge-m3` schlägt Chunking das Dokument-Embedding auf R@1 (0.466 vs 0.379), beim starken `voyage-3-large` ist es umgekehrt (0.569 vs 0.638). Lesart: Chunking kompensiert Modellschwäche bei langen Dokumenten und wird überflüssig, sobald das Modell lange Texte gut verarbeitet. Relevant nur, falls lokal-kostenlos gefahren werden soll.

R40 — **Titel-only ist in beiden Modellen der schlechteste Arm** und liegt unter dem heutigen Substring-Scoring (0.138 bzw. 0.241 R@1). Die S3-Garantie des Vorgängerprojekts (Body-Vokabular muss auffindbar bleiben) ist damit empirisch belegt, nicht nur argumentativ.

R41 — **Unverzerrter Query-Satz v2** (`queries_v2.json`): 40 Queries, von vier Subagenten aus den Konzepten geschrieben, Regel „kein Wort >3 Zeichen darf im Zieldokument vorkommen". Maschinell geprüft: 168 Terme, **1 Leak (0,6 %)** gegen 75 % in v1. Umlaut-Transliterationen eines Batches (`qualitaetsmanagement`) wurden zurückgesetzt, da sie FTS5 künstlich benachteiligt hätten (unicode61 faltet `ä`→`a`, nicht `ae`).

R42 — **Messung auf dem unverzerrten Satz** (n=48 = v2 + real). Alle v1-Zahlen waren durch den Leak aufgebläht:

| Arm | R@1 | R@10 | MRR | Zero-Hit |
|-----|-----|------|-----|----------|
| `voyage-3-large+titlebody` | 0.271 | 0.833 | 0.452 | 0.167 |
| `voyage-3-large+chunk` | 0.250 | 0.729 | 0.394 | 0.271 |
| `bge-m3+titlebody` | 0.083 | 0.354 | 0.150 | 0.646 |
| FTS5 (bester lexikaler Arm) | 0.021 | 0.104 | 0.057 | 0.896 |
| `K` Substring (heute) | 0.021 | 0.021 | 0.021 | **0.979** |

**Das heutige Retrieval findet 1 von 48 Paraphrasen.** Auf den 40 reinen Paraphrasen findet FTS5 **null** (Zero-Hit 1.000) — lexikale Aufwertung löst Morphologie, nicht Synonymie. Der frühere Befund „größter Hebel ist lexikal" (R32) war ein Leak-Artefakt und ist **hinfällig**.

R43 — **Fusionsregel im Regime-Vergleich** (MRR), `hybrid_v1c.json` / `hybrid_v2c.json`:

| Regel | wörtliche Queries (n=50) | Paraphrasen (n=40) | schlechtester Fall |
|-------|--------------------------|--------------------|--------------------|
| nur FTS5 | 0.780 | 0.000 | 0.000 |
| nur Embedding | 0.781 | 0.439 | 0.439 |
| Pin + Score-Mischung (**okf-cli heute**) | 0.783 | 0.029 | 0.029 |
| Reciprocal Rank Fusion | **0.815** | 0.201 | 0.201 |
| **bedingte Übergabe** | 0.791 | 0.437 | **0.437** |

Bedingte Übergabe = der lexikale Arm besitzt das Ranking nur bei klarer Top-1-Marge, sonst besitzt es der semantische Arm; der jeweils andere wird hinten angehängt, nie davor. Beide *Misch*-Verfahren verschlechtern gegenüber dem besseren Einzelarm, weil ein uninformativer Arm Rauschränge gleichberechtigt einbringt.

## R — Vorgänger-Artefakte

| ID | Ort | Inhalt |
|----|-----|--------|
| R16 | `docs/okf-revision/PLAN.md` | Plan der abgeschlossenen Maturity-Revision (ce-plan-reviewer GREEN, PO-approved). |
| R17 | `~/Obsidian/Vault/okf-revision/{DESIGN,EVAL-DESIGN,DECISIONS}.md` | Think-Sammlung der Vorgänger-Session (außerhalb Repo). |
| R18 | `.beans/okf-cli-wuiv--okf-climcp-maturity-revision.md` | Milestone-Bean; Q01–Q04 offen, Q03 ist Auslöser dieser Sammlung. |
| R19 | `Knowledge-Catalogue/okf-meta-wiki/extensions/embedding-based-tag-consolidation.md` | Quell-SOP der Slug-only-Entscheidung (via R06 referenziert). |
