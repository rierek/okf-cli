#!/usr/bin/env python3
"""Integration tests at the MCP -> subprocess boundary (T09 / okf-cli-asky).

The per-module test files import the cli/okf/ modules and call their functions
directly — they can never catch a B01-class break, which lives in argv
marshalling across the process boundary (build_argv -> subprocess.run ->
json.loads). These tests instead drive okf_mcp.run_okf, which shells out to
the REAL cli/okf-cli.py, exactly as the MCP server does.

Run: just test tests.test_okf_mcp -v
"""
import importlib.util
import inspect
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

_HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "cli")
if _HERE not in sys.path:  # cli/ holds the okf package
    sys.path.insert(0, _HERE)

from okf import parser as okf_parser
from tests.okf_testkit import uv_start_log

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


class McpStartsTheCliThroughUv(McpBoundaryTestBase):
    """R-11 — every okf_mcp call starts okf-cli as `uv run --script <OKF_CLI>`, so the PEP 723
    header of the script, not the Python on PATH, supplies the dependencies."""

    def test_run_okf_starts_the_cli_with_uv_run_script_and_the_OKF_CLI_path(self):
        calls = uv_start_log(self)
        self.assertIn("data", mcp.run_okf(self.root, "list", {"where": "type = Runbook"}))
        self.assertEqual(len(calls()), 1, calls())
        self.assertTrue(calls()[0].startswith("run --script {} --root {} list".format(mcp.OKF_CLI, self.root)),
                        calls()[0])


class McpIndexListBoundary(McpBoundaryTestBase):
    """SC-001: run_okf(root, "index"/"list", ...) over the real subprocess
    returns parsed JSON without raising — the exact B01 failure, now guarded."""

    def test_list_json_over_subprocess(self):
        out = mcp.run_okf(self.root, "list", {"where": "type = Runbook"})["data"]
        self.assertIsInstance(out, list)
        self.assertEqual(len(out), 2)

    def test_list_json_filters_by_type(self):
        out = mcp.run_okf(self.root, "list", {"where": "type = Nope"})["data"]
        self.assertEqual(out, [])

    def test_index_json_over_subprocess_no_bundle(self):
        out = mcp.run_okf(self.root, "index", {"bundle": ""})
        self.assertEqual(list(out), ["data", "warnings"])
        self.assertIn("bundles", out["data"])

    def test_index_json_over_subprocess_with_bundle(self):
        out = mcp.run_okf(self.root, "index", {"bundle": "b"})["data"]
        self.assertIsInstance(out, dict)
        self.assertEqual(out["bundle"], "b")
        self.assertEqual(len(out["concepts"]), 2)

    def test_index_json_over_subprocess_no_bundle_defaults_to_compact(self):
        """okf-cli-t2w8 SC-002 — the MCP surface offers the same
        compact/full split `index` does: bundle+description by default,
        no concepts/directories keys without full=True."""
        out = mcp.run_okf(self.root, "index", {"bundle": ""})["data"]
        entry = out["bundles"][0]
        self.assertNotIn("concepts", entry)
        self.assertNotIn("directories", entry)

    def test_index_json_over_subprocess_no_bundle_full_includes_concepts(self):
        out = mcp.run_okf(self.root, "index", {"bundle": "", "full": True})["data"]
        entry = out["bundles"][0]
        self.assertEqual(entry["concepts"], 2)
        self.assertIn("directories", entry)


class McpCheckRefsBoundary(McpBoundaryTestBase):
    """SC-002: check + refs locked at the subprocess boundary too, so every
    structured tool (index, list, check, refs) is guarded end-to-end."""

    def test_check_json_over_subprocess(self):
        out = mcp.run_okf(self.root, "check", {"target": ""})
        self.assertEqual(list(out), ["data", "warnings"])
        self.assertEqual(list(out["data"]), ["findings"])

    def test_refs_json_over_subprocess(self):
        out = mcp.run_okf(
            self.root, "refs", {"path": "b/one.md", "scan_root": self.root})["data"]
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


class BuildArgvIndexFullFlag(unittest.TestCase):
    """okf-cli-t2w8 SC-002 — `full` marshals to --full on `index` only,
    scoped to `index` alone."""

    def test_full_true_adds_the_flag(self):
        argv = mcp.build_argv("/root", "index", {"bundle": "", "full": True})
        self.assertIn("--full", argv)

    def test_full_false_omits_the_flag(self):
        argv = mcp.build_argv("/root", "index", {"bundle": ""})
        self.assertNotIn("--full", argv)


class McpFindFilterBoundary(McpBoundaryTestBase):
    """OKFT-iy9n — okf_find and okf_list expose `where`; _FLAGS marshals it across the real
    subprocess boundary. A second bundle sharing the query token proves the filter actually
    excludes (not a silent no-op, per the bean's B01-class warning)."""

    def setUp(self):
        super().setUp()
        _w(self.root, "other/dupe.md",
           "---\ntype: Runbook\ntitle: Dupe\ndescription: third\ntags: [gamma]\n"
           "---\n# Dupe\n\nalpha shared token.\n")

    def test_find_where_path_reaches_cli_over_subprocess(self):
        out = mcp.run_okf(self.root, "find", {"query": "alpha", "where": "path ~ b/"})["data"]
        paths = [h["path"] for h in out["hits"]]
        self.assertIn("b/one", paths)
        self.assertNotIn("other/dupe", paths)

    def test_find_where_type_and_tag_reach_cli_over_subprocess(self):
        out = mcp.run_okf(self.root, "find", {
            "query": "one two", "where": "type = Runbook and tag = alpha"})["data"]
        paths = [h["path"] for h in out["hits"]]
        self.assertIn("b/one", paths)
        self.assertNotIn("b/two", paths)

    def test_list_where_returns_the_concepts_the_expression_selects(self):
        out = mcp.run_okf(self.root, "list", {"where": "type = Runbook and tag = beta"})["data"]
        self.assertEqual([r["path"] for r in out], ["b/two"])

    def test_a_malformed_where_reaches_the_caller_as_the_invalid_input_error(self):
        for command, params in (("find", {"query": "alpha"}), ("list", {})):
            with self.subTest(command=command):
                with self.assertRaises(RuntimeError) as caught:
                    mcp.run_okf(self.root, command, dict(params, where="type ="))
                self.assertIn("invalid_input", str(caught.exception))
                self.assertIn("--where", str(caught.exception))

    def test_index_with_bundle_still_works_after_flags_change(self):
        # Regression guard for the positional-collision fix above.
        out = mcp.run_okf(self.root, "index", {"bundle": "b"})["data"]
        self.assertEqual(out["bundle"], "b")


class McpTagsBoundary(McpBoundaryTestBase):
    """SC-001 (okf-cli-x0l7): okf_tags registered + runs over subprocess —
    both full audit-dump mode (empty query) and fuzzy candidate-search mode."""

    def test_tags_full_dump_over_subprocess(self):
        out = mcp.run_okf(self.root, "tags", {"query": ""})["data"]
        self.assertEqual([t["tag"] for t in out["tags"]], ["alpha", "beta"])

    def test_tags_query_over_subprocess(self):
        out = mcp.run_okf(self.root, "tags", {"query": "alph"})["data"]
        self.assertEqual(out["searches"][0]["query"], "alph")
        self.assertIn("alpha", [m["tag"] for m in out["searches"][0]["matches"]])


class McpAgentRemedyBoundary(McpBoundaryTestBase):
    """The remedy find prescribes must be executable by the audience it
    addresses (okf-cli-4ws6)."""

    def test_build_index_reaches_the_cli_and_writes_the_index(self):
        out = mcp.run_okf(self.root, "build-index", {})
        db = os.path.join(self.root, ".fts", "fts.sqlite")
        self.assertTrue(os.path.exists(db))
        self.assertEqual((out["data"]["applied"], out["data"]["path"]), (True, db))

    def test_prime_reaches_the_cli(self):
        self.assertTrue(mcp.run_okf(self.root, "prime", {})["data"]["guide"].strip())

    def test_info_reaches_the_cli(self):
        files = mcp.run_okf(self.root, "info", {})["data"]["files"]
        self.assertEqual([f["name"] for f in files], ["TYPES.md", "PROPERTIES.md"])

    def test_build_semantic_index_reaches_the_cli_and_degrades_without_key(self):
        """OKFT-wsne. Real subprocess -> real CLI, same as
        test_build_index_reaches_the_cli_and_writes_the_index above, but
        VOYAGE_API_KEY is popped for the call so this never makes a network
        call regardless of what the host environment carries — the CLI's
        own degradation note (D01) must still reach this tool's return
        value, exit 0, no raise."""
        saved = os.environ.pop("VOYAGE_API_KEY", None)
        try:
            out = mcp.run_okf(self.root, "build-semantic-index", {})
        finally:
            if saved is not None:
                os.environ["VOYAGE_API_KEY"] = saved
        self.assertEqual(out["data"], {"applied": False, "embedded": 0, "path": os.path.join(
            self.root, ".tagvec", "tag_vectors.sqlite")})
        (warning,) = [w for w in out["warnings"] if "semantic index build skipped" in w]
        self.assertIn("VOYAGE_API_KEY", warning)


class McpFindDegradationNoteBoundary(McpBoundaryTestBase):
    """SC-01 (okf-cli-2o39, D01): a degradation note of the CLI reaches the MCP caller as an entry
    of `warnings`, next to the hits in `data`. The fresh catalogue from setUp has no
    .fts/fts.sqlite yet, so `find` degrades to the substring scan and notes the missing index."""

    def test_find_returns_the_absent_note_as_a_warning(self):
        out = mcp.run_okf(self.root, "find", {"query": "one"})
        self.assertTrue(any("lexical index absent" in w for w in out["warnings"]), out["warnings"])
        self.assertIn("b/one", [h["path"] for h in out["data"]["hits"]])


class McpJsonCommandIgnoresStderr(unittest.TestCase):
    """SC-02 (okf-cli-2o39, AC-03): the return value is built from the envelope alone. A note
    on stderr during the same call, which the CLI no longer writes in envelope mode, never mixes
    in. This pins the wrapper's own contract through a stubbed subprocess.run."""

    def test_json_command_return_value_ignores_stderr_note(self):
        stub = subprocess.CompletedProcess(
            args=["python3", "okf-cli.py"], returncode=0,
            stdout='{"command": "list", "ok": true, "data": [{"title": "One"}], '
                   '"warnings": [], "error": null}\n',
            stderr="note: some future degradation\n")
        # Patch the `mcp` module's OWN `subprocess` name binding, not the
        # real subprocess module (which fastmcp/other code also imports) —
        # keeps the stub scoped to this call.
        fake_subprocess = mock.Mock()
        fake_subprocess.run.return_value = stub
        with mock.patch.object(mcp, "subprocess", fake_subprocess):
            out = mcp.run_okf("/root", "list", {"where": "type = Runbook"})
        self.assertEqual(out, {"data": [{"title": "One"}], "warnings": []})


class McpSurfaceParity(unittest.TestCase):
    """Every whitelisted MCP command is a real CLI command. Catches a typo or
    a command renamed on one side only — the drift class of okf-cli-4ws6."""

    def test_whitelist_only_names_real_cli_commands(self):
        unknown = sorted(set(mcp._COMMANDS) - set(okf_parser.COMMAND_DISPATCH))
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
        self.assertIn("bundles", out["data"])


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


class _ToolCollector:
    """Minimal stand-in for the FastMCP server object. _register() only ever
    calls server.tool() as a decorator factory and returns the server, so
    collecting the decorated functions is enough to call a tool exactly as the
    MCP runtime would — without importing fastmcp, which is not a dependency of
    this repository."""

    def __init__(self):
        self.tools = {}

    def tool(self):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn
        return deco


class McpWikilinksSurface(unittest.TestCase):
    """REQ-15 — the wikilinks verb is reachable from an agent. A command absent
    from _COMMANDS is invisible to MCP no matter how well the CLI implements
    it, and a boolean flag absent from _BOOL_FLAGS is silently dropped."""

    def test_command_is_whitelisted_with_target(self):
        self.assertEqual(mcp._COMMANDS["wikilinks"], ["target"])

    def test_unresolved_flag_is_marshalled(self):
        with_flag = mcp.build_argv("/root", "wikilinks",
                                   {"target": "b", "unresolved": True})
        self.assertEqual(with_flag,
                         ["--root", "/root", "wikilinks", "b", "--unresolved", "--json"])
        without = mcp.build_argv("/root", "wikilinks",
                                 {"target": "b", "unresolved": False})
        self.assertNotIn("--unresolved", without)


class McpPrimeIsCompact(unittest.TestCase):
    """okf-cli, 2026-08-05 — okf_prime is a session-start call, and the tool
    result lands in the agent's context whole. It takes the compact rendering
    for the same reason the `just -g start` recipe does; the long form stays
    reachable from the CLI. A boolean absent from _BOOL_FLAGS is silently
    dropped, so the marshalling is asserted, not the intent."""

    def test_compact_is_marshalled_onto_the_prime_call(self):
        self.assertEqual(mcp.build_argv("/root", "prime", {"compact": True}),
                         ["--root", "/root", "prime", "--compact", "--json"])

    def test_the_registered_tool_asks_for_compact(self):
        argvs = []
        real = mcp.run_okf

        def spy(root, command, params):
            argvs.append(mcp.build_argv(root, command, params))
            return ""
        mcp.run_okf = spy
        try:
            mcp._register(_ToolCollector()).tools["okf_prime"]("/root")
        finally:
            mcp.run_okf = real
        self.assertEqual(argvs, [["--root", "/root", "prime", "--compact", "--json"]])


class McpOptionalRoot(unittest.TestCase):
    """okf-cli worktree bug — every MCP tool now defaults `root` to "" so a
    session whose cwd is a linked worktree (never a hull layout's own
    catalogue root) can omit it and let okf-cli auto-detect from cwd
    instead of the caller guessing wrong path arithmetic. build_argv is the
    single point deciding whether `--root` reaches the CLI at all."""

    def test_falsy_root_omits_the_root_flag(self):
        argv = mcp.build_argv("", "prime", {"compact": True})
        self.assertNotIn("--root", argv)
        self.assertEqual(argv, ["prime", "--compact", "--json"])

    def test_truthy_root_still_emits_the_root_flag(self):
        argv = mcp.build_argv("/x", "prime", {"compact": True})
        self.assertEqual(argv, ["--root", "/x", "prime", "--compact", "--json"])

    def test_registered_tool_called_with_no_args_omits_root(self):
        # build_argv alone does not guard the 15 tool SIGNATURES — if
        # `root` were ever restored as a required positional there, this
        # is what would catch it (build_argv's own unit tests cannot).
        argvs = []
        real = mcp.run_okf

        def spy(root, command, params):
            argvs.append(mcp.build_argv(root, command, params))
            return ""
        mcp.run_okf = spy
        try:
            mcp._register(_ToolCollector()).tools["okf_prime"]()
        finally:
            mcp.run_okf = real
        self.assertNotIn("--root", argvs[0])


class McpToolSignatureContract(unittest.TestCase):
    """FastMCP translates a keyword-only parameter without a default into
    JSON-Schema `required`, and a parameter with a default into optional
    (verified once against the real library — okf-cli-z69p). Runs against a
    stand-in tool collector, unlike a FastMCP-backed check, so it passes
    without `mcp` installed; `just test` adds `mcp` only for the tests that
    need the real library."""

    REQUIRED_KEYWORD_ONLY = {
        "okf_find": {"query"},
        "okf_ctx_show": {"slug"},
        "okf_read": {"path"},
        "okf_toc": {"path"},
        "okf_reindex": {"target"},
        "okf_refs": {"path"},
        "okf_rename": {"old", "new"},
    }

    def _tools(self):
        return mcp._register(_ToolCollector()).tools

    def test_root_always_has_a_default(self):
        for name, fn in self._tools().items():
            root_param = inspect.signature(fn).parameters["root"]
            self.assertIsNot(root_param.default, inspect.Parameter.empty, name)

    def test_genuinely_required_params_are_keyword_only_without_a_default(self):
        for name, required in self.REQUIRED_KEYWORD_ONLY.items():
            params = inspect.signature(self._tools()[name]).parameters
            for param_name in required:
                p = params[param_name]
                self.assertIs(p.kind, inspect.Parameter.KEYWORD_ONLY,
                               "{}.{}".format(name, param_name))
                self.assertIs(p.default, inspect.Parameter.empty,
                               "{}.{}".format(name, param_name))


class McpWhereParameter(unittest.TestCase):
    """OKFT-iy9n — `where` is the one filter parameter: a string on okf_find and okf_list that
    reaches okf-cli as `--where`; the four removed parameters exist nowhere on the surface."""

    REMOVED = ("type", "tag", "scope", "include_archive")

    def tools(self):
        return mcp._register(_ToolCollector()).tools

    def test_where_marshals_to_the_flag_when_set_and_is_omitted_when_empty(self):
        self.assertEqual(mcp.build_argv("/root", "list", {"where": "type = Runbook"}),
                         ["--root", "/root", "list", "--where", "type = Runbook", "--json"])
        self.assertEqual(mcp.build_argv("/root", "find", {"query": "q", "where": "tag = a or tag = b"}),
                         ["--root", "/root", "find", "q", "--where", "tag = a or tag = b", "--json"])
        for empty in ("", None):
            self.assertNotIn("--where", mcp.build_argv("/root", "list", {"where": empty}))

    def test_a_removed_parameter_marshals_to_no_flag(self):
        for command in ("find", "list"):
            for key in self.REMOVED:
                with self.subTest(command=command, key=key):
                    argv = mcp.build_argv("/root", command, {"query": "q", key: "x" if key != "include_archive" else True})
                    self.assertEqual(argv, mcp.build_argv("/root", command, {"query": "q"}))

    def test_find_and_list_accept_where(self):
        for name in ("okf_find", "okf_list"):
            params = inspect.signature(self.tools()[name]).parameters
            with self.subTest(tool=name):
                self.assertIn("where", params)
                self.assertIs(params["where"].annotation, str)
                self.assertEqual(params["where"].default, "")

    def test_no_tool_takes_a_removed_parameter(self):
        for name, fn in self.tools().items():
            with self.subTest(tool=name):
                self.assertEqual(set(self.REMOVED) & set(inspect.signature(fn).parameters), set())

    def test_find_and_list_forward_where_to_run_okf(self):
        calls = []
        real = mcp.run_okf
        mcp.run_okf = lambda root, command, params: calls.append((command, params)) or {}
        try:
            self.tools()["okf_find"]("/root", query="q", where="type = A")
            self.tools()["okf_list"]("/root", where="type = B")
        finally:
            mcp.run_okf = real
        self.assertEqual([(c, p.get("where")) for c, p in calls], [("find", "type = A"), ("list", "type = B")])

    def test_docstrings_and_the_budget_hint_name_where_with_an_example_and_no_removed_parameter(self):
        texts = {name: self.tools()[name].__doc__ for name in ("okf_find", "okf_list")}
        mcp.MAX_OUTPUT_CHARS, saved = 10, mcp.MAX_OUTPUT_CHARS
        try:
            catalogue = tempfile.mkdtemp()
            try:
                with self.assertRaises(RuntimeError) as caught:
                    mcp.run_okf(catalogue, "index", {})
                texts["budget hint"] = str(caught.exception)
            finally:
                shutil.rmtree(catalogue, ignore_errors=True)
        finally:
            mcp.MAX_OUTPUT_CHARS = saved
        for name, text in texts.items():
            with self.subTest(text=name):
                self.assertIn("where", text)
                self.assertRegex(text, r"where[= ]*[\"'`]?\w+ ?[=~] ?\w+")
                self.assertNotRegex(text, r"include_archive|\b(type|tag|scope)=|--(type|tag|scope|include-archive)\b")


class McpWikilinksBoundary(McpBoundaryTestBase):
    """REQ-15 / AC-15.3 — the registered tool function, driven over the real
    subprocess, returns the REQ-08 object."""

    def setUp(self):
        super().setUp()
        _w(self.root, "b/three.md",
           "---\ntype: Runbook\ntitle: Three\ndescription: third\n---\n"
           "Resolves to [[one]], breaks on [[ghost]].\n")

    def _tool(self, name):
        return mcp._register(_ToolCollector()).tools[name]

    def test_okf_wikilinks_returns_links_and_by_bundle(self):
        out = self._tool("okf_wikilinks")(root=self.root)["data"]
        self.assertIsInstance(out, dict)
        self.assertIn("links", out)
        self.assertIn("by_bundle", out)
        self.assertEqual(
            {(l["page"], l["status"]) for l in out["links"]},
            {("one", "resolved"), ("ghost", "unresolved")})

    def test_okf_wikilinks_unresolved_filter_reaches_the_cli(self):
        out = self._tool("okf_wikilinks")(root=self.root, unresolved=True)["data"]
        self.assertEqual([l["page"] for l in out["links"]], ["ghost"])

    def test_okf_wikilinks_target_scopes_the_scan(self):
        _w(self.root, "other/x.md", "---\ntype: Runbook\n---\nSee [[phantom]].\n")
        out = self._tool("okf_wikilinks")(root=self.root, target="other")["data"]
        self.assertEqual(sorted(out["by_bundle"]), ["other"])


class McpCtxBoundary(McpBoundaryTestBase):
    """OKFT-eyhm — okf_ctx_list / okf_ctx_show over the real CLI."""

    def _ctx_create(self, slug, *paths):
        subprocess.run([sys.executable, mcp.OKF_CLI, "--root", self.root, "ctx",
                        "create", slug, *paths], check=True, capture_output=True)

    def _tool(self, name):
        return mcp._register(_ToolCollector()).tools[name]

    def test_list_and_show_on_one_ctx(self):
        self._ctx_create("alpha", "b/one.md", "b/two.md")
        listed = self._tool("okf_ctx_list")(root=self.root)["data"]
        self.assertEqual([c["slug"] for c in listed], ["alpha"])
        self.assertIn("entries", listed[0])
        shown = self._tool("okf_ctx_show")(root=self.root, slug="alpha")
        self.assertNotIn("error", shown)
        self.assertEqual([e["path"] for e in shown["data"]["entries"]],
                         ["b/one.md", "b/two.md"])

    def test_show_dead_entry_returns_object_with_dead_count(self):
        self._ctx_create("alpha", "b/one.md", "b/two.md")
        os.remove(os.path.join(self.root, "b/two.md"))
        shown = self._tool("okf_ctx_show")(root=self.root, slug="alpha")
        self.assertGreater(shown["data"]["dead"], 0)
        self.assertEqual((shown["error"]["kind"], shown["error"]["code"]), ("non_conformant", 4))

    def test_show_unknown_slug_raises_with_cli_stderr(self):
        with self.assertRaises(RuntimeError) as cm:
            self._tool("okf_ctx_show")(root=self.root, slug="nope")
        self.assertIn("ctx: unknown slug: nope", str(cm.exception))

    def test_list_for_path_limits_to_bundles_listing_the_file(self):
        self._ctx_create("alpha", "b/one.md")
        self._ctx_create("beta", "b/two.md")
        out = self._tool("okf_ctx_list")(root=self.root, for_path="b/one.md")["data"]
        self.assertEqual([c["slug"] for c in out], ["alpha"])

    def test_check_on_a_missing_target_raises_with_the_envelope_error(self):
        with self.assertRaises(RuntimeError) as cm:
            mcp.run_okf(self.root, "check", {"target": "nonexist"})
        self.assertIn("not_found", str(cm.exception))
        self.assertIn("not a directory: nonexist", str(cm.exception))

    def test_check_with_violations_returns_the_findings_with_the_error(self):
        _w(self.root, "b/bad.md", "no frontmatter\n")
        out = mcp.run_okf(self.root, "check", {})
        self.assertIn(("okf/frontmatter/parseable", "b/bad.md"),
                      [(f["rule"], f["path"]) for f in out["data"]["findings"]])
        self.assertEqual((out["error"]["kind"], out["error"]["code"]), ("non_conformant", 4))


class McpEnvelopeHandling(unittest.TestCase):
    """The wrapper decides from the CLI's one envelope, never from the exit code: `ok` returns
    {data, warnings}; a failure that still carries a result returns it with `error`; a failure
    without a result, or stdout that is no envelope, raises. Stubbed subprocess: the `mcp`
    module's own binding is patched, as the other stub tests do."""

    @staticmethod
    def envelope(ok, data, kind="", code=0, message="", warnings=()):
        error = None if ok else {"kind": kind, "code": code, "message": message}
        return json.dumps({"command": "x", "ok": ok, "data": data, "warnings": list(warnings),
                           "error": error}) + "\n"

    def _run(self, command, returncode, stdout="", stderr=""):
        stub = subprocess.CompletedProcess(
            args=["python3", "okf-cli.py"], returncode=returncode,
            stdout=stdout, stderr=stderr)
        fake_subprocess = mock.Mock()
        fake_subprocess.run.return_value = stub
        with mock.patch.object(mcp, "subprocess", fake_subprocess):
            return mcp.run_okf("/root", command, {})

    def test_success_returns_data_and_warnings_only(self):
        out = self._run("list", 0, stdout=self.envelope(True, [1], warnings=["a note"]))
        self.assertEqual(out, {"data": [1], "warnings": ["a note"]})

    def test_a_failure_with_a_result_returns_data_warnings_and_error(self):
        for command, kind, code, data in (("check", "non_conformant", 4, {"findings": [1]}),
                                          ("sync-status", "drift", 5, {"blocks": []}),
                                          ("ctx", "non_conformant", 4, {"dead": 1})):
            with self.subTest(command=command):
                out = self._run(command, code, stdout=self.envelope(
                    False, data, kind, code, "m", warnings=["w"]))
                self.assertEqual(out, {"data": data, "warnings": ["w"],
                                       "error": {"kind": kind, "code": code, "message": "m"}})

    def test_a_failure_without_a_result_raises_with_the_envelope_error(self):
        for kind, code in (("internal", 1), ("invalid_input", 2), ("not_found", 3), ("drift", 5)):
            with self.subTest(kind=kind):
                with self.assertRaises(RuntimeError) as cm:
                    self._run("find", code, stdout=self.envelope(False, None, kind, code, "the reason"),
                              stderr="boom")
                self.assertIn("the reason", str(cm.exception))
                self.assertIn(kind, str(cm.exception))
                self.assertNotIn("boom", str(cm.exception))

    def test_the_exit_code_is_never_read(self):
        self.assertEqual(self._run("check", 5, stdout=self.envelope(True, {"findings": []})),
                         {"data": {"findings": []}, "warnings": []})
        out = self._run("check", 0, stdout=self.envelope(False, {"findings": [1]}, "non_conformant", 4, ""))
        self.assertEqual(out["error"]["kind"], "non_conformant")

    def test_stdout_that_is_no_envelope_raises_with_exit_code_and_stderr(self):
        for stdout in ("", "partial", "[1]", '{"ok": true}', "null"):
            with self.subTest(stdout=stdout):
                with self.assertRaises(RuntimeError) as cm:
                    self._run("find", 2, stdout=stdout, stderr="usage: boom")
                self.assertIn("did not print one JSON envelope", str(cm.exception))
                self.assertIn("exit 2", str(cm.exception))
                self.assertIn("usage: boom", str(cm.exception))


class McpBuildSemanticIndexSurface(unittest.TestCase):
    """OKFT-wsne — okf_build_semantic_index is analog to okf_build_index:
    whitelisted with no positional/flag params, wired straight through to
    run_okf. No real subprocess here (that boundary is covered by
    McpAgentRemedyBoundary above); this class only pins the wiring."""

    def test_command_is_whitelisted_with_no_positionals(self):
        self.assertEqual(mcp._COMMANDS["build-semantic-index"], [])

    def test_the_registered_tool_reaches_run_okf_with_no_extra_params(self):
        argvs = []
        real = mcp.run_okf

        def spy(root, command, params):
            argvs.append(mcp.build_argv(root, command, params))
            return ""
        mcp.run_okf = spy
        try:
            mcp._register(_ToolCollector()).tools["okf_build_semantic_index"]("/root")
        finally:
            mcp.run_okf = real
        self.assertEqual(
            argvs, [["--root", "/root", "build-semantic-index", "--json"]])


class McpReadTargeted(McpBoundaryTestBase):
    """OKFT-0kcz (R-08 part 1) — okf_read passes section, frontmatter_only and
    body_only to the CLI's read; the two booleans exist for read alone."""

    def _read_argv(self, **kw):
        argvs = []
        real = mcp.run_okf

        def spy(root, command, params):
            argvs.append(mcp.build_argv(root, command, params))
            return ""
        mcp.run_okf = spy
        try:
            mcp._register(_ToolCollector()).tools["okf_read"]("/root", path="b/one", **kw)
        finally:
            mcp.run_okf = real
        return argvs[0]

    def test_section_builds_the_section_option(self):
        self.assertEqual(self._read_argv(section="Alpha > Deep"),
                         ["--root", "/root", "read", "b/one", "--section", "Alpha > Deep", "--json"])

    def test_frontmatter_only_builds_the_flag(self):
        self.assertEqual(self._read_argv(frontmatter_only=True),
                         ["--root", "/root", "read", "b/one", "--frontmatter-only", "--json"])

    def test_body_only_builds_the_flag(self):
        self.assertEqual(self._read_argv(body_only=True),
                         ["--root", "/root", "read", "b/one", "--body-only", "--json"])

    def test_none_set_builds_the_plain_argv(self):
        self.assertEqual(self._read_argv(), ["--root", "/root", "read", "b/one", "--json"])

    def test_no_other_command_emits_either_boolean_flag(self):
        others = sorted(set(mcp._COMMANDS) - {"read"})
        self.assertTrue(others)
        for command in others:
            argv = mcp.build_argv("/root", command,
                                  {"frontmatter_only": True, "body_only": True})
            for flag in ("--frontmatter-only", "--body-only"):
                self.assertNotIn(flag, argv, "command {!r} must never emit {}".format(command, flag))

    def test_path_stays_the_only_required_parameter(self):
        params = inspect.signature(mcp._register(_ToolCollector()).tools["okf_read"]).parameters
        for name, default in (("section", ""), ("frontmatter_only", False), ("body_only", False)):
            self.assertEqual(params[name].default, default, name)

    def test_the_registered_tool_returns_only_the_selected_section(self):
        _w(self.root, ".okf.toml", "")
        _w(self.root, "b/two-sections.md",
           "---\ntype: Runbook\ntitle: S\n---\n# S\n## Alpha\nalpha text\n## Beta\nbeta text\n")
        out = mcp._register(_ToolCollector()).tools["okf_read"](
            self.root, path="b/two-sections", section="Alpha")
        self.assertEqual(out["data"], {"path": "b/two-sections", "text": "## Alpha\nalpha text\n"})

    def test_the_registered_tool_returns_frontmatter_or_body_alone(self):
        _w(self.root, ".okf.toml", "")
        _w(self.root, "b/two-sections.md",
           "---\ntype: Runbook\ntitle: S\n---\n# S\n## Alpha\nalpha text\n")
        read = mcp._register(_ToolCollector()).tools["okf_read"]
        self.assertEqual(read(self.root, path="b/two-sections", frontmatter_only=True)["data"]["text"],
                         "---\ntype: Runbook\ntitle: S\n---\n")
        self.assertEqual(read(self.root, path="b/two-sections", body_only=True)["data"]["text"],
                         "# S\n## Alpha\nalpha text\n\n")


if __name__ == "__main__":
    unittest.main()
