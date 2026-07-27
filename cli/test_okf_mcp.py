#!/usr/bin/env python3
"""Integration tests at the MCP -> subprocess boundary (T09 / okf-cli-asky).

test_okf_cli.py loads okf-cli.py via importlib and calls functions directly
(test_okf_cli.py:6-13) — it can never catch a B01-class break, which lives in
argv marshalling across the process boundary (build_argv -> subprocess.run ->
json.loads). These tests instead drive okf_mcp.run_okf, which shells out to
the REAL cli/okf-cli.py, exactly as the MCP server does.

Run: python3 -m unittest cli.test_okf_mcp -v
"""
import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "okf_mcp", os.path.join(_HERE, "..", "mcp", "okf_mcp.py"))
mcp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mcp)


def _w(root, rel, text):
    ap = os.path.join(root, rel)
    os.makedirs(os.path.dirname(ap), exist_ok=True)
    with open(ap, "w", encoding="utf-8") as f:
        f.write(text)


def _make_tmp_catalogue():
    """A tiny two-concept catalogue on real disk — the MCP boundary talks to
    a real subprocess, so it needs a real root, not an in-memory fixture."""
    root = tempfile.mkdtemp()
    _w(root, "b/one.md",
       "---\ntype: Runbook\ntitle: One\ndescription: first\ntags: [alpha]\n"
       "---\n# One\n")
    _w(root, "b/two.md",
       "---\ntype: Runbook\ntitle: Two\ndescription: second\ntags: [beta]\n"
       "---\n# Two\n")
    _w(root, "b/index.md", "# B\n\nSee [One](one.md).\n")
    return root


class McpBoundaryTestBase(unittest.TestCase):
    """setUp/tearDown shared by both boundary suites: real tmp catalogue,
    OKF_CLI pinned to this worktree's cli/okf-cli.py.

    okf_mcp.OKF_CLI is bound from os.environ at IMPORT time (module-level
    global in mcp/okf_mcp.py) and read as a plain global inside
    run_okf() -- it is never re-read from os.environ afterwards. Since this
    module's import (above) already ran before any setUp, setting
    os.environ["OKF_CLI"] here would be a no-op. Patch the module attribute
    directly instead."""

    def setUp(self):
        self.root = _make_tmp_catalogue()
        self._prev_okf_cli = mcp.OKF_CLI
        mcp.OKF_CLI = os.path.join(_HERE, "okf-cli.py")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)
        mcp.OKF_CLI = self._prev_okf_cli


class McpIndexListBoundary(McpBoundaryTestBase):
    """SC-001: run_okf(root, "index"/"list", ...) over the real subprocess
    returns parsed JSON without raising — the exact B01 failure, now guarded."""

    def test_list_json_over_subprocess(self):
        out = mcp.run_okf(self.root, "list", {"type": "Runbook"})
        self.assertIsInstance(out, list)
        self.assertEqual(len(out), 2)

    def test_list_json_filters_by_type(self):
        out = mcp.run_okf(self.root, "list", {"type": "Nope"})
        self.assertEqual(out, [])

    def test_index_json_over_subprocess_no_bundle(self):
        out = mcp.run_okf(self.root, "index", {"bundle": ""})
        self.assertIsInstance(out, dict)
        self.assertIn("bundles", out)

    def test_index_json_over_subprocess_with_bundle(self):
        out = mcp.run_okf(self.root, "index", {"bundle": "b"})
        self.assertIsInstance(out, dict)
        self.assertEqual(out["bundle"], "b")
        self.assertEqual(len(out["concepts"]), 2)


class McpCheckRefsBoundary(McpBoundaryTestBase):
    """SC-002: check + refs (already --json-valid pre-P1) locked at the
    subprocess boundary too, so the whole supports_json=True surface
    (index, list, check, refs) is guarded end-to-end."""

    def test_check_json_over_subprocess(self):
        out = mcp.run_okf(self.root, "check", {"target": ""})
        self.assertIsInstance(out, dict)
        self.assertIn("errors", out)
        self.assertIn("warnings", out)

    def test_refs_json_over_subprocess(self):
        out = mcp.run_okf(
            self.root, "refs", {"path": "b/one.md", "scan_root": self.root})
        self.assertIsInstance(out, dict)
        self.assertEqual(out["target"], "b/one.md")
        self.assertEqual([h["source"] for h in out["inbound"]], ["b/index.md"])


class BuildArgvBundlePositionalGuard(unittest.TestCase):
    """P8/8a (okf-cli-8uaf, SC-004) — a _FLAGS key must NOT resurface as an
    extra flag for commands where that key is already a POSITIONAL param
    name (index's "bundle"). build_argv must skip a _FLAGS key when it is
    also in that command's positional list. (find's own "bundle" --scope
    alias was removed D02, PO-grilling 2026-07-26 — this guard now only
    concerns index's positional.)"""

    def test_index_bundle_stays_positional_only(self):
        argv = mcp.build_argv("/root", "index", {"bundle": "b"})
        self.assertEqual(argv, ["--root", "/root", "index", "b", "--json"])
        self.assertNotIn("--bundle", argv)


class McpFindFilterBoundary(McpBoundaryTestBase):
    """P8/8a (okf-cli-8uaf, SC-004) — okf_find exposes type/tag/scope;
    _FLAGS marshals all three across the real subprocess boundary. A second
    bundle sharing the query token proves the filter actually excludes
    (not a silent no-op, per the bean's B01-class warning)."""

    def setUp(self):
        super().setUp()
        _w(self.root, "other/dupe.md",
           "---\ntype: Runbook\ntitle: Dupe\ndescription: third\ntags: [gamma]\n"
           "---\n# Dupe\n\nalpha shared token.\n")

    def test_find_scope_reaches_cli_over_subprocess(self):
        out = mcp.run_okf(self.root, "find", {"query": "alpha", "scope": "b"})
        self.assertIn("path: b/one", out)
        self.assertNotIn("path: other/dupe", out)

    def test_find_type_and_tag_reach_cli_over_subprocess(self):
        out = mcp.run_okf(
            self.root, "find", {"query": "one two", "type": "Runbook", "tag": "alpha"})
        self.assertIn("path: b/one", out)
        self.assertNotIn("path: b/two", out)

    def test_index_with_bundle_still_works_after_flags_change(self):
        # Regression guard for the positional-collision fix above.
        out = mcp.run_okf(self.root, "index", {"bundle": "b"})
        self.assertEqual(out["bundle"], "b")


class McpTagsBoundary(McpBoundaryTestBase):
    """SC-001 (okf-cli-x0l7): okf_tags registered + runs over subprocess —
    both full audit-dump mode (empty query) and fuzzy candidate-search mode."""

    def test_tags_full_dump_over_subprocess(self):
        out = mcp.run_okf(self.root, "tags", {"query": ""})
        self.assertIn("alpha", out)
        self.assertIn("beta", out)

    def test_tags_query_over_subprocess(self):
        out = mcp.run_okf(self.root, "tags", {"query": "alph"})
        self.assertIn("== searched: alph ==", out)
        self.assertIn("alpha", out)


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


class McpFindDegradationNoteBoundary(McpBoundaryTestBase):
    """SC-01 (okf-cli-2o39, D01): a degradation note the CLI writes to stderr
    on a non-JSON command must reach the MCP caller, prepended to stdout.
    The fresh catalogue from setUp has no .fts/fts.sqlite yet, so `find`
    degrades to the substring scan and prints the "absent" note."""

    def test_find_returns_absent_note_ahead_of_stdout(self):
        out = mcp.run_okf(self.root, "find", {"query": "one"})
        self.assertIn("note: lexical index absent", out)
        self.assertIn("path: b/one", out)
        self.assertLess(out.index("note:"), out.index("path: b/one"))


class McpJsonCommandParsesDespiteStderrNote(unittest.TestCase):
    """SC-02 (okf-cli-2o39, AC-03): a JSON-supporting command's return value
    must stay byte-identical (still json.loads-able, nothing from stderr
    mixed in) even when the CLI writes a note to stderr during that same
    call. No JSON-supporting command in the current CLI both exits 0 and
    writes to stderr (checked: cmd_check/cmd_list/cmd_index/cmd_refs emit
    nothing to stderr on a clean exit), so this pins the wrapper's own
    contract directly via a stubbed subprocess.run rather than relying on a
    real CLI code path that does not exist today — the guarantee must hold
    regardless of whether the CLI ever grows one."""

    def test_json_command_return_value_ignores_stderr_note(self):
        stub = subprocess.CompletedProcess(
            args=["python3", "okf-cli.py"], returncode=0,
            stdout='[{"title": "One"}]\n',
            stderr="note: some future degradation\n")
        # Patch the `mcp` module's OWN `subprocess` name binding, not the
        # real subprocess module (which fastmcp/other code also imports) —
        # keeps the stub scoped to this call.
        fake_subprocess = mock.Mock()
        fake_subprocess.run.return_value = stub
        with mock.patch.object(mcp, "subprocess", fake_subprocess):
            out = mcp.run_okf("/root", "list", {"type": "Runbook"})
        self.assertEqual(out, [{"title": "One"}])


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


class McpOutputCeiling(McpBoundaryTestBase):
    """okf-cli-7u5z (D02) — a result too large for any consumer must fail with
    guidance instead of being handed back. The catalogue-wide `index --json`
    reached 794 KB; the harness discarded the call, so the agent got nothing
    and no hint about what to do differently."""

    def setUp(self):
        super().setUp()
        self._prev_max = mcp.MAX_OUTPUT_CHARS
        mcp.MAX_OUTPUT_CHARS = 10

    def tearDown(self):
        mcp.MAX_OUTPUT_CHARS = self._prev_max
        super().tearDown()

    def test_oversized_result_raises_with_the_command_size_and_remedy(self):
        with self.assertRaises(RuntimeError) as ctx:
            mcp.run_okf(self.root, "index", {})
        msg = str(ctx.exception)
        self.assertIn("index", msg)
        self.assertIn("10", msg)
        self.assertIn("narrow", msg.lower())

    def test_result_within_budget_passes_through(self):
        mcp.MAX_OUTPUT_CHARS = 10_000_000
        out = mcp.run_okf(self.root, "index", {})
        self.assertIn("bundles", out)


class McpDefaultCliPath(unittest.TestCase):
    """The OKF_CLI fallback (no env override) must point at a CLI that exists.
    Every boundary suite patches mcp.OKF_CLI, so the fallback was uncovered --
    a repo move left it dangling at the old absolute path and every tool call
    died with ENOENT before reaching the CLI."""

    def test_default_resolves_next_to_this_repo(self):
        env = dict(os.environ)
        env.pop("OKF_CLI", None)
        spec = importlib.util.spec_from_file_location(
            "okf_mcp_fresh", os.path.join(_HERE, "..", "mcp", "okf_mcp.py"))
        fresh = importlib.util.module_from_spec(spec)
        with mock.patch.dict(os.environ, env, clear=True):
            spec.loader.exec_module(fresh)
        self.assertEqual(os.path.realpath(fresh.OKF_CLI),
                         os.path.realpath(os.path.join(_HERE, "okf-cli.py")))
        self.assertTrue(os.path.exists(fresh.OKF_CLI), fresh.OKF_CLI)


if __name__ == "__main__":
    unittest.main()
