---
type: Spec
title: "mcp — EARS-Requirements MCP-1..MCP-12"
description: "The MCP server as an in-process subcommand of the same binary: tool surface, mutation polarity, schema and degradation contract for the agent-facing interface."
tags:
  - okf-cli
  - ears
  - requirements
  - spec
---

# mcp — EARS-Requirements MCP-1..MCP-12

The MCP server is the agent-facing surface of the okf binary, delivered alongside it rather than as a separate Python process (R1 in AUDIT.md). It exposes a subset of the command directory as MCP tools over stdio. Today it is a thin subprocess wrapper (`mcp/okf_mcp.py`) that shells out to `okf-cli.py` per call and re-marshals its text/JSON output back into a tool result; the rewrite folds it into the same binary and the same in-process call path the CLI itself uses.

The cross-cutting rules apply unchanged; this file states only what the MCP surface adds on top of them.

## Requirements

### Transport und Einbettung (D07, I12)

| ID | EARS-Requirement |
|----|------------------|
| MCP-1 | THE okf binary SHALL expose its MCP server as the `mcp serve` subcommand. |
| MCP-2 | THE okf binary SHALL serve MCP tool calls over the stdio transport. |
| MCP-3 | THE okf binary SHALL invoke each tool's command logic in-process, without spawning a subprocess per call. |

### Tool-Oberfläche (I12, B06)

| ID | EARS-Requirement |
|----|------------------|
| MCP-4 | THE okf binary SHALL expose an MCP tool for every read command of the command directory. |
| MCP-5 | THE okf binary SHALL name each exposed tool `okf_<command>`, replacing a hyphen in the command name with an underscore. |

### Mutations-Polarität (I03)

| ID | EARS-Requirement |
|----|------------------|
| MCP-6 | WHERE an exposed tool performs a store write and its `apply` parameter is false, THE okf binary SHALL perform none of the write. |
| MCP-7 | WHERE an exposed tool performs a store write and its `apply` parameter is true, THE okf binary SHALL perform the write. |

### Ausgabe-Vertrag (COM-19, COM-25–28, I13, I14)

| ID | EARS-Requirement |
|----|------------------|
| MCP-8 | THE okf binary SHALL treat every MCP tool call as a request for JSON output. |
| MCP-9 | WHERE a degradation occurs, THE okf binary SHALL carry it in the tool result's notes field in place of prefixing it to the payload text. |
| MCP-10 | THE okf binary SHALL derive each tool's declared schema from the same type its command handler returns. |
| MCP-11 | WHERE a tool's result count exceeds the output ceiling, THE okf binary SHALL return a truncated result carrying a `truncated` flag and the count remaining, in place of an error. |

### Parameter-Mapping (I12)

| ID | EARS-Requirement |
|----|------------------|
| MCP-12 | THE okf binary SHALL map each tool's parameters to its command directly, without a table of flag names shared across commands. |

## Grounding

Tool registration today: `_register()` (`mcp/okf_mcp.py:101-214`), fourteen tools — `okf_find` (`103`), `okf_read` (`127`), `okf_toc` (`132`), `okf_index` (`137`), `okf_list` (`142`), `okf_check` (`147`), `okf_reindex` (`152`), `okf_refs` (`157`), `okf_rename` (`162`), `okf_wikilinks` (`171`), `okf_tags` (`183`), `okf_build_index` (`190`), `okf_prime` (`198`), `okf_info` (`208`). `recent` is the sole pure read command the CLI has that none of these cover (B06; AUDIT A11: "`recent` ist als einziges Lese-Kommando … nicht exponiert"). `log` and `visualize` stay CLI-only by the same AUDIT finding ("die acht anderen Nicht-Exponierten sind Mutationen bzw. `log`/`visualize`") — MCP-4 does not pull them in, since neither is a read command in the COM-25 sense.

Naming convention: the one hyphenated command, `build-index`, is exposed as `okf_build_index` (`_COMMANDS` key `mcp/okf_mcp.py:18`, tool name `mcp/okf_mcp.py:190`) — the pattern MCP-5 generalizes.

Subprocess bridge to eliminate (I12): `run_okf()` calls `subprocess.run(["python3", OKF_CLI] + argv, ...)` per tool invocation (`mcp/okf_mcp.py:85`), built by `build_argv()` (`mcp/okf_mcp.py:31-56`) from the shared `_FLAGS`/`_BOOL_FLAGS` tables (`mcp/okf_mcp.py:24-28`) — the documented cross-command collision guard sits at `mcp/okf_mcp.py:40-48`.

Mutation polarity today: `okf_rename` takes `apply: bool = False` (`mcp/okf_mcp.py:162-168`) and forwards it as `--apply`. `okf_reindex` (`mcp/okf_mcp.py:152-154`) takes no such parameter and writes unconditionally — the exact gap MCP-6/MCP-7 close (AUDIT A3: "`okf_reindex` schreibt ohne Vorschau").

Schema mismatch (B03): `okf_find` declares `-> list` (`mcp/okf_mcp.py:103-104`), but `find` has `supports_json=False` in `_COMMANDS` (`mcp/okf_mcp.py:8`), so `run_okf` returns the raw text `str` `find` prints — the declared type and the actual return type disagree.

Degradation as prefixed text: for non-JSON commands `run_okf` prepends `proc.stderr` to `out` (`mcp/okf_mcp.py:96-97`), the mechanism MCP-9 replaces with a structured field; the intent is documented in the surrounding comment (`mcp/okf_mcp.py:73-83`), which is also `_common.md`'s Grounding source for COM-19's MCP arm.

Output ceiling as a hard error (I14): `MAX_OUTPUT_CHARS` (`mcp/okf_mcp.py:66-70`) is checked against `len(out)` only after the subprocess has produced the complete text, and the response is a `RuntimeError` naming the overage (`mcp/okf_mcp.py:89-93`) rather than a usable partial result.

## Deltas gegenüber heute

| Delta | Deckung |
|---|---|
| Subkommando im selben Binary statt Python-Subprozess pro Tool-Call | D07, I12 |
| stdio als einziger Transport in v1 | D07 |
| `recent` als Tool ergänzt | B06 |
| Eine Mutations-Polarität über alle schreibenden Tools (`okf_reindex` schreibt heute ungefragt) | I03 |
| Schema aus dem Rückgabetyp generiert statt handdeklariert (schließt B03 als Klasse) | I13, B03 |
| Degradation als Feld (`notes`) statt vorangestellter Text | COM-19 |
| Truncation vor der vollständigen Ausgabe, mit `truncated`-Flag statt Fehler danach | I14 |
| Kein geteiltes `_FLAGS`/`_BOOL_FLAGS`-Kollisionsrisiko | I12 |

## Anmerkungen

**MCP-6/MCP-7 schließen `okf_reindex` namentlich ein.** Heute ist `apply` nur bei `okf_rename` ein Parameter; `okf_reindex` schreibt ohne Vorschau. Das ist derselbe A3-Befund, den I03 „ohne Ausnahme" schließt — die beiden Zeilen gelten für jedes schreibende Tool, nicht nur für die, die den Parameter heute schon tragen.

**MCP-8 macht COM-25 bis COM-28 an der MCP-Grenze wirksam, ohne sie zu wiederholen.** Ein Tool-Call kennt kein `--json`-Flag zum Setzen — er verlangt strukturierte Ausgabe durch die Natur der Schnittstelle. Die Envelope-Regeln (COM-26/COM-27/COM-28) greifen deshalb bei jedem Call, nicht optional; MCP-9 spezifiziert nur, wohin eine Degradation innerhalb dieses Envelopes wandert.

## Offene Fragen

Ob COM-18 (stdout = Payload, stderr = Diagnose) innerhalb von `mcp serve` unverändert gilt, wo stdout für das JSON-RPC-Protokoll reserviert ist, ist durch AUDIT/DECISIONS nicht gedeckt.

Ob über das Lese-Set hinaus (MCP-4) weitere Mutationskommandos (`merge-tags`, `remove-tags`, `normalize-tags`, `fix-crosslinks`, `fix-xml-tags`, `rewrite-path`, `archive`) als Tools dazukommen, ist nicht entschieden — B06 deckt ausdrücklich nur `recent`. Diese Datei hält am heutigen Zuschnitt schreibender Tools (`rename`, `reindex`) fest.

Ob `root` weiterhin ein Pflichtparameter jedes Tool-Calls bleibt oder die Store-Erkennung (COM-1) einmalig beim Start von `mcp serve` läuft, ist nicht entschieden.
