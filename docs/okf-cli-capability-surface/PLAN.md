# okf-cli Capability Surface — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `okf-cli` tell the truth about what it can do — to a human at `--help` and to an agent over MCP — and make an undocumented command unmergeable rather than merely noticeable.

**Architecture:** The argparse parser becomes the single source of truth for the command surface. Every subcommand is registered through one helper that takes its one-line summary and its purpose group; that one authored string reaches both help levels (`help=` in the top-level directory, `description=` at the top of `<command> --help`), and the grouped overview in the epilog is *rendered* from the registered parsers instead of hand-maintained in the module docstring. The one piece of genuine detail in the deleted docstring block — `find`'s scoring explanation — is not dropped: it moves into `find`'s own epilog, corrected on the way, so `<command> --help` gets richer rather than poorer (Task 2 Step 4b). Everything else in that block is a one-liner already carried by the summaries. A conformance test asserts the invariants (every command has a summary, every option has help, every command is grouped and dispatchable), which converts the whole defect class from "notice it in a review" to "cannot merge it". The MCP surface stays a deliberately selective whitelist, but gains the three commands an agent cannot work without.

**Tech Stack:** Python 3 standard library only (`argparse`, `textwrap`). `unittest`. No install, no external CLI framework — the CLI's defining constraint (module docstring, `cli/okf-cli.py:1-6`).

## Global Constraints

- **Standard library only, no install, no external CLI framework.** The whole point of the surface being argparse-shaped is that it stays dependency-free. `textwrap` is stdlib and may be added to the import block (`cli/okf-cli.py:49-62`).
- **Artifact language English** — git commit subjects/bodies, bean titles/bodies, code comments, help strings. Chat with the PO stays German (global CLAUDE.md).
- **Commits:** `<type>(<scope>): <subject>`, subject max 50 characters, no `Co-Authored-By` trailer (hook-enforced E1/E2). Commit after every task. Explicit paths in `git add` — never `git add -A`.
- **Branch:** work directly on `main` (`docs/CLAUDE.md` → Worktree-Weiche: main-direct allowed, solo repo).
- **Test baseline:** `python3 -m unittest discover -s cli -p "test_*.py"` from the repo root. Measured at plan time on `main` (2026-07-26): `Ran 259 tests` / `FAILED (failures=19, errors=2)`. All 19F/2E are pre-existing in the crosslink suites. A task is done only when the count is still **exactly** 19 failures / 2 errors plus whatever new tests the task added, all green. Every new failure is yours.
- **`~/Obsidian/Knowledge-Catalogue` is a separate git repo.** Read from it, never commit into it. No task in this plan needs to write there.
- **No network in any test.** Nothing in this plan touches the embedding path; if a test of yours reaches the network, it is wrong.
- **Claims are evidence, not phrasing (LL-13).** A step that says "verify" means: run the command, quote its observed output in the bean. Never write "behaviour-preserving, verified" without the command that established it.

## Decisions this plan implements

| Dxx | Decision | Source |
|-----|----------|--------|
| D01 | Strang A (this plan) and Strang B (zero-hit reachability) are separated. Strang B gets a **measurement mandate** as its own bean, no fix plan, because its fix depends on a number nobody has measured. That bean does **not exist yet** — creating it is a pending action of the operationalization step, not of this plan; `okf-cli-snxj` still carries its original T10 content plus the PO reject | PO 2026-07-26, this session |
| D02 | **argparse is the single source of truth** for the capability surface. The hand-written `Commands:` prose block in the module docstring is replaced by a rendered overview; `find`'s scoring detail — the only non-one-liner in that block — moves into `find`'s own epilog rather than being deleted. A conformance test enforces the invariants | PO 2026-07-26, closes 6zhw design question 1+2 |
| D03 | **Both layouts, one source.** argparse's own listing stays flat and alphabetical (the PO's literal review request); a purpose-grouped overview is additionally rendered into the epilog. Two views cannot drift because both are generated | PO 2026-07-26, closes 6zhw design question 3 |
| D04 | MCP gains **`build-index`, `prime`, `info`** and nothing else. All three leave catalogue content untouched (`build-index` writes only its own `.fts` artefact, locally, without network). The wider surface question — which of the remaining eight commands belong in an agent's hands — stays explicitly open | PO 2026-07-26. The PO was offered three bundles (defect minimum only / these three / all non-mutating incl. `visualize`+`log`) and chose this one; `info` is therefore PO-selected, not plan-author bundling, even though the review itself named only `build-index` and `prime` |

## Findings this plan fixes (all reproduced live at plan time, not taken from the beans)

| Code | Severity | Finding | Location |
|------|----------|---------|----------|
| B01 | medium | `find`, `index` and `read` have no description line in the top-level command directory, because their `add_parser()` calls omit `help=` and argparse lists only subparsers that carry one. The primary command of the retrieval feature is invisible in its own CLI's directory | `cli/okf-cli.py:2584` (index), `:2596` (find), `:2610` (read) |
| B02 | low | `--limit LIMIT` renders with an empty description column while every sibling option of `find` has one | `cli/okf-cli.py:2598` |
| B03 | low | Neither the top-level help nor any subcommand help tells the reader that per-command detail exists at `<command> --help` | `cli/okf-cli.py:2579-2580` (no `epilog`) |
| B04 | low | The command listing follows registration order (`index, list, find, read, prime, info, toc, visualize, …`), not alphabetical | `cli/okf-cli.py:2584-2692` |
| B05 | medium | `--expand-tags` advertises itself as "experimental, off by default **until measured**". It was measured (T11, bean `okf-cli-ftri`), the result was negative for structural reasons, and the flag stays off — the help text promises a pending decision that has been made (Q05, D17) | `cli/okf-cli.py:2606-2609` |
| B06 | medium | Nine positionals/options across six subcommands carry no help at all: `index bundle` `:2585`, `find query` `:2597`, `find --limit` `:2598`, `read path` `:2611`, `toc path` `:2618`, `visualize bundle` `:2622`, `refs --json` `:2627`, `rewrite-path old` `:2629`, `rewrite-path new` `:2630` | `cli/okf-cli.py` as listed |
| B07 | high | An agent over MCP is told `note: lexical index is stale (catalogue changed since build) — run 'okf-cli build-index'` and cannot follow it: `build-index` is not on the MCP surface. Reproduced live against `~/Obsidian/Knowledge-Catalogue` at plan time — the stale note printed, and `mcp/okf_mcp.py:7-17` whitelists 10 of the CLI's 21 commands, `build-index` not among them | `mcp/okf_mcp.py:7-17` |
| B08 | medium | `prime` — documented as "one-shot agent onboarding … start here in a new session" — is missing from the agent interface | `mcp/okf_mcp.py:7-17` |
| B09 | medium | `okf_find`'s MCP docstring still describes the pre-feature keyword search ("Ranked keyword search across a catalogue/repo root…"). An MCP consumer cannot learn from it that results may come from either of two arms, that `provenance:` lines exist, or that degradation notes appear on stderr | `mcp/okf_mcp.py:79-80` |
| B10 | medium | The docstring block being deleted documents `find`'s score as `achieved/max ("4/6") — 3 title-hit + 2 tag-hit + 1 body-hit per term … max = 6 * number of terms`. That is only true of the **substring fallback**. Since the FTS arm shipped, `_rank_lexically()` returns a 0..100 scale relative to the run's own top hit, and semantic hits are `round(100 * cosine)` — which is why a live query prints `score: 46/100`. The prose to be carried into `find`'s epilog therefore has to be corrected, not copied | `cli/okf-cli.py:16-19` (stale prose) vs `:912-928` (`_rank_lexically`), `:1140-1152` (`_semantic_hit_dicts`) |

### Live evidence for B07-B09 (LL-13: the command, not the conclusion)

```
$ python3 cli/okf-cli.py --root ~/Obsidian/Knowledge-Catalogue find "zzzzqqqq" --limit 3
note: lexical index is stale (catalogue changed since build) — run `okf-cli build-index`
note: semantic arm owns this ranking (lexical top-1 lacked a clear margin)
------
score: 46/100
title: QMunity
type: Concept
path: qm-wiki/documented-information/basics/qmunity
...
provenance: semantic (cosine=0.46)
```

The first stderr line is the instruction an MCP consumer receives and cannot execute (B07). The whitelist it would need is `mcp/okf_mcp.py:7-17` — ten entries: `find, read, toc, index, list, check, reindex, refs, rename, tags`, against the CLI's 21 subcommands; neither `build-index` (B07) nor `prime` (B08) is among them. `okf_find`'s docstring at `mcp/okf_mcp.py:79-80` reads `"""Ranked keyword search across a catalogue/repo root, composable with exact-match type/tag filters and a bundle/subdir scope."""` — no arm, no provenance, no degradation (B09). The same transcript is also the live proof for the `score: …/100` scale in B10.

## File structure

| File | Responsibility | Change |
|------|----------------|--------|
| `cli/okf-cli.py` | The CLI. Gains `build_parser()`, `_sub()`, `COMMAND_GROUPS`, `_GROUP_ORDER`, `render_command_overview()`, `subcommand_parsers()`, `parser_actions()`, `COMMAND_DISPATCH`; `main()` shrinks to parse + dispatch; the module docstring loses its hand-written command block | Modify `:8-45` (docstring command block), `:49-62` (imports), `:2578-2712` (parser + main) |
| `cli/test_okf_cli.py` | Tests for the CLI, loaded via `importlib` (`:15-18`) | Append classes `ParserExtraction`, `CommandDirectory`, `FindOptionHelp`, `CommandDirectoryOrder`, `GroupedOverview`, `CommandHelpConformance` |
| `mcp/okf_mcp.py` | Thin subprocess wrapper. Gains three whitelist entries and three tool wrappers; `okf_find`'s docstring is rewritten | Modify `:7-17` (`_COMMANDS`), `:76-81` (`okf_find` docstring), append tools in `_register()` |
| `cli/test_okf_mcp.py` | Integration tests at the MCP → subprocess boundary | Append classes `McpAgentRemedyBoundary`, `McpSurfaceParity` |

No new files. The plan deliberately does not split `cli/okf-cli.py` — it is a single-file tool by design, and the parser section is the one part of it that benefits from staying adjacent to the dispatch table.

## Task → bean mapping

| Task | Serves | Why |
|------|--------|-----|
| 1 | `okf-cli-6zhw` | Extraction is the precondition for testing help output at all |
| 2 | `okf-cli-6zhw` + `okf-cli-3suc` (B01, B10) | The registration helper is where the three missing summaries land, and where `find`'s corrected scoring prose gets a home |
| 3 | `okf-cli-3suc` (B02, B05) | The two remaining option-text defects |
| 4 | `okf-cli-3suc` (B03, B04) + `okf-cli-6zhw` (D03) | Sorting, pointer and the generated grouped overview are one rendering change |
| 5 | `okf-cli-6zhw` (B06) | The conformance gate and the nine arguments it catches |
| 6 | `okf-cli-4ws6` (B07, B08, B09) | MCP surface, independent of everything above |

---

### Task 1: Extract `build_parser()` from `main()`

**Files:**
- Modify: `cli/okf-cli.py:2578-2712`
- Test: `cli/test_okf_cli.py` (append)

**Interfaces:**
- Consumes: nothing.
- Produces: `build_parser() -> argparse.ArgumentParser`; `COMMAND_DISPATCH: dict[str, callable]`; `subcommand_parsers(ap) -> dict[str, argparse.ArgumentParser]`; `parser_actions(parser) -> list[argparse.Action]`. Tasks 2-5 all drive these.

This task is a pure refactor: the help output must not change by a single byte. Everything after it depends on being able to build the parser without executing a command.

- [ ] **Step 1: Write the failing test**

Append to `cli/test_okf_cli.py`:

```python
class ParserExtraction(unittest.TestCase):
    """build_parser() renders the surface without executing a command."""

    def test_every_registered_command_is_dispatchable(self):
        parsers = okf.subcommand_parsers(okf.build_parser())
        self.assertEqual(set(parsers), set(okf.COMMAND_DISPATCH))

    def test_parser_actions_skips_the_auto_help_action(self):
        parsers = okf.subcommand_parsers(okf.build_parser())
        dests = [a.dest for a in okf.parser_actions(parsers["read"])]
        self.assertNotIn("help", dests)
        self.assertIn("path", dests)
```

- [ ] **Step 2: Run it, confirm it fails for the stated reason**

```bash
cd /Users/erik/Obsidian/tools/okf-tools
rm -rf cli/__pycache__
python3 -m unittest cli.test_okf_cli.ParserExtraction -v
```

Expected: `AttributeError: module 'okf_cli' has no attribute 'subcommand_parsers'`. Anything else means the test is wrong, not the code.

- [ ] **Step 3: Add the accessors and the dispatch table**

Insert immediately **above** `def main():` (currently `cli/okf-cli.py:2578`):

```python
COMMAND_DISPATCH = {
    "prime": cmd_prime, "index": cmd_index, "find": cmd_find, "list": cmd_list,
    "read": cmd_read, "info": cmd_info, "toc": cmd_toc, "visualize": cmd_visualize,
    "refs": cmd_refs,
    "rewrite-path": cmd_rewrite_path, "rename": cmd_rename,
    "build-index": cmd_build_index,
    "reindex": cmd_reindex, "log": cmd_log, "tags": cmd_tags,
    "merge-tags": cmd_merge_tags,
    "remove-tags": cmd_remove_tags,
    "normalize-tags": cmd_normalize_tags,
    "check": cmd_check, "fix-crosslinks": cmd_fix_crosslinks,
    "fix-xml-tags": cmd_fix_xml_tags,
}


def subcommand_parsers(ap):
    """{name: parser} for a built parser's subcommands. argparse exposes the
    individual subparsers only through the subparsers action, so the private
    attribute access is contained here rather than spread across tests."""
    for action in ap._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action.choices
    return {}


def parser_actions(parser):
    """Every argparse action of a parser except the auto-added -h/--help.
    Same contained-private-access rationale as subcommand_parsers()."""
    return [a for a in parser._actions
            if not isinstance(a, argparse._HelpAction)]
```

- [ ] **Step 4: Split `main()` into `build_parser()` + `main()`**

Rename the existing `def main():` to `def build_parser():`, keep its body up to and including the last `pfxt.add_argument(...)` line (`cli/okf-cli.py:2695`), and end it with `return ap`. Then write the new `main()` directly beneath it:

```python
def main():
    args = build_parser().parse_args()
    root = catalogue_root(args.root)
    if root is None:
        sys.exit("ERROR: no catalogue found in cwd or its ancestors; pass --root <path>")
    if not os.path.isdir(root):
        sys.exit("ERROR: root not found: {} (pass --root <path>)".format(root))
    COMMAND_DISPATCH[args.cmd](root, args)
```

The inline dispatch dict at `cli/okf-cli.py:2701-2711` is deleted — `COMMAND_DISPATCH` replaces it verbatim, same keys, same functions.

- [ ] **Step 5: Prove the refactor changed no output**

```bash
cd /Users/erik/Obsidian/tools/okf-tools
git stash && python3 cli/okf-cli.py --help > /tmp/help_before.txt 2>&1 && \
  python3 cli/okf-cli.py find --help > /tmp/find_before.txt 2>&1 && git stash pop
python3 cli/okf-cli.py --help > /tmp/help_after.txt 2>&1
python3 cli/okf-cli.py find --help > /tmp/find_after.txt 2>&1
diff /tmp/help_before.txt /tmp/help_after.txt && diff /tmp/find_before.txt /tmp/find_after.txt && echo "IDENTICAL"
```

Expected: `IDENTICAL`. Quote that line plus both `diff` invocations in the bean — this is the evidence for "pure refactor", and per LL-13 the claim without the command does not count.

- [ ] **Step 6: Run the new tests and the full suite**

```bash
rm -rf cli/__pycache__
python3 -m unittest cli.test_okf_cli.ParserExtraction -v
python3 -m unittest discover -s cli -p "test_*.py" 2>&1 | tail -3
```

Expected: 2 tests OK; suite at `Ran 261 tests` with exactly `failures=19, errors=2`.

- [ ] **Step 7: Commit**

```bash
git add cli/okf-cli.py cli/test_okf_cli.py
git commit -m "refactor(cli): split build_parser out of main"
```

---

### Task 2: Register every subcommand through `_sub()` with summary and group

**Files:**
- Modify: `cli/okf-cli.py` — new `_GROUP_ORDER`/`COMMAND_GROUPS`/`_sub()` above `build_parser()`, then all 21 registrations inside it
- Test: `cli/test_okf_cli.py` (append)

**Interfaces:**
- Consumes: `build_parser()`, `subcommand_parsers()` from Task 1.
- Produces: `_sub(sub, name, group, summary, **kwargs) -> parser`; `COMMAND_GROUPS: dict[str, str]`; `_GROUP_ORDER: tuple[str, ...]`. Task 4 renders from both; Task 5 asserts on both.

This is where B01 dies: a command physically cannot be registered without a summary, because `_sub()` requires it as a positional argument.

- [ ] **Step 1: Write the failing test**

Append to `cli/test_okf_cli.py`:

```python
class CommandDirectory(unittest.TestCase):
    """Every command carries a summary, at exactly one authored place."""

    def test_find_index_read_are_no_longer_invisible(self):
        parsers = okf.subcommand_parsers(okf.build_parser())
        for name in ("find", "index", "read"):
            self.assertTrue((parsers[name].description or "").strip(),
                            "{} has no summary".format(name))

    def test_the_summary_reaches_both_help_levels(self):
        ap = okf.build_parser()
        parsers = okf.subcommand_parsers(ap)
        summary = parsers["read"].description
        self.assertIn(summary, parsers["read"].format_help())
        self.assertIn("find", ap.format_help())

    def test_every_command_declares_a_group(self):
        parsers = okf.subcommand_parsers(okf.build_parser())
        self.assertEqual(set(okf.COMMAND_GROUPS), set(parsers))

    def test_find_help_explains_both_score_scales(self):
        parsers = okf.subcommand_parsers(okf.build_parser())
        text = parsers["find"].format_help()
        self.assertIn("100", text)
        self.assertIn("6 * number of terms", text)
        self.assertIn("provenance", text)
```

- [ ] **Step 2: Run it, confirm it fails for the stated reason**

```bash
rm -rf cli/__pycache__
python3 -m unittest cli.test_okf_cli.CommandDirectory -v
```

Expected: `test_find_index_read_are_no_longer_invisible` fails with `find has no summary`; `test_every_command_declares_a_group` fails with `AttributeError: … COMMAND_GROUPS`; `test_find_help_explains_both_score_scales` fails with `'6 * number of terms' not found in …`.

- [ ] **Step 3: Add the registration helper**

Insert above `def build_parser():`:

```python
_GROUP_ORDER = ("navigation", "search", "tags", "maintenance")

# command name -> group; filled by _sub() at registration time, so it can
# never disagree with the parser it describes.
COMMAND_GROUPS = {}


def _sub(sub, name, group, summary, **kwargs):
    """Register one subcommand. The summary is authored exactly once, here,
    and reaches both help levels: argparse prints it in the top-level command
    directory (help=) and at the top of `okf-cli.py <command> --help`
    (description=). The group feeds the rendered overview in the epilog.

    A command cannot ship undocumented: summary and group are required
    positionals, and CommandHelpConformance asserts the rest."""
    if group not in _GROUP_ORDER:
        raise ValueError("unknown command group: {}".format(group))
    COMMAND_GROUPS[name] = group
    return sub.add_parser(name, help=summary, description=summary, **kwargs)
```

- [ ] **Step 4: Convert all 21 registrations**

Replace each `sub.add_parser(...)` call in `build_parser()` with the `_sub()` form. Keep the registration order as it is for now — Task 4 sorts it. The three commands that had no `help=` get these summaries (new text, B01):

```python
    pi = _sub(sub, "index", "navigation",
              "catalogue TOC (bundles, descriptions, concept counts), or one "
              "bundle's index.md")
    pf = _sub(sub, "find", "search",
              "hybrid ranked search: lexical FTS5/BM25 arm plus semantic arm",
              formatter_class=argparse.RawDescriptionHelpFormatter,
              epilog=_FIND_EPILOG)
    pr = _sub(sub, "read", "navigation", "print one concept page")
```

The other eighteen keep their existing help string verbatim as the summary, and gain a group:

| command | group | command | group |
|---------|-------|---------|-------|
| `build-index` | search | `read` | navigation |
| `check` | maintenance | `refs` | search |
| `find` | search | `reindex` | maintenance |
| `fix-crosslinks` | maintenance | `remove-tags` | tags |
| `fix-xml-tags` | maintenance | `rename` | maintenance |
| `index` | navigation | `rewrite-path` | maintenance |
| `info` | navigation | `tags` | tags |
| `list` | navigation | `toc` | navigation |
| `log` | navigation | `visualize` | navigation |
| `merge-tags` | tags | | |
| `normalize-tags` | tags | | |
| `prime` | navigation | | |

Example of a conversion that keeps existing text (do the same for the rest):

```python
    pls = _sub(sub, "list", "navigation",
               "list concepts filtered by frontmatter type and/or tag")
    _sub(sub, "build-index", "search",
         "(re)build the FTS5 lexical search index at <root>/.fts/fts.sqlite "
         "(local only, no network)")
```

`find` is the one command whose summary alone loses information (B10, D02), so it keeps a verbatim epilog — which is why its registration passes `RawDescriptionHelpFormatter` and why its summary is kept to a single line: that formatter prints the description verbatim too, and a 140-character summary would render as one unwrapped line.

- [ ] **Step 4b: Carry `find`'s scoring detail into its epilog — corrected**

The deleted docstring block claims `score … max = 6 * number of terms` for every `find` result. That has been wrong since the FTS arm shipped: `_rank_lexically()` (`cli/okf-cli.py:912-928`) returns a 0..100 scale relative to the run's own top hit and only falls back to `6 * len(terms)` when no FTS index is usable, and `_semantic_hit_dicts()` (`:1140-1152`) scores semantic hits as `round(100 * cosine)`. Copying the old prose forward would carry a stale claim into the new help. Insert above `def build_parser():`:

```python
_FIND_EPILOG = """\
score lines:
  The two arms report on different scales, and `score: a/b` names the scale
  in use, not a confidence:
    a/100        the FTS5/BM25 lexical arm (relative to this run's own top
                 hit) and the semantic arm (round(100 * cosine)).
    a/(6 * n)    the substring fallback used when no FTS index is available:
                 per query term 3 for a title hit, 2 for a tag hit, 1 for a
                 body hit, capped at one per field per term — so the maximum
                 is 6 * number of terms.
  `provenance:` names the arm that produced the line; on a semantic hit it
  also prints the cosine. Degradations (index absent or stale, embedding
  backend unavailable) are announced on stderr, one note per degraded arm.
"""
```

- [ ] **Step 5: Run the tests**

```bash
rm -rf cli/__pycache__
python3 -m unittest cli.test_okf_cli.CommandDirectory cli.test_okf_cli.ParserExtraction -v
python3 -m unittest discover -s cli -p "test_*.py" 2>&1 | tail -3
```

Expected: 6 tests OK; suite `Ran 265 tests`, exactly `failures=19, errors=2`.

- [ ] **Step 6: Look at the result with your own eyes**

```bash
python3 cli/okf-cli.py --help | sed -n '/^positional/,/^options/p'
python3 cli/okf-cli.py find --help | head -5
```

Expected: `find`, `index` and `read` now carry a description line, and `find --help` opens with the summary. Quote both in the bean.

- [ ] **Step 7: Commit**

```bash
git add cli/okf-cli.py cli/test_okf_cli.py
git commit -m "fix(cli): every subcommand carries a summary"
```

---

### Task 3: Document `--limit`, correct the `--expand-tags` promise

**Files:**
- Modify: `cli/okf-cli.py` — `find`'s `--limit` and `--expand-tags` registrations (currently `:2598` and `:2606-2609`)
- Test: `cli/test_okf_cli.py` (append)

**Interfaces:**
- Consumes: `subcommand_parsers()`, `parser_actions()` from Task 1.
- Produces: nothing new.

B05 is the finding the PO did not raise: the flag advertises a decision as pending that was made. `--expand-tags` was measured against the full live catalogue over 48 queries and changed nothing on any per-file metric, for a structural reason — `mockup` and `excalidraw` are simply not neighbours in the tag-slug vector space (Q05, `docs/okf-retrieval-architecture/QUESTIONS.md`). The flag stays off; the help text has to say why, not promise a future measurement.

- [ ] **Step 1: Write the failing test**

Append to `cli/test_okf_cli.py`:

```python
class FindOptionHelp(unittest.TestCase):
    """find's options describe themselves, and truthfully."""

    def _find_action(self, dest):
        parsers = okf.subcommand_parsers(okf.build_parser())
        for act in okf.parser_actions(parsers["find"]):
            if act.dest == dest:
                return act
        self.fail("find has no action with dest {!r}".format(dest))

    def test_limit_carries_help_text(self):
        self.assertIn("default 10", self._find_action("limit").help or "")

    def test_expand_tags_no_longer_promises_a_pending_measurement(self):
        help_text = self._find_action("expand_tags").help or ""
        self.assertNotIn("until measured", help_text)
        self.assertIn("measured", help_text)
```

- [ ] **Step 2: Run it, confirm it fails for the stated reason**

```bash
rm -rf cli/__pycache__
python3 -m unittest cli.test_okf_cli.FindOptionHelp -v
```

Expected: `test_limit_carries_help_text` fails with `'default 10' not found in ''`; `test_expand_tags_no_longer_promises_a_pending_measurement` fails with `'until measured' unexpectedly found in …`.

- [ ] **Step 3: Fix both help strings**

```python
    pf.add_argument("--limit", type=int, default=10,
                    help="max results to print (default 10)")
```

```python
    pf.add_argument("--expand-tags", action="store_true",
                    help="expand the query with semantically near registered "
                         "tags before lexical scoring. Measured against the "
                         "full catalogue and found ineffective for the "
                         "vocabulary-mismatch class it was built for, so it "
                         "stays off by default (Q05/D17)")
```

- [ ] **Step 4: Run the tests**

```bash
rm -rf cli/__pycache__
python3 -m unittest cli.test_okf_cli.FindOptionHelp -v
python3 -m unittest discover -s cli -p "test_*.py" 2>&1 | tail -3
```

Expected: 2 tests OK; suite `Ran 267 tests`, exactly `failures=19, errors=2`.

- [ ] **Step 5: Commit**

```bash
git add cli/okf-cli.py cli/test_okf_cli.py
git commit -m "fix(cli): document --limit, correct --expand-tags"
```

---

### Task 4: Alphabetical listing, per-command pointer, generated grouped overview

**Files:**
- Modify: `cli/okf-cli.py:1-52` (module docstring), `:49-62` (imports), `build_parser()` (registration order + epilog)
- Test: `cli/test_okf_cli.py` (append)

**Interfaces:**
- Consumes: `_sub()`, `COMMAND_GROUPS`, `_GROUP_ORDER` from Task 2.
- Produces: `render_command_overview(sub) -> str`.

This is D03 in code: argparse's own listing becomes flat and alphabetical (the PO's literal request), and the purpose-grouped view is rendered into the epilog from the same registrations. Neither can go stale, because neither is authored twice. The hand-written `Commands:` block in the module docstring — the artefact that already drifted, documenting `find` in detail while the generated listing omitted it — is removed.

- [ ] **Step 1: Write the failing test**

Append to `cli/test_okf_cli.py`:

```python
class CommandDirectoryOrder(unittest.TestCase):

    def test_commands_are_listed_alphabetically(self):
        names = list(okf.subcommand_parsers(okf.build_parser()))
        self.assertEqual(names, sorted(names))

    def test_top_level_help_points_at_per_command_help(self):
        self.assertIn("<command> --help", okf.build_parser().format_help())


class GroupedOverview(unittest.TestCase):

    def test_overview_names_every_group_that_has_commands(self):
        text = okf.build_parser().format_help()
        self.assertIn("commands by purpose:", text)
        for group in okf._GROUP_ORDER:
            self.assertIn("  {}:".format(group), text)

    def test_overview_covers_every_command(self):
        text = okf.build_parser().format_help()
        overview = text.split("commands by purpose:", 1)[1]
        for name in okf.COMMAND_GROUPS:
            self.assertRegex(overview, r"\n\s+{}\s".format(re.escape(name)))

    def test_module_docstring_no_longer_lists_commands_by_hand(self):
        self.assertNotIn("okf-cli.py find", okf.__doc__)
        self.assertNotIn("okf-cli.py merge-tags", okf.__doc__)
```

`re` is already imported in the test module's target; add `import re` to `cli/test_okf_cli.py`'s import block if it is not there yet.

- [ ] **Step 2: Run it, confirm it fails for the stated reason**

```bash
rm -rf cli/__pycache__
python3 -m unittest cli.test_okf_cli.CommandDirectoryOrder cli.test_okf_cli.GroupedOverview -v
```

Expected: order test fails with a list mismatch starting `['index', 'list', 'find', …] != ['build-index', 'check', 'find', …]`; the other four fail on missing `<command> --help` / `commands by purpose:` / the docstring still containing `okf-cli.py find`.

- [ ] **Step 3: Add `textwrap` to the imports**

In `cli/okf-cli.py:49-62`, insert `import textwrap` in alphabetical position (after `import sys`).

- [ ] **Step 4: Add the renderer**

Insert below `_sub()`:

```python
def render_command_overview(sub):
    """The purpose-grouped command directory, rendered from the registered
    parsers (D02/D03). argparse's own listing above it is flat and
    alphabetical; this block answers "what can this CLI do" by purpose. Both
    come from the same registrations, so neither can drift from the other."""
    lines = ["commands by purpose:"]
    for group in _GROUP_ORDER:
        names = sorted(n for n, g in COMMAND_GROUPS.items() if g == group)
        if not names:
            continue
        lines.append("  {}:".format(group))
        for name in names:
            lines.append(textwrap.fill(
                sub.choices[name].description, width=96,
                initial_indent="    {:<16} ".format(name),
                subsequent_indent=" " * 21))
    lines.append("")
    lines.append("run `okf-cli.py <command> --help` for one command's options.")
    return "\n".join(lines)
```

- [ ] **Step 5: Sort the registrations and attach the epilog**

Reorder the 21 `_sub()` calls in `build_parser()` alphabetically — `build-index, check, find, fix-crosslinks, fix-xml-tags, index, info, list, log, merge-tags, normalize-tags, prime, read, refs, reindex, remove-tags, rename, rewrite-path, tags, toc, visualize` — moving each command's own `add_argument()` calls with it. Registration order is what argparse prints, and nothing else depends on it.

Then, immediately before `return ap`:

```python
    ap.epilog = render_command_overview(sub)
```

The top-level parser already uses `RawDescriptionHelpFormatter` (`cli/okf-cli.py:2579-2580`), so the epilog is printed verbatim — which is why `render_command_overview()` wraps its own lines.

- [ ] **Step 6: Shrink the module docstring**

Replace the `Commands:` block — `cli/okf-cli.py:8-45`, i.e. from the line `Commands:` (`:8`) up to and including the `rename` entry's last continuation line `change, then reindex affected bundles; dry-run default` (`:45`) — with:

```
Run `okf-cli.py --help` for the command directory (flat + grouped by purpose),
and `okf-cli.py <command> --help` for one command's options. Both are generated
from the parser — this file documents no command list by hand.
```

Keep the first paragraph (`:2-6`, purpose + catalogue definition + stdlib constraint) unchanged, and keep the blank line `:46`, the closing `Run from the catalogue root, or pass --root <path>.` (`:47`) and the docstring terminator `"""` (`:48`) exactly where they are — the replacement range ends at `:45` and must not swallow them.

- [ ] **Step 7: Run the tests**

```bash
rm -rf cli/__pycache__
python3 -m unittest cli.test_okf_cli.CommandDirectoryOrder cli.test_okf_cli.GroupedOverview -v
python3 -m unittest discover -s cli -p "test_*.py" 2>&1 | tail -3
```

Expected: 5 tests OK; suite `Ran 272 tests`, exactly `failures=19, errors=2`.

- [ ] **Step 8: Read the help as a user would**

```bash
python3 cli/okf-cli.py --help
```

Expected: alphabetical listing, then the grouped overview, then the `<command> --help` pointer. Paste the output into the bean — this is the artefact the PO rejected US-07 over, and the bean should carry its replacement.

- [ ] **Step 9: Commit**

```bash
git add cli/okf-cli.py cli/test_okf_cli.py
git commit -m "feat(cli): generated command directory in help"
```

---

### Task 5: The conformance gate

**Files:**
- Modify: `cli/okf-cli.py` — the nine registrations listed in B06
- Test: `cli/test_okf_cli.py` (append)

**Interfaces:**
- Consumes: everything from Tasks 1-4.
- Produces: nothing new.

This task is the durable half of `okf-cli-6zhw`: after it, a command or option that ships without a description fails the suite. Write the gate first, then fix what it catches — that order is the point, because the gate has to be shown catching real omissions before it is trusted.

- [ ] **Step 1: Write the failing test**

Append to `cli/test_okf_cli.py`:

```python
class CommandHelpConformance(unittest.TestCase):
    """An undocumented command or option is unmergeable, not merely
    noticeable (D02). This is the gate the 2026-07-26 PO review asked for."""

    def setUp(self):
        self.ap = okf.build_parser()
        self.parsers = okf.subcommand_parsers(self.ap)

    def test_every_subcommand_has_a_summary(self):
        missing = sorted(n for n, p in self.parsers.items()
                         if not (p.description or "").strip())
        self.assertEqual(missing, [])

    def test_every_option_and_positional_has_help(self):
        missing = []
        for name, parser in sorted(self.parsers.items()):
            for act in okf.parser_actions(parser):
                if not (act.help or "").strip():
                    missing.append("{} {}".format(name, act.dest))
        self.assertEqual(missing, [])

    def test_every_command_is_grouped_and_dispatchable(self):
        self.assertEqual(set(okf.COMMAND_GROUPS), set(self.parsers))
        self.assertEqual(set(okf.COMMAND_DISPATCH), set(self.parsers))
```

- [ ] **Step 2: Run it, confirm it catches exactly the nine known omissions**

```bash
rm -rf cli/__pycache__
python3 -m unittest cli.test_okf_cli.CommandHelpConformance -v
```

Expected: `test_every_option_and_positional_has_help` fails with a list of nine entries — `['find limit', ...]` will already be gone (Task 3), so the list should read exactly:

```
['find query', 'index bundle', 'read path', 'refs json', 'rewrite-path old',
 'rewrite-path new', 'toc path', 'visualize bundle']
```

That is eight, because `find --limit` was fixed in Task 3. The list is built by iterating commands in sorted order and their actions in **registration** order, which is why `rewrite-path old` precedes `rewrite-path new` (`cli/okf-cli.py:2629-2630`) — not alphabetical within a command. If the list differs, stop and reconcile against B06 before changing anything — a longer list means the plan's inventory was incomplete and the extra entries need their own help text written here.

- [ ] **Step 3: Give the eight arguments help text**

```python
    pi.add_argument("bundle", nargs="?",
                    help="bundle to print (default: the whole catalogue TOC)")
    pf.add_argument("query", help="search terms; quote multi-word queries")
    pr.add_argument("path", help="<bundle>/<concept-id> of the page to print")
    pt.add_argument("path", help="<bundle>/<concept-id> to list headings for")
    pv.add_argument("bundle", help="bundle to render the graph for")
    prf.add_argument("--json", action="store_true",
                     help="machine-readable output")
    prw.add_argument("old", help="literal path string to replace")
    prw.add_argument("new", help="replacement path string")
```

- [ ] **Step 4: Run the gate again, then the suite**

```bash
rm -rf cli/__pycache__
python3 -m unittest cli.test_okf_cli.CommandHelpConformance -v
python3 -m unittest discover -s cli -p "test_*.py" 2>&1 | tail -3
```

Expected: 3 tests OK; suite `Ran 275 tests`, exactly `failures=19, errors=2`.

- [ ] **Step 5: Prove the gate actually bites (mutation self-test)**

Temporarily drop the `help=` from `pr.add_argument("path", …)`, then:

```bash
rm -rf cli/__pycache__
python3 -m unittest cli.test_okf_cli.CommandHelpConformance -v
```

Expected: `AssertionError: ['read path'] != []`. Revert the edit, clear the cache, re-run, confirm green, and record the md5 of `cli/okf-cli.py` before and after the mutation to show the revert was byte-identical:

```bash
md5 cli/okf-cli.py
```

A gate that has not been seen failing is not evidence (LL-01, LL-07).

- [ ] **Step 6: Commit**

```bash
git add cli/okf-cli.py cli/test_okf_cli.py
git commit -m "feat(cli): conformance gate for help coverage"
```

---

### Task 6: Reach `build-index`, `prime` and `info` over MCP

**Files:**
- Modify: `mcp/okf_mcp.py:7-17` (`_COMMANDS`), `:79-80` (`okf_find` docstring), `_register()` (three new tools)
- Test: `cli/test_okf_mcp.py` (append)

**Interfaces:**
- Consumes: nothing from Tasks 1-5 — this task is independent and may be done first if that is more convenient.
- Produces: MCP tools `okf_build_index`, `okf_prime`, `okf_info`.

B07 is the substance: `find` prints `run 'okf-cli build-index'` on a stale or absent index, and the audience that note was written for cannot execute it. Verified live at plan time against `~/Obsidian/Knowledge-Catalogue` — the stale note printed on a real query while `_COMMANDS` whitelists ten commands without `build-index` among them.

All three commands exit 0 on a catalogue that lacks `CLAUDE.md`/`TYPES.md` (probed at plan time: `prime` prints `(missing: CLAUDE.md)`, `info` prints `(missing: TYPES.md)`, both `rc=0`), so the boundary tests can run against the existing tiny fixture catalogue without seeding those files.

- [ ] **Step 1: Write the failing test**

Append to `cli/test_okf_mcp.py`:

```python
class McpAgentRemedyBoundary(McpBoundaryTestBase):
    """The remedy find prescribes must be executable by the audience it
    addresses (okf-cli-4ws6)."""

    def test_build_index_reaches_the_cli_and_writes_the_index(self):
        out = mcp.run_okf(self.root, "build-index", {})
        self.assertTrue(os.path.exists(
            os.path.join(self.root, ".fts", "fts.sqlite")))
        self.assertIn("indexed", out)

    def test_prime_reaches_the_cli(self):
        self.assertTrue(mcp.run_okf(self.root, "prime", {}).strip())

    def test_info_reaches_the_cli(self):
        self.assertTrue(mcp.run_okf(self.root, "info", {}).strip())


class McpSurfaceParity(unittest.TestCase):
    """Every whitelisted MCP command is a real CLI command. Catches a typo or
    a command renamed on one side only — the drift class of okf-cli-4ws6."""

    def test_whitelist_only_names_real_cli_commands(self):
        spec = importlib.util.spec_from_file_location(
            "okf_cli", os.path.join(_HERE, "okf-cli.py"))
        okf = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(okf)
        unknown = sorted(set(mcp._COMMANDS) - set(okf.COMMAND_DISPATCH))
        self.assertEqual(unknown, [])
```

`McpSurfaceParity` consumes `COMMAND_DISPATCH` from Task 1. If Task 6 runs before Task 1, write the other three tests now and add this class when Task 1 has landed — do not weaken it to a hardcoded list.

- [ ] **Step 2: Run it, confirm it fails for the stated reason**

```bash
rm -rf cli/__pycache__ mcp/__pycache__
python3 -m unittest cli.test_okf_mcp.McpAgentRemedyBoundary -v
```

Expected: three failures with `ValueError: unsupported okf command: build-index` (and `prime`, `info`).

- [ ] **Step 3: Whitelist the three commands**

In `mcp/okf_mcp.py:7-17`, add to `_COMMANDS`:

```python
    "build-index": ([], False),
    "prime": ([], False),
    "info":  ([], False),
```

- [ ] **Step 4: Add the three tool wrappers**

Append inside `_register()`, before `return server`:

```python
    @server.tool()
    def okf_build_index(root: str) -> str:
        """(Re)build the FTS5 lexical index at <root>/.fts/fts.sqlite. Local
        only, no network, no change to catalogue content. Run this when
        okf_find reports the lexical index as absent or stale — that note
        names this command, and this tool is how you act on it."""
        return run_okf(root, "build-index", {})

    @server.tool()
    def okf_prime(root: str) -> str:
        """One-shot onboarding for a fresh session: the catalogue's CLAUDE.md
        guide plus its TOC. Start here before searching a catalogue you have
        not worked with in this session."""
        return run_okf(root, "prime", {})

    @server.tool()
    def okf_info(root: str) -> str:
        """The catalogue's schema docs (TYPES.md + PROPERTIES.md): the valid
        `type` values and the frontmatter properties a concept must carry.
        Read this before writing into a catalogue."""
        return run_okf(root, "info", {})
```

- [ ] **Step 5: Rewrite `okf_find`'s docstring (B09)**

Replace the docstring at `mcp/okf_mcp.py:79-80`:

```python
        """Ranked search across a catalogue/repo root, composable with
        exact-match type/tag filters and a bundle/subdir scope.

        Two arms produce results: a lexical FTS5/BM25 arm and a semantic
        embedding arm. Exactly one of them owns the ranking per query — the
        lexical arm when its top hit has a clear margin, otherwise the
        semantic one — and the other arm's hits are appended behind, never in
        front. Every result line names its origin as `provenance: lexical` or
        `provenance: semantic (cosine=…)`.

        Degradations are announced on stderr and never fail the call: a
        missing or stale lexical index falls back to a substring scan (fix it
        with okf_build_index), and an unavailable embedding backend leaves
        lexical results only."""
```

- [ ] **Step 6: Run the tests**

```bash
rm -rf cli/__pycache__ mcp/__pycache__
python3 -m unittest cli.test_okf_mcp -v 2>&1 | tail -5
python3 -m unittest discover -s cli -p "test_*.py" 2>&1 | tail -3
```

Expected: the MCP module's tests all pass; suite `Ran 279 tests`, exactly `failures=19, errors=2`.

- [ ] **Step 7: Commit**

```bash
git add mcp/okf_mcp.py cli/test_okf_mcp.py
git commit -m "fix(mcp): expose build-index, prime, info"
```

---

## Out of scope, deliberately

**Strang B — the unreachable zero-hit branch (`okf-cli-snxj`).** The PO decided on 2026-07-26 that this plan does not carry a fix for it. What ships instead is a measurement mandate as its own bean — which does not exist yet and is created at operationalization, not by this plan — because the fix depends on a number nobody has measured, and this chain has thrown away three retrieval intuitions that turned out to be wrong when measured (chunking, the absolute cosine floor, "lexical is the biggest lever"). A threshold chosen by a plan author would be exactly the overfitting that was avoided three times.

One correction the measurement bean must carry, found while grounding this plan: **R34 is not the answer to this question.** R34 rejected an absolute cosine floor (Q12/T06, status 🔴) on the evidence that correct rank-1 targets and best false hits overlap completely — but that was measured exclusively on queries that *have* a target in the catalogue. The population in `okf-cli-snxj` is the opposite one: queries with no target at all. Its top-1 cosine distribution has never been measured, because all 48 evaluation queries have targets. The one live data point (nonsense query tops out at 0.46, minimum correct target sits at 0.494 per R34) suggests separation may exist, at n=1. The counter-evidence in the same dataset is just as concrete: the two `synonymy` zero-hits in `eval/taxonomy.md` sit at cosine 0.40 and 0.35, so a floor around 0.47 would destroy precisely the cases the feature exists to rescue. That asymmetry is why the bean must measure *both* candidate mechanisms — a suppressing floor, and a confidence bar that keeps the results but adds the suggestion line — against the same data, and recommend rather than ship.

**Which of the remaining eight CLI commands belong on the MCP surface** stays open (D04). `visualize` writes `viz.html` into the catalogue and `log --write` materialises `log.md`, so neither is the read-only addition it appears to be; the six tag/fix/rewrite commands mutate catalogue content. That is a blast-radius decision for the PO, not a completeness exercise.

## Self-review

**Spec coverage.** Every finding B01-B10 maps to a task: B01 → Task 2, B02+B05 → Task 3, B03+B04 → Task 4, B06 → Task 5, B07+B08 → Task 6 (whitelist + wrappers), B09 → Task 6 Step 5, B10 → Task 2 Step 4b. The three origin beans are covered: `okf-cli-3suc` by Tasks 2-4, `okf-cli-6zhw` by Tasks 1, 2, 4, 5 (single source of truth = D02, conformance gate = Task 5, sorting = D03), `okf-cli-4ws6` by Task 6. The PO decisions D01-D04 are each implemented or explicitly recorded as out of scope.

**Placeholders.** None: every step carries its literal code, its literal command and its expected output. The one conditional instruction (Task 5 Step 2, "if the list differs, reconcile against B06") names the exact expected list rather than deferring the content.

**Type consistency.** `build_parser()`, `subcommand_parsers()`, `parser_actions()` and `COMMAND_DISPATCH` are defined in Task 1 and used under those exact names in Tasks 2-6. `_sub(sub, name, group, summary, **kwargs)`, `COMMAND_GROUPS` and `_GROUP_ORDER` are defined in Task 2 and used under those names in Tasks 4 and 5. `render_command_overview(sub)` is defined and called in Task 4 only. The test classes referenced across tasks (`ParserExtraction`, `CommandDirectory`, `FindOptionHelp`, `CommandDirectoryOrder`, `GroupedOverview`, `CommandHelpConformance`, `McpAgentRemedyBoundary`, `McpSurfaceParity`) are each defined exactly once.

**Test-count arithmetic.** 259 baseline + 2 (T1) + 4 (T2) + 2 (T3) + 5 (T4) + 3 (T5) + 4 (T6) = 279. The per-task expectations above use these running totals; if a count is off by more than the tests you wrote, something else changed and you investigate before continuing.
