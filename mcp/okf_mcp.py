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
    "build-semantic-index": ([], False),
    "prime": ([], False),
    "info":  ([], False),
    "wikilinks": (["target"], True),
}
# optional value-flag params: tool-key -> okf-cli flag
_FLAGS = {"scan_root": "--scan-root", "type": "--type", "tag": "--tag", "limit": "--limit",
          "scope": "--scope"}
# optional boolean-flag params: tool-key -> okf-cli flag (emitted when truthy)
_BOOL_FLAGS = {"apply": "--apply", "force": "--force", "unresolved": "--unresolved",
               "compact": "--compact", "include_archive": "--include-archive",
               "full": "--full"}
# _BOOL_FLAGS is shared across every command's params dict, but okf-cli's own
# argparse only defines --include-archive on the find/list subparsers (R-14,
# okf-cli-9e2b) — any OTHER command handed that flag would fail at the
# subprocess boundary with an argparse error. Command-scope it explicitly
# rather than relying on no other tool function ever populating the key:
# a key absent from this map stays as unrestricted as before (apply/force/
# unresolved/compact are untouched, out of this task's scope). `full` gets
# the same treatment (okf-cli-t2w8, SC-002): argparse only defines --full on
# index/prime, and okf_prime never populates the key, so scoping to index
# alone is enough.
_BOOL_FLAG_COMMANDS = {"include_archive": {"find", "list"}, "full": {"index"}}


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
        allowed = _BOOL_FLAG_COMMANDS.get(key)
        if allowed is not None and command not in allowed:
            continue
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

# Ceiling on a single result (okf-cli-7u5z, D02). Beyond it the consumer drops
# the call entirely, so returning the payload helps nobody -- an error naming the
# remedy does. Sized so the largest legitimate bundle listing still passes while
# a catalogue-wide dump does not.
MAX_OUTPUT_CHARS = int(os.environ.get("OKF_MCP_MAX_CHARS", "120000"))


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
    if len(out) > MAX_OUTPUT_CHARS:
        raise RuntimeError(
            "okf-cli {} produced {} characters, over the {} character budget. "
            "Narrow the call -- pass a bundle/scope/type filter, or use find "
            "for a ranked subset.".format(command, len(out), MAX_OUTPUT_CHARS))
    if _COMMANDS[command][1]:  # supports_json
        return json.loads(out) if out.strip() else {}
    if proc.stderr:
        return proc.stderr + out
    return out


def _register(server):
    @server.tool()
    def okf_find(root: str, query: str, limit: int = 10, type: str = "",
                 tag: str = "", scope: str = "",
                 include_archive: bool = False) -> list:
        """Ranked search across a catalogue/repo root, composable with
        exact-match type/tag filters and a bundle/subdir scope.

        Two arms produce results: a lexical FTS5/BM25 arm and a semantic
        embedding arm. Exactly one of them owns the ranking per query — the
        lexical arm when its top hit has a clear margin, otherwise the
        semantic one — and the other arm's hits are appended behind, never in
        front. Every result line names its own arm: `provenance: semantic`
        on a semantic hit, `provenance: lexical` on a lexical one — the
        owning arm of the ranking is a separate statement, made once in the
        note above the list.

        Degradations never fail the call and are announced as a note
        prepended to the returned text (okf-cli-2o39, D01 — the CLI itself
        writes them to stderr, which run_okf folds into this tool's return
        value): a missing or stale lexical index falls back to a substring
        scan (fix it with okf_build_index), and an unavailable embedding
        backend leaves lexical results only.

        Pass include_archive=True to also search archived material
        (`archive`-verb output). The lexical arm honours it fully; the
        semantic arm's embeddings are built only for the active catalogue
        (a deliberate cost limit), so a call that hands over to the
        semantic arm carries an extra note saying so (R-13)."""
        return run_okf(root, "find", {
            "query": query, "limit": limit, "type": type, "tag": tag,
            "scope": scope, "include_archive": include_archive,
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
    def okf_index(root: str, bundle: str = "", full: bool = False) -> dict:
        """Catalogue/bundle TOC. Without `bundle`, defaults to one entry per
        bundle with just its name + one-line description — pass full=True
        for the structured per-bundle summary (description, concept count,
        directories) instead. With `bundle`, unaffected by `full`."""
        return run_okf(root, "index", {"bundle": bundle, "full": full})

    @server.tool()
    def okf_list(root: str, type: str = "", tag: str = "",
                 include_archive: bool = False) -> dict:
        """Concepts filtered by frontmatter type and/or tag. Pass
        include_archive=True to also list archived concepts."""
        return run_okf(root, "list", {
            "type": type, "tag": tag, "include_archive": include_archive,
        })

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
    def okf_wikilinks(root: str, target: str = "", unresolved: bool = False) -> dict:
        """Obsidian wikilinks ([[…]]) in a catalogue, with the resolution status
        of each. Returns {links, by_bundle, totals}; every link record names its
        source file, the region it sits in (body or frontmatter), the raw
        occurrence and one of resolved / ambiguous / unresolved. The markdown
        link surfaces (okf_refs, okf_check's crosslink-format) are blind to this
        form — use this one before renaming a concept a wikilink may point at.
        Pass unresolved=True to list only the broken and ambiguous ones."""
        return run_okf(root, "wikilinks",
                       {"target": target, "unresolved": unresolved})

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
    def okf_build_semantic_index(root: str) -> str:
        """Fill <root>/.tagvec/tag_vectors.sqlite's concept_emb table for
        every concept still missing a voyage-3-large embedding. NETWORK —
        calls the Voyage AI embedding API and requires VOYAGE_API_KEY in
        the CLI process's environment; without it (or on a failed call)
        this degrades to a `note: ...` on stderr (folded into this tool's
        return value, D01) instead of raising. The CLI's own --if-stale
        flag is not exposed here (mirrors okf_build_index, which does not
        expose FTS's --if-stale either) — every call here is an
        unconditional delta fill; run this when okf_prime or okf_find
        reports the semantic index as absent or partial."""
        return run_okf(root, "build-semantic-index", {})

    @server.tool()
    def okf_prime(root: str) -> str:
        """One-shot onboarding for a fresh session: what the store is, how to
        retrieve from it, the full command directory, `find`'s options and its
        rank/score scales (rank: N is the headline, the arms' own raw scores
        surface only under --breakdown), this catalogue's live state (index,
        tag vocabulary) and its bundle TOC. Start here before searching a
        catalogue you have not worked with in this session. Rendered compact —
        bundle descriptions come from okf_index, find's full option help from
        the CLI."""
        return run_okf(root, "prime", {"compact": True})

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
