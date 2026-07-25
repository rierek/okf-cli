# EVAL-DESIGN — Retrieval-Erfolgsmessung okf-cli/mcp

Zweck: Reifegrad des Retrievals **messbar** machen, damit WS1-Optimierungen (keyword → hybrid)
als Delta sichtbar werden. Grounds: `08-retrieval-flow.yaml`, `06-retrieval-quality.yaml`.
Prinzip: Baseline JETZT einfrieren (keyword-only) → nach WS1 erneut → Delta pro Metrik/Szenario.

## Szenarien (golden fixtures, "versteckte" Fake-Konzepte mit bekannter Ground-Truth)

| Sz | Fixture-Aufbau | Isoliert | Keyword-Baseline (Erwartung) |
|----|----------------|----------|------------------------------|
| S1 | Term in Titel + H2 + Body | Ceiling/Sanity | Top-1, Score nahe max |
| S2 | wie S1, aber im FALSCHEN Bundle abgelegt | Location-Sensitivity | `find` Rang unverändert (ortsblind, `:544`) · `list --scope=richtig` = Miss |
| S3 | richtiges Bundle, generischer Titel, keine passenden Tags, Term NUR im Body | Feld-Gewichtung + Semantik-Gap | literal: niedriger Rang (Body×1) · Paraphrase: Zero-Hit |
| S4 | richtiges Bundle, Meta falsch/fehlend (type/tag), nur via Index-Walk auffindbar | Metadaten- vs. Struktur-Retrieval | `list(type,tag)` = Miss · Index-Walk / `find`-Body = einziger Weg |

Hinweis S2: für `find` allein ~identisch zu S1 (kein Scope) — das IST der Befund: find gibt keine
Orts-Disziplin. S2 wird komparativ gemessen (find-recall unverändert vs. scoped-retrieval miss).

## Query-Klassen (Pflicht: pro Fixture ZWEI)

- **literal**: Query enthält den exakten Katalog-Term → Keyword feuert.
- **paraphrase**: Synonym/Umschreibung des Terms → Keyword Zero-Hit, nur Semantik rettet.
- Die Paraphrase-Delta (Zero-Hit-Rate literal vs. paraphrase) = primäres Optimierungssignal.

## Testziele → Messung

| Ziel (User) | Verb | Szenario | Metrik |
|-------------|------|----------|--------|
| 1. Findet find schlecht abgelegte Fundstellen effizient? | find | S3, S4 | Rang-des-Ziels, Zero-Hit-Rate (literal vs paraphrase) |
| 2. Bundle-Walk über Indizes zur Quelle? | index/reindex | S4 | Ziel in Bundle-TOC listbar + index.md→Datei navigierbar |
| 3. Abruf nur über Meta (type:runbook, tag:tailscale)? | list | S1(korrekt) vs S4(kaputt) | list Precision/Recall; S4 = erwarteter Fail |

## Metriken

| Metrik | Legt offen | Delta-Richtung bei Hybrid |
|--------|-----------|---------------------------|
| Recall@1, Recall@5 | Ziel in Top-k | ↑ |
| MRR | mittlerer Rang über Query-Set | ↑ |
| Zero-Hit-Rate (bes. paraphrase) | Semantik-Lücke | ↓↓ (Kernsignal) |
| Score-des-Ziels (roh + /max) | Ranking-Stärke/Trennschärfe | ↑ |
| Location-Correct-Rate (S2) | Orts-Disziplin | erst mit Scope-Filter messbar |
| Metadata-Hit-Rate | list-Güte (Ziel 3) | — (list-abhängig) |

Definition "effizient" = Rang + Recall + Zero-Hit, NICHT Wall-Time (Scan über ~1783 Konzepte trivial).

## Harness-Mechanik (2 Modi — nicht vermischen)

- **A) Mechanischer Runner (Metrik-Rückgrat, CI-fähig)**: Golden-File `query → erwarteter Konzept-Pfad
  + Schwellwert`; Runner ruft `find`/`list`/`index`, scored gegen Golden, emittiert Metrik-Tabelle.
  Deterministisch, reproduzierbar, für Regressions-Gate.
- **B) Agentischer Realismus-Check (periodisch)**: Test-Agent bekommt nur eine Aufgabe ("finde das
  Runbook zu X") + okf-Tools, Erfolg gemessen. Testet den ganzen Loop inkl. Query-Formulierung.
  Realistisch aber nicht-deterministisch → nicht als Metrik-Basis, nur als Sanity.

## Offene Design-Forks (→ QUESTIONS Q06/Q07)

- Fixtures in isoliertem Eval-Root (sauberer Baseline) vs. in echten Katalog geseedet (realistisch,
  konkurriert mit 1783 Dokumenten ums Ranking).
- Umfang Modus B (nur A, oder A+B).
