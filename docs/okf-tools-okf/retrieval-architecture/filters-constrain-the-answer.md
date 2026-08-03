---
type: Pattern
title: Filter gelten für die Antwort, nicht für einen Arm
description: Entwurfsregel für Retrieval mit bedingter Übergabe — wer das Ranking besitzt, wird zur Laufzeit entschieden, also muss jeder Arm dieselben Filter durchsetzen; mit dem Residual-Rückgabewert als Durchsetzungsmechanismus und dem Testschnitt, der ihn bewacht.
tags:
  - retrieval
  - architecture
  - hybrid-search
  - filter
timestamp: 2026-08-03T00:00:00Z
---

# Filter gelten für die Antwort, nicht für einen Arm

Ein Suchfilter (`--scope`, `--type`, `--tag`) ist eine Aussage über das **Ergebnis**, nicht über einen Rechenweg dorthin. In einem Retrieval mit mehreren Armen heißt das: jeder Arm, der einen Treffer beisteuern kann, muss denselben Filter durchsetzen — sonst hängt die Korrektheit der Antwort davon ab, welcher Arm sie zufällig geliefert hat.

Bei [bedingter Übergabe](/okf-tools-okf/retrieval-architecture/hybrid-retrieval-design.md) wird genau das zur Laufzeit und pro Query entschieden. Damit ist ein Filter, den nur ein Arm kennt, kein Filter, sondern ein Zufall.

## Der Vorfall, aus dem die Regel stammt

`okf-cli find --scope home-lab-wiki/services` lieferte Konzepte aus `agent-memory` und `qm-wiki`. Der lexikale Arm filterte korrekt — im SQL-Prädikat gegen die FTS-Tabelle. Der semantische Arm filterte gar nicht: er bekam die Filter nie übergeben. Solange der lexikale Arm das Ranking besaß, sah alles richtig aus. Sobald die Übergabe an den semantischen Arm ging — also genau bei den Paraphrasen-Queries, für die er gebaut wurde — antwortete die Suche ungefiltert.

Der Fehler war nicht, dass jemand eine Zeile vergessen hat. Der Fehler war, dass Vergessen möglich und unsichtbar war.

## Warum Arm-lokale Filterung zwangsläufig driftet

Die drei Arme filtern über verschiedene Datenquellen: der FTS-Arm über eine Volltext-Tabelle mit `ctype`/`tags`/`path`-Spalten, der Substring-Arm über einen Verzeichnis-Scan mit Frontmatter-Lesung, der semantische Arm über einen Embedding-Cache, der nur den Pfad kennt. Jeder Arm formuliert das Prädikat also anders — und drei getrennte Formulierungen desselben Prädikats sind drei Gelegenheiten, es unterschiedlich zu meinen.

Verschärfend: die Filter reisten als lose Positionsargumente durch fünf Signaturen. Eine Signatur, die sie nicht annimmt, fällt niemandem auf; ein Aufruf, der sie nicht weiterreicht, ebenso wenig. Das Typsystem schweigt, die Tests schweigen, das Ergebnis sieht plausibel aus.

## Durchsetzung: das Residual als Vertrag

Ein Wertobjekt bündelt die Filter und definiert das Prädikat einmal. Entscheidend ist nicht die Bündelung — das ist bloß Hygiene —, sondern was die Konsum-Methode **zurückgibt**:

```
sql_where(columns) -> (sql_fragment, params, residual)
```

`columns` sagt, welche Filterdimensionen die Zieltabelle nativ tragen kann. `residual` ist ein Filterobjekt mit exakt den Dimensionen, die das erzeugte SQL **nicht** abgedeckt hat. Der Aufrufer muss es anwenden, sonst verliert er sie.

Damit wird aus einer stillen Auslassung ein sichtbarer Rückgabewert:

- Volltext-Tabelle mit allen drei Spalten → `residual` leer, per Assertion festgenagelt
- Embedding-Cache mit nur einer Pfadspalte → `residual` trägt Typ und Tag, die der Arm beim Absteigen durch die Rangliste selbst anwendet

Eine neue Datenquelle mit anderen Spalten bekommt automatisch ein passendes Residual. Ein Arm, der es ignoriert, ignoriert etwas Benanntes.

Zwei Feinheiten, die in der Umsetzung teuer waren:

**Filtern vor dem Ranken, nicht danach.** Wird erst gerankt und dann gefiltert, verbrauchen aussortierte Treffer Plätze im `limit` — die Ergebnisliste wird still kürzer als angefordert. Was in SQL geht, gehört ins SQL; der Rest wird beim Absteigen durch die Rangliste angewandt und bricht bei `limit` ab, statt jeden Kandidaten anzufassen.

**Leerer Filtertreffer ist keine Degradation.** Ein Cache ohne Einträge für das Modell ist ein Ausfall und verdient eine Notiz auf stderr. Ein voller Cache ohne Einträge im angefragten Scope ist eine korrekte, vollständige, leere Antwort. Wer beide auf denselben Rückgabewert abbildet, meldet dem Nutzer „Embeddings fehlen", sobald er auf ein Bundle einschränkt, das eben keine hat.

## Der Testschnitt, der die Regel bewacht

Ein Arm-Test kann diese Bugklasse grundsätzlich nicht fangen: welcher Arm antwortet, entscheidet sich pro Query zur Laufzeit. Getestet wird deshalb am Kommando — dort, wo der Nutzer den Filter setzt — über die Matrix *Filterdimension × Besitzregime*: lexikal besitzt, semantisch besitzt, degradiert auf den Fallback-Arm.

Zwei Eigenschaften machen so einen Test erst wirksam:

**Jeder Fall braucht eine Positivkontrolle.** Nur zu prüfen, dass der Köder fehlt, besteht auch ein Filter, der versehentlich alles verwirft. Das gewollte Konzept muss anwesend sein.

**Jedes Regime muss die anderen Arme stilllegen.** Sonst decken die Arme einander. Die erste Fassung des Regressionstests lief grün gegen absichtlich zurückgebauten Code: bei fehlendem Volltextindex sprang der semantische Arm ein und lieferte aus seinem Cache den korrekt gefilterten Pfad, den der lexikale Arm gerade verstümmelt hatte. Der Test bestand — aus dem falschen Grund. Genau die Redundanz, die das System im Betrieb robust macht, macht seine Tests blind.

Nachweisen lässt sich das nur durch Mutation: den Fix auf einer Kopie zurückbauen und prüfen, dass der Test rot wird. Ein Regressionstest, der nie gegen den kaputten Zustand gelaufen ist, ist eine Behauptung.

## Verwandt

- [Zielarchitektur und Messbefunde](/okf-tools-okf/retrieval-architecture/hybrid-retrieval-design.md) — die bedingte Übergabe, die diese Regel nötig macht
- [Entscheidungen D01-D17](/okf-tools-okf/retrieval-architecture/hybrid-retrieval-decisions.md)
