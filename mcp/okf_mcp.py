#!/usr/bin/env python3
"""okf-MCP — mechanical okf-cli verbs as MCP tools. Thin subprocess wrapper;
all correctness logic lives in okf-cli.py."""
import os

# command -> (positional param names, supports --json)
_COMMANDS = {
    "find":  (["query"], False),
    "read":  (["path"], False),
    "toc":   (["path"], False),
    "index": (["bundle"], True),
    "list":  ([], True),
    "check": (["target"], True),
    "reindex": (["target"], False),
    "refs":  (["path"], True),
    "rename": (["old", "new"], False),
    "tags":  (["query"], False),
    "build-index": ([], False),
    "prime": ([], False),
    "info":  ([], False),
}
# optional value-flag params: tool-key -> okf-cli flag
_FLAGS = {"scan_root": "--scan-root", "type": "--type", "tag": "--tag", "limit": "--limit",
          "scope": "--scope"}
# optional boolean-flag params: tool-key -> okf-cli flag (emitted when truthy)
_BOOL_FLAGS = {"apply": "--apply", "force": "--force"}


def build_argv(root, command, params):
    if command not in _COMMANDS:
        raise ValueError("unsupported okf command: {}".format(command))
    positional, supports_json = _COMMANDS[command]
    argv = ["--root", root, command]
    for name in positional:
        val = params.get(name)
        if val is not None and val != "":
            argv.append(str(val))
    for key, flag in _FLAGS.items():
        if key in positional:
            # A _FLAGS key can collide with a POSITIONAL param name of a
            # DIFFERENT command — _FLAGS is shared across all commands, so
            # skip re-marshaling as a flag here; the positional loop above
            # already placed it correctly. (No live collision today since
            # find's --bundle alias was removed D02, PO-grilling 2026-07-26;
            # guard stays as defense against a future one.)
            continue
        if params.get(key) not in (None, ""):
            argv += [flag, str(params[key])]
    for key, flag in _BOOL_FLAGS.items():
        if params.get(key):
            argv.append(flag)
    if supports_json:
        argv.append("--json")
    return argv


import json
import subprocess

# Resolve the CLI relative to this file so a repo move cannot strand the server.
OKF_CLI = os.environ.get("OKF_CLI",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cli", "okf-cli.py"))


def run_okf(root, command, params):
    """Invoke okf-cli.py, return parsed JSON for --json commands else raw text.
    Note: check exits 1 on violations — that is data, not a crash, so exit code
    is only treated as an error for non-check commands.

    D01 (okf-cli-2o39): the CLI announces degradation (stale/absent lexical
    index, unavailable embedding backend, ...) on stderr, never on stdout.
    For non-JSON commands that stderr text is prepended to the returned
    stdout text, so an MCP consumer actually sees it. JSON-supporting
    commands are left untouched — their stdout feeds json.loads() directly,
    and mixing stderr in would break every consumer of those tools."""
    argv = build_argv(root, command, params)
    proc = subprocess.run(["python3", OKF_CLI] + argv, capture_output=True, text=True)
    if proc.returncode != 0 and command != "check":
        raise RuntimeError("okf-cli {} failed: {}".format(command, proc.stderr.strip()))
    out = proc.stdout
    if _COMMANDS[command][1]:  # supports_json
        return json.loads(out) if out.strip() else {}
    if proc.stderr:
        return proc.stderr + out
    return out


def _register(server):
    @server.tool()
    def okf_find(root: str, query: str, limit: int = 10, type: str = "",
                 tag: str = "", scope: str = "") -> list:
        """Ranked search across a catalogue/repo root, composable with
        exact-match type/tag filters and a bundle/subdir scope.

        Two arms produce results: a lexical FTS5/BM25 arm and a semantic
        embedding arm. Exactly one of them owns the ranking per query — the
        lexical arm when its top hit has a clear margin, otherwise the
        semantic one — and the other arm's hits are appended behind, never in
        front. A semantic-arm result line carries `provenance: semantic
        (cosine=…)`; a line with no such marker came from the lexical arm.

        Degradations never fail the call and are announced as a note
        prepended to the returned text (okf-cli-2o39, D01 — the CLI itself
        writes them to stderr, which run_okf folds into this tool's return
        value): a missing or stale lexical index falls back to a substring
        scan (fix it with okf_build_index), and an unavailable embedding
        backend leaves lexical results only."""
        return run_okf(root, "find", {
            "query": query, "limit": limit, "type": type, "tag": tag,
            "scope": scope,
        })

    @server.tool()
    def okf_read(root: str, path: str) -> str:
        """Print one concept page (bundle/concept-id)."""
        return run_okf(root, "read", {"path": path})

    @server.tool()
    def okf_toc(root: str, path: str) -> str:
        """Section headings of a concept."""
        return run_okf(root, "toc", {"path": path})

    @server.tool()
    def okf_index(root: str, bundle: str = "") -> dict:
        """Catalogue/bundle TOC."""
        return run_okf(root, "index", {"bundle": bundle})

    @server.tool()
    def okf_list(root: str, type: str = "", tag: str = "") -> dict:
        """Concepts filtered by frontmatter type and/or tag."""
        return run_okf(root, "list", {"type": type, "tag": tag})

    @server.tool()
    def okf_check(root: str, target: str = "") -> dict:
        """§9 conformance scan (config-aware TYPES). Returns {errors, warnings}."""
        return run_okf(root, "check", {"target": target})

    @server.tool()
    def okf_reindex(root: str, target: str) -> str:
        """Regenerate marker-bounded index listings for a bundle/subdir."""
        return run_okf(root, "reindex", {"target": target})

    @server.tool()
    def okf_refs(root: str, path: str, scan_root: str = "") -> dict:
        """Inbound markdown references to a file (reference-integrity step a)."""
        return run_okf(root, "refs", {"path": path, "scan_root": scan_root})

    @server.tool()
    def okf_rename(root: str, old: str, new: str, apply: bool = False,
                   force: bool = False) -> str:
        """Move a concept and keep every reference intact: rewrites inbound links
        repo-wide plus the file's own outbound links on a bundle change, then
        reindexes affected bundles. Defaults to a dry-run preview; pass apply=True
        to perform the move (git mv, staged). Reference-integrity step b."""
        return run_okf(root, "rename", {"old": old, "new": new, "apply": apply, "force": force})

    @server.tool()
    def okf_tags(root: str, query: str = "", limit: int = 8) -> str:
        """List all tags with usage counts (query omitted), or fuzzy-search a
        candidate tag against the tag universe. Write/admin tag verbs
        (merge-tags, normalize-tags, --register) stay CLI-only by intent."""
        return run_okf(root, "tags", {"query": query, "limit": limit})

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

    return server


if __name__ == "__main__":
    from mcp.server.fastmcp import FastMCP
    _register(FastMCP("okf")).run()
