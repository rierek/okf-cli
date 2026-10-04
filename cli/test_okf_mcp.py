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
import inspect
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

    def test_index_json_over_subprocess_no_bundle_defaults_to_compact(self):
        """okf-cli-t2w8 SC-002 — the MCP surface offers the same
        compact/full split `index` does: bundle+description by default,
        no concepts/directories keys without full=True."""
        out = mcp.run_okf(self.root, "index", {"bundle": ""})
        entry = out["bundles"][0]
        self.assertNotIn("concepts", entry)
        self.assertNotIn("directories", entry)

    def test_index_json_over_subprocess_no_bundle_full_includes_concepts(self):
        out = mcp.run_okf(self.root, "index", {"bundle": "", "full": True})
        entry = out["bundles"][0]
        self.assertEqual(entry["concepts"], 2)
        self.assertIn("directories", entry)


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


class BuildArgvIndexFullFlag(unittest.TestCase):
    """okf-cli-t2w8 SC-002 — `full` marshals to --full on `index` only,
    scoped the same way include_archive is scoped to find/list."""

    def test_full_true_adds_the_flag(self):
        argv = mcp.build_argv("/root", "index", {"bundle": "", "full": True})
        self.assertIn("--full", argv)

    def test_full_false_omits_the_flag(self):
        argv = mcp.build_argv("/root", "index", {"bundle": ""})
        self.assertNotIn("--full", argv)


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
        self.assertIn("note: semantic index build skipped", out)
        self.assertIn("VOYAGE_API_KEY", out)


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

    def test_command_is_whitelisted_with_target_and_json(self):
        self.assertEqual(mcp._COMMANDS["wikilinks"], (["target"], True))

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
                         ["--root", "/root", "prime", "--compact"])

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
        self.assertEqual(argvs, [["--root", "/root", "prime", "--compact"]])


class McpOptionalRoot(unittest.TestCase):
    """okf-cli worktree bug — every MCP tool now defaults `root` to "" so a
    session whose cwd is a linked worktree (never a hull layout's own
    catalogue root) can omit it and let okf-cli auto-detect from cwd
    instead of the caller guessing wrong path arithmetic. build_argv is the
    single point deciding whether `--root` reaches the CLI at all."""

    def test_falsy_root_omits_the_root_flag(self):
        argv = mcp.build_argv("", "prime", {"compact": True})
        self.assertNotIn("--root", argv)
        self.assertEqual(argv, ["prime", "--compact"])

    def test_truthy_root_still_emits_the_root_flag(self):
        argv = mcp.build_argv("/x", "prime", {"compact": True})
        self.assertEqual(argv, ["--root", "/x", "prime", "--compact"])

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
    (verified once against the real library — okf-cli-z69p). Runs under
    plain python3, unlike a FastMCP-backed check: `mcp` is not on the
    system interpreter `just test` uses, only inside the `uv run --with
    'mcp<2'` sandbox the server itself launches in."""

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


class McpIncludeArchiveFlag(unittest.TestCase):
    """R-14 (okf-cli-9e2b) — _BOOL_FLAGS is shared across every command, so
    the tool SIGNATURE decides who can reach the flag: a command whose
    Python signature never accepts `include_archive` can never put it in
    `params`, and build_argv only emits `--include-archive` for a key that
    is actually present and truthy in `params`. AC3/SC-02 is the real risk
    (shared dict, easy to leak): tested over EVERY other command, not a
    sample of two."""

    def test_sc01_find_carries_the_flag_when_set_and_omits_it_when_unset(self):
        with_flag = mcp.build_argv("/root", "find",
                                    {"query": "q", "include_archive": True})
        self.assertIn("--include-archive", with_flag)
        without = mcp.build_argv("/root", "find",
                                  {"query": "q", "include_archive": False})
        self.assertNotIn("--include-archive", without)

    def test_sc01_list_carries_the_flag_when_set_and_omits_it_when_unset(self):
        with_flag = mcp.build_argv("/root", "list", {"include_archive": True})
        self.assertIn("--include-archive", with_flag)
        without = mcp.build_argv("/root", "list", {"include_archive": False})
        self.assertNotIn("--include-archive", without)

    def test_ac3_sc02_no_other_command_emits_the_flag(self):
        others = sorted(set(mcp._COMMANDS) - {"find", "list"})
        self.assertTrue(others)  # sanity: the exclusion set is non-empty
        for command in others:
            argv = mcp.build_argv("/root", command, {"include_archive": True})
            self.assertNotIn(
                "--include-archive", argv,
                "command {!r} must never emit --include-archive".format(command))

    def test_ac1_okf_find_tool_accepts_include_archive_and_reaches_build_argv(self):
        argvs = []
        real = mcp.run_okf

        def spy(root, command, params):
            argvs.append(mcp.build_argv(root, command, params))
            return ""
        mcp.run_okf = spy
        try:
            mcp._register(_ToolCollector()).tools["okf_find"](
                "/root", query="q", include_archive=True)
        finally:
            mcp.run_okf = real
        self.assertEqual(
            argvs[0],
            ["--root", "/root", "find", "q", "--limit", "10", "--include-archive"])

    def test_ac1_okf_list_tool_accepts_include_archive_and_reaches_build_argv(self):
        argvs = []
        real = mcp.run_okf

        def spy(root, command, params):
            argvs.append(mcp.build_argv(root, command, params))
            return ""
        mcp.run_okf = spy
        try:
            mcp._register(_ToolCollector()).tools["okf_list"](
                "/root", include_archive=True)
        finally:
            mcp.run_okf = real
        self.assertEqual(
            argvs[0],
            ["--root", "/root", "list", "--include-archive", "--json"])


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
        out = self._tool("okf_wikilinks")(root=self.root)
        self.assertIsInstance(out, dict)
        self.assertIn("links", out)
        self.assertIn("by_bundle", out)
        self.assertEqual(
            {(l["page"], l["status"]) for l in out["links"]},
            {("one", "resolved"), ("ghost", "unresolved")})

    def test_okf_wikilinks_unresolved_filter_reaches_the_cli(self):
        out = self._tool("okf_wikilinks")(root=self.root, unresolved=True)
        self.assertEqual([l["page"] for l in out["links"]], ["ghost"])

    def test_okf_wikilinks_target_scopes_the_scan(self):
        _w(self.root, "other/x.md", "---\ntype: Runbook\n---\nSee [[phantom]].\n")
        out = self._tool("okf_wikilinks")(root=self.root, target="other")
        self.assertEqual(sorted(out["by_bundle"]), ["other"])


class McpCtxBoundary(McpBoundaryTestBase):
    """OKFT-eyhm — okf_ctx_list / okf_ctx_show over the real CLI."""

    def _ctx_create(self, slug, *paths):
        subprocess.run(["python3", mcp.OKF_CLI, "--root", self.root, "ctx",
                        "create", slug, *paths], check=True, capture_output=True)

    def _tool(self, name):
        return mcp._register(_ToolCollector()).tools[name]

    def test_list_and_show_on_one_ctx(self):
        self._ctx_create("alpha", "b/one.md", "b/two.md")
        listed = self._tool("okf_ctx_list")(root=self.root)
        self.assertEqual([c["slug"] for c in listed], ["alpha"])
        self.assertIn("entries", listed[0])
        shown = self._tool("okf_ctx_show")(root=self.root, slug="alpha")
        self.assertEqual([e["path"] for e in shown["entries"]],
                         ["b/one.md", "b/two.md"])

    def test_show_dead_entry_returns_object_with_dead_count(self):
        self._ctx_create("alpha", "b/one.md", "b/two.md")
        os.remove(os.path.join(self.root, "b/two.md"))
        shown = self._tool("okf_ctx_show")(root=self.root, slug="alpha")
        self.assertGreater(shown["dead"], 0)

    def test_show_unknown_slug_raises_with_cli_stderr(self):
        with self.assertRaises(RuntimeError) as cm:
            self._tool("okf_ctx_show")(root=self.root, slug="nope")
        self.assertIn("ctx: unknown slug: nope", str(cm.exception))

    def test_list_for_path_limits_to_bundles_listing_the_file(self):
        self._ctx_create("alpha", "b/one.md")
        self._ctx_create("beta", "b/two.md")
        out = self._tool("okf_ctx_list")(root=self.root, for_path="b/one.md")
        self.assertEqual([c["slug"] for c in out], ["alpha"])

    def test_nonzero_empty_stdout_still_returns_empty_for_other_commands(self):
        self.assertEqual(
            mcp.run_okf(self.root, "check", {"target": "nonexist"}), {})


class McpBuildSemanticIndexSurface(unittest.TestCase):
    """OKFT-wsne — okf_build_semantic_index is analog to okf_build_index:
    whitelisted with no positional/flag params, wired straight through to
    run_okf. No real subprocess here (that boundary is covered by
    McpAgentRemedyBoundary above); this class only pins the wiring."""

    def test_command_is_whitelisted_with_no_positionals_and_no_json(self):
        self.assertEqual(mcp._COMMANDS["build-semantic-index"], ([], False))

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
            argvs, [["--root", "/root", "build-semantic-index"]])


if __name__ == "__main__":
    unittest.main()
