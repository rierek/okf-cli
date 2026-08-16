---
type: Spec
title: "refs — EARS-Requirements"
description: "Inbound-Markdown-Referenzen auf eine Zieldatei; teilt die Zustandsvokabel resolved/ambiguous/unresolved mit wikilinks.md, obwohl nur der resolved-Zustand hier je zutrifft."
tags:
  - okf-cli
  - ears
  - requirements
  - spec
---

# refs — EARS-Requirements

`refs` beantwortet für eine Zieldatei, welche Markdown-Links (`[text](pfad)`) im Store auf sie zeigen — die Umkehrung eines Crosslinks, benutzt vor einer Umbenennung oder Archivierung, um die Blast-Radius zu sehen. Anders als `wikilinks` löst `refs` deterministisch gegen einen Dateisystempfad auf: ein Pfad-Link hat keinen Basename-Kandidatenraum, in dem er kollidieren könnte, also trägt jeder Treffer denselben Zustand — `resolved`, derselbe Begriff, den wikilinks.md für seine drei Zustände `resolved`/`ambiguous`/`unresolved` benutzt. Die Klassifikation ist hier einwertig, aber identisch benannt.

## Requirements

### Auffindung

| ID | EARS-Requirement |
|----|------------------|
| REFS-1 | THE okf binary SHALL report every markdown-style link in the store whose target path resolves to the file named by the command's target argument. |
| REFS-2 | IF the target argument does not name an existing file, THEN THE okf binary SHALL exit 2 and SHALL name the path it tried. |
| REFS-3 | THE okf binary SHALL name, for every reported reference, the file that carries it and the literal link text it uses. |
| REFS-4 | THE okf binary SHALL include staging directories, root-level files and symlinked bundles in its search for inbound references. |
| REFS-5 | WHERE no markdown-style link resolves to the target argument, THE okf binary SHALL state that no inbound reference exists. |

### Klassifikation

| ID | EARS-Requirement |
|----|------------------|
| REFS-6 | THE okf binary SHALL label every reported reference as resolved. |

### JSON

| ID | EARS-Requirement |
|----|------------------|
| REFS-7 | WHERE JSON output is requested, THE okf binary SHALL place the target path and every reported reference in `data`. |

## Grounding

`cmd_refs()` (`cli/okf-cli.py:1795-1818`) resolves the target argument against the scan root or the store root, whichever exists, exits 2 and names the tried path when neither does (`cli/okf-cli.py:1805-1807`), then delegates to `build_ref_matrix()`.

`build_ref_matrix()` (`cli/okf-cli.py:1755-1792`) walks the scan root with `iter_rename_scan_md()`, masks fenced code, comments and inline code with `wikilink_scan_text()` before matching the markdown-link regex, and resolves each candidate target path-wise (catalogue-root-absolute or relative to the linking file's directory), with a case-insensitive `samefile()` fallback for a link spelled in different case than the disk (`cli/okf-cli.py:1782-1790`). A link is included only when its resolved path matches the target — there is no partial match, so no second or third state exists to report.

`iter_rename_scan_md()` (`cli/okf-cli.py:3564-3590`) is deliberately wider than `iter_all_md()` (used by `check` and `wikilinks`): it walks the scan root's staging directories and root-level files, plus a second pass into every symlinked bundle, because `os.walk` does not descend into a symlinked subdirectory and five catalogue bundles are symlinks.

Output shape today: text mode prints `"no inbound references"` when `hits` is empty (`cli/okf-cli.py:1815-1816`), else one `source -> link` line per hit; JSON mode emits `{"target": …, "inbound": [{"source": …, "link": …}, …]}` (`cli/okf-cli.py:1809-1813`). Parser registration: `cli/okf-cli.py:4268-4273`.

## Deltas gegenüber heute

| Delta | Deckung |
|---|---|
| Envelope statt eigenem JSON-Objekt | I04, COM-26, REFS-7 |
| Exit-Code-Kontrakt für den Nicht-Existenz-Fall bleibt Exit 2, jetzt aus der geteilten Kontrakt-Definition statt einer Einzelfall-Ausnahme | I09, COM-23 |

## Anmerkungen

**`refs` weicht heute schon auf Exit 2 aus, wo jedes andere Lese-Kommando Exit 1 benutzt** (AUDIT A5). Unter COM-23 wird aus der Ausnahme die Regel — REFS-2 beschreibt deshalb keine Verhaltensänderung, sondern hält fest, dass `refs` unter dem neuen Kontrakt unverändert bleibt, während der Rest der CLI zu ihm aufschließt.

**REFS-6 ist die Brücke zu wikilinks.md, nicht ein eigenständiger Befund.** `refs` besitzt keinen Mechanismus, der zwei Kandidaten für dieselbe Zieldatei erzeugen könnte — ein Dateisystempfad löst pro Konstruktion auf höchstens einen Ort auf. Die Zeile hält trotzdem fest, dass ein Treffer denselben Begriff trägt wie ein eindeutig aufgelöster Wikilink, damit ein Konsument, der beide Kommandos liest, ein Vokabular sieht, kein zweites.

## Offene Fragen

**Der Verbleib von `--scan-root`.** I02 verwirft `--scan-root` als Scope-Mechanismus zugunsten eines einzigen optionalen Positionals — aber `--scan-root` bei `refs` engt nicht auf einen Teil des Stores ein, es weitet den Suchraum über den Store hinaus aus (Hilfetext: „pass repo root for repo-wide"), zum Beispiel wenn der Store per Symlink in einem größeren Repo hängt und Referenzen von außerhalb des Stores mitgezählt werden sollen. COM-41 trägt nur die Einengungs-Richtung. Ob diese Fähigkeit unter einem anderen Mechanismus weiterlebt oder mit dem Flag-Namen entfällt, ist durch kein Finding und keine Entscheidung gedeckt — hier bewusst nicht spezifiziert, bis geklärt.

**Ob `refs` auch inbound Wikilinks auf die Zieldatei zeigen sollte.** Heute findet `refs` ausschließlich Markdown-Links; ein `[[page]]`, das über `resolve_wikilink` auf dieselbe Zieldatei aufginge, taucht nicht auf — nur `wikilinks` sieht Wikilinks, aber ohne Ziel-Filter. Eine vollständige „wer referenziert diese Datei"-Antwort bräuchte beides zusammengeführt. Kein Finding und keine Entscheidung verlangt das; nicht spezifiziert.
