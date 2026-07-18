# okf-tools — Session State Transfer

> Current status of ongoing work (SSTD, `/sstd` format). Plain file. Update at session end.

## State (2026-07-18)

- **Focus:** Extraktion aus Knowledge-Catalogue abgeschlossen und verifiziert. Repo
  (`okf-tools`, Unterordner `cli/`, `mcp/`, `plugin/`) lauffähig, Git-Historie beider
  Quellen (okf-cli, okf-mcp) erhalten. Cross-Referenzen (Skills/CLAUDE.md/MCP-Config/
  AOS) auf neuen Pfad umgestellt. Verify-Findings behoben (roher Traceback bei
  ungültigem `--root` gefixt, KC-Katalog auf `OK — 0 violations`).
- **In progress:** —
- **Blocked:** —
- **Next step:** Bean `okf-cli-dwcq` (task/high) — `okf-cli prime`-Output verschlanken,
  Progressive Disclosure für Bundle-Infos einhalten (aktuell zu aufgebläht).

## Open decisions

- Worktree-Weiche: main-direkt erlaubt (Solo, ein Repo für alle drei Komponenten).
- `plugin/` ist Platzhalter — Zweck/Scope noch offen, keine Klasse-B-Substanz dafür bisher.
- Test-Suite (`cli/test_okf_cli.py`) hat 19 Failures/2 Errors — verifiziert pre-existing
  (identisch vor der Extraktion), nicht Teil dieser Session, nicht angefasst.

## Verify-Historie

- 2026-07-18: `/verify` gegen die Extraktion → PASS. CLI + MCP-Wrapper-Subprozesskette
  real getrieben, P0-Risiko (fehlendes `--root`) bestätigt und in allen Aufrufstellen
  gefixt. Findings (roher Traceback, 7 Pre-existing-Check-Warnings in fremden Bundles)
  auf Nutzeranweisung behoben, siehe Commits `f26791c` (okf-tools) und `dbcef17`/
  `2e20b8d`/`f3c7b21` (KC — inkl. `TaskNotes/`-Entfernung als separater Nutzerauftrag).
