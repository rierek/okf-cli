---
type: Report
title: "MODUS-B-REPORT — okf-revision"
description: "Outcome of the Modus-B agentic realism check: five independent agents, okf MCP tools only, five retrieval tasks against real catalogue concepts, scored qualitatively and excluded from the P12 gate metric."
tags:
  - tpic
  - okf-revision
timestamp: 2026-08-10T13:05:00Z
---
# Modus B — Agentic Realism Check, Ergebnis

## Summary

Fünf frische Agenten mit ausschließlich `mcp__okf__*`-Tools, ohne Repo-Zugriff und ohne Kenntnis der Zielpfade, haben je eine Retrieval-Aufgabe gegen den realen Katalog gelöst; alle fünf haben ihr Ziel benannt (5/5), vier davon mit einem einzigen Suchaufruf. Der Lauf ersetzt die Fixture-Fassung des Tasksets vom 2026-07-25 (Begründung und PO-Entscheidung: `modus-b-tasks.md`, Abschnitt „Revision 2026-08-10"); Katalog und beide Indizes blieben bitweise unverändert (`git status` leer, md5 von `.tagvec/tag_vectors.sqlite` und `.fts/fts.sqlite` vor und nach dem Lauf identisch). Das Ergebnis ist ein qualitatives Sanity-Signal und geht ausdrücklich nicht in die P12-Gate-Metrik ein.

Der zentrale positive Befund: R2 ist die dokumentierte Zero-Hit-Gegenprobe des PO vom 2026-07-25. Damals fand `find "mockup tailscale"` das Zielkonzept überhaupt nicht; heute holt der semantische Arm es bei einer reinen Paraphrase ohne ein einziges Vokabel des Zieldokuments auf Rang 1, und selbst die wörtliche Originalquery des PO liefert es auf Rang 2. Der zentrale negative Befund ist das Gegenstück in R1: eine Paraphrase in Nutzersprache verfehlte ein Konzept, dessen Titel und Description den gesuchten Fachbegriff wörtlich tragen — genau der Fall, für den der semantische Arm gebaut wurde.

## Ergebnistabelle

| # | Szenario | Ergebnis | Calls | Vom Agenten formulierte Query (verbatim) | Provenance | Rang |
|---|----------|----------|-------|------------------------------------------|------------|------|
| R1 | S1-Analogon, gut getaggt, kanonisches Bundle | success | 3/5 | „passwortlose Anmeldung am selbstgehosteten Login-Dienst über gerätegebundenen Schlüssel", danach „Passkey WebAuthn Authelia passwortlos" | lexikalisch (unter Semantik-Banner) | 5, erst im zweiten Versuch |
| R2 | S2-Analogon, richtiger Inhalt an überraschendem Ort | success | 2/5 | „Diagramm als Bild und bearbeitbare Quelldatei im privaten Heimnetz auf dem Handy ansehen" | semantic, cosine 0.63 | 1 |
| R3 | S3-Analogon, nur über Body-Vokabular auffindbar | success | 2/5 | „Integrationsmuster zwischen Systemen: REST-API, Webhooks, Plugins — warum Integrationen scheitern" | semantic, cosine 0.75 | 1 |
| R4 | S4-Analogon, dünne Metadaten, über Navigation auffindbar | success | 3/5 | keine — reiner Index-Walk `okf_index` → `okf_index bundle` → `okf_read` | browse | browse |
| R5 | Literal-Kontrolle | success | 2/5 | „ralph wiggum loop" | semantic, cosine 0.54 | 1 |

R5 verlangte „nenne das Konzept"; der Agent nannte `general-knowledge-wiki/ai-agentic-coding/ralph-wiggum-loop` und führte den von mir designierten Zielpfad `ai-wiki/ralph-wiggum-loop` explizit als eine von drei Kopien mit auf. Die Aufgabe ist damit erfüllt, die Zieldesignation war selbst mehrdeutig — was den Katalog-Befund B02 überhaupt erst sichtbar gemacht hat.

## 1. Bugs

| Bxx | Schwere | Beschreibung | Empfehlung | Status |
|-----|---------|--------------|------------|--------|
| B01 | medium | Der Banner `note: semantic arm owns this ranking` steht über der gesamten Trefferliste, obwohl der tatsächlich tragende Treffer aus dem lexikalischen Arm stammen kann (R1: Rang 5, Score `100/100`, ohne `provenance:`-Zeile). Die Zuordnung Banner-zu-Trefferzeile ist für den Konsumenten nur über das *Fehlen* eines Markers erschließbar. | Jede Trefferzeile trägt ihren eigenen `provenance:`-Wert, auch den lexikalischen (`provenance: lexical`), statt Herkunft implizit zu lassen. | 🟣 |
| B02 | medium | Katalog-Inhalt, nicht Code: `ralph-wiggum-loop` liegt dreifach (`ai-wiki/`, `general-knowledge-wiki/ai-agentic-coding/`, `claude-code-wiki/sessions-workflow/`, drei verschiedene md5), `integration` doppelt (`ai-wiki/`, `general-knowledge-wiki/ai-agentic-coding/`). Der Agent in R5 leitet daraus die plausible Hypothese ab, dass sich die Duplikate den BM25-Margin gegenseitig nehmen — bei einer Query, die exakt dem Titel dreier Konzepte entspricht, fiel das Ranking an den semantischen Arm. | Duplikate zusammenführen; die Margin-Hypothese vorher gegen `find` mit und ohne Duplikate messen, statt sie zu glauben. | 🟣 |

## 2. Improvements

| Ixx | Beschreibung | Nutzen | Empfehlung | Status |
|-----|--------------|--------|------------|--------|
| I01 | Der semantische Arm verfehlte in R1 sein eigenes Kernszenario: Die Paraphrase in Nutzersprache („selbstgehosteter Login-Dienst", „gerätegebundener Schlüssel") brachte zehn plausible Nachbarn (Vaultwarden, OAuth2, SSO, SSH, Tailscale), aber nicht das Konzept, dessen Titel „Passkey" und dessen Description „Passwordloser Login" wörtlich enthält; cosine 0.53 für Vaultwarden schlug das Ziel. Erst die Reformulierung mit Fachtermini traf — und dann lexikalisch. | Deckt die Lücke, in der Nutzer den Fachbegriff gerade nicht kennen — der einzige Grund, überhaupt semantisch zu suchen. | Als Query gegen die bestehende Eval-Infrastruktur nachfahren: Ist das ein Einzelfall oder eine Klasse (Umschreibung → Fachterminus)? Erst danach über Fusion-Parameter oder Query-Expansion entscheiden. | 🟣 |
| I02 | Die gemischte Trefferliste zeigt zwei nicht vergleichbare Skalen nebeneinander — `score: cosine 0.63` und `score: 100/100` — wobei die numerisch größeren BM25-Werte weiter unten stehen. Drei von fünf Agenten (R1, R2, R5) nennen das unabhängig voneinander als Lesehürde. | Der häufigste Konsument ist ein Agent, der die Liste überfliegt und die oberen Ränge weiterverarbeitet; eine irreführende Zahlenordnung kostet dort direkt Trefferqualität. | Eine einzige Ranking-Skala ausgeben und den Rohwert je Arm nur im Score-Breakdown führen. | 🟣 |
| I03 | Der Browse-Pfad ist teuer: `okf_index` auf Katalogebene liefert 22 Bundles mit vollen Beschreibungen, wovon in R4 genau eine Zeile trug. Bei einem Budget von fünf Calls hätte ein Fehlgriff bei der Bundle-Wahl (plausible Alternativen waren `home-lab-wiki/decisions` und `general-knowledge-wiki/home-lab-and-hosting`) kaum Spielraum für einen zweiten Index gelassen. | Macht den Navigationspfad für budgetierte Agenten überhaupt erst gangbar. | Eine knappe Form des Katalog-Index (Bundle-Name plus Einzeiler) als Default, die volle Beschreibung nur auf Anforderung. | 🟣 |
| I04 | Die Verzeichnisstruktur trägt als Filter nicht: Das gesuchte Dokument in R4 hat `type: Decision`, liegt aber unter `memory-analyses/` statt unter dem vorhandenen `decisions/`. Gefunden wurde es allein über die Descriptions im Bundle-Index. | Wer nach Struktur navigiert, verlässt sich sonst auf ein Signal, das nicht hält. | Katalogseitig prüfen, ob `type` und Ablageort im `memory-layer-wiki` auseinanderlaufen; kein Tooling-Fix. | 🟣 |

## 3. Questions

| Qxx | Hintergrund | Relevanz | Frage | Status |
|-----|-------------|----------|-------|--------|
| Q01 | R4 fand die Entscheidung, ohne dass aus dem Dokument hervorgeht, dass ein späteres Konzept (`decisions/memory-db-layer-teardown`) den beschriebenen Layer wieder abbaut. Der Agent bemerkte das nur, weil er den Bundle-Index gesehen hatte. | Retrieval liefert hier eine formal korrekte, inhaltlich überholte Antwort — ein Fehlermodus, den weder Modus A noch die Gate-Metrik erfasst. | Soll Superseding im Katalog explizit werden (Frontmatter-Relation, Status-Feld), damit ein Agent die Gültigkeit einer gefundenen Entscheidung einschätzen kann? | 🟣 |

## Qualitatives Verdikt

Der ausgelieferte Retrieval-Stand trägt den realistischen agentischen Gebrauch: alle fünf Aufgaben gelöst, vier davon mit einer einzigen Suche, und die zuvor unerreichbare Paraphrase-Klasse ist erreichbar geworden — R2 belegt das an genau dem Fall, an dem der PO das Problem ursprünglich festgemacht hat. Die verbliebenen Reibungspunkte sind keine Recall-Probleme, sondern Lesbarkeits- und Attributionsprobleme der Ausgabe (B01, I02) plus ein Katalog-Hygiene-Befund (B02, I04), der das Ranking messbar stört, ohne im Code zu liegen. Der einzige echte Retrieval-Fehlschlag ist I01: der semantische Arm versagte ausgerechnet bei der Umschreibung eines Fachbegriffs, dem Szenario, das seine Existenz begründet — das gehört gemessen, bevor daran geschraubt wird.

## Nachtrag 2026-08-10 — I01 gemessen, Hypothese widerlegt, Ursache gefunden

I01 wurde noch in derselben Session gemessen statt geglaubt. Zwölf Ziele wurden mechanisch gesampelt, bevor eine einzige Query existierte (Filter: Titel enthält einen im Katalog seltenen Term, Body zwischen 1200 und 20000 Zeichen, `random.seed(20260810)`); drei unabhängige Agenten schrieben je vier Queries in Alltagssprache unter absolutem Verbot der Titelterme. Inhaltswort-Leak gegen das jeweilige Zieldokument: 1 von 111 Wörtern, die übrigen elf Überlappungen sind Funktionswörter wie „ohne", „statt", „eine". Artefakte: `docs/okf-retrieval-architecture/eval/queries_i01.json`, `i01_jargon.json`, `i01_jargon_after.json`.

**Die Klassenhypothese ist widerlegt.** Die Jargon-Paraphrase-Klasse schneidet deutlich BESSER ab als der allgemeine unverzerrte Paraphrase-Satz: recall@1 0.583 gegen 0.25, MRR 0.694 gegen 0.438, Zero-Hit 0.167 gegen 0.175. Wer aus R1 eine Schwäche der Fusionsregel abgeleitet hätte, hätte an einem gesunden Mechanismus gedreht.

**Die tatsächliche Ursache ist eine Abdeckungslücke, kein Ranking-Problem.** Das Konzept aus R1, `home-lab-wiki/notes/authelia-passkey-authentication`, hatte überhaupt keinen Vektor in `concept_emb` — der semantische Arm konnte es nicht finden, weil er es nicht kannte. Katalogweit fehlten 115 von 2589 Konzepten (4,4 %), und alle 115 wurden nach dem einmaligen produktiven Befüllungslauf angelegt (frühestes Anlegedatum 2026-08-05). Dazu 74 verwaiste Zeilen für Dateien, die es nicht mehr gibt. Der Producer kennt sein Delta (`build_tagvec.py` meldete im Dry-Run 166 zu embeddende Konzepte) — es stößt ihn nur niemand an. `.fts` hat einen Rebuild-Trigger, `.tagvec` hat keinen.

**Gegenprobe nach dem Producer-Lauf** (166 Konzepte embedded, `--target concepts --model voyage-3-large --produce`): Die R1-Originalquery liefert das Zielkonzept jetzt auf Rang 1 statt gar nicht. Auf dem I01-Satz stieg MRR von 0.694 auf 0.771, Zero-Hit fiel von 0.167 auf 0.083 — genau das eine Ziel, dem der Vektor fehlte, kam von „nicht auffindbar" auf Rang 1.

**Der Preis, sauber gemessen.** Ein A/B auf demselben Katalogstand (Vorzustand aus dem Backup zurückgespielt, gemessen, danach wiederhergestellt — beide md5 verifiziert) zeigt auf dem kanonischen 48-Query-Satz eine leichte Verschlechterung: MRR 0.450 auf 0.432, recall@1 0.271 auf 0.250, recall@10 und Zero-Hit unverändert. Bewegt haben sich vier Ränge (7→6, 3→5, 1→3, 5→6); die 166 neuen Vektoren konkurrieren mit den alten Zielen. Das ist Rauschen in der Größenordnung einer einzelnen Query bei n=48 und der Preis dafür, dass 4,4 % des Katalogs überhaupt semantisch erreichbar werden. Ergebnisdatei `shipped_2026-08-10.json`; sie ersetzt `shipped_expand.json` nicht, sondern steht daneben.

Nebenbefund am Rande: Der Producer-Lauf hat die Zeilenzahl von 2989 auf 2662 gesenkt, also genau eine Zeile je existierendem Pfad plus die 74 Waisen hinterlassen. Duplikate pro Pfad — der in `OKFT-3520` beschriebene Effekt — sind danach nicht mehr vorhanden; die Waisen gelöschter Dateien bleiben. Das gehört an jenem Bean verifiziert, nicht hier entschieden.

Damit korrigiert sich das Verdikt oben in einem Punkt: I01 ist kein Retrieval-Fehlschlag, sondern war das Symptom einer stillen Degradation. Der ausgelieferte Mechanismus ist gesünder, als der erste Blick nahelegte — er wurde nur mit einem Teil des Katalogs betrieben, ohne dass es jemandem angezeigt wurde.
