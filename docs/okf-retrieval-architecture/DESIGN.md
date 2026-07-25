# DESIGN — Retrieval-Architektur okf-cli

Verdichtungs-Artefakt der Think-Session 2026-07-25/26. Kein Code, keine EARS.
Belege einzeln: `REFERENCES.md` (R01–R43) · Entscheidungen: `DECISIONS.md` (D01–D13) · Offene Punkte: `QUESTIONS.md` · Messgrundlage: `eval/`.

## Ausgangspunkt und wie er sich verschoben hat

Auslöser war Q03 des Beans `okf-cli-wuiv`: „`concept_emb` produktiv befüllen — und mit welchem Embedding-Design?", mit der Empfehlung, auf **Chunk-Embedding** umzubauen, weil eine Live-Demo Fehltreffer bei cosine 0.40–0.44 gezeigt hatte.

Diese Diagnose hielt der Prüfung nicht stand. Die Demo hatte 10 Konzepte eines einzigen Bundles befüllt, während das Zielkonzept der Gegenprobe außerhalb lag — „Zieltreffer fehlte komplett" war damit tautologisch (R13/Q11). Zusätzlich fehlt dem Backstop jeder absolute Schwellwert, er liefert also zwangsläufig Treffer, egal wie schlecht (R05b). Zwei Erklärungen, die nichts mit Granularität zu tun haben.

Die Session hat deshalb nicht die Bean-Frage beantwortet, sondern sie ersetzt: **gemessen statt argumentiert**, über den vollen Katalog (2437 Konzepte, 35 800 Vektoren, sechs Arme, zwei Modelle) gegen 48 Queries mit bekanntem Ziel.

## Was gemessen wurde

Drei Embedding-Einheiten (`title`, `title+body`, `Chunk pro h2/h3`) × zwei Modelle (`bge-m3` lokal, `voyage-3-large` API), dazu der heutige Substring-Scorer, ein FTS5/BM25-Arm und drei Fusionsregeln. Query-Sätze: 40 subagenten-geschriebene Paraphrasen mit 0,6 % Vokabular-Überlappung zum Zieldokument plus 8 reale PO-Queries (R41).

Die Messgrundlage war selbst der schwierigste Teil: der erste generierte Satz überlappte zu 75 % mit dem Body der Zieldokumente und hat jedes lexikale Verfahren massiv geschmeichelt (R33). Alle Aussagen dieses Dokuments stützen sich auf den korrigierten Satz.

## Befunde

**1. Das heutige Retrieval ist bei Paraphrasen funktionslos.** 1 Treffer bei 48 Queries, Zero-Hit 0.979 (R42). Nicht „verbesserungswürdig" — es leistet außerhalb wörtlicher Übereinstimmung praktisch nichts.

**2. Lexikale Aufwertung löst das nicht.** FTS5 + BM25 + Porter + Prefix findet auf 40 reinen Paraphrasen **null** Ziele (R42). Stemming adressiert Morphologie; das Problem ist Synonymie (`mockup` ↔ `excalidraw`). Auf wörtlichen Queries ist FTS5 dagegen stark (MRR 0.780) — es bleibt als Primärpfad sinnvoll, aber es ersetzt nichts.

**3. Chunking ist der falsche Umbau.** Beim starken Modell ist es dem Dokument-Embedding unterlegen (MRR 0.394 vs 0.452); nur beim schwachen Modell hilft es (R39). Es kaschiert Modellschwäche bei langen Texten. Titel-only ist in beiden Modellen der schlechteste Arm und liegt unter dem heutigen Substring-Scoring (R40) — die S3-Garantie des Vorgängerprojekts ist damit empirisch bestätigt.

**4. Der eigentliche Defekt ist die Fusionsregel.** `okf-cli` sammelt semantische Kandidaten ein und rankt sie anschließend weg: normalisierte BM25-Werte der Plätze 2–10 liegen bei ~0.9, gute Cosines bei ~0.6, gemischt wird nach Score (R36). Der Backstop feuerte bei 47 von 48 Queries und blieb wirkungslos. Im Regime-Vergleich ist die heutige Regel die zweitschlechteste von fünf (R43).

**5. Ein absoluter Cosine-Floor ist unmöglich.** Korrekte Ziele und falsche Top-Treffer überlappen vollständig — Fehltreffer erreichen 0.813, korrekte Treffer fallen auf 0.494 (R34). Cosine ist ein Rang-, kein Konfidenzsignal.

**6. Die Modellwahl entscheidet über Brauchbarkeit.** `voyage-3-large` erreicht MRR 0.452 / Zero-Hit 0.167, `bge-m3` 0.150 / 0.646 (R42). Faktor 3, kein Feintuning-Abstand.

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

Kernpunkt: es wird entschieden, **wer das Ranking besitzt**, statt zwei unvergleichbare Skalen zu mischen. Diese Regel ist in beiden Query-Regimen nahe am jeweils besten Einzelarm und hat den mit Abstand besten schlechtesten Fall (0.437 gegen 0.201 für RRF und 0.029 für die heutige Regel, R43).

Degradationskette bleibt Pflicht: fehlender API-Key, fehlendes Netz oder fehlende Vektoren → lexikaler Pfad allein, mit Hinweis auf stderr, nie Hard-Fail (bestehende Regel R05).

## Verworfen, mit Begründung

| Option | Warum verworfen |
|--------|-----------------|
| Chunk-Embedding (Bean-Empfehlung d) | gemessen schlechter als Dokument-Embedding beim produktiv gewählten Modell (D11) |
| Titel-only-Embedding | schlechtester Arm überhaupt, unter dem Status quo (R40) |
| Absoluter Cosine-Floor | trennt nicht, Verteilungen überlappen vollständig (R34) |
| Reciprocal Rank Fusion | bestes Ergebnis auf wörtlichen Queries, bricht bei Paraphrasen ein (R43) |
| FTS5 **statt** Embedding | löst Morphologie, nicht Synonymie (R42) |
| `bge-m3` als produktives Modell | Faktor 3 schlechter; bleibt Fallback-Kandidat (D13) |

## Offen — Übergabe an die Plan-Phase

- **Q09** Constraint-Klärung: Netzabruf im Request-Pfad ist mit D13 akzeptiert, aber die Frage, ob ein Index-Artefakt (`.fts`/`.tagvec`) zum Pflichtbestandteil des Katalogs wird oder optional bleibt, ist offen.
- **Q05/Q06** Tag-Query-Expansion über die bereits befüllten Tag-Vektoren — ungemessen, könnte einen Teil der Fälle ohne Konzept-Embeddings lösen.
- **Q13** informativer Zero-Hit für Agent-Konsumenten (nächste Tags/Terme zurückgeben statt „(no matches)").
- **Q14** Alias-Anreicherung beim Ingest — verschiebt Synonym-Auflösung von der Query- auf die Autorenzeit.
- **Q15** Navigation statt Suche: `index` fand Konzepte, die `find` nicht fand.
- **Q08** Latenz/Full-Scan als eigener Treiber; **Q10** Anteil echter Katalog-Lücken an den Zero-Hits; **Q03** Feintaxonomie der Fehlschläge.
- **LL-08/LL-09** (in `docs/LESSONS-LEARNED.md`): fehlende Fehlertoleranz und fehlendes Batching im Producer — beide Betriebsdefekte, unabhängig von der Architekturentscheidung, aber Voraussetzung für tragbares Re-Embedding.

## Nächste Schritte

Reihenfolge nach Hebel, nicht nach Aufwand:

1. **Fusionsregel** auf bedingte Übergabe umstellen (T12) — ohne sie verpufft jede weitere Verbesserung.
2. **`concept_emb` produktiv befüllen** mit `voyage-3-large`, Einheit `title+body` (T14/D13) — das ist die ursprüngliche Bean-Frage, jetzt beantwortet.
3. **Producer härten** (T10/T11): Fehlertoleranz und Batching.
4. **Lexikalen Pfad auf FTS5** (T13) — für wörtliche Queries und Latenz.
5. **Eval-Assets versionieren** (T15), damit jede künftige Änderung gegen dieselbe Grundlage gemessen wird.
