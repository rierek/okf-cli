# TASKS — okf-retrieval-architecture

Latente Konvergenz: konkret gewordene, umsetzbare Einheiten. Noch **kein** Plan — Reihenfolge/Blocker erst bei Konvergenz.

| Txx | Prio | Aufgabe | Herkunft | Status |
|-----|------|---------|----------|--------|
| T01 | hoch | ~~Reproduktion der Q03-Demo klären~~ — durch das Vollkatalog-Experiment (D03) gegenstandslos: jedes Konzept hat in jedem Arm einen Vektor, die Scope-Konfundierung kann nicht mehr auftreten | R13-Prüfung | 🟢 erledigt durch D03 |
| T02 | hoch | ~~Ground Truth erheben~~ — 50 generierte (R23) + 8 reale, pfad-verifizierte Queries (R24) liegen vor | Q07 | 🟢 |
| T10 | hoch | `build_tagvec.py` fehlertolerant machen: Retry/Backoff, Input-Halbierung, Skip-mit-Protokoll statt Abbruch des ganzen Laufs (LL-08) | LL-08 | 🟣 |
| T11 | hoch | Batching für den Ollama-Pfad (`/api/embed` nimmt Listen) — gemessener Faktor 10–35 gegenüber Einzel-Calls (LL-09). Entscheidet mit, ob Re-Embedding operativ tragbar ist | LL-09 | 🟣 |
| T09 | hoch | Ergebnisse aus dem Scratchpad ins Repo überführen (Zahlen + Query-Sets + Scripts), sonst geht die Messgrundlage mit der Session verloren | Persistenz | 🟣 |
| T03 | hoch | Fehlschlag-Taxonomie auf dieser Menge: morphologisch (stembar) / synonymisch / Katalog-Lücke / Ranking (→ Q03, Q10) | Q03, Q10 | 🟣 |
| T04 | mittel | Lexikal-Prototyp messen: FTS5 + Porter-Stemmer + BM25 + Prefix gegen dieselbe Menge, als neue Baseline gegen das heutige Substring-Scoring (→ Q02) | Q02 | 🟣 |
| T05 | mittel | Tag-Expansion-Prototyp: Query-Terme gegen die bereits befüllte `emb`-Tabelle, Expansion VOR dem Keyword-Scoring; Kosten/Nutzen gegen T04 (→ Q05, Q06) | Q05 | 🟣 |
| T06 | ~~mittel~~ | ~~Absoluten Cosine-Floor einführen~~ — verworfen: korrekte und falsche Cosines überlappen vollständig (R34), ein Floor kann nicht trennen | R05b | 🔴 verworfen |
| T12 | **hoch** | Fusionsregel in `cmd_find` auf **bedingte Uebergabe** umstellen (nicht RRF, nicht Score-Mischung): lexikal besitzt das Ranking nur bei klarer Marge, sonst besitzt es die Semantik (R43). Heutige Regel ist im Regime-Vergleich zweitschlechteste | R36/R43 | 🟣 |
| T13 | mittel | Lexikalen Pfad auf FTS5 + BM25 + Prefix umstellen (stdlib). **Herabgestuft:** der Gewinn galt nur auf dem verzerrten Satz; auf Paraphrasen findet FTS5 null (R42). Bleibt sinnvoll fuer woertliche Queries und Latenz (Q08), ist aber nicht die Loesung des Vokabular-Problems | R32/R42 | 🟣 |
| T07 | niedrig | Zero-Hit-Antwort für Agent-Konsumenten anreichern (nächste Tags/Terme statt „(no matches)") — Reformulierung an den aufrufenden Agenten zurückgeben | Divergenz-Option (f) | 🟣 |
| T08 | niedrig | Aliase/Synonyme als Frontmatter-Feld erwägen: Verschiebung der Synonym-Auflösung von der Query- auf die Autorenzeit (→ Divergenz-Option (g)) | Divergenz-Option (g) | 🟣 |
| T14 | **hoch** | Modell-Entscheidung fuer den semantischen Arm treffen: `voyage-3-large` (MRR 0.452, aber Netzabhaengigkeit + Kosten im Request-Pfad) gegen `bge-m3` lokal (MRR 0.150). Beruehrt den stdlib-/Degradations-Constraint (Q09) | R42 | 🟣 |
| T15 | mittel | Query-Satz v2 (40 Queries, 0,6 % Leak) als versioniertes Eval-Asset ins Repo uebernehmen — er ist die erste unverzerrte Messgrundlage des Projekts | R41 | 🟣 |
