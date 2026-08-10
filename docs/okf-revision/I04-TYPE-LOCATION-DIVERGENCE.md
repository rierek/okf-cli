---
type: Report
title: "I04-TYPE-LOCATION-DIVERGENCE — okf-revision"
description: "Read-only Divergenzliste zwischen type-Frontmatter und Ablageort im Bundle memory-layer-wiki, plus katalogweiter Konsistenz-Check der Konvention 'Verzeichnis spiegelt Typ'."
tags:
  - tpic
  - okf-revision
timestamp: 2026-08-10T14:07:49Z
---

# I04 — Type/Location-Divergenz in `memory-layer-wiki`

Auslöser ist bean `OKFT-idch` ("Decision filed outside decisions/"), Kind von `OKFT-hkze`. Das bean nennt als Evidenz genau ein Konzept, verlangt aber die Prüfung des gesamten Bundles und warnt ausdrücklich davor, die Konvention ohne vorherige Entscheidung über das eine Bundle hinaus durchzusetzen. Dieser Report liefert die vollständige Liste, die Belegungsstatistik als Beleg dafür, welche Verzeichnisse überhaupt eine Typ-Bedeutung tragen, und den katalogweiten Gegencheck.

Der Katalog `~/Obsidian/Knowledge-Catalogue` wurde ausschließlich gelesen. Es wurde keine Datei angelegt, geändert, verschoben oder gelöscht; `okf-cli rename` wurde nicht ausgeführt, auch nicht als Dry-Run.

## 1. Bundle-Struktur

`memory-layer-wiki` enthält 41 Markdown-Dateien, davon 8 `index.md`-Listings ohne `type`-Frontmatter und 33 echte Konzepte. Die Verzeichnisse sind:

| Verzeichnis | Konzepte (ohne `index.md`) | Vorkommende `type`-Werte |
| --- | --- | --- |
| `<bundle-root>` | 2 | `Reference` 2 |
| `architecture/` | 6 | `Concept` 4, `Reference` 1, `LessonLearned` 1 |
| `change-notes/` | 4 | `ChangeNote` 3, `Reference` 1 |
| `decisions/` | 5 | `Decision` 4, `Reference` 1 |
| `lessons-learned/` | 1 | `LessonLearned` 1 |
| `memory-analyses/` | 5 | `Reference` 3, `Decision` 1, `<none>` — |
| `memory-analyses/p-review-memory-system/` | 5 | `Reference` 3, `Decision` 1, `LessonLearned` 1 |
| `setup/` | 4 | `Guide` 2, `Reference` 2 |
| `usage/` | 3 | `Guide` 2 |

Das Verzeichnis `assets/` enthält keine Konzepte und bleibt außen vor.

## 2. Welche Verzeichnisse tragen eine Typ-Bedeutung

Die Frage ist nicht, welcher Name nach einem Typ klingt, sondern welche Belegung das trägt. Drei Verzeichnisse haben einen Namen, der auf einen `type`-Wert aus `TYPES.md` abbildet, und deren Belegung bestätigt das:

| Verzeichnis | impliziter `type` | passend | abweichend | Reinheit |
| --- | --- | --- | --- | --- |
| `decisions/` | `Decision` | 4 | 1 (`Reference`) | 80 % |
| `change-notes/` | `ChangeNote` | 3 | 1 (`Reference`) | 75 % |
| `lessons-learned/` | `LessonLearned` | 1 | 0 | 100 % (n=1, statistisch wertlos) |

Die übrigen Verzeichnisse sind Themen-, keine Typ-Verzeichnisse: `architecture/`, `memory-analyses/`, `setup/`, `usage/` und der Bundle-Root gruppieren nach Gegenstand, nicht nach Konzeptart. `architecture/` enthält zwar zu 4 von 6 den Typ `Concept`, aber „architecture" ist kein `type`-Wert — die Häufung ist Folge des Themas, nicht einer Typ-Regel. Für diese Verzeichnisse existiert also keine Sollvorgabe, gegen die man divergieren könnte.

Daraus folgt die Divergenz-Definition, die in Abschnitt 3 angewandt wird: divergent ist ein Konzept genau dann, wenn (a) sein `type` einen der drei Typ-Verzeichnisse im Bundle besitzt, das Konzept aber woanders liegt, oder (b) das Konzept in einem Typ-Verzeichnis liegt, dessen impliziter Typ nicht sein `type` ist.

## 3. Divergenzliste — vollständig

Sechs Konzepte des Bundles laufen nach dieser Definition auseinander. Die Referenzzahl ist die Anzahl der von `okf-cli refs <pfad>` gemeldeten eingehenden Markdown-Referenzen, `index.md`-Einträge eingerechnet.

| # | Pfad | `type` | `title` | Refs | Empfehlung |
| --- | --- | --- | --- | --- | --- |
| 1 | `memory-layer-wiki/memory-analyses/2026-06-02-mem-27-sprint-plan-backend-consolidation.md` | `Decision` | MEM-27 Sprint Plan — Backend Consolidation | 1 | verschieben nach `memory-layer-wiki/decisions/2026-06-02-mem-27-sprint-plan-backend-consolidation.md` |
| 2 | `memory-layer-wiki/memory-analyses/p-review-memory-system/2026-05-26-context-management-foundation-plan-and-decisions.md` | `Decision` | Context-Management Foundation — Plan and Decisions (2026-05-26) | 4 | bleibt, weil Dossier-Kohäsion |
| 3 | `memory-layer-wiki/decisions/chyros.md` | `Reference` | Chyros (Unverified) | 1 | verschieben nach `memory-layer-wiki/chyros.md` |
| 4 | `memory-layer-wiki/architecture/mem0-evaluation-findings-2026-03-27.md` | `LessonLearned` | mem0 Evaluation Findings 2026-03-27 | 1 | verschieben nach `memory-layer-wiki/lessons-learned/mem0-evaluation-findings-2026-03-27.md` |
| 5 | `memory-layer-wiki/memory-analyses/p-review-memory-system/feedback-ai-memory-system.md` | `LessonLearned` | Feedback — AI Memory System | 2 | bleibt, weil Dossier-Kohäsion |
| 6 | `memory-layer-wiki/change-notes/sessionstart-fix-verification-test.md` | `Reference` | SessionStart Fix — Verification Test | 2 | bleibt, weil Anhang zur ChangeNote im selben Verzeichnis |

### Begründungen im Einzelnen

**#1 — MEM-27 Sprint Plan.** Das ist der im bean genannte Fall. Die `description` sagt selbst „Decision log and issue breakdown", der Body führt mit `MEM-D07` eine nummerierte Entscheidung und begründet die Backend-Wahl gegen Postgres. Der Inhalt rechtfertigt `type: Decision`; der Ablageort tut es nicht. Genau eine eingehende Referenz, und die kommt aus `memory-analyses/index.md`, das `okf-cli rename` ohnehin neu schreibt — die Verschiebung ist damit der billigste denkbare Eingriff.

**#2 — Context-Management Foundation.** Vier eingehende Referenzen aus drei Dateien, alle aus `p-review-memory-system/`. Dieses Unterverzeichnis ist ein Dossier zu einer zusammenhängenden Review-Strecke; `review-context-management-foundation.md` und `2026-05-27-analysis-and-plan-memory-layer-devdash-cli.md` lesen sich als Fortsetzung. Das Dokument bezeichnet sich im Body als „Guidance-Dokument zur Session vom 2026-05-26" — es ist primär ein Plan, in dem Entscheidungen mitprotokolliert sind, nicht eine einzelne Entscheidung. Herausziehen würde die Lesereihenfolge des Dossiers zerlegen und einen mehrdeutigen Rest hinterlassen. Der saubere Fix hier ist nicht ein Move, sondern die Frage, ob `type: Decision` die richtige Wahl ist — das ist eine Typ-Entscheidung, keine Ablage-Entscheidung, und gehört nicht in dieses bean.

**#3 — Chyros.** Einzige echte Fremdkörper-Datei in `decisions/`. Der Inhalt ist eine unverifizierte Single-Source-Notiz über einen angeblichen Anthropic-Memory-Daemon, ausdrücklich als Gerücht markiert — es wird nichts entschieden. Der Bundle-Root beherbergt bereits zwei Landschafts-Referenzen desselben Zuschnitts (`ce-surface-overview.md`, `devdash-project-memory-features.md`, beide `type: Reference`), das ist der passende Ort. Eine eingehende Referenz, aus `decisions/index.md`.

**#4 — mem0 Evaluation Findings.** `type: LessonLearned`, liegt aber in `architecture/`, obwohl `lessons-learned/` im selben Bundle existiert und mit `findings-and-pitfalls.md` genau diesen Zweck belegt. Der Body ist eine Erkenntnis-Sammlung aus einer Evaluationssession, keine Architekturbeschreibung. Eine eingehende Referenz, aus `architecture/index.md`. Klarer Move.

**#5 — Feedback AI Memory System.** Dieselbe Dossier-Logik wie #2: zwei eingehende Referenzen, beide aus `p-review-memory-system/`, davon eine aus einer inhaltlich anschließenden Analyse. Der Nutzen der Nachbarschaft übersteigt hier den Nutzen der Typ-Sortierung.

**#6 — SessionStart Fix Verification Test.** `type: Reference` in `change-notes/`, aber der Sinn der Datei ist der Verifikationsanhang zu `change-notes/2026-05-12-sessionstart-json-fix.md`, das direkt auf sie verlinkt. Die Nachbarschaft ist der Punkt der Ablage. Bleibt.

`okf-cli check` meldet für `memory-layer-wiki` keine Verstöße; der Ist-Zustand ist konform, die Divergenz ist eine Ordnungs-, keine Konformitätsfrage.

## 4. Trägt „Verzeichnis spiegelt Typ" katalogweit?

Nein — die Konvention ist lokal, nicht katalogweit. Drei unabhängige Belege.

**Beleg A — die SPEC verbietet die Regel implizit.** `SPEC.md` §5 sagt wörtlich: „A bundle is a directory tree of markdown files. The directory structure is independent of the domain — producers organize concepts however makes sense for the knowledge being captured." Eine Regel „Verzeichnis muss `type` spiegeln" widerspricht dieser Freiheit direkt. Sie ließe sich nur als lokale Konvention eines einzelnen Bundles rechtfertigen, nicht als OKF-Invariante.

**Beleg B — nur 4 von 22 Bundles haben überhaupt ein `decisions/`.** Verteilung und interne Reinheit:

| Bundle | `decisions/`-Belegung | `Decision`-Konzepte im Bundle gesamt | davon außerhalb `decisions/` |
| --- | --- | --- | --- |
| `home-lab-wiki` | `Decision` 14 | 14 | 0 |
| `bew_BeWiki-Python-Download-okf` | `Decision` 2 | 2 | 0 |
| `devd2-okf` | `Decision` 1 | 1 | 0 |
| `memory-layer-wiki` | `Decision` 4, `Reference` 1 | 6 | 2 |

Wo das Verzeichnis existiert, wird es weitgehend eingehalten — drei von vier Bundles sind sauber, `memory-layer-wiki` ist der einzige Ausreißer. Das rechtfertigt die Bereinigung genau dieses Bundles.

**Beleg C — katalogweit hält die Zuordnung nicht.** Von 40 `Decision`-Konzepten im gesamten Katalog liegen 21 in einem `decisions/` und 19 nicht (52 %). Bei `LessonLearned` ist das Bild eindeutig: 158 Konzepte insgesamt, davon 6 in einem `lessons-learned/` (4 %) — allein `agent-memory` trägt 104 `LessonLearned` und hat kein solches Verzeichnis, `dev-wiki` weitere 20. Bei `ChangeNote` sind es 3 von 8 (38 %). Bundles wie `lean-stack-okf` führen 4 `Decision`-Konzepte ganz ohne `decisions/`.

Fazit: PARTIAL. Die Konvention ist innerhalb der Bundles, die sie führen, belastbar und dort durchsetzenswert; katalogweit ist sie eine Minderheitspraxis und darf nicht zur Regel erhoben werden. Für `agent-memory` wäre ein erzwungenes `lessons-learned/` mit 104 Konzepten sogar schädlich — dort ist die flache Ablage die Struktur. Empfehlung: die Regel als bundle-lokale Konvention führen, deklariert im jeweiligen `index.md` des Bundles, und `okf-cli check` nicht darum erweitern.

## 5. Vorgeschlagene `okf-cli rename`-Aufrufe

Die folgenden drei Aufrufe setzen die Empfehlungen aus Abschnitt 3 um. Sie wurden **nicht** ausgeführt — weder mit noch ohne `--apply`. `rename` schreibt eingehende und ausgehende Links um und regeneriert die betroffenen `index.md`, deshalb ist es das einzige zulässige Mittel (bean-Akzeptanz: „WHERE a concept is misfiled, THE move SHALL go through `okf-cli rename` so crosslinks follow"). Ohne `--apply` ist jeder Aufruf ein Dry-Run.

````
python3 /Users/erik/dev/okf-tools/cli/okf-cli.py --root ~/Obsidian/Knowledge-Catalogue rename memory-layer-wiki/memory-analyses/2026-06-02-mem-27-sprint-plan-backend-consolidation.md memory-layer-wiki/decisions/2026-06-02-mem-27-sprint-plan-backend-consolidation.md --apply
python3 /Users/erik/dev/okf-tools/cli/okf-cli.py --root ~/Obsidian/Knowledge-Catalogue rename memory-layer-wiki/decisions/chyros.md memory-layer-wiki/chyros.md --apply
python3 /Users/erik/dev/okf-tools/cli/okf-cli.py --root ~/Obsidian/Knowledge-Catalogue rename memory-layer-wiki/architecture/mem0-evaluation-findings-2026-03-27.md memory-layer-wiki/lessons-learned/mem0-evaluation-findings-2026-03-27.md --apply
````

Empfohlene Reihenfolge: jeden Aufruf zuerst ohne `--apply` prüfen, dann anwenden, danach `okf-cli check` und `okf-cli wikilinks memory-layer-wiki` gegen SC-002 laufen lassen.

## Findings

| ID | Sachverhalt | Status |
| --- | --- | --- |
| D01 | Die Konvention „Verzeichnis spiegelt Typ" wird als bundle-lokale Konvention geführt, nicht katalogweit erzwungen und nicht in `okf-cli check` aufgenommen — Begründung in Abschnitt 4. | 🟣 offen |
| T01 | Die drei `rename`-Aufrufe aus Abschnitt 5 anwenden, danach `okf-cli check` und `okf-cli wikilinks memory-layer-wiki` als Nachweis für SC-002. | 🟣 offen |
| Q01 | Trägt `2026-05-26-context-management-foundation-plan-and-decisions.md` den richtigen `type`? Der Body bezeichnet sich als Guidance-/Plan-Dokument, `Decision` könnte zu eng sein. Typ-Frage, nicht Ablage-Frage. | 🟡 unklar |
