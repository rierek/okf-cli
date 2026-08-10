---
# OKFT-idch
title: Decision filed outside decisions/
status: completed
type: task
priority: low
created_at: 2026-08-10T12:59:09Z
updated_at: 2026-08-10T14:21:16Z
parent: OKFT-hkze
---

## Objective (User Story)
As an agent navigating by structure, I want a concept's directory to agree with its `type`, so that the directory tree is a usable filter.

## Evidence (MODUS-B-REPORT I04)
`memory-layer-wiki/memory-analyses/2026-06-02-mem-27-sprint-plan-backend-consolidation` carries `type: Decision` while a `decisions/` directory exists in the same bundle. The agent in R4 found it only through the bundle index descriptions; the directory structure carried no signal.

## EARS Acceptance
- THE `memory-layer-wiki` bundle SHALL be checked for `type`/location divergence across all its concepts, not only this one.
- WHERE a concept is misfiled, THE move SHALL go through `okf-cli rename` so crosslinks follow.

## Success Criteria
- SC-001: divergence list produced; each entry either moved or justified in writing.
- SC-002: `okf-cli check` clean, no dangling wikilinks.

## Note
Catalogue hygiene, no tooling change. Whether the convention "directory mirrors type" holds catalogue-wide is an open question — do not enforce it beyond this bundle without deciding that first.


## Done 2026-08-10 (catalogue commit 9f95a27)

Divergenzliste erstellt und abgearbeitet. Vollständiger Befund: `docs/okf-revision/I04-TYPE-LOCATION-DIVERGENCE.md` (Repo-Commit `c9ffd21`).

Sechs Konzepte im Bundle `memory-layer-wiki` haben `type` und Ablageort auseinanderlaufen. Drei wurden per `okf-cli rename --apply` verschoben, drei bleiben mit schriftlicher Begründung liegen — zwei wegen Dossier-Kohäsion innerhalb von `memory-analyses/p-review-memory-system/`, eines als Verifikationsanhang zu seiner ChangeNote im selben Verzeichnis. Verschoben: `memory-analyses/2026-06-02-mem-27-sprint-plan-backend-consolidation.md` nach `decisions/`, `decisions/chyros.md` (type `Reference`) auf die Bundle-Wurzel, `architecture/mem0-evaluation-findings-2026-03-27.md` nach `lessons-learned/`. Alle drei Zielverzeichnisse existierten bereits; die Moves haben keine neue Struktur erfunden.

SC-002 nachgewiesen: `okf-cli check` → `OK — 0 violations`, `git status` im Katalog leer, `rename` hat je zwei `index.md` regeneriert und die eingehenden Pfad-Links mitgezogen (0 Wikilinks betroffen). Die 1852 katalogweit unaufgelösten Wikilinks sind Vorzustand und von diesen Moves unberührt.

D01 — die Konvention „Verzeichnis spiegelt Typ" wird NICHT katalogweit durchgesetzt und bekommt keine `check`-Regel. `SPEC.md` §5 gibt Bundles die Strukturfreiheit ausdrücklich („The directory structure is independent of the domain"), und katalogweit liegen nur 21 von 40 `Decision`, 6 von 158 `LessonLearned` und 3 von 8 `ChangeNote` im namensgleichen Verzeichnis. Innerhalb der vier Bundles, die überhaupt ein `decisions/` führen, trägt sie dagegen: drei sind zu 100 Prozent rein, `memory-layer-wiki` war der einzige Ausreißer. Die Konvention gilt damit bundle-lokal, nicht global.
