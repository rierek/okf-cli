---
type: Report
title: "eval — Messgrundlage der Retrieval-Architektur-Session"
description: "Experiment code and raw results of the retrieval think session — throwaway code whose measurements carry the decisions that followed."
tags:
  - tpic
  - okf-retrieval-architecture
timestamp: 2026-07-25T22:43:35Z
---
# eval — Messgrundlage der Retrieval-Architektur-Session (2026-07-25/26)

Experiment-Code und Rohergebnisse der Think-Session. **Wegwerf-Code mit bleibendem Wert**: die Scripts waren als Einweg-Werkzeug gebaut, die Query-Sätze und Ergebnisse sind die erste unverzerrte Messgrundlage des Projekts und dürfen nicht verlorengehen.

## Query-Sätze

| Datei | n | Herkunft | Leak-Quote |
|-------|---|----------|------------|
| `queries_real.json` | 8 | vom PO getippt, Zielkonzept bekannt und pfad-verifiziert | 47 % Body-Überlappung (natürlich) |
| `queries_v2.json` | 40 | von vier Subagenten aus den Konzepten geschrieben, Regel: kein Wort >3 Zeichen im Zieldokument | **0,6 %** |
| `queries_generated.json` | 50 | qwen3.5:9b, Sperre nur Titel+Tags | **75 %** — verzerrt zugunsten lexikaler Verfahren, nur als Kontrastmenge nutzen |

Für belastbare Aussagen `queries_v2.json` + `queries_real.json` verwenden. `queries_generated.json` überschätzt jedes lexikale Verfahren massiv (siehe REFERENCES R33).

## Scripts

| Datei | Zweck |
|-------|-------|
| `embed_arms.py` | Befüllt eine separate `eval.sqlite` mit Konzept-Vektoren, Arme über die `model`-Spalte getrennt (`<backend>+{title,titlebody,chunk}`). `--ollama-host` verlagert Calls auf einen anderen Rechner, `--reverse` erlaubt einen Gegenläufer. Rührt die Live-`.tagvec` nie an. |
| `gen_queries.py` | v1-Generator (qwen3.5:9b). Historisch — seine Sperre war unvollständig, siehe Leak-Quote oben. |
| `eval_arms.py` | Misst alle in der DB gefundenen Vektor-Arme plus den heutigen `okf-cli find` gegen einen Query-Satz: Recall@1/5/10, MRR, Zero-Hit, je Teilmenge. |
| `fts_arm.py` | Lexikaler Arm: FTS5-Index über title/tags/body, BM25 mit Feldgewichten 3/2/1, Varianten plain/porter × mit/ohne Prefix. |
| `hybrid_eval.py` | Misst die **Architektur**: lexikal + semantisch unter drei Fusionsregeln (heutige Score-Mischung, RRF, bedingte Übergabe). |

Die `eval.sqlite` mit den 35 800 Vektoren ist **nicht** eingecheckt (~150 MB). Reproduzierbar über `embed_arms.py`; die Voyage-Arme kosten dabei ~$0.71, die bge-Arme ~45 min lokale GPU-Zeit.

## Ergebnisse

| Datei | Inhalt |
|-------|--------|
| `eval_full6.json` | Sechs-Arm-Matrix gegen den v1-Satz (verzerrt) |
| `eval_v2.json` | Sechs-Arm-Matrix gegen v2 + real (unverzerrt) — die maßgebliche Messung |
| `hybrid_v1c.json` | Fusionsregeln im wörtlichen Regime |
| `hybrid_v2c.json` | Fusionsregeln im Paraphrase-Regime |

Interpretation und Schlussfolgerungen: `../DESIGN.md`, Belege einzeln in `../REFERENCES.md` (R20–R43).
