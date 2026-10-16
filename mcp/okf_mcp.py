#!/usr/bin/env python3
"""okf-MCP — mechanical okf verbs as MCP tools. Thin subprocess wrapper;
all correctness logic lives in the okf binary.

`root` on every tool defaults to "" (omit it): okf then auto-detects the
catalogue by walking this server process's own cwd upward for a `.okf.toml`/
`SPEC.md`+`TYPES.md` marker, checked both in each candidate directory and in
its `docs/` child (the workspace+repo/-hull layout keeps the marker under
`<hull>/docs/`, never in `<hull>` itself); if nothing is found there, the `root` in
`~/.config/okf/config.toml` applies. Since each server instance's cwd
is the session's own project directory — main checkout or linked worktree
alike — this resolves correctly from a worktree with no path arithmetic.
Two modes, one meaning each: default = the catalogue of the session's own project tree;
`use_global=true` = the `root` of the user config (the central Knowledge-Catalogue), even
when a project catalogue lies above cwd. (`global` is a Python keyword, hence `use_global`.)
Pass an explicit `root` only for a third catalogue; a leading `~` is expanded. `use_global`
together with `root` fails with `invalid_input`.

Every tool returns the CLI's one `--json` envelope reduced to {"data", "warnings"}:
`data` is the result, `warnings` the call notes. When the CLI reports a failure that
still carries a result (check findings, drift rows, a dead ctx entry), the return adds
`error` {kind, code, message} next to that `data`; a failure without a result raises with
the CLI's own `error.kind` and `error.message`. The CLI's exit code is never read."""
import os

# command -> positional param names
_COMMANDS = {
    "find":  ["query"],
    "read":  ["path"],
    "toc":   ["path"],
    "index": ["bundle"],
    "list":  [],
    "check": ["target"],
    "reindex": ["target"],
    "refs":  ["path"],
    "rename": ["old", "new"],
    "tags":  ["query"],
    "build-index": [],
    "build-semantic-index": [],
    "prime": [],
    "info":  [],
    "wikilinks": ["target"],
    "sync-export": ["concept", "block_id"],
    "sync-insert": ["consumer", "concept", "block_id"],
    "sync-status": ["target"],
    "sync-update": ["target"],
    "ctx":   ["verb", "slug"],
}
# optional value-flag params: tool-key -> okf flag
_FLAGS = {"scan_root": "--scan-root", "where": "--where", "limit": "--limit",
          "source": "--source", "block": "--block",
          "for_path": "--for", "section": "--section",
          "follow": "--follow", "max_tokens": "--max-tokens"}
# optional boolean-flag params: tool-key -> okf flag (emitted when truthy)
_BOOL_FLAGS = {"apply": "--apply", "force": "--force", "unresolved": "--unresolved",
               "compact": "--compact", "full": "--full", "frontmatter_only": "--frontmatter-only",
               "body_only": "--body-only", "inbound": "--inbound"}
# _BOOL_FLAGS is shared across every command's params dict, but okf's own
# argparse defines some of them on one command only — any OTHER command handed
# that flag would fail at the subprocess boundary with an argparse error.
# Command-scope it explicitly rather than relying on no other tool function
# ever populating the key: a key absent from this map stays as unrestricted as
# before (apply/force/unresolved/compact are untouched, out of this task's
# scope). `full` (okf-cli-t2w8, SC-002): argparse only defines --full on
# index/prime, and okf_prime never populates the key, so scoping to index
# alone is enough. frontmatter_only, body_only, follow, inbound and max_tokens exist on read alone
# (OKFT-0kcz, OKFT-5x3b); value flags are scoped the same way.
_FLAG_COMMANDS = {"full": {"index"},
                  "frontmatter_only": {"read"}, "body_only": {"read"},
                  "follow": {"read"}, "inbound": {"read"}, "max_tokens": {"read"}}


def build_argv(root, command, params):
    if command not in _COMMANDS:
        raise ValueError("unsupported okf command: {}".format(command))
    positional = _COMMANDS[command]
    argv = (["--root", root] if root else []) + (["--global"] if params.get("use_global") else []) + [command]
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
        if command not in _FLAG_COMMANDS.get(key, {command}):
            continue
        if params.get(key) not in (None, ""):
            argv += [flag, str(params[key])]
    for key, flag in _BOOL_FLAGS.items():
        if command not in _FLAG_COMMANDS.get(key, {command}):
            continue
        if params.get(key):
            argv.append(flag)
    argv.append("--json")
    return argv


import json
import subprocess


def _okf_binary():
    """The okf binary this server runs: $OKF_BIN, else the one beside this file's package root
    (`bin/okf` of a Homebrew keg, `go/bin/okf` of a source checkout built by `just go-build`),
    else `okf` on PATH (a wheel install ships no binary next to the script)."""
    if os.environ.get("OKF_BIN"):
        return os.environ["OKF_BIN"]
    pkg = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for rel in ("bin/okf", "go/bin/okf"):
        if os.path.isfile(os.path.join(pkg, rel)):
            return os.path.join(pkg, rel)
    return "okf"


OKF_BIN = _okf_binary()

# Ceiling on a single result (okf-cli-7u5z, D02). Beyond it the consumer drops
# the call entirely, so returning the payload helps nobody -- an error naming the
# remedy does. Sized so the largest legitimate bundle listing still passes while
# a catalogue-wide dump does not.
MAX_OUTPUT_CHARS = int(os.environ.get("OKF_MCP_MAX_CHARS", "120000"))


def run_okf(root, command, params):
    """Invoke the okf binary (OKF_BIN) with --json and read its one envelope
    {command, ok, data, warnings, error}. Success and failure come from the envelope
    alone, never from the exit code: `ok` true returns {"data", "warnings"}; `ok` false
    with a result (check findings, drift rows, ambiguous-section candidates) returns
    {"data", "warnings", "error"}; `ok` false without a result, or stdout that is not
    one envelope, raises. The CLI's call notes arrive as `warnings`; nothing is read
    from stderr except to explain a stdout that is not an envelope."""
    argv = build_argv(root, command, params)
    proc = subprocess.run([OKF_BIN] + argv, capture_output=True, text=True)
    out = proc.stdout
    if len(out) > MAX_OUTPUT_CHARS:
        raise RuntimeError(
            "okf {} produced {} characters, over the {} character budget. "
            "Narrow the call -- pass a bundle, filter with where (for example "
            "where=\"type = Runbook\"), or use find for a ranked subset."
            .format(command, len(out), MAX_OUTPUT_CHARS))
    try:
        envelope = json.loads(out)
        ok, data, warnings, error = (envelope["ok"], envelope["data"],
                                     envelope["warnings"], envelope["error"])
    except (ValueError, KeyError, TypeError):
        raise RuntimeError("okf {} did not print one JSON envelope (exit {}): {}".format(
            command, proc.returncode, proc.stderr.strip()))
    if ok:
        return {"data": data, "warnings": warnings}
    if data is None:
        raise RuntimeError("okf {} failed: {}: {}".format(command, error["kind"], error["message"]))
    return {"data": data, "warnings": warnings, "error": error}


def _register(server):
    @server.tool()
    def okf_find(root: str = "", *, query: str, limit: int = 10, where: str = "", use_global: bool = False) -> dict:
        """Ranked search across a catalogue/repo root, narrowed by a `where`
        expression: `field op value` with op one of = != < <= > >= ~ (contains)
        or `field in (a, b)`, joined by and, or, not and parentheses. Fields:
        type, tag, path (<bundle>/<concept-id>), archived (true or false),
        tier (unverified, machine-confirmed or human-reviewed), stale (true or
        false), status (an absent status is stable) and any frontmatter key
        (nested: a.b; through lists: verified.by, sources.resource). Timestamp
        keys (generated.at, verified.at, stale_after, usage_window.from/to,
        sources.last_modified) compare as instants and take an ISO 8601 value
        with an explicit offset. Quote a value with spaces or +: 'a b'.
        Example: where="type = Runbook and path ~ home-lab/".

        Two arms produce results: a lexical FTS5/BM25 arm and a semantic
        embedding arm. Exactly one of them owns the ranking per query — the
        lexical arm when its top hit has a clear margin, otherwise the
        semantic one — and the other arm's hits are appended behind, never in
        front. Every hit names its own arm in `provenance` (`semantic` or
        `lexical`); which arm owns the ranking is a separate statement, made
        once as a warning.

        Degradations never fail the call and arrive in `warnings` (the CLI's
        call notes, okf-cli-2o39, D01): a missing or stale lexical index falls
        back to a substring scan (fix it with okf_build_index), and an
        unavailable embedding backend leaves lexical results only.

        Archived concepts are hidden unless `where` names `archived`, for
        example where="archived in (true, false)". The lexical arm honours it
        fully; the semantic arm's embeddings are built only for the active
        catalogue (a deliberate cost limit), so a call that hands over to the
        semantic arm carries an extra warning saying so (R-13). A malformed
        expression fails the call with an `invalid_input` error."""
        return run_okf(root, "find", {"use_global": use_global, "query": query, "limit": limit, "where": where})

    @server.tool()
    def okf_read(root: str = "", *, path: str, section: str = "",
                 frontmatter_only: bool = False, body_only: bool = False,
                 follow: int | None = None, inbound: bool = False,
                 max_tokens: int | None = None, use_global: bool = False) -> dict:
        """Print one concept page (bundle/concept-id). At most one of `section`,
        `frontmatter_only`, `body_only`: `section` prints only that section — the heading
        text, case-insensitive and exact, up to the next heading of equal or
        higher level, sub-sections included; "A > B" resolves B inside A. An
        ambiguous heading is an error whose `data.candidates` lists the matching
        headings with their lines, an unknown one a plain error. `frontmatter_only=True` prints
        only the frontmatter block (delimiters included), `body_only=True`
        everything after it.

        `follow` (integer, at least 0): also return the concepts the page links to, up to that
        many hops, as `data.nodes` (path, depth, tokens, reduced, text); combines with `section`,
        not with the two booleans.
        `inbound=True`: with `follow`, the pages that link to a page count as its neighbours too.
        `max_tokens` (integer, at least 1): with `follow`, keep the block within that many
        tokens (chars/4); the root stays in full, from the first page that does not fit on,
        pages carry title and description only (`reduced`)."""
        return run_okf(root, "read", {"use_global": use_global,
            "path": path, "section": section,
            "frontmatter_only": frontmatter_only, "body_only": body_only,
            "follow": follow, "inbound": inbound, "max_tokens": max_tokens,
        })

    @server.tool()
    def okf_toc(root: str = "", *, path: str, use_global: bool = False) -> dict:
        """Section headings of a concept."""
        return run_okf(root, "toc", {"use_global": use_global, "path": path})

    @server.tool()
    def okf_index(root: str = "", bundle: str = "", full: bool = False, use_global: bool = False) -> dict:
        """Catalogue/bundle TOC. Without `bundle`, defaults to one entry per
        bundle with just its name + one-line description — pass full=True
        for the structured per-bundle summary (description, concept count,
        directories) instead. With `bundle`, unaffected by `full`."""
        return run_okf(root, "index", {"use_global": use_global, "bundle": bundle, "full": full})

    @server.tool()
    def okf_list(root: str = "", where: str = "", use_global: bool = False) -> dict:
        """The complete, unranked set of concepts a `where` expression selects;
        the expression is required (an empty one fails with `invalid_input`).
        Grammar as in okf_find: `field op value` or `field in (a, b)`, joined by
        and, or, not and parentheses, over type, tag, path, archived, tier,
        stale, status and any frontmatter key. Example: where="type = Runbook and tag = alpha".
        Archived concepts are listed only when `where` names `archived`, for
        example where="archived in (true, false)"."""
        return run_okf(root, "list", {"use_global": use_global, "where": where})

    @server.tool()
    def okf_check(root: str = "", target: str = "", use_global: bool = False) -> dict:
        """§9 conformance scan (config-aware TYPES). Returns {findings}: a list of
        {rule, severity, path, message}, rule an okf/ or kc/ ID, severity error or
        warning; rules matched by the catalogue's .okf.toml ignore_rules are left out."""
        return run_okf(root, "check", {"use_global": use_global, "target": target})

    @server.tool()
    def okf_reindex(root: str = "", *, target: str, use_global: bool = False) -> dict:
        """Regenerate marker-bounded index listings for a bundle/subdir."""
        return run_okf(root, "reindex", {"use_global": use_global, "target": target})

    @server.tool()
    def okf_refs(root: str = "", *, path: str, scan_root: str = "", use_global: bool = False) -> dict:
        """Inbound and outbound markdown references of a file (reference-integrity step a)."""
        return run_okf(root, "refs", {"use_global": use_global, "path": path, "scan_root": scan_root})

    @server.tool()
    def okf_rename(root: str = "", *, old: str, new: str, apply: bool = False,
                   force: bool = False, use_global: bool = False) -> dict:
        """Move a concept and keep every reference intact: rewrites inbound links
        repo-wide plus the file's own outbound links on a bundle change, then
        reindexes affected bundles. Defaults to a dry-run preview (data.files: one
        unified diff per affected file); pass apply=True to perform the move (git mv, staged). Reference-integrity step b."""
        return run_okf(root, "rename", {"use_global": use_global, "old": old, "new": new, "apply": apply, "force": force})

    @server.tool()
    def okf_ctx_list(root: str = "", *, for_path: str = "", use_global: bool = False) -> dict:
        """Curated ctx bundles (_ctx/<slug>.md): slug, description, entry counts.
        for_path limits the result to bundles that list that file."""
        return run_okf(root, "ctx", {"use_global": use_global, "verb": "list", "for_path": for_path})

    @server.tool()
    def okf_ctx_show(root: str = "", *, slug: str, use_global: bool = False) -> dict:
        """One ctx bundle in reading order: entries with live title, type,
        description, comment, alive flag and token estimate."""
        return run_okf(root, "ctx", {"use_global": use_global, "verb": "show", "slug": slug})

    @server.tool()
    def okf_wikilinks(root: str = "", target: str = "", unresolved: bool = False, use_global: bool = False) -> dict:
        """Obsidian wikilinks ([[…]]) in a catalogue, with the resolution status
        of each. Returns {links, by_bundle, totals}; every link record names its
        source file, the region it sits in (body or frontmatter), the raw
        occurrence and one of resolved / ambiguous / unresolved. The markdown
        link surfaces (okf_refs, okf_check's kc/link/crosslink-format) are blind to this
        form — use this one before renaming a concept a wikilink may point at.
        Pass unresolved=True to list only the broken and ambiguous ones."""
        return run_okf(root, "wikilinks",
                       {"use_global": use_global, "target": target, "unresolved": unresolved})

    @server.tool()
    def okf_tags(root: str = "", query: str = "", limit: int = 8, use_global: bool = False) -> dict:
        """List all tags with usage counts (query omitted), or fuzzy-search a
        candidate tag against the tag universe. Write/admin tag verbs
        (merge-tags, normalize-tags, --register) stay CLI-only by intent."""
        return run_okf(root, "tags", {"use_global": use_global, "query": query, "limit": limit})

    @server.tool()
    def okf_build_index(root: str = "", use_global: bool = False) -> dict:
        """(Re)build the FTS5 lexical index at <root>/.fts/fts.sqlite. Local
        only, no network, no change to catalogue content. Run this when
        okf_find reports the lexical index as absent or stale — that note
        names this command, and this tool is how you act on it."""
        return run_okf(root, "build-index", {"use_global": use_global, })

    @server.tool()
    def okf_build_semantic_index(root: str = "", use_global: bool = False) -> dict:
        """Fill <root>/.tagvec/tag_vectors.sqlite's concept_emb table for
        every concept still missing a voyage-3-large embedding. NETWORK —
        calls the Voyage AI embedding API and requires VOYAGE_API_KEY in
        the CLI process's environment; without it (or on a failed call)
        this degrades to an entry in `warnings` (D01) instead of raising. The CLI's own --if-stale
        flag is not exposed here (mirrors okf_build_index, which does not
        expose FTS's --if-stale either) — every call here is an
        unconditional delta fill; run this when okf_prime or okf_find
        reports the semantic index as absent or partial."""
        return run_okf(root, "build-semantic-index", {"use_global": use_global, })

    @server.tool()
    def okf_prime(root: str = "", use_global: bool = False) -> dict:
        """One-shot onboarding for a fresh session: what the store is, how to
        retrieve from it, the full command directory, `find`'s options and its
        rank/score scales (rank: N is the headline, the arms' own raw scores
        surface only under --breakdown), this catalogue's live state (index,
        tag vocabulary) and its bundle TOC. Start here before searching a
        catalogue you have not worked with in this session. Rendered compact —
        bundle descriptions come from okf_index, find's full option help from
        the CLI."""
        return run_okf(root, "prime", {"use_global": use_global, "compact": True})

    @server.tool()
    def okf_info(root: str = "", use_global: bool = False) -> dict:
        """The catalogue's schema docs (TYPES.md + PROPERTIES.md): the valid
        `type` values and the frontmatter properties a concept must carry.
        Read this before writing into a catalogue."""
        return run_okf(root, "info", {"use_global": use_global, })

    @server.tool()
    def okf_sync_export(root: str = "", *, concept: str, block_id: str, use_global: bool = False) -> dict:
        """Print one canonical block's payload, as declared between
        `<!-- okf:canon id=<block_id> -->` and `<!-- /okf:canon -->` in
        `concept`. Read-only. Use it to see what a consumer would receive;
        use okf_sync_insert to actually materialise it."""
        return run_okf(root, "sync-export",
                       {"use_global": use_global, "concept": concept, "block_id": block_id})

    @server.tool()
    def okf_sync_insert(root: str = "", *, consumer: str, concept: str,
                        block_id: str, apply: bool = False, use_global: bool = False) -> dict:
        """Materialise a canonical block inside a consumer concept, so the
        consumer holds the Canon it needs in its own context without becoming
        a second authority. The generated block records its owner and the
        payload hash, which is what makes drift detectable later. Defaults to
        a dry-run preview; pass apply=True to write. NEVER hand-write or
        hand-edit such a block — a needed change goes into the canon owner and
        then downstream through okf_sync_update."""
        return run_okf(root, "sync-insert",
                       {"use_global": use_global, "consumer": consumer, "concept": concept,
                        "block_id": block_id, "apply": apply})

    @server.tool()
    def okf_sync_status(root: str = "", target: str = "", source: str = "",
                        block: str = "", use_global: bool = False) -> dict:
        """Drift report for every materialised canon block: returns
        {blocks, totals}, each block naming its consumer, id, source and one
        of synced / source-changed / consumer-modified / both-changed /
        source-missing / malformed. `source` (e.g. /kc-governance/ownership.md)
        lists the consumers of one canonical concept; `block` narrows to one
        id. Derived by a live catalogue walk — there is no index to rebuild."""
        return run_okf(root, "sync-status",
                       {"use_global": use_global, "target": target, "source": source, "block": block})

    @server.tool()
    def okf_sync_update(root: str = "", target: str = "", source: str = "",
                        block: str = "", apply: bool = False,
                        force: bool = False, use_global: bool = False) -> dict:
        """Re-materialise every outdated consumer block from its canon owner.
        Defaults to a dry-run preview; pass apply=True to write. A block whose
        LOCAL copy was modified is refused, not overwritten: reconcile that
        edit into the canon owner first. force=True discards the local copy
        instead. A block whose owner is gone or whose markers are broken is
        reported and never written — that is a human decision."""
        return run_okf(root, "sync-update",
                       {"use_global": use_global, "target": target, "source": source, "block": block,
                        "apply": apply, "force": force})

    return server


if __name__ == "__main__":
    from mcp.server.fastmcp import FastMCP
    _register(FastMCP("okf")).run()
