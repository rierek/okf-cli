---
type: Plan
title: "PLAN — okf-cli-dwcq-cli-okf-prime-optimieren"
description: "Implementation plan for progressive disclosure in okf-cli prime, so agent onboarding output scales with what the agent actually needs."
tags:
  - tpic
  - okf-cli-dwcq-cli-okf-prime-optimieren
timestamp: 2026-07-18T12:50:09Z
---
# okf-cli prime — Progressive Disclosure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `okf-cli prime`'s default output compact and constant-ish in size, instead of growing linearly with catalogue bundle count.

**Architecture:** `cmd_prime` (cli/okf-cli.py:624) currently prints the CLAUDE.md guide, then loops over every bundle calling `render_bundle_block` (cli/okf-cli.py:456) — the same full per-bundle rendering `cmd_index` (cli/okf-cli.py:475) uses for browsing. Measured against `~/Obsidian/Knowledge-Catalogue` (21 bundles): default output is 268 lines / 13.5KB (~3355 tokens); `--full` is 310 lines / 25KB (~6326 tokens). Fix: add a one-line-per-bundle renderer (`render_bundle_line`) and make it the **default** `prime` bundle listing (name + concept count only). `--full` keeps today's full per-bundle blocks (description + directories + types + tags) for when an agent explicitly wants the detailed TOC in one call. `cmd_index` is untouched — it stays the place for full per-bundle/description browsing.

**Tech Stack:** Python 3 stdlib, `unittest` (no deps), existing test file `cli/test_okf_cli.py`.

---

### Task 1: `render_bundle_line` helper + test

**Files:**
- Modify: `cli/okf-cli.py` (add function near `render_bundle_block`, cli/okf-cli.py:456-472)
- Test: `cli/test_okf_cli.py` (new test class, append at end of file)

- [ ] **Step 1: Write the failing test**

Append to `cli/test_okf_cli.py`:

```python
class RenderBundleLine(unittest.TestCase):
    """T-okf-cli-dwcq — compact one-liner for prime's default bundle listing."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _concept(self, bundle, name):
        ap = os.path.join(self.tmp, bundle, name)
        os.makedirs(os.path.dirname(ap), exist_ok=True)
        with open(ap, "w", encoding="utf-8") as f:
            f.write("---\ntype: Concept\ntitle: {}\n---\n# {}\n".format(name, name))

    def test_line_has_bundle_name_and_concept_count(self):
        self._concept("b", "one.md")
        self._concept("b", "two.md")
        line = okf.render_bundle_line(self.tmp, "b")
        self.assertEqual(line, "b (2 concepts)")

    def test_zero_concepts_still_renders(self):
        os.makedirs(os.path.join(self.tmp, "empty"))
        line = okf.render_bundle_line(self.tmp, "empty")
        self.assertEqual(line, "empty (0 concepts)")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/erik/dev/okf-tools && python3 -m unittest cli.test_okf_cli.RenderBundleLine -v`
Expected: FAIL / ERROR with `AttributeError: module 'okf_cli' has no attribute 'render_bundle_line'`

- [ ] **Step 3: Write minimal implementation**

In `cli/okf-cli.py`, add directly above `def render_bundle_block(root, b, full=False):` (cli/okf-cli.py:456):

```python
def render_bundle_line(root, b):
    """Compact one-liner for prime's default bundle listing: name + concept count."""
    bp = os.path.join(root, b)
    n = sum(1 for _ in iter_concepts(bp))
    return "{} ({} concepts)".format(b, n)


```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/erik/dev/okf-tools && python3 -m unittest cli.test_okf_cli.RenderBundleLine -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
cd /Users/erik/dev/okf-tools
git add cli/okf-cli.py cli/test_okf_cli.py
git commit -m "feat(cli): add render_bundle_line compact bundle renderer"
```

---

### Task 2: Wire `cmd_prime` to the compact listing by default

**Files:**
- Modify: `cli/okf-cli.py:624-635` (`cmd_prime`)
- Modify: `cli/okf-cli.py:1885` (`--full` help text — now switches prime's bundle listing, not just types+tags)
- Test: `cli/test_okf_cli.py` (new test class, append after `RenderBundleLine`)

- [ ] **Step 1: Write the failing test**

Append to `cli/test_okf_cli.py`:

```python
class CmdPrimeBundleListing(unittest.TestCase):
    """T-okf-cli-dwcq — prime defaults to compact per-bundle lines; --full keeps
    today's full per-bundle blocks (description/directories/types/tags)."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        with open(os.path.join(self.tmp, "CLAUDE.md"), "w", encoding="utf-8") as f:
            f.write("# Guide\n")
        ap = os.path.join(self.tmp, "b", "one.md")
        os.makedirs(os.path.dirname(ap))
        with open(ap, "w", encoding="utf-8") as f:
            f.write("---\ntype: Concept\ntitle: One\n---\n# One\n")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _prime(self, full=False):
        import io, contextlib, types
        args = types.SimpleNamespace(full=full)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            okf.cmd_prime(self.tmp, args)
        return buf.getvalue()

    def test_default_uses_compact_line_not_description(self):
        out = self._prime(full=False)
        self.assertIn("b (1 concepts)", out)
        self.assertNotIn("description:", out)
        self.assertNotIn("directories:", out)

    def test_full_keeps_description_and_directories(self):
        out = self._prime(full=True)
        self.assertIn("description:", out)
        self.assertIn("concepts: 1", out)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/erik/dev/okf-tools && python3 -m unittest cli.test_okf_cli.CmdPrimeBundleListing -v`
Expected: FAIL on `test_default_uses_compact_line_not_description` (current default already prints `description:`)

- [ ] **Step 3: Write minimal implementation**

Replace `cmd_prime` (cli/okf-cli.py:624-635):

```python
def cmd_prime(root, args):
    """One-shot agent onboarding: CLAUDE.md guide + catalogue TOC in a single call."""
    p = os.path.join(root, "CLAUDE.md")
    print("------")
    if os.path.isfile(p):
        print(read_file(p))
    else:
        print("(missing: CLAUDE.md)")
    print("------")
    bundles = list_bundles(root)
    if args.full:
        for b in bundles:
            print(render_bundle_block(root, b, full=True))
            print("-----")
    else:
        print("bundles:")
        for b in bundles:
            print("- " + render_bundle_line(root, b))
        print("(for description/directories/types/tags per bundle: "
              "okf-cli index <bundle> [--full], or `okf-cli index` for all)")
```

Update the `--full` help text (cli/okf-cli.py:1885):

```python
    pp.add_argument("--full", action="store_true",
                    help="print full per-bundle blocks (description+directories+types+tags) "
                         "instead of the default compact name+count listing")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/erik/dev/okf-tools && python3 -m unittest cli.test_okf_cli.CmdPrimeBundleListing cli.test_okf_cli.RenderBundleLine -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
cd /Users/erik/dev/okf-tools
git add cli/okf-cli.py cli/test_okf_cli.py
git commit -m "fix(cli): prime defaults to compact bundle listing, --full keeps detail"
```

---

### Task 3: Re-measure against the real catalogue + close the bean

**Files:**
- None modified — verification only.

- [ ] **Step 1: Run the full test suite, confirm no new failures**

Run: `cd /Users/erik/dev/okf-tools && python3 -m unittest discover -s cli -v 2>&1 | tail -30`
Expected: same pre-existing 19 failures/2 errors as before this plan (per `docs/SSTD.md`, 2026-07-18) — no new ones. If the count changed, stop and investigate before continuing.

- [ ] **Step 2: Re-measure `prime` against the real catalogue**

Run:
```bash
cd /Users/erik/dev/okf-tools
python3 cli/okf-cli.py --root ~/Obsidian/Knowledge-Catalogue prime | wc -l
python3 cli/okf-cli.py --root ~/Obsidian/Knowledge-Catalogue prime | wc -c
python3 cli/okf-cli.py --root ~/Obsidian/Knowledge-Catalogue prime --full | wc -l
```
Expected: default line count drops from 268 to roughly 90-100 (69-line guide + ~21 one-line bundle entries + separators); `--full` line count unchanged at 310 (behavior preserved).

- [ ] **Step 3: Commit the measurement as bean evidence, close the bean**

```bash
cd /Users/erik/dev/okf-tools
beans update okf-cli-dwcq -s completed --body-append "## Summary of Changes

Default \`prime\` bundle listing is now compact (name + concept count), matching
render_bundle_line. --full is unchanged (full per-bundle blocks). Measured against
~/Obsidian/Knowledge-Catalogue: default output dropped from 268 to <N> lines
(13.5KB to <N>KB). cmd_index is untouched — still the place for full per-bundle
browsing."
git add .
git commit -m "docs(sstd): prime progressive-disclosure fix verified"
```

(Fill in `<N>` with the actual numbers from Step 2 before running.)

---

## Design note (not a task — context for the implementer)

`beans prime` was used as a reference point: it is a **static** onboarding doc (189 lines, fixed size) — it never dumps live bean data inline; that stays behind `beans list`/`beans show`. `okf-cli prime` mixed a static guide with a dynamic per-bundle data dump that grows with catalogue size. The user explicitly chose to **keep** the bundle listing in `prime` (rejecting the "drop it entirely, point only at `index`" option) but wants it compact — hence `render_bundle_line` instead of removing the listing.
