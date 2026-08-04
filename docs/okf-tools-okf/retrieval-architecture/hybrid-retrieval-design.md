---
type: Concept
title: Hybrid retrieval architecture — target design and findings
description: Target retrieval architecture for okf-cli — FTS5/BM25 lexical arm plus voyage-3-large semantic arm, conditional-handover fusion — with the measured findings that rule out chunking, an absolute cosine floor, and RRF.
tags:
  - retrieval
  - architecture
  - hybrid-search
  - embeddings
  - fusion
timestamp: 2026-07-26T00:00:00Z
---

# Hybrid retrieval architecture — target design and findings

Verdichtungs-Artefakt der Think-Session 2026-07-25/26 (Slug `okf-retrieval-architecture`).
Kein Code, keine EARS. Entscheidungen: [hybrid-retrieval-decisions.md](/okf-tools-okf/retrieval-architecture/hybrid-retrieval-decisions.md).
Rohbelege (R01–R43) und die Messgrundlage (`eval/`) blieben im Repo unter
`docs/okf-retrieval-architecture/` — sie sind das Messsubstrat der Vorgänger-Feature,
nicht migriert.

## Ausgangspunkt und wie er sich verschoben hat

Auslöser war Q03 des Beans `okf-cli-wuiv`: „`concept_emb` produktiv befüllen — und mit
welchem Embedding-Design?", mit der Empfehlung, auf **Chunk-Embedding** umzubauen, weil
eine Live-Demo Fehltreffer bei cosine 0.40–0.44 gezeigt hatte.

Diese Diagnose hielt der Prüfung nicht stand. Die Demo hatte 10 Konzepte eines einzigen
Bundles befüllt, während das Zielkonzept der Gegenprobe außerhalb lag — „Zieltreffer
fehlte komplett" war damit tautologisch. Zusätzlich fehlt dem Backstop jeder absolute
Schwellwert, er liefert also zwangsläufig Treffer, egal wie schlecht. Zwei Erklärungen,
die nichts mit Granularität zu tun haben.

Die Session hat deshalb nicht die Bean-Frage beantwortet, sondern sie ersetzt:
**gemessen statt argumentiert**, über den vollen Katalog (2437 Konzepte, 35 800
Vektoren, sechs Arme, zwei Modelle) gegen 48 Queries mit bekanntem Ziel.

## Was gemessen wurde

Drei Embedding-Einheiten (`title`, `title+body`, `Chunk pro h2/h3`) × zwei Modelle
(`bge-m3` lokal, `voyage-3-large` API), dazu der heutige Substring-Scorer, ein
FTS5/BM25-Arm und drei Fusionsregeln. Query-Sätze: 40 subagenten-geschriebene
Paraphrasen mit 0,6 % Vokabular-Überlappung zum Zieldokument plus 8 reale PO-Queries.

Die Messgrundlage war selbst der schwierigste Teil: der erste generierte Satz
überlappte zu 75 % mit dem Body der Zieldokumente und hat jedes lexikale Verfahren
massiv geschmeichelt. Alle Aussagen dieses Dokuments stützen sich auf den korrigierten
Satz.

## Befunde

**1. Das heutige Retrieval ist bei Paraphrasen funktionslos.** 1 Treffer bei 48
Queries, Zero-Hit 0.979. Nicht „verbesserungswürdig" — es leistet außerhalb wörtlicher
Übereinstimmung praktisch nichts.

**2. Lexikale Aufwertung löst das nicht.** FTS5 + BM25 + Porter + Prefix findet auf 40
reinen Paraphrasen **null** Ziele. Stemming adressiert Morphologie; das Problem ist
Synonymie (`mockup` ↔ `excalidraw`). Auf wörtlichen Queries ist FTS5 dagegen stark (MRR
0.780) — es bleibt als Primärpfad sinnvoll, aber es ersetzt nichts.

**3. Chunking ist der falsche Umbau.** Beim starken Modell ist es dem
Dokument-Embedding unterlegen (MRR 0.394 vs 0.452); nur beim schwachen Modell hilft es.
Es kaschiert Modellschwäche bei langen Texten. Titel-only ist in beiden Modellen der
schlechteste Arm und liegt unter dem heutigen Substring-Scoring — die S3-Garantie des
Vorgängerprojekts ist damit empirisch bestätigt.

**4. Der eigentliche Defekt ist die Fusionsregel.** `okf-cli` sammelt semantische
Kandidaten ein und rankt sie anschließend weg: normalisierte BM25-Werte der Plätze 2–10
liegen bei ~0.9, gute Cosines bei ~0.6, gemischt wird nach Score. Der Backstop feuerte
bei 47 von 48 Queries und blieb wirkungslos. Im Regime-Vergleich ist die heutige Regel
die zweitschlechteste von fünf.

**5. Ein absoluter Cosine-Floor ist unmöglich.** Korrekte Ziele und falsche Top-Treffer
überlappen vollständig — Fehltreffer erreichen 0.813, korrekte Treffer fallen auf 0.494.
Cosine ist ein Rang-, kein Konfidenzsignal.

**6. Die Modellwahl entscheidet über Brauchbarkeit.** `voyage-3-large` erreicht MRR
0.452 / Zero-Hit 0.167, `bge-m3` 0.150 / 0.646. Faktor 3, kein Feintuning-Abstand.

## Zielarchitektur

```
Query
 │
 ├─ lexikaler Arm: FTS5 + BM25 (title 3 / tags 2 / body 1, Prefix)
 │
 ├─ semantischer Arm: voyage-3-large, EIN Vektor pro Konzept aus title+body
 │
 └─ Fusion: BEDINGTE ÜBERGABE
      lexikaler Top-1 mit klarer Marge  → lexikal besitzt das Ranking,
                                          Semantik hinten angehängt
      sonst                             → Semantik besitzt das Ranking,
                                          lexikale Treffer hinten angehängt
      semantische Treffer bleiben als solche markiert (provenance)
```

Kernpunkt: es wird entschieden, **wer das Ranking besitzt**, statt zwei unvergleichbare
Skalen zu mischen. Diese Regel ist in beiden Query-Regimen nahe am jeweils besten
Einzelarm und hat den mit Abstand besten schlechtesten Fall (0.437 gegen 0.201 für RRF
und 0.029 für die heutige Regel).

Degradationskette bleibt Pflicht: fehlender API-Key, fehlendes Netz oder fehlende
Vektoren → lexikaler Pfad allein, mit Hinweis auf stderr, nie Hard-Fail.

## Verworfen, mit Begründung

| Option | Warum verworfen |
|--------|-----------------|
| Chunk-Embedding (Bean-Empfehlung d) | gemessen schlechter als Dokument-Embedding beim produktiv gewählten Modell |
| Titel-only-Embedding | schlechtester Arm überhaupt, unter dem Status quo |
| Absoluter Cosine-Floor | trennt nicht, Verteilungen überlappen vollständig |
| Reciprocal Rank Fusion | bestes Ergebnis auf wörtlichen Queries, bricht bei Paraphrasen ein |
| FTS5 **statt** Embedding | löst Morphologie, nicht Synonymie |
| `bge-m3` als produktives Modell | Faktor 3 schlechter; bleibt Fallback-Kandidat |

## Verwandt

- [Entscheidungen D01-D17](/okf-tools-okf/retrieval-architecture/hybrid-retrieval-decisions.md)
- Messsubstrat (Rohdaten, Query-Sets, Taxonomie): `docs/okf-retrieval-architecture/eval/` (bleibt im Repo)
