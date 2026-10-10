#!/usr/bin/env python3
"""okf-cli.py — dependency-free navigation/search for an OKF Knowledge Catalogue.

Catalogue-aware fork inspired by Cole Medin's single-bundle okf-cli.py.
A *catalogue* is a directory whose immediate subdirectories (not starting with
'.' or '_') are OKF *bundles*. Standard library only — no install required.

Run `okf-cli.py --help` for the command directory (flat + grouped by purpose),
and `okf-cli.py <command> --help` for one command's options. Both are generated
from the parser — this file documents no command list by hand.

Run from the catalogue root, or pass --root <path>.
"""
import argparse
import datetime
import difflib
import hashlib
import importlib.util
import json
import math
import os
import re
import sqlite3
import struct
import subprocess
import sys
import shlex
import unicodedata
import urllib.request

from okf import catalogue, linkscan
from okf.catalogue import (
    CANON_END, CANON_OPEN_RE, CROSSLINK_RE, CTX_DIR, CTX_MODES, CTX_VERBS, EXEMPT, FM_DELIM,
    MARK_END, MARK_START, RESERVED, SYNC_BODY, SYNC_END, SYNC_OPEN_LIT, SYNC_OPEN_RE, SYNC_SPAN_RE,
    TAG_DESC_MAX, _collapse, _ctx_die, _dequote, _find_reserved_name, _prune_walk_dirs, all_tags,
    catalogue_root, ctx_dir, ctx_entry_abspath, ctx_file, ctx_findings, ctx_memberships,
    ctx_normalize_path, ctx_slug_problem, ctx_slugs, extract_tags, index_h1_and_desc, iter_all_md,
    iter_concepts, iter_headings, list_bundles, list_dir_concepts, list_indexable_bundles,
    list_search_bundles, load_ctx, load_okf_config, load_tags, load_types, managed_block_for,
    meta_of, parse_tag_list, read_file, read_file_verbatim, register_tags, reindex_tree,
    replace_managed_block, resolve_concept, resolve_scopes, save_ctx, split_frontmatter, write_file,
    write_file_verbatim,
)
from okf.linkscan import (
    _refs_display, iter_md_links, iter_rename_scan_md, wikilink_regions, wikilink_scan_text,
)
from okf.parser_support import (
    _complete_bundles, _complete_concept_files, _complete_concepts, _complete_dirs, _complete_files,
    _complete_scopes, _complete_tags, _complete_types, _completion_root, _sub, merge_commands,
    render_command_overview, subcommand_parsers,
)


def require_bundle_dir(root, bundle):
    """Refuse a bundle argument that names no directory under root — the gate
    `check` has carried alone (cmd_check: "a typo'd or renamed bundle scanned
    nothing and exited 0 — a clean bill of health for a directory that does
    not exist"). `index` printed an empty listing for one; `visualize` created
    the directory to write into.

    The test is existence, deliberately NOT is_bundle_dir(): a `_`-prefixed
    directory is not a bundle for listing purposes but is a real, printable
    directory, and refusing it here would break callers that name one."""
    if not os.path.isdir(os.path.join(root, os.path.normpath(bundle))):
        print("not a directory: {}".format(bundle), file=sys.stderr)
        sys.exit(1)


TAGS_INLINE_RE = re.compile(r"^tags:[ \t]*\[.*\]\s*$", re.M)
TAGS_INLINE_CONTENT_RE = re.compile(r"^tags:[ \t]*\[(.*)\]\s*$", re.M)
TAGS_BLOCK_RE = re.compile(r"^tags:[ \t]*\n((?:[ \t]*-[ \t]*.+\n?)*)", re.M)


def rewrite_tags_in_frontmatter(text, new_tags):
    """Rewrite the `tags:` field inside a concept's frontmatter, preserving
    whichever style the file used — inline (`tags: [a, b]`) or YAML block-list
    (`tags:\\n  - a\\n  - b`). Returns the new file text, or None if there is
    no frontmatter / no parseable `tags` field (caller should skip + flag)."""
    if not text.startswith(FM_DELIM):
        return None
    end = text.find("\n" + FM_DELIM, len(FM_DELIM))
    if end == -1:
        return None
    fm, rest = text[:end], text[end:]

    m = TAGS_INLINE_RE.search(fm)
    if m:
        new_field = "tags: [{}]".format(", ".join(new_tags))
        return fm[:m.start()] + new_field + fm[m.end():] + rest

    m = TAGS_BLOCK_RE.search(fm)
    if m:
        new_field = "tags:\n" + "".join("  - {}\n".format(t) for t in new_tags)
        return fm[:m.start()] + new_field + fm[m.end():] + rest

    return None


def remove_tags_field(text):
    """Strip the entire `tags:` field (inline or block) from frontmatter — used
    when a removal empties the tag list, so no dangling `tags:` key is left.
    Returns the new text, or None if there's no frontmatter / no tags field."""
    if not text.startswith(FM_DELIM):
        return None
    end = text.find("\n" + FM_DELIM, len(FM_DELIM))
    if end == -1:
        return None
    fm, rest = text[:end], text[end:]

    m = TAGS_INLINE_RE.search(fm)
    if m:
        e = m.end() + 1 if m.end() < len(fm) and fm[m.end()] == "\n" else m.end()
        return fm[:m.start()] + fm[e:] + rest

    m = TAGS_BLOCK_RE.search(fm)
    if m:
        return fm[:m.start()] + fm[m.end():] + rest

    return None


def cmd_merge_tags(root, args):
    sources = set(args.tags)
    touched, unparseable = [], []
    for _bundle, bp in resolve_scopes(root, args.scope):
        # prune_staging=False (OKFT-oe8t Review D02): a tag rename must reach
        # staging content too, or it silently leaves the old tag behind there.
        for _cid, ap in iter_concepts(bp, prune_staging=False):
            text = read_file(ap)
            tags = extract_tags(text)
            if not any(t in sources for t in tags):
                continue
            new_tags, seen = [], set()
            for t in tags:
                nt = args.into if t in sources else t
                if nt not in seen:
                    seen.add(nt)
                    new_tags.append(nt)
            if new_tags == tags:
                continue
            new_text = rewrite_tags_in_frontmatter(text, new_tags)
            rel = os.path.relpath(ap, root).replace(os.sep, "/")
            if new_text is None:
                unparseable.append(rel)
                continue
            touched.append(rel)
            if args.apply:
                write_file(ap, new_text)
    verb = "rewrote" if args.apply else "would rewrite"
    for rel in touched:
        print("{:<14} {}".format(verb, rel))
    for rel in unparseable:
        print("unparseable    {}  (tags field not in inline/block form — skipped)".format(rel))
    print("merge-tags: {} file(s) {}, {} unparseable — {} -> {}".format(
        len(touched), verb, len(unparseable), ", ".join(sorted(sources)), args.into))


def cmd_remove_tags(root, args):
    """Remove one or more tags from concept frontmatter (no merge target).
    Symmetric to merge-tags: dry-run default, --scope-limited, --apply writes.
    Emptying the tag list strips the whole `tags:` field (no dangling key)."""
    targets = set(args.tags)
    touched, emptied, unparseable = [], [], []
    for _bundle, bp in resolve_scopes(root, args.scope):
        # prune_staging=False (OKFT-oe8t Review D02): same reasoning as
        # cmd_merge_tags — a tag removal must reach staging content too.
        for _cid, ap in iter_concepts(bp, prune_staging=False):
            text = read_file(ap)
            tags = extract_tags(text)
            if not any(t in targets for t in tags):
                continue
            new_tags = [t for t in tags if t not in targets]
            rel = os.path.relpath(ap, root).replace(os.sep, "/")
            if new_tags:
                new_text = rewrite_tags_in_frontmatter(text, new_tags)
            else:
                new_text = remove_tags_field(text)
                if new_text is not None:
                    emptied.append(rel)
            if new_text is None:
                unparseable.append(rel)
                continue
            touched.append(rel)
            if args.apply:
                write_file(ap, new_text)
    verb = "rewrote" if args.apply else "would rewrite"
    for rel in touched:
        print("{:<14} {}".format(verb, rel))
    for rel in unparseable:
        print("unparseable    {}  (tags field not in inline/block form — skipped)".format(rel))
    print("remove-tags: {} file(s) {}, {} emptied, {} unparseable — removed {}".format(
        len(touched), verb, len(emptied), len(unparseable), ", ".join(sorted(targets))))


def normalize_tags_in_file(text):
    """Convert a non-empty inline `tags: [a, b]` field to YAML block-list form.
    Local convention (this catalogue), not an OKF spec requirement — both forms
    stay valid OKF, this just harmonizes the one file that drifts. Returns the
    new text, or None if there's no frontmatter, no tags field, it's already
    block-list, or the inline list is empty (`[]`)."""
    if not text.startswith(FM_DELIM):
        return None
    end = text.find("\n" + FM_DELIM, len(FM_DELIM))
    if end == -1:
        return None
    fm, rest = text[:end], text[end:]
    m = TAGS_INLINE_CONTENT_RE.search(fm)
    if not m:
        return None
    tags = parse_tag_list(m.group(1))
    if not tags:
        return None
    new_field = "tags:\n" + "\n".join("  - {}".format(t) for t in tags)
    return fm[:m.start()] + new_field + fm[m.end():] + rest


def cmd_normalize_tags(root, args):
    touched = []
    for _bundle, bp in resolve_scopes(root, args.scope):
        # prune_staging=False (OKFT-oe8t Review D02): same reasoning as
        # cmd_merge_tags — normalization must reach staging content too.
        for _cid, ap in iter_concepts(bp, prune_staging=False):
            text = read_file(ap)
            new_text = normalize_tags_in_file(text)
            if new_text is None:
                continue
            rel = os.path.relpath(ap, root).replace(os.sep, "/")
            touched.append(rel)
            if args.apply:
                write_file(ap, new_text)
    verb = "rewrote" if args.apply else "would rewrite"
    for rel in touched:
        print("{:<14} {}".format(verb, rel))
    print("normalize-tags: {} file(s) {}".format(len(touched), verb))


def fuzzy_matches(query, candidates, limit=8):
    """Rank candidates against query, merging two signals so both typo/subsequence
    matches (fzf --filter) AND abbreviation/reordering matches (difflib ratio,
    e.g. `km-management` vs `knowledge-management`) surface — fzf alone misses
    the latter since it requires an in-order character subsequence."""
    if not candidates:
        return []
    fzf_hits = []
    try:
        proc = subprocess.run(
            ["fzf", "--filter", query],
            input="\n".join(candidates),
            capture_output=True, text=True, timeout=5,
        )
        fzf_hits = [l for l in proc.stdout.splitlines() if l.strip()]
    except (FileNotFoundError, subprocess.SubprocessError):
        pass

    ql = query.lower()
    scored = []
    for c in candidates:
        cl = c.lower()
        ratio = difflib.SequenceMatcher(None, ql, cl).ratio()
        if ql in cl or cl in ql:
            ratio += 0.3
        scored.append((ratio, c))
    scored.sort(key=lambda x: -x[0])
    difflib_hits = [c for r, c in scored if r > 0.5]

    seen, merged = set(), []
    for c in fzf_hits + difflib_hits:
        if c not in seen:
            seen.add(c)
            merged.append(c)
    return merged[:limit]


def auto_embed_new_tags(root, tags):
    """Best-effort bge-m3 embedding of newly registered tags, scoped to just
    `tags` (never a full re-embed). Fix for PO-review reject 2026-07-25
    (bean okf-cli-3geg): registration and embedding coverage must not drift
    apart. Never raises — `tags --register` must succeed even if Ollama/
    network is unavailable; a failure here is a stderr warning, not an error."""
    if not tags:
        return
    try:
        bt = catalogue._load_build_tagvec()
        output = os.path.join(root, ".tagvec", "tag_vectors.sqlite")
        delta = bt.plan_delta(set(tags), "bge-m3", output)
        if not delta:
            return
        texts = [text for _tag, text, _key in delta]
        vectors = bt.embed_bge_m3(texts)
        rows = [
            (key, tag, "bge-m3", bt.MODELS["bge-m3"]["dim"], bt.pack_vec(vec))
            for (tag, _text, key), vec in zip(delta, vectors)
        ]
        bt.write_rows(output, rows)
        print("auto-embedded {} new tag(s) (bge-m3)".format(len(rows)), file=sys.stderr)
    except Exception as e:
        print("warning: auto-embed skipped for new tag(s) ({}: {}) — "
              "run cli/embeddings/build_tagvec.py --produce manually later".format(
                  type(e).__name__, e), file=sys.stderr)


def cmd_tags(root, args):
    if getattr(args, "register", None):
        try:
            added, already = register_tags(root, args.register)
        except ValueError as e:
            sys.exit("ERROR: {}".format(e))
        if added:
            print("registered {} new tag(s) in TAGS.md: {}".format(len(added), ", ".join(added)))
            auto_embed_new_tags(root, added)
        if already:
            print("already registered: {}".format(", ".join(already)))
        return
    if getattr(args, "validate", None):
        tags_set = load_tags(root)
        if tags_set is None:
            print("(no TAGS.md — closed vocabulary not enabled)")
            return
        unknown = [t for t in args.validate if t not in tags_set]
        for t in unknown:
            print("UNKNOWN  {}".format(t))
        print("OK — all {} known".format(len(args.validate)) if not unknown
              else "{} UNKNOWN — register with: okf-cli.py tags --register <tag> \"<description, max {} chars>\"".format(
                  len(unknown), TAG_DESC_MAX))
        sys.exit(1 if unknown else 0)
    counts = all_tags(root)
    if not args.query:
        if not counts:
            print("(no tags found)")
            return
        items = counts.items()
        if args.singletons:
            items = [(t, n) for t, n in items if n == 1]
            if not items:
                print("(no singleton tags)")
                return
        width = max(len(t) for t, _n in items)
        for t, n in sorted(items, key=lambda kv: (-kv[1], kv[0])):
            print("  {:<{w}}  {}".format(t, n, w=width))
        return
    universe = sorted(counts.keys())
    for q in args.query:
        print(f"== searched: {q} ==")
        matches = fuzzy_matches(q, universe, limit=args.limit)
        if not matches:
            print("  (no match — new tag)")
        for m in matches:
            print("  - {}  ({})".format(m, counts[m]))
        print()


def bundle_description(bp):
    """H1 + intro paragraph from a bundle's entry file (INDEX-MAP.md/index.md)."""
    for fn in ("INDEX-MAP.md", "index.md"):
        fp = os.path.join(bp, fn)
        if os.path.isfile(fp):
            _, desc = index_h1_and_desc(fp)
            return desc
    return ""


def bundle_top_dirs(bp):
    """Immediate subdirectories of a bundle, excluding hidden dirs and assets/."""
    return sorted(
        d for d in os.listdir(bp)
        if os.path.isdir(os.path.join(bp, d)) and not d.startswith(".") and d != "assets"
    )


def bundle_types_and_tags(bp):
    """Return (sorted types, sorted tags) used across a bundle's concepts."""
    types, tags = set(), set()
    for _cid, ap in iter_concepts(bp):
        t, _title, _desc = meta_of(ap)
        if t:
            types.add(t)
        tags.update(extract_tags(read_file(ap)))
    return sorted(types), sorted(tags)


def render_bundle_line(root, b):
    """Compact one-liner for prime's default bundle listing: name + concept count."""
    bp = os.path.join(root, b)
    n = sum(1 for _ in iter_concepts(bp))
    return "{} ({} concepts)".format(b, n)


def render_bundle_compact(root, b):
    """One-liner for `index`'s catalogue-wide default: name + one-line
    description (okf-cli-t2w8, I03). Distinct from render_bundle_line
    (prime's compact, name+count) — picking the right bundle out of a
    catalogue TOC needs to know what it's about, not how big it is."""
    bp = os.path.join(root, b)
    return "{}: {}".format(b, _collapse(bundle_description(bp)))


def render_bundle_block(root, b, full=False):
    bp = os.path.join(root, b)
    n = sum(1 for _ in iter_concepts(bp))
    lines = [
        "bundle: {}".format(b),
        "description: {}".format(_collapse(bundle_description(bp))),
        "concepts: {}".format(n),
    ]
    dirs = bundle_top_dirs(bp)
    if dirs:
        lines.append("directories:")
        lines.extend("- {}".format(d) for d in dirs)
    if full:
        types, tags = bundle_types_and_tags(bp)
        lines.append("types: {}".format(", ".join(types)))
        lines.append("tags: {}".format(", ".join(tags)))
    return "\n".join(lines)


def _bundle_summary_json(root, b, full=False):
    """The machine-readable twin of the catalogue TOC (okf-cli-7u5z, revised
    okf-cli-t2w8): compact by default (bundle + one-line description, the
    same shape the text form defaults to now), concepts/directories added
    only under full=True. Enumerating concepts unconditionally once turned
    the catalogue-wide TOC into a 794 KB dump no MCP consumer could accept
    — full stays opt-in for the same reason (SC-002)."""
    bp = os.path.join(root, b)
    summary = {"bundle": b, "description": _collapse(bundle_description(bp))}
    if full:
        summary["concepts"] = sum(1 for _ in iter_concepts(bp))
        summary["directories"] = bundle_top_dirs(bp)
    return summary


def _concepts_json(bp):
    """[{id, title, type, description}, ...] for every concept under `bp`,
    sorted by concept id (F02 dedup, prelude 2026-07-25 on okf-cli-83vq)."""
    concepts = []
    for cid, ap in sorted(iter_concepts(bp)):
        t, title, desc = meta_of(ap)
        concepts.append({"id": cid, "title": title, "type": t, "description": desc})
    return concepts


def cmd_index(root, args):
    if args.bundle:
        require_bundle_dir(root, args.bundle)
    if getattr(args, "json", False):
        if args.bundle:
            bp = os.path.join(root, args.bundle)
            print(json.dumps({"bundle": args.bundle, "concepts": _concepts_json(bp)}))
            return
        print(json.dumps({"bundles": [_bundle_summary_json(root, b, full=args.full)
                                      for b in list_bundles(root)]}))
        return
    if args.bundle:
        bp = os.path.join(root, args.bundle)
        if args.full:
            print(render_bundle_block(root, args.bundle, full=True))
            return
        for fn in ("INDEX-MAP.md", "index.md"):
            p = os.path.join(bp, fn)
            if os.path.isfile(p):
                print(read_file(p))
                return
        # synthesize
        print("# {}\n".format(args.bundle))
        for cid, ap in sorted(iter_concepts(bp)):
            t, title, desc = meta_of(ap)
            print("* [{}]({}.md) [{}]{}".format(title, cid, t, " - " + desc if desc else ""))
        return
    # catalogue TOC — compact by default (name + one-line description,
    # okf-cli-t2w8/I03: a wrong-bundle guess against the full block left
    # almost no budget for a second call). --full restores the structured
    # per-bundle block (description/concepts/directories, plus types/tags)
    # that used to be the only form.
    if not args.full:
        for b in list_bundles(root):
            print(render_bundle_compact(root, b))
        return
    for b in list_bundles(root):
        print(render_bundle_block(root, b, full=True))
        print("-----")


def tokenize(s):
    """Lowercased word tokens. `\\w` is Unicode-aware in Python 3, so umlauts
    and ß stay inside their token (B01); `_` is kept as a separator, matching
    the previous behaviour for identifiers like build_tagvec."""
    return [t for t in re.split(r"[\W_]+", s.lower(), flags=re.UNICODE) if t]


def cmd_list(root, args):
    if not args.type and not args.tag:
        print("(error: pass --type and/or --tag)", file=sys.stderr)
        sys.exit(1)
    hits = []
    for _bundle, bp in resolve_scopes(
            root, args.scope, getattr(args, "include_archive", False)):
        for _cid, ap in iter_concepts(bp):
            t, title, desc = meta_of(ap)
            if args.type and t != args.type:
                continue
            if args.tag and args.tag not in extract_tags(read_file(ap)):
                continue
            rel = os.path.relpath(ap, root).replace(os.sep, "/")
            path = rel[:-3] if rel.endswith(".md") else rel
            hits.append((title, t, path, desc))
    hits.sort(key=lambda x: x[0].casefold())
    if getattr(args, "json", False):
        print(json.dumps([
            {"title": title, "type": t, "path": path, "description": desc}
            for (title, t, path, desc) in hits
        ]))
        return
    if not hits:
        print("(no matches)")
        return
    for title, t, path, desc in hits:
        print("------")
        print("title: {}".format(title))
        print("type: {}".format(t))
        print("path: {}".format(path))
        print("description: {}".format(desc))
    print("------")
    print("list: {} concept(s)".format(len(hits)))


def _format_contrib(contrib):
    """SC-002 — per-hit breakdown text: which field(s) each term hit."""
    parts = []
    for field in ("title", "tags", "body"):
        terms = contrib.get(field) or []
        if terms:
            parts.append("{}=[{}]".format(field, ",".join(terms)))
    return "; ".join(parts) if parts else "(none)"


# ── Lexical index (D14/D15) ──────────────────────────────────────────────
# FTS5 + BM25 is the lexical arm of the measured target architecture
# (DESIGN.md). The index is a PERSISTENT but OPTIONAL artefact: when it is
# absent or unusable, find falls back to the substring scan with one stderr
# note — never a hard fail (D15). Field weights title 3 / tags 2 / body 1 are
# the same ratios the substring scorer used, so the comparison isolates the
# retrieval model, not the weighting (eval/fts_arm.py:52-55).
#
# Query-side tokenization vs. index-side tokenization (I01, T04 review
# 2026-07-26): two layers apply in sequence, deliberately, not by accident.
#   1. Python tokenize() (word-splitting, lowercasing, underscore as a
#      separator) decides QUERY TERM BOUNDARIES before a term is quoted into
#      an FTS5 MATCH expression (Task 6: `'"{}"*'.format(t)`).
#   2. SQLite's own configured tokenizer (porter unicode61 remove_diacritics
#      2) is applied a SECOND time by FTS5 itself, both to the indexed
#      title/tags/body text at build time AND to each quoted term inside a
#      MATCH expression at query time — so diacritic-folding/stemming stays
#      symmetric on both sides even though Python's tokenize() alone does
#      not fold (ä stays ä at that layer).
# Verified empirically, not inferred: a query for the raw string "café"
# (unfolded) run as `docs MATCH '"café"*'` DOES match an indexed document
# containing "cafe"/"café_menü", and an unfolded `'"qualitätsmanagement"*'`
# DOES match the porter-stemmed indexed token, because FTS5 tokenizes quoted
# MATCH terms with the table's own tokenizer before comparing. Underscore
# splitting is likewise consistent between the two layers: unicode61 itself
# splits "build_tagvec" into "build"/"tagvec" (checked via fts5vocab), the
# same split tokenize() already performs — so there is no parity gap on
# that dimension either. Net effect: the FTS5 arm never needs Python-level
# folding: SQLite closes that gap on every MATCH.
# ───────────────────────────────────────────────────────────────────────
FTS_DIRNAME = ".fts"
FTS_FILENAME = "fts.sqlite"
# unicode61 folds diacritics (a German catalogue needs ä/ö/ü to match a/o/u);
# porter stems English morphology. Measured best variant: porter + prefix
# (R32).
FTS_TOKENIZER = "porter unicode61 remove_diacritics 2"
FTS_SCHEMA = (
    "CREATE VIRTUAL TABLE docs USING fts5("
    "path UNINDEXED, ctype UNINDEXED, title, tags, body, tokenize='{}')"
).format(FTS_TOKENIZER)
FTS_META_SCHEMA = "CREATE TABLE IF NOT EXISTS fts_meta(k TEXT PRIMARY KEY, v TEXT)"
# bm25() weight per column, in declaration order: path, ctype, title, tags, body.
FTS_BM25_WEIGHTS = "0.0, 0.0, 3.0, 2.0, 1.0"

def _fts_db_path(root):
    return os.path.join(root, FTS_DIRNAME, FTS_FILENAME)


def build_fts_index(root, db_path=None, include_topics=False):
    """(Re)build the FTS5 lexical index from the catalogue. Returns
    (n_concepts, db_path) where n_concepts is active + archived combined.
    Local I/O only — no network, stdlib sqlite3. Builds into a .tmp sibling
    and os.replace()s it, so an interrupted build never leaves a
    half-written index in place of a working one.

    Also indexes `_archive/<bundle>/<cid>` at that exact path (R-11) —
    without it `--include-archive` is a decoration, since FTS is the
    default retrieval arm and no predicate can surface a concept the index
    never saw. Active and archived counts are recorded separately in
    fts_meta (see _fts_index_stale) rather than summed, because a summed
    counter stays constant across an archive move — `git mv` preserves the
    file's mtime, so neither signal alone would catch the move."""
    db_path = db_path or _fts_db_path(root)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    tmp = db_path + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    conn = sqlite3.connect(tmp)
    n_active = 0
    n_archived = 0
    newest = 0.0
    try:
        conn.execute(FTS_SCHEMA)
        conn.execute(FTS_META_SCHEMA)

        def _index_bundle(b, bp, path_prefix):
            nonlocal newest
            count = 0
            for cid, ap in iter_concepts(bp):
                raw = read_file(ap)
                fm, body = split_frontmatter(raw)
                title = _dequote(fm.get("title", "")) or cid
                conn.execute(
                    "INSERT INTO docs(path, ctype, title, tags, body)"
                    " VALUES (?, ?, ?, ?, ?)",
                    ("{}{}/{}".format(path_prefix, b, cid), fm.get("type", ""),
                     title, " ".join(extract_tags(raw)), body))
                count += 1
                mt = os.path.getmtime(ap)
                if mt > newest:
                    newest = mt
            return count

        for b in list_search_bundles(root, include_topics):
            n_active += _index_bundle(b, os.path.join(root, b), "")

        archive_root = os.path.join(root, "_archive")
        if os.path.isdir(archive_root):
            for b in list_search_bundles(archive_root, include_topics, root):
                n_archived += _index_bundle(
                    b, os.path.join(archive_root, b), "_archive/")

        conn.executemany(
            "INSERT OR REPLACE INTO fts_meta(k, v) VALUES (?, ?)",
            [("n_concepts", str(n_active)), ("n_archived", str(n_archived)),
             ("newest_mtime", repr(newest)),
             ("includes_topics", "1" if include_topics else "0")])
        conn.commit()
    finally:
        conn.close()
    os.replace(tmp, db_path)
    return n_active + n_archived, db_path


def _fts_index_stale(root, conn, include_topics=False, check_corpus=True):
    """True when the catalogue gained/lost concepts (active OR archived) or
    any concept file is newer than the newest one seen at build time.
    stat()-only — it never reads a concept body, which is exactly what
    makes it cheaper than the full scan it replaces. An unreadable/missing
    meta table counts as stale — this also covers an index built before
    R-11 landed, whose fts_meta has no 'n_archived' key: the KeyError below
    is caught the same way a missing table already is, so an old index is
    reported stale (clean rebuild) rather than crashing this check.

    Active and archived are compared as two separate counters, not their
    sum (R-11/AC2-AC3). A summed counter would stay constant across an
    archive move: `git mv` preserves the file's mtime, so the move would
    be invisible to both signals at once and the index would keep serving
    the concept under its stale, active path."""
    try:
        meta = dict(conn.execute("SELECT k, v FROM fts_meta").fetchall())
        n_active_idx = int(meta["n_concepts"])
        n_archived_idx = int(meta["n_archived"])
        newest_idx = float(meta["newest_mtime"])
        stored_topics = meta.get("includes_topics", "0") == "1"
        if check_corpus and stored_topics != include_topics:
            return True
    except (sqlite3.DatabaseError, KeyError, ValueError, TypeError):
        return True
    # A query against a broad index is current for its stored broad corpus;
    # the query predicate hides topic rows for the default narrow view.
    count_topics = include_topics if check_corpus else stored_topics
    n_active = 0
    n_archived = 0
    newest = 0.0
    for b in list_search_bundles(root, count_topics):
        for _cid, ap in iter_concepts(os.path.join(root, b)):
            n_active += 1
            mt = os.path.getmtime(ap)
            if mt > newest:
                newest = mt
    archive_root = os.path.join(root, "_archive")
    if os.path.isdir(archive_root):
        for b in list_search_bundles(archive_root, count_topics, root):
            for _cid, ap in iter_concepts(os.path.join(archive_root, b)):
                n_archived += 1
                mt = os.path.getmtime(ap)
                if mt > newest:
                    newest = mt
    return (n_active != n_active_idx or n_archived != n_archived_idx
            or newest > newest_idx)


def cmd_build_index(root, args):
    """(Re)build the FTS index, or — with --if-stale — skip when it is
    already current. Skips only when the artefact both exists and passes
    _fts_index_stale()'s stat()-only check; absent or stale still gets the
    full rebuild path (D02). Without the flag this is unconditional, exactly
    as before the flag existed — a caller that omits --if-stale must see
    byte-identical behaviour to the pre-flag CLI."""
    if getattr(args, "if_stale", False):
        db_path = _fts_db_path(root)
        if os.path.isfile(db_path):
            conn = sqlite3.connect(db_path)
            try:
                stale = _fts_index_stale(root, conn, getattr(args, "include_topics", False))
            finally:
                conn.close()
            if not stale:
                print("index is current, skipping rebuild -> {}".format(db_path))
                return
    n, db = build_fts_index(root, include_topics=getattr(args, "include_topics", False))
    print("indexed {} concept(s) -> {}".format(n, db))


def cmd_build_semantic_index(root, args):
    """Fill .tagvec/tag_vectors.sqlite's concept_emb table for every concept
    still missing a voyage-3-large embedding (OKFT-wsne) -- the trigger the
    producer (cli/embeddings/build_tagvec.py) never had. Offline half is
    plan_concept_delta(); network half is embed_voyage(), run batch-by-batch
    through embed_resilient() so one bad batch (LL-08) does not throw away
    an already-embedded run.

    With --if-stale, skip the whole call when semantic_coverage()'s PATH-SET
    probe already reports every on-disk concept embedded -- same D02 shape
    as cmd_build_index's --if-stale: skip only when the artefact both
    exists and is current, absent/partial still gets the full run, and
    omitting the flag stays unconditional exactly as before the flag
    existed. The probe is semantic_coverage(), not a row count, because
    concept_emb keeps orphan rows for deleted concepts (OKFT-3520) that
    would let a row-count check report complete while paths are missing.

    Never raises: a missing VOYAGE_API_KEY or an exhausted-retries network
    failure degrades to a stderr `note: ...` (same shape as the existing
    lexical-index degradation notices) and a clean return, because this is
    meant to run unattended from a SessionStart hook, detached, and must
    never surface a traceback into a session transcript. The query path
    (`find`) is untouched by any of this -- it never calls this producer
    itself (D13/D16)."""
    db_path = _tagvec_db_path(root)
    if getattr(args, "if_stale", False):
        bundles = list_indexable_bundles(root)
        paths = ["{}/{}".format(b, cid) for b in bundles
                 for cid, _ap in iter_concepts(os.path.join(root, b))]
        cov = semantic_coverage(root, paths)
        if cov is not None and cov[0] >= cov[1]:
            print("semantic index is current, skipping rebuild -> {}".format(db_path))
            return
    if not os.environ.get("VOYAGE_API_KEY"):
        print("note: semantic index build skipped (VOYAGE_API_KEY not set) "
              "-- run again once it is set, or set it before the next "
              "SessionStart hook run", file=sys.stderr)
        return
    bt = catalogue._load_build_tagvec()
    try:
        delta = bt.plan_concept_delta(root, SEMANTIC_MODEL, db_path)
        written = 0
        incomplete = False
        max_items, max_chars = bt.BATCH_LIMITS[SEMANTIC_MODEL]
        for batch in bt.batches(delta, max_items, max_chars):
            vectors = bt.embed_resilient(
                bt.embed_voyage, [t for _path, t, _key in batch],
                "voyage concepts {}..".format(batch[0][0]))
            if vectors is None:
                incomplete = True
                continue
            rows = [
                (key, path, SEMANTIC_MODEL, bt.MODELS[SEMANTIC_MODEL]["dim"],
                 bt.pack_vec(vec))
                for (path, _text, key), vec in zip(batch, vectors)
            ]
            bt.write_concept_rows(db_path, rows)
            written += len(rows)
        print("embedded {} concept(s) -> {}".format(written, db_path))
        if incomplete:
            print("note: semantic index build incomplete -- {} concept(s) "
                  "left unembedded after retries; rerun to pick up the "
                  "rest".format(len(delta) - written), file=sys.stderr)
    except Exception as exc:
        print("note: semantic index build failed ({}: {}) -- lexical arm "
              "unaffected".format(type(exc).__name__, exc), file=sys.stderr)


def _like_escape(value):
    """Escape a value for safe use inside a SQL LIKE pattern bound with
    `ESCAPE '\\'`. `\\`, `%` and `_` are the three characters LIKE gives
    special meaning to (backslash because it is about to become the escape
    character itself); every one of them is a literal, user-controlled byte
    that must survive verbatim, or a scope value collides with a
    similarly-named foreign bundle (I01/B01, again, one level down: inside a
    single arm's own pattern rather than between arms). Backslash MUST be
    escaped first, or escaping `%`/`_` afterwards would double-escape the
    backslashes those two steps just introduced."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class FindFilters:
    """--scope/--type/--tag/--include-archive as ONE value, with the
    predicate defined once.

    I01, the architectural finding behind B01: the same three filters used to
    be implemented three times — SQL in the FTS arm, a Python scan in the
    substring arm, nothing at all in the semantic arm — and travelled as three
    loose positional arguments through five signatures. Nothing made an arm
    apply them, so the semantic arm silently answered unfiltered and a scoped
    query returned concepts from other bundles entirely. R-08 adds a fourth
    dimension deliberately INTO this object rather than beside it, on pain of
    repeating exactly that finding.

    The filters describe the ANSWER, not one arm of it. Whichever arm ends up
    owning the ranking (fuse_conditional decides per query), the same
    predicate holds:

      scope            path is the scope itself or lives beneath it
      type             exact equality on the concept's frontmatter `type`
      tag              WHOLE-tag membership — "tail" must never hit "tailscale"
      include_archive  a path under `_archive/` is no match unless set (R-08);
                        while it IS set, scope compares against the path with
                        its leading `_archive/` segment stripped, so a scoped
                        query reaches the archived concepts of that same
                        bundle and no other (R-09)

    Arms consume it one of two ways, and both hand back what they did NOT
    cover so that skipping a dimension is visible instead of silent:
    sql_where() for arms that filter in the database, matches()/matches_loaded()
    for arms that walk the file tree."""

    __slots__ = ("scope", "type", "tag", "include_archive", "include_topics", "corpus_bundles")

    _ARCHIVE_PREFIX = "_archive/"
    # Escaped once here rather than re-derived at each of the two LIKE call
    # sites (review B01 round 3, okf-cli-pn72): the constant's own leading
    # `_` is exactly as much a wildcard inside a bound LIKE pattern as a
    # user's scope value is, and two independent `_like_escape(...)` call
    # sites is how the first fix already missed one of them.
    _ARCHIVE_PREFIX_ESC = _like_escape(_ARCHIVE_PREFIX)

    def __init__(self, scope=None, type=None, tag=None, include_archive=False, include_topics=False, corpus_bundles=None):
        # Normalize "" to None once, here: cmd_find reads these off argparse
        # and the MCP layer passes empty strings for "unset".
        self.scope = (scope or "").rstrip("/") or None
        self.type = type or None
        self.tag = tag or None
        self.include_archive = bool(include_archive)
        self.include_topics = bool(include_topics)
        self.corpus_bundles = tuple(corpus_bundles or ())

    def __bool__(self):
        # Deliberately NOT include_archive: this reports whether scope/type/
        # tag hold a restriction, which is what sql_where()'s residual
        # assertions and callers reason about. include_archive's own default
        # (False) is a restriction too, but path_in_scope() enforces it
        # unconditionally in matches()/matches_loaded() regardless of this
        # value, so nothing needs it folded in here.
        return bool(self.scope or self.type or self.tag)

    def __repr__(self):
        return "FindFilters(scope={!r}, type={!r}, tag={!r}, include_archive={!r})".format(
            self.scope, self.type, self.tag, self.include_archive)

    def sql_where(self, columns):
        """(sql_fragment, params, residual) for a table that natively carries
        the dimensions named in `columns` ({dimension: column_name}).

        `residual` is a FindFilters holding exactly the dimensions this SQL did
        NOT cover — the caller must run it through matches()/matches_loaded()
        or it drops them. That return value IS the contract: a table lacking a
        column no longer means the filter quietly disappears.

        Column names come from caller literals, never from user input, so
        formatting them into the SQL is safe; every VALUE is still bound."""
        sql, params = "", []
        covered = set()
        if self.corpus_bundles and "scope" in columns:
            col = columns["scope"]
            branches = []
            for b in self.corpus_bundles:
                esc_bundle = _like_escape(b)
                archived = self._ARCHIVE_PREFIX + b
                branches.extend([
                    "{} = ?".format(col),
                    "{} LIKE ? ESCAPE char(92)".format(col),
                    "{} = ?".format(col),
                    "{} LIKE ? ESCAPE char(92)".format(col),
                ])
                params.extend([
                    b, esc_bundle + "/%",
                    archived, _like_escape(archived) + "/%",
                ])
            sql += " AND (" + " OR ".join(branches) + ")"
            covered.add("corpus")
        if self.scope and "scope" in columns:
            col = columns["scope"]
            # R-09: an archived concept of this scope lives at
            # `_archive/<scope>[/...]`, not `<scope>[/...]` — match both
            # forms here; visibility of the archived form is decided below,
            # by the include_archive predicate, not by this OR-chain.
            #
            # Every LIKE branch binds an ESCAPED copy of the scope value
            # (review B01, okf-cli-pn72): scope is user-controlled, and an
            # unescaped `_`/`%` in it is a LIKE wildcard, not a literal — a
            # scope of "my_bundle" would otherwise also match a foreign
            # bundle "myXbundle". The `=` branches stay on the raw value;
            # exact equality never interprets wildcards.
            esc_scope = _like_escape(self.scope)
            sql += (" AND ({0} = ? OR {0} LIKE ? ESCAPE '\\'"
                    " OR {0} = ? OR {0} LIKE ? ESCAPE '\\')".format(col))
            params.extend([
                self.scope, esc_scope + "/%",
                self._ARCHIVE_PREFIX + self.scope,
                self._ARCHIVE_PREFIX_ESC + esc_scope + "/%",
            ])
            covered.add("scope")
        if self.type and "type" in columns:
            sql += " AND {} = ?".format(columns["type"])
            params.append(self.type)
            covered.add("type")
        if self.tag and "tag" in columns:
            # whole-tag match: the column is a space-joined slug list, so pad
            # both sides rather than substring-matching.
            sql += " AND instr(' ' || {} || ' ', ' ' || ? || ' ') > 0".format(
                columns["tag"])
            params.append(self.tag)
            covered.add("tag")
        if not self.include_archive and "scope" in columns:
            # R-08's default exclusion, on the same column scope uses — only
            # a table carrying `path` can tell an archived concept from an
            # active one. ESCAPE is not optional (R-10): `_` is a LIKE
            # single-char wildcard, so an unescaped pattern would also
            # exclude a bundle literally named "xarchive".
            sql += " AND {} NOT LIKE '{}%' ESCAPE '\\'".format(
                columns["scope"], self._ARCHIVE_PREFIX_ESC)
        residual = FindFilters(
            scope=None if "scope" in covered else self.scope,
            type=None if "type" in covered else self.type,
            tag=None if "tag" in covered else self.tag,
            include_archive=self.include_archive,
            include_topics=self.include_topics, corpus_bundles=self.corpus_bundles,
        )
        return sql, params, residual

    def path_in_scope(self, path):
        """R-08/R-09 live here, next to scope, because they are the same
        predicate: a path under `_archive/` is invisible unless
        include_archive is set, and once it IS set, scope is compared
        against the path with that leading segment stripped — so
        `--scope <bundle> --include-archive` reaches the archived concepts
        of exactly that bundle, never another's. This is the one named,
        reusable spot: any future caller that walks paths in Python (not
        SQL) gets both rules by calling this, not by re-deriving them."""
        archived = path.startswith(self._ARCHIVE_PREFIX)
        compared = path[len(self._ARCHIVE_PREFIX):] if archived else path
        if (self.corpus_bundles
                and not any(compared == b or compared.startswith(b + "/")
                            for b in self.corpus_bundles)):
            return False
        if archived and not self.include_archive:
            return False
        if not self.scope:
            return True
        return compared == self.scope or compared.startswith(self.scope + "/")

    def matches_loaded(self, path, fm, text):
        """Full predicate for a concept whose file the caller already read.
        Covers all three dimensions — an arm that has the text in hand has no
        reason to check only some of them."""
        if not self.path_in_scope(path):
            return False
        if self.type and fm.get("type", "") != self.type:
            return False
        if self.tag and self.tag not in extract_tags(text):
            return False
        return True

    def matches(self, root, path):
        """Same predicate, reading the concept file when needed. Checks scope
        first so a filtered-out path costs no disk read. A path that no longer
        resolves fails — _hydrate_hit drops it anyway.

        No `if not self: return True` shortcut here (there used to be one):
        include_archive's default is itself a restriction, so even an
        otherwise "empty" FindFilters() must still run path_in_scope()."""
        if not self.path_in_scope(path):
            return False
        if not (self.type or self.tag):
            return True
        ap = os.path.join(root, path + ".md")
        if not os.path.isfile(ap):
            return False
        text = read_file(ap)
        fm, _body = split_frontmatter(text)
        return self.matches_loaded(path, fm, text)


# Column maps naming which dimensions each table can filter natively. The FTS
# `docs` table carries all three; the embedding cache carries only the path,
# which is why semantic_ranking gets a non-empty residual to apply itself.
FTS_FILTER_COLUMNS = {"scope": "path", "type": "ctype", "tag": "tags"}
EMB_FILTER_COLUMNS = {"scope": "path"}


def _fts_ranking(root, query, limit, filters, notify=True):
    """[(path, positive_score), ...] best first, or None when the index is
    unusable (absent or corrupt) — None is the caller's signal to degrade to
    the substring scan (D15). bm25() is lower-is-better, so it is negated.
    Filters run inside SQL against the UNINDEXED ctype/path columns and the
    indexed tags column, so filtering never re-reads a concept file.

    `notify` exists because a degradation note describes the INVOCATION, not
    the call: --expand-tags reruns this arm over the widened term set within
    the same `find`, and an unconditional print would emit the same note
    twice (PF-4 violation — exactly one note per degraded arm). The rescue
    rerun passes notify=False; it is a second look at the same index and has
    nothing new to report."""
    db = _fts_db_path(root)
    if not os.path.isfile(db):
        # D15 requires a note for EVERY degradation, absent included — the
        # semantic arm does the same for its missing cache. Silent degradation
        # is the failure mode where "running fine" and "running on the weaker
        # arm" look identical from the outside. It goes to stderr, so stdout
        # stays byte-identical to the pre-plan output.
        if notify:
            print("note: lexical index absent — falling back to substring "
                  "scan; run `okf-cli build-index` for BM25 ranking",
                  file=sys.stderr)
        return None
    terms = tokenize(query)
    if not terms:
        return []
    expr = " OR ".join('"{}"*'.format(t.replace('"', "")) for t in terms)
    sql = ("SELECT path, bm25(docs, {}) AS r FROM docs WHERE docs MATCH ?"
           .format(FTS_BM25_WEIGHTS))
    params = [expr]
    # `docs` carries all three dimensions, so the residual is empty and there
    # is nothing left for this arm to enforce in Python.
    where, where_params, residual = filters.sql_where(FTS_FILTER_COLUMNS)
    sql += where
    params.extend(where_params)
    assert not residual, "docs table covers every filter dimension"
    sql += " ORDER BY r, path LIMIT ?"  # path is the tiebreaker for equal
    # bm25 scores (OKFT-rx72): the FTS5 doc-insertion order that would
    # otherwise decide ties comes from os.walk() at build-index time, which
    # is not a contract SQLite is bound to preserve run over run — an
    # explicit secondary key makes tied ranks reproducible instead of
    # accidental.
    params.append(limit)
    try:
        conn = sqlite3.connect(db)
        try:
            # Run the real query FIRST. A corrupt file raises DatabaseError
            # here (garbage bytes still open() fine — sqlite3 does not
            # validate the format until the first read), caught below by the
            # single except. _fts_index_stale() has its own except branch
            # that SWALLOWS DatabaseError and reports "stale" (T05 AC7,
            # locked by FtsIndexStaleDegrades) — calling it before the query
            # would print a second, misleading "stale" note ahead of the
            # "unusable" one for the exact same corrupt file (caught by
            # adversarial testing, not in the original plan). Checking
            # staleness only after a successful query keeps the corrupt path
            # at exactly one stderr note without changing what
            # _fts_index_stale() itself reports when called directly.
            rows = conn.execute(sql, params).fetchall()
            topic_corpus_missing = (
                filters.include_topics and _fts_index_includes_topics(root) is False)
            if (notify and not topic_corpus_missing
                    and _fts_index_stale(
                        root, conn, filters.include_topics, check_corpus=False)):
                print("note: lexical index is stale (catalogue changed since "
                      "build) — run `okf-cli build-index`", file=sys.stderr)
        finally:
            conn.close()
    except sqlite3.DatabaseError:
        if notify:
            print("note: lexical index unusable — falling back to substring "
                  "scan", file=sys.stderr)
        return None
    return [(p, -r) for p, r in rows]


def _hydrate_hit(root, path, terms, score, provenance, cosine=None):
    """Build the hit dict cmd_find prints, reading the concept file itself.
    Only ever called for the <= limit paths that actually rank, which is what
    makes the FTS path cheaper than the full scan. Returns None when the path
    no longer resolves (index or embedding cache newer than the file tree)."""
    ap = os.path.join(root, path + ".md")
    if not os.path.isfile(ap):
        return None
    fm, body = split_frontmatter(read_file(ap))
    hit = {
        "score": score,
        "path": path,
        "title": _dequote(fm.get("title", "")) or path.rsplit("/", 1)[-1],
        "type": fm.get("type", ""),
        "desc": _dequote(fm.get("description", "")),
        "snip": make_snippet(body, terms),
        "provenance": provenance,
    }
    sb = _dequote(fm.get("superseded_by", ""))
    if sb:
        hit["superseded_by"] = sb
    if cosine is not None:
        hit["cosine"] = cosine
    return hit


def _substring_ranking(root, query, terms, limit, filters):
    """The pre-FTS lexical arm, unchanged: substring matching with field
    weights title 3 / tags 2 / body 1 over a full scan. It stays in the tool
    as the degradation target for a missing or unusable index (D15) — its
    scoring, its `contrib` breakdown and its 6*len(terms) scale must remain
    byte-identical, because the frozen eval baseline was recorded against it.

    Scope is enforced twice on purpose, and the two are not redundant:
    resolve_scopes() confines the TRAVERSAL (so a filtered-out concept is
    never even read from disk), while matches_loaded() re-checks the assembled
    path. Only the second one is a predicate; dropping it would reopen the
    I01 gap the moment the traversal changes shape.

    `indexable_only` tracks `--include-topics`: the default uses the declared
    index corpus while an explicit topic search scans all bundles."""
    hits = []
    for _b, bp in resolve_scopes(
            root, filters.scope, filters.include_archive,
            indexable_only=not filters.include_topics):
        # B04: the path prefix is the SCOPE's position under root, not the
        # bundle name. iter_concepts() yields cids relative to `bp`, so with
        # --scope b/sub the old "{bundle}/{cid}" form printed `b/y` for a
        # concept that actually lives at `b/sub/y` — a path no okf-cli read
        # can resolve. Unscoped, relpath(bp, root) IS the bundle name, so the
        # frozen eval baseline sees byte-identical output.
        prefix = os.path.relpath(bp, root).replace(os.sep, "/")
        for cid, ap in iter_concepts(bp):
            text = read_file(ap)
            fm, body = split_frontmatter(text)
            t = fm.get("type", "")
            if not filters.matches_loaded("{}/{}".format(prefix, cid), fm, text):
                continue
            title = fm.get("title", cid)
            tags = fm.get("tags", "")
            hay_title = title.lower()
            hay_tags = tags.lower()
            hay_body = body.lower()
            score = 0
            contrib = {"title": [], "tags": [], "body": []}
            for term in terms:
                if hay_title.count(term):
                    score += 3
                    contrib["title"].append(term)
                if hay_tags.count(term):
                    score += 2
                    contrib["tags"].append(term)
                if hay_body.count(term):
                    score += 1
                    contrib["body"].append(term)
            if score:
                hit = {
                    "score": score, "path": "{}/{}".format(prefix, cid),
                    "title": title, "type": t,
                    "desc": _dequote(fm.get("description", "")),
                    "snip": make_snippet(body, terms), "contrib": contrib,
                    "provenance": "lexical",
                }
                sb = _dequote(fm.get("superseded_by", ""))
                if sb:
                    hit["superseded_by"] = sb
                hits.append(hit)
    hits.sort(key=lambda h: -h["score"])
    return hits[:limit]


def _rank_lexically(root, query, terms, limit, filters, notify=True):
    """(hits, max_score) — the FTS arm when the index is usable, otherwise the
    substring scan (D15). The two arms report on different scales, so the
    scale is returned with the result instead of being recomputed by the
    caller: 0..100 for BM25 (relative to this run's own top hit), and
    6*len(terms) for the substring fallback, which keeps that path
    byte-identical to pre-plan output."""
    ranked = _fts_ranking(root, query, limit, filters, notify=notify)
    if ranked is None:
        return (_substring_ranking(root, query, terms, limit, filters),
                6 * len(terms))
    top = ranked[0][1] if ranked else 1.0
    hits = []
    for path, s in ranked:
        hit = _hydrate_hit(root, path, terms,
                           int(round(100 * s / top)) if top else 0, "lexical")
        if hit is not None:
            hits.append(hit)
    return hits, 100


# 8c (D04) — semantic arm (renamed from "semantic backstop" in T07/D12: on a
# paraphrase query it OWNS the ranking, it does not just fill gaps). Fires
# only as cmd_find's gate below decides (zero/weak/ambiguous keyword hits),
# reads .tagvec's concept_emb table (title+body scope, cli/embeddings/
# build_tagvec.py) via stdlib sqlite3, and embeds the query with a REMOTE
# voyage-3-large call (Voyage AI HTTP API, D13) — best-effort: any failure
# (cache absent, key missing, backend unreachable) degrades to keyword-only
# with a one-line stderr note, never raises, never blocks the keyword path
# (Global Constraints). bge-m3 is NOT a runtime fallback here (D16).
# Post-review fix (F01, 2026-07-25): the original absolute score/max_score
# ratio gate misclassified legitimate literal top-1 hits as "weak" — this
# repo's OWN golden fixtures have literal min_score_ratio well below any
# sane absolute threshold (S1=0.30, S2=0.25, S4=0.55), because a partial
# multi-term title/tag/body match is a perfectly confident top-1, not a weak
# one; the ratio depends on term count and per-field weighting, not on
# actual retrieval confidence. Replaced with a margin gate: fire the
# backstop on zero hits OR when the keyword top-1 has no clear lead over
# the runner-up (ambiguous ranking) — never on an absolute ratio.
SEMANTIC_MARGIN_RATIO = 0.5  # top1 >= (1 + ratio) * top2, i.e. top1 must
                              # lead the runner-up by at least 1.5x to count
                              # as "confident" enough for the lexical arm to
                              # OWN the ranking (D12). Copied from
                              # eval/hybrid_eval.py:151, NOT calibrated: on
                              # the real catalogue it fires ~1 of 48 queries
                              # (OKFT-8l96 SC-001), so R43 ~ semantic arm
                              # alone. Honest fallback, not a tuning knob.
# SEMANTIC_NOISE_RATIO removed (T08/D12): it was a crutch for the old
# pin+blend rule, forcing the backstop to fire against a noisy substring
# top-1 regardless of margin. Under conditional handover a noisy lexical
# arm simply does not own the ranking (its top-1 has no clear margin, or
# there IS no meaningful runner-up comparison at all when hits are sparse
# noise), so the absolute floor is redundant — R43 measured the rule
# without it. Do not resurrect it as a second, competing gate.
# D13 — voyage-3-large is the productive semantic model: MRR 0.452 vs 0.150
# for bge-m3 on the unbiased query set, zero-hit 0.167 vs 0.646 (R42). That is
# the difference between usable and not, not a tuning gap. The accepted price
# is a network call and an API key in the request path; D16 makes the
# degradation two-stage (voyage -> lexical only), so bge-m3 is NOT a runtime
# fallback and concept_emb holds voyage rows only.
SEMANTIC_MODEL = "voyage-3-large"
VOYAGE_EMBED_URL = "https://api.voyageai.com/v1/embeddings"
VOYAGE_EMBED_TIMEOUT = 10


def _tagvec_db_path(root):
    return os.path.join(root, ".tagvec", "tag_vectors.sqlite")


def _load_concept_vectors(db_path, model, filters=None):
    """([(path, [float, ...]), ...], residual) for every concept_emb row of
    `model`, or (None, _) if the cache file/table is absent or has no rows for
    this model (the graceful-skip signal semantic_ranking() acts on).

    concept_emb carries only the path, so of the three filter dimensions this
    query can enforce scope alone — with the SAME predicate the FTS arm uses,
    since concept_emb.path and docs.path share the `<bundle>/<concept>` form.
    Enforcing it in SQL rather than after ranking keeps --limit meaningful: an
    out-of-scope concept never occupies a slot it would then be dropped from
    (B01). The returned `residual` carries type/tag for the caller to apply."""
    filters = filters or FindFilters()
    where, where_params, residual = filters.sql_where(EMB_FILTER_COLUMNS)
    if not os.path.isfile(db_path):
        return None, residual
    scope = filters.scope
    sql = "SELECT path, dim, vec FROM concept_emb WHERE model = ?" + where
    params = [model] + where_params
    try:
        conn = sqlite3.connect(db_path)
        try:
            rows = conn.execute(sql, params).fetchall()
            # "no rows" means two different things once a scope narrows the
            # query, and they must not share a return value: a cache with no
            # embeddings for this model is a DEGRADATION (None -> stderr
            # note), while a populated cache holding nothing inside the
            # requested scope is a correct, complete, empty answer ([] -> no
            # note). Conflating them would print "embeddings absent" at the
            # user every time they scoped to a bundle that simply has none.
            if not rows and scope:
                have_any = conn.execute(
                    "SELECT 1 FROM concept_emb WHERE model = ? LIMIT 1",
                    (model,)).fetchone()
                if have_any:
                    return [], residual
        finally:
            conn.close()
    except sqlite3.DatabaseError:
        return None, residual
    if not rows:
        return None, residual
    return ([(path, list(struct.unpack("<{}f".format(dim), vec_blob)))
             for path, dim, vec_blob in rows], residual)


# One CLI invocation answers one query, and both the semantic arm and (when
# enabled) tag expansion embed the SAME string. Cache it so --expand-tags
# costs zero extra network calls rather than doubling them.
_QUERY_VEC_CACHE = {}


def _query_vector(text):
    """Cached _embed_query_voyage(). Raises exactly what it raises, so every
    caller keeps its own degradation behaviour."""
    if text not in _QUERY_VEC_CACHE:
        _QUERY_VEC_CACHE[text] = _embed_query_voyage(text)
    return _QUERY_VEC_CACHE[text]


def _embed_query_voyage(text):
    """Best-effort Voyage embed call for the query string. NETWORK — reached
    only when the semantic arm actually runs (never at import time, never
    unconditionally). `input_type="query"` is the asymmetric query form the
    measurement used (eval/hybrid_eval.py:73-80); documents were embedded with
    input_type="document" by the producer. Any failure propagates so the
    caller degrades gracefully; this function never catches."""
    api_key = os.environ.get("VOYAGE_API_KEY")
    if not api_key:
        raise RuntimeError("VOYAGE_API_KEY not set")
    req = urllib.request.Request(
        VOYAGE_EMBED_URL,
        data=json.dumps({
            "model": SEMANTIC_MODEL,
            "input": [text],
            "input_type": "query",
        }).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + api_key,
        },
    )
    with urllib.request.urlopen(req, timeout=VOYAGE_EMBED_TIMEOUT) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return body["data"][0]["embedding"]


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _load_tag_vectors(db_path, model):
    """[(tag, [float, ...]), ...] from the `emb` table, or None when the cache
    or the model's rows are absent — mirrors _load_concept_vectors()."""
    if not os.path.isfile(db_path):
        return None
    try:
        conn = sqlite3.connect(db_path)
        try:
            rows = conn.execute(
                "SELECT tag, dim, vec FROM emb WHERE model = ?", (model,)
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.DatabaseError:
        return None
    if not rows:
        return None
    return [(tag, list(struct.unpack("<{}f".format(dim), blob)))
            for tag, dim, blob in rows]


def _expand_query_tags(root, query, top_k=3, floor=0.6):
    """Registered tag slugs semantically near the query (Q05). Reuses the
    query vector the semantic arm needs anyway, which is what makes Q06 moot:
    a query term that is not a registered tag never needs its own embedding
    call. Returns [] on any degradation — expansion is an enhancement, never a
    precondition. The floor exists because a nearest neighbour is always
    returned otherwise; unlike the concept case (R34, no separable floor),
    tag slugs are short, clean labels where a cutoff is defensible — that is
    exactly what Step 6 measures."""
    vectors = _load_tag_vectors(_tagvec_db_path(root), SEMANTIC_MODEL)
    if not vectors:
        return []
    try:
        qvec = _query_vector(query)
    except Exception:
        return []
    ranked = sorted(((_cosine(qvec, v), tag) for tag, v in vectors),
                    key=lambda x: -x[0])
    return [tag for score, tag in ranked[:top_k] if score >= floor]


def _keyword_top1_is_confident(hits):
    """True when the lexical arm may OWN the ranking: it has hits and either a
    single one (nothing to be ambiguous against) or a top-1 leading the
    runner-up by the measured margin.

    The comparison is `top1 >= (1 + SEMANTIC_MARGIN_RATIO) * top2`, i.e.
    top1 >= 1.5x top2 — copied from the rule that actually produced R43's
    0.437 (eval/hybrid_eval.py:151). The pre-plan code computed
    `(top1-top2)/top1 >= SEMANTIC_MARGIN_RATIO`, which is top1 >= 2x top2: a
    stricter bar that hands over to the semantic arm LESS often than what was
    measured. Do not "simplify" it back."""
    if not hits:
        return False
    if len(hits) == 1:
        return True
    top1, top2 = hits[0]["score"], hits[1]["score"]
    if top1 <= 0:
        return False
    return top1 >= (1 + SEMANTIC_MARGIN_RATIO) * top2


def semantic_ranking(root, query, limit, filters):
    """[(cosine, path), ...] best first, or [] with one stderr note on any
    degradation (cache/table absent, no API key, backend unreachable).

    Renamed from semantic_backstop(): under conditional handover this arm is
    no longer a fallback that only fills gaps — on a paraphrase query it OWNS
    the ranking (D12). It also no longer takes exclude_paths, because
    deduplication happens in fusion, after the owner has been decided.

    B01: the filters are not the lexical arm's private business. Whichever arm
    ends up owning the ranking, --scope/--type/--tag describe the ANSWER, so
    they are enforced here too. Scope rides along in the cache query; the
    residual (type/tag, absent from concept_emb) is applied while walking the
    ranked list — lazily, stopping at `limit`, so it costs one frontmatter
    read per candidate actually considered rather than one per embedding."""
    vectors, residual = _load_concept_vectors(
        _tagvec_db_path(root), SEMANTIC_MODEL, filters)
    if vectors is None:
        print("note: semantic arm skipped (.tagvec cache/concept embeddings "
              "absent) — lexical results only", file=sys.stderr)
        return []
    if not vectors:
        return []
    try:
        qvec = _query_vector(query)
    except Exception as exc:
        print("note: semantic arm skipped (embedding backend unavailable: {})"
              " — lexical results only".format(exc), file=sys.stderr)
        return []
    # path is the tiebreaker for equal cosine values (OKFT-rx72): the SQL
    # row order feeding this sort has no ORDER BY of its own, so without a
    # secondary key here two runs could stably-sort equal cosines in
    # whatever order concept_emb happened to return them in.
    ranked = sorted(((_cosine(qvec, vec), path) for path, vec in vectors),
                    key=lambda x: (-x[0], x[1]))
    if not residual:
        return ranked[:limit]
    out = []
    for cosine, path in ranked:
        if len(out) >= limit:
            break
        if residual.matches(root, path):
            out.append((cosine, path))
    return out


def _semantic_hit_dicts(root, query, limit, filters):
    """semantic_ranking() results, hydrated into the same hit-dict shape the
    lexical arm produces so fusion and printing treat both uniformly.
    Semantic score is round(100 * cosine) — the same 0..100 scale the FTS arm
    reports, which makes the printed number comparable without implying the
    two are fused by score (they are not; see fuse_conditional)."""
    terms = tokenize(query)
    out = []
    for cosine, path in semantic_ranking(root, query, limit, filters):
        hit = _hydrate_hit(root, path, terms, int(round(100 * cosine)),
                           "semantic", cosine=cosine)
        if hit is not None:
            out.append(hit)
    return out


def fuse_conditional(lexical_hits, semantic_hits, limit):
    """(fused_hits, lexical_owned) — conditional HANDOVER, not blending (D12).

    Measured on the unbiased query set: blending a lexical list that is pure
    noise on paraphrases (zero-hit 1.000) into a working semantic list costs
    more than it adds, whether by score interleaving (MRR 0.029) or by RRF
    (0.201). On literal queries the lexical arm is the better one. So decide
    per query WHICH arm owns the ranking instead of averaging them: worst case
    0.437 across both regimes (R43).

    The owning arm's list comes first in its own order; the other arm is
    appended behind it, never in front. Duplicates keep the owning arm's entry
    (and therefore its provenance), so a concept both arms found is not
    reported twice."""
    lexical_owned = _keyword_top1_is_confident(lexical_hits)
    primary = lexical_hits if lexical_owned else semantic_hits
    secondary = semantic_hits if lexical_owned else lexical_hits
    out, seen = [], set()
    for hit in list(primary) + list(secondary):
        if hit["path"] in seen:
            continue
        seen.add(hit["path"])
        out.append(hit)
    return out[:limit], lexical_owned


def _zero_hit_suggestions(root, query, limit=5):
    """Registered tag slugs closest to the query's terms — the reformulation
    hint a zero hit hands back (Q13). difflib only: no network, no vectors, so
    this works on the fully degraded path too."""
    tags = sorted(all_tags(root))
    if not tags:
        return []
    out = []
    for term in tokenize(query):
        for cand in difflib.get_close_matches(term, tags, n=limit, cutoff=0.7):
            if cand not in out:
                out.append(cand)
    return out[:limit]


def _fts_index_includes_topics(root):
    db = _fts_db_path(root)
    if not os.path.isfile(db):
        return None
    try:
        conn = sqlite3.connect(db)
        try:
            row = conn.execute("SELECT v FROM fts_meta WHERE k = 'includes_topics'").fetchone()
        finally:
            conn.close()
        return bool(row and row[0] == "1")
    except sqlite3.DatabaseError:
        return None


def cmd_find(root, args):
    if getattr(args, "include_topics", False) and _fts_index_includes_topics(root) is False:
        print("note: lexical index excludes topic folders — run `okf-cli build-index --include-topics`", file=sys.stderr)
    terms = tokenize(args.query)
    if not terms:
        print("(empty query)")
        return
    breakdown = getattr(args, "breakdown", False)
    # I01: built ONCE, here, and handed to every arm as a single value. The
    # three filters used to travel as loose positional arguments, which is how
    # the semantic arm ended up never receiving them at all (B01).
    # 8a (FIL03/FIL04): --scope narrows via resolve_scopes(); without it,
    # behavior is unchanged (resolve_scopes(root, None) == list_bundles(root)
    # iteration, as before). --bundle was a duplicate alias, removed D02
    # (PO-grilling 2026-07-26).
    include_topics = getattr(args, "include_topics", False)
    # Only a positive `bundle` declaration narrows the result predicate.
    # A catalogue without that declaration keeps its historic behavior:
    # archived-only bundles remain reachable via --include-archive.
    config = load_okf_config(root)
    corpus_bundles = (list_search_bundles(root) if config.get("bundle")
                      and not include_topics else None)
    filters = FindFilters(
        scope=getattr(args, "scope", None),
        type=getattr(args, "type", None),
        tag=getattr(args, "tag", None),
        include_archive=getattr(args, "include_archive", False),
        include_topics=include_topics,
        corpus_bundles=corpus_bundles,
    )
    hits, max_score = _rank_lexically(root, args.query, terms, args.limit,
                                      filters)

    # The semantic arm costs a network call, so run it only when it can
    # change the answer: whenever the lexical arm is not confident (it will
    # then OWN the ranking), or when a confident lexical list is too short to
    # fill --limit (it then fills the tail, exactly as measured).
    lexical_owned_provisionally = _keyword_top1_is_confident(hits)

    # T05/Q05 (experimental, off by default): when the unexpanded lexical arm
    # is not confident, widen the query with semantically near registered tags
    # and give the lexical arm a second chance. Deliberately NOT run when the
    # lexical arm is already confident — that query needs no rescue, and the
    # call would be pure cost (same rule the semantic arm follows below).
    if getattr(args, "expand_tags", False) and not lexical_owned_provisionally:
        extra = _expand_query_tags(root, args.query)
        if extra:
            print("note: query expanded with tag(s): {}".format(
                ", ".join(extra)), file=sys.stderr)
            terms = terms + [t for t in extra if t not in terms]
            # notify=False: this is the SAME index, looked at a second time
            # within one invocation. Repeating its degradation note here
            # would print it twice with the expansion note in between —
            # PF-4 says exactly one note per degraded arm, per invocation.
            hits, max_score = _rank_lexically(
                root, " ".join(terms), terms, args.limit, filters,
                notify=False)
            lexical_owned_provisionally = _keyword_top1_is_confident(hits)

    semantic_hits = []
    if not lexical_owned_provisionally or len(hits) < args.limit:
        # B01: the SAME filters object the lexical arm got — --scope/--type/
        # --tag constrain the answer, not one arm of it.
        semantic_hits = _semantic_hit_dicts(root, args.query, args.limit,
                                            filters)

    # R-13: the embedding build stays on the active catalogue by design
    # (cli/embeddings/build_tagvec.py:174) — an unannounced limit is a trap,
    # so tell the searcher when --include-archive did not reach the arm
    # that just shaped the answer. Gated on the conjunction (flag set AND
    # the semantic arm actually contributed hits), not the flag alone, and
    # printed at most once per invocation (PF-4).
    if filters.include_archive and semantic_hits:
        print("note: --include-archive covers the lexical arm only; "
              "embeddings stay on the active catalogue", file=sys.stderr)

    all_hits, lexical_owned = fuse_conditional(hits, semantic_hits, args.limit)
    if not lexical_owned and semantic_hits:
        print("note: semantic arm owns this ranking (lexical top-1 lacked a "
              "clear margin)", file=sys.stderr)

    if not all_hits:
        print("(no matches for: {})".format(args.query))
        near = _zero_hit_suggestions(root, args.query)
        if near:
            print("nearest registered tags: {}".format(", ".join(near)))
            print("try: okf-cli find \"{}\"".format(" ".join(near[:2])))
        return
    for i, h in enumerate(all_hits[: args.limit], start=1):
        print("------")
        # D01 (OKFT-3rb6): `rank` is the ONE comparable scale across a mixed
        # result list — the 1-based position actually delivered. It is
        # comparable by construction (it IS the list order) and claims
        # nothing about the two arms' raw scores being on one scale, which
        # D12 rejects. Those raw values (a/b lexical, cosine X.XX semantic)
        # are informative but not sortable against each other, so they move
        # out of the headline entirely and only reappear under --breakdown.
        print("rank: {}".format(i))
        print("title: {}".format(h["title"]))
        print("type: {}".format(h["type"]))
        # Present only when the concept's frontmatter carries the relation
        # (D01, OKFT-gpcx) — a hit without it stays byte-identical to the
        # pre-existing block shape (this is asserted, not assumed).
        if h.get("superseded_by"):
            print("superseded_by: {}".format(h["superseded_by"]))
        print("path: {}".format(h["path"]))
        print("description: {}".format(h["desc"]))
        print("body-snippet: {}".format(h["snip"]))
        # Every line names its own arm. The banner above says who OWNS the
        # ranking, which is not the same statement — a lexical hit can sit
        # inside a semantic-owned list, and leaving it unmarked made its
        # provenance derivable only from a missing marker (Modus-B B01).
        print("provenance: {}".format(h.get("provenance", "lexical")))
        if breakdown:
            if h.get("provenance") == "semantic":
                print("score: cosine {:.2f}".format(h["cosine"]))
                print("contrib: semantic-only (cosine={:.2f}, no keyword field match)".format(h["cosine"]))
            else:
                print("score: {}/{}".format(h["score"], max_score))
                if "contrib" in h:
                    print("contrib: {}".format(_format_contrib(h["contrib"])))
                else:
                    print("contrib: bm25 (fts5 index; field-level breakdown not "
                          "available)")
    print("------")


def make_snippet(body, terms, width=140):
    low = body.lower()
    pos = -1
    for t in terms:
        i = low.find(t)
        if i != -1 and (pos == -1 or i < pos):
            pos = i
    if pos == -1:
        pos = 0
    start = max(0, pos - width // 3)
    frag = re.sub(r"\s+", " ", body[start:start + width]).strip()
    return ("…" if start else "") + frag + "…"


def cmd_read(root, args):
    print(read_file(resolve_concept(root, args.path)))


def cmd_info(root, _args):
    """Print the catalogue's schema docs (TYPES.md + PROPERTIES.md) so an
    agent can load the type vocabulary and property spec in one call."""
    for fn in ("TYPES.md", "PROPERTIES.md"):
        print("------")
        p = os.path.join(root, fn)
        if os.path.isfile(p):
            print(read_file(p))
        else:
            print("(missing: {})".format(fn))
    print("------")


_PRIME_INTRO = """\
# OKF Knowledge Catalogue — agent onboarding

The catalogue is a read-mostly, LLM-facing knowledge store, separate from any
Obsidian vault it may be opened in. It holds thematic *bundles*; a bundle is a
folder of Markdown *concepts*, each with YAML frontmatter carrying a non-empty
`type`. A concept-id is its path below the bundle, minus `.md`. The store is a
plain git repo — ordinary file tools and git apply.

Every invocation needs `--root <catalogue>`; without it the CLI searches cwd and
its ancestors for a catalogue marker and fails if it finds none. It never falls
back to its own script directory.

## Retrieve — by command, not by blind grep

Progressive disclosure: widen only when the cheaper step left the question open.

  1. find "<query>"             ranked search across all bundles
  2. index [<bundle>]           what bundles and directories exist
  3. toc <bundle>[/<concept>]   headings before bodies — the cheapest way to
                                decide whether a page is worth reading. A bare
                                <bundle> or <bundle>/<subdir> resolves to its
                                index.md, so the names listed below are the
                                argument, verbatim.
  4. read <bundle>/<concept>    the page itself
  5. refs / wikilinks           follow the graph out of a page

Reach for `toc` before `read`: a concept can run long, and its headings usually
settle the question or name the section to read. Concepts cross-link in
Markdown — following a link beats re-running a search, and a large bundle's
`index.md` is the map its concepts hang from.

## Write — through the ce-okf skill, never by hand

Concepts are not hand-authored. The `ce-okf` skill routes a source to a bundle,
applies frontmatter and re-indexes. `index.md` listings are marker-managed and
generated (`reindex`) — never edit between the `<!-- okf:... -->` markers. Tag
edits go through `merge-tags` / `remove-tags`, not a search-and-replace. A
commit is allowed only once `check` reports zero violations.
"""


_PRIME_INTRO_COMPACT = """\
# OKF Knowledge Catalogue — agent onboarding

The catalogue is a read-mostly, LLM-facing knowledge store, separate from any
Obsidian vault it may be opened in. It holds thematic *bundles*; a bundle is a
folder of Markdown *concepts*, each with YAML frontmatter carrying a non-empty
`type`. A concept-id is its path below the bundle, minus `.md`. The store is a
plain git repo — ordinary file tools and git apply.

## Retrieve — by command, not by blind grep

Progressive disclosure: widen only when the cheaper step left the question open.

  1. find "<query>"             ranked search across all bundles
  2. index [<bundle>]           what bundles and directories exist
  3. toc <bundle>[/<concept>]   headings before bodies — the cheapest way to
                                decide whether a page is worth reading. A bare
                                <bundle> or <bundle>/<subdir> resolves to its
                                index.md, so the names listed below are the
                                argument, verbatim.
  4. read <bundle>/<concept>    the page itself
  5. refs / wikilinks           follow the graph out of a page

## Write — through the ce-okf skill, never by hand

Concepts are not hand-authored: `ce-okf` routes a source to a bundle, applies
frontmatter and re-indexes. `index.md` listings are marker-managed and
generated — never edit between the `<!-- okf:... -->` markers. A commit is
allowed only once `check` reports zero violations.
"""

_FIND_SCALES_COMPACT = """\
Each result line's headline number is `rank: N` — its 1-based position in
the delivered list, the one scale comparable across a mixed-arm result
because it IS the list order (D12: handover, never blend by score). The
arm's own raw value is not in that column; pass `--breakdown` to see it,
per hit: `score: a/b` for a lexical hit (a/100 is the FTS5/BM25 arm,
relative to this run's own top hit; a/(6 * n) is the substring fallback
used when no FTS index is available, over n query terms), `score: cosine
X.XX` for a semantic hit — its own scale, never the same column as a
lexical a/b. `provenance:` names the arm that produced the line.
Degradations are announced on stderr.
"""


def render_find_compact():
    """`find`'s options for the compact guide. The signature comes from the
    parser, so a flag registered later cannot go missing here — only the score
    scales are prose, because they are the one thing an agent cannot recover by
    trying the command. Everything else is one `find --help` away."""
    usage = subcommand_parsers(build_parser())["find"].format_usage().strip()
    return "## find — the entry point\n\n{}\n\n{}\nFull flag semantics: `find --help`.".format(
        usage, _FIND_SCALES_COMPACT)


def semantic_coverage(root, paths):
    """(embedded, total) for the concepts named in `paths`, or None when the
    catalogue carries no `.tagvec` at all.

    Delegates to plan_concept_delta() — the same content-hash comparison
    (concept_cache_key over title+body) the producer uses to decide what to
    re-embed — rather than running a second, weaker detector next to it. A
    PATH-SET-only comparison used to pass here: a concept whose body changed
    after embedding kept its old row's path, so the gap between "coverage
    thinks it's done" and "the producer still has 40 concepts queued"
    (measured live, 2026-08-10) went unreported. `paths` is intersected with
    the delta rather than trusted verbatim, so a caller passing a subset
    still gets an answer scoped to what it asked about.

    Costs ~2.2s over ~2600 concepts (offline, one read+hash per concept) —
    call sparingly on a hot path; see _semantic_coverage_line()'s `thorough`
    gate for the default-prime case."""
    db = _tagvec_db_path(root)
    if not os.path.isfile(db):
        return None
    try:
        bt = catalogue._load_build_tagvec()
        delta = bt.plan_concept_delta(root, SEMANTIC_MODEL, db)
    except sqlite3.Error:
        return None
    stale = {path for path, _text, _key in delta} & set(paths)
    return len(paths) - len(stale), len(paths)


def _semantic_coverage_line(root, paths, thorough=False):
    """The onboarding statement about the semantic arm's reach. The lexical
    index announces its absence and its staleness; before this, an incomplete
    `concept_emb` said nothing at all, and the arm simply did not see the
    concepts it lacked (Modus-B, 2026-08-10: 4.4 % of the live catalogue).

    `thorough=False` (prime's default) reports presence only: semantic_coverage()
    now does a real content-hash pass and costs ~2.2s over the live catalogue,
    too slow for a call on every session start. Presence-only is an honest
    "don't know", not a diluted count — the one counting method lives in
    semantic_coverage() and only runs when `thorough=True` (`prime
    --check-semantic`)."""
    db = _tagvec_db_path(root)
    if not os.path.isfile(db):
        return ("semantic index: absent — `find` runs its lexical arm only")
    if not thorough:
        return ("semantic index: present — staleness not checked by default "
                 "(costs ~2s on a large catalogue); run `prime --check-semantic` "
                 "for an exact count")
    cov = semantic_coverage(root, paths)
    if cov is None:
        return ("semantic index: absent — `find` runs its lexical arm only")
    embedded, total = cov
    if embedded >= total:
        return ("semantic index: complete — all {} concept(s) embedded".format(total))
    return ("semantic index: partial — {} of {} concept(s) embedded; the rest is "
            "invisible to the semantic arm (rebuild: cli/embeddings/"
            "build_tagvec.py --target concepts)".format(embedded, total))


def render_catalogue_state(root, thorough=False):
    """The live half of the onboarding: facts read off this catalogue rather
    than asserted in prose, so they cannot go stale. Retrieval quality depends
    on the FTS index being there, and a write attempt depends on whether the
    tag vocabulary is closed — an agent needs both before its first call."""
    bundles = list_bundles(root)
    paths = ["{}/{}".format(b, cid) for b in bundles
             for cid, _ap in iter_concepts(os.path.join(root, b))]
    lines = ["## This catalogue", "",
             "root: {}".format(root),
             "bundles: {} · concepts: {}".format(len(bundles), len(paths))]
    if os.path.isfile(_fts_db_path(root)):
        lines.append("fts index: present — `find` runs its lexical arm")
    else:
        lines.append("fts index: absent — `find` degrades to a substring scan; "
                     "run `build-index`")
    lines.append(_semantic_coverage_line(root, paths, thorough=thorough))
    registered = load_tags(root)
    if registered is None:
        lines.append("tag vocabulary: open — no TAGS.md, any tag passes")
    else:
        lines.append("tag vocabulary: closed — {} tags in TAGS.md; check a new one with "
                     "`tags --validate`, adopt it with `tags --register`".format(len(registered)))
    slugs = ctx_slugs(root)
    if slugs:
        lines.append("ctx bundles: {} — {} — `ctx show <slug>` lists one".format(
            len(slugs), " · ".join(slugs)))
    docs = [d for d in ("README.md", "SPEC.md", "TYPES.md", "PROPERTIES.md", "TAGS.md")
            if os.path.isfile(os.path.join(root, d))]
    if docs:
        lines.append("root docs: {}".format(" · ".join(docs)))
    return "\n".join(lines)


def cmd_prime(root, args):
    """One-shot agent onboarding: guide, command directory, catalogue state and
    bundle TOC in a single call. The guide used to be <root>/CLAUDE.md, which
    made prime empty the moment that file was removed (okf-cli-3hjr); it is now
    the CLI's own, and its command section is generated from the parser.

    --compact is the session-start rendering (okf-cli, 2026-08-05): a recipe
    that primes on every session pays this guide against the SSTD, the roadmap
    and the git log. It keeps every command, every find flag and the live
    state, and drops the prose that is one call away."""
    if args.compact:
        print(_PRIME_INTRO_COMPACT)
        print(command_overview(width=10 ** 6))
        print()
        print(render_find_compact())
    else:
        print(_PRIME_INTRO)
        print(command_overview())
        print()
        print("## find — the entry point, in full\n")
        print(subcommand_parsers(build_parser())["find"].format_help().strip())
    print()
    print(render_catalogue_state(root, thorough=getattr(args, "check_semantic", False)))
    print()
    print("## Bundles\n")
    print("The catalogue TOC, as `index` renders it. Each name is a path: "
          "`toc <bundle>`,\n`index <bundle>`, `--scope <bundle>` on find and "
          "list.\n")
    bundles = list_bundles(root)
    if args.compact:
        for b in bundles:
            print("- " + render_bundle_line(root, b))
        print("(`prime` without --compact inlines each bundle's description and "
              "directories)")
    else:
        for b in bundles:
            print(render_bundle_block(root, b, full=args.full))
            print("-----")
        if not args.full:
            print("(types+tags per bundle: `prime --full`; name+count only: "
                  "`prime --compact`)")


def cmd_toc(root, args):
    ap = resolve_concept(root, args.path)
    fm, body = split_frontmatter(read_file(ap))
    title = fm.get("title") or os.path.basename(ap)[:-3]
    print("# {}  [{}]".format(title, fm.get("type", "")))
    found = False
    for lvl, text in iter_headings(body):
        if args.level == 0:                       # --level 0 → full tree, indented
            print("  " * (lvl - 1) + "- " + text)
            found = True
        elif lvl == args.level:                   # default: only this level (h2)
            print("- " + text)
            found = True
    if not found:
        print("(no h{} headings)".format(args.level) if args.level else "(no headings)")


def bundle_graph(root, bundle):
    """Return (nodes, edges) for one bundle. Nodes=concepts, edges=in-bundle md links."""
    bp = os.path.join(root, bundle)
    concepts = dict(iter_concepts(bp))            # cid -> abspath
    nodes, edges = [], []
    link_re = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    for cid, ap in sorted(concepts.items()):
        fm, body = split_frontmatter(read_file(ap))
        nodes.append({"id": cid, "title": fm.get("title") or cid,
                      "type": fm.get("type", ""), "body": body})
        cdir = os.path.dirname(cid)
        for m in link_re.finditer(re.sub(r"```.*?```", "", body, flags=re.S)):
            tgt = m.group(1).split("#")[0].strip()
            if not tgt.endswith(".md") or tgt.startswith(("http", "..")):
                continue
            if tgt.startswith("/"):
                # catalogue-root-absolute (/bundle/subdir/concept.md): strip the
                # leading /bundle/ to get the bundle-relative cid. A link into a
                # different bundle won't match this bundle's concepts and is
                # dropped — bundle_graph only builds in-bundle edges.
                dest = tgt[1:-3]
                if dest == bundle:
                    dest = ""
                elif dest.startswith(bundle + "/"):
                    dest = dest[len(bundle) + 1:]
            else:
                dest = os.path.normpath(os.path.join(cdir, tgt[:-3]))
            dest = dest.replace(os.sep, "/")
            if dest in concepts and dest != cid:
                edges.append({"source": cid, "target": dest})
    return nodes, edges


def cmd_visualize(root, args):
    import json
    require_bundle_dir(root, args.bundle)
    nodes, edges = bundle_graph(root, args.bundle)
    out = args.out or os.path.join(root, args.bundle, "assets", "viz.html")
    data = json.dumps({"name": args.bundle, "nodes": nodes, "edges": edges})
    html = _VIZ_TEMPLATE.replace("__DATA__", data).replace("__NAME__", args.bundle)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print("wrote {} ({} nodes, {} edges)".format(out, len(nodes), len(edges)))


def cmd_refs(root, args):
    import json
    scan_root = os.path.abspath(args.scan_root) if getattr(args, "scan_root", None) else root
    if os.path.isabs(args.path):
        target = args.path
    else:
        # resolve against scan_root (the tree the path lives in) when given,
        # else root; prefer whichever actually exists.
        cand_scan = os.path.join(scan_root, args.path)
        target = cand_scan if os.path.exists(cand_scan) else os.path.join(root, args.path)
    if not os.path.exists(target):
        sys.stderr.write("refs: target not found: {}\n".format(args.path))
        sys.exit(2)
    only_in = getattr(args, "only_in", False)
    only_out = getattr(args, "only_out", False)
    want_in, want_out = not only_out, not only_in
    hits = linkscan.build_ref_matrix(scan_root, target) if want_in else []
    out = []
    if want_out and target.endswith(".md") and os.path.isfile(target):
        out = [(raw, _refs_display(scan_root, t), ex)
               for raw, t, ex in linkscan.outbound_links(scan_root, target)]
    if getattr(args, "json", False):
        d = {"target": os.path.relpath(os.path.abspath(target), scan_root).replace(os.sep, "/")}
        if want_in:
            d["inbound"] = [{"source": s, "link": l} for s, l in hits]
        if want_out:
            d["outbound"] = [{"link": l, "target": t, "exists": ex} for l, t, ex in out]
        print(json.dumps(d))
        return
    if want_in:
        print("inbound ({}):".format(len(hits)))
        for s, l in hits:
            print("  {}  ->  {}".format(s, l))
        if not hits:
            print("  (none)")
    if want_out:
        print("outbound ({}):".format(len(out)))
        for l, t, ex in out:
            print("  {}  ->  {}{}".format(l, t, "" if ex else "  [missing]"))
        if not out:
            print("  (none)")


REWRITE_EXTS = (".md", ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".rb",
                ".yml", ".yaml", ".toml", ".json", ".txt", ".rst", ".cfg", ".ini", ".sh")


def rewrite_path(scan_root, old, new, dry_run=False):
    """Literal old->new path-string replace across text files under scan_root
    (covers non-markdown references markdown tooling can't see). Prunes .git,
    node_modules, dotdirs. Returns [(rel_path, count), ...]."""
    touched = []
    for dirpath, dirnames, filenames in os.walk(scan_root):
        _prune_walk_dirs(dirnames)
        for fn in filenames:
            if not fn.endswith(REWRITE_EXTS):
                continue
            ap = os.path.join(dirpath, fn)
            text = read_file(ap)
            pat = re.compile(r"(?<![\w./-])" + re.escape(old) + r"(?![\w./-])")
            n = len(pat.findall(text))
            if not n:
                continue
            if not dry_run:
                with open(ap, "w", encoding="utf-8") as f:
                    f.write(pat.sub(lambda _m: new, text))
            touched.append((os.path.relpath(ap, scan_root).replace(os.sep, "/"), n))
    return touched


def cmd_rewrite_path(root, args):
    scan_root = os.path.abspath(args.scan_root) if getattr(args, "scan_root", None) else root
    dry = getattr(args, "check", False)
    touched = rewrite_path(scan_root, args.old, args.new, dry_run=dry)
    verb = "would rewrite" if dry else "rewrote"
    for rel, n in touched:
        print("{} {} ({}x)".format(verb, rel, n))
    print("{} file(s) {}".format(len(touched), "affected (dry-run)" if dry else "written"))


_VIZ_TEMPLATE = """<!doctype html><html><head><meta charset="utf-8">
<title>OKF — __NAME__</title>
<script src="https://unpkg.com/cytoscape@3.28.1/dist/cytoscape.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/marked@12/marked.min.js"></script>
<style>
 body{margin:0;font:14px/1.5 system-ui,sans-serif;display:flex;height:100vh}
 #g{flex:1;background:#0d1117}
 #p{width:38%;max-width:560px;overflow:auto;padding:16px 22px;border-left:1px solid #30363d;background:#161b22;color:#c9d1d9}
 #p h1,#p h2,#p h3{color:#e6edf3} #p a{color:#58a6ff} #p code,#p pre{background:#0d1117;border-radius:6px}
 #p pre{padding:12px;overflow:auto} #bar{padding:8px 12px;background:#161b22;color:#c9d1d9;border-bottom:1px solid #30363d}
 #s{width:220px} .meta{color:#8b949e;font-size:12px;margin-bottom:10px}
</style></head><body>
<div style="flex:1;display:flex;flex-direction:column">
 <div id="bar"><b>__NAME__</b> &nbsp; <input id="s" placeholder="filter title/type…"></div>
 <div id="g"></div>
</div>
<div id="p"><div class="meta">Klick auf einen Knoten.</div></div>
<script>
const D=__DATA__;
const COL={ADR:'#f78166',Service:'#3fb950',Component:'#a371f7',Template:'#d29922',Reference:'#58a6ff',Guide:'#39c5cf',Concept:'#8b949e',Pattern:'#db61a2',SOP:'#e3b341',Playbook:'#ff7b72',LessonLearned:'#7ee787',ChangeNote:'#6e7681',Decision:'#bc8cff'};
const cy=cytoscape({container:document.getElementById('g'),
 elements:[...D.nodes.map(n=>({data:{id:n.id,label:n.title,type:n.type}})),
           ...D.edges.map(e=>({data:{source:e.source,target:e.target}}))],
 style:[{selector:'node',style:{'background-color':n=>COL[n.data('type')]||'#8b949e','width':10,'height':10,'label':'data(label)','font-size':6,'color':'#8b949e','min-zoomed-font-size':7}},
        {selector:'edge',style:{'width':.6,'line-color':'#30363d','curve-style':'haystack','target-arrow-shape':'none'}},
        {selector:'.hl',style:{'background-color':'#e6edf3','width':16,'height':16}}],
 layout:{name:'cose',animate:false,nodeRepulsion:8000,idealEdgeLength:60}});
const body=Object.fromEntries(D.nodes.map(n=>[n.id,n]));
cy.on('tap','node',e=>{const n=body[e.target.id()];
 document.getElementById('p').innerHTML='<div class="meta">'+n.type+' · '+e.target.id()+'</div><h1>'+n.title+'</h1>'+marked.parse(n.body||'');
 cy.elements().removeClass('hl');e.target.addClass('hl');});
document.getElementById('s').addEventListener('input',ev=>{const q=ev.target.value.toLowerCase();
 cy.nodes().forEach(n=>{const h=!q||n.data('label').toLowerCase().includes(q)||(n.data('type')||'').toLowerCase().includes(q);n.style('display',h?'element':'none');});});
</script></body></html>"""


# --- reindex: mechanical, marker-bounded index.md generation (OKF §6) -------

def convert_flat_index(text, force=False):
    """Migrate a marker-less, hand-curated index.md to a managed marker block.

    Returns (new_text, status). A *single-section* flat listing (one `## `
    section whose tail is only a bullet list) always converts. A *multi-section*
    listing converts only with force=True, and only when every section body is
    still pure headings+bullets — any prose/table (real content) refuses. Trailing
    prose or a missing list is left untouched and flagged.

    status ∈ {converted, already-managed, skip-multi-section,
              skip-trailing-content, skip-no-list}
    """
    if MARK_START in text:
        return text, "already-managed"
    lines = text.splitlines()
    h2_idxs = [i for i, ln in enumerate(lines) if re.match(r"^##\s", ln)]
    if len(h2_idxs) == 0:
        return text, "skip-no-list"
    multi = len(h2_idxs) >= 2
    if multi and not force:
        return text, "skip-multi-section"
    h2 = h2_idxs[0]
    saw_bullet = saw_prose = False
    for ln in lines[h2 + 1:]:
        s = ln.strip()
        if not s or re.match(r"^##\s", s):   # blank / sub-section heading: allowed
            continue
        if re.match(r"^[*\-+]\s", s):
            saw_bullet = True
        else:
            saw_prose = True                 # prose or table = real content
    if not saw_bullet:
        return text, "skip-no-list"
    if saw_prose:
        return text, "skip-trailing-content"
    head = "\n".join(lines[:h2]).rstrip()
    section = "## Contents" if multi else lines[h2].rstrip()
    new = head + "\n\n" + section + "\n\n" + MARK_START + "\n" + MARK_END + "\n"
    return new, "converted"


def ensure_markers(dirpath):
    """Create dirpath/index.md with an empty marker block if it is missing.

    Create-only: an existing marker-less index.md is left untouched — its
    hand-curated content is migrated by convert_flat_index (via init_indexes),
    never by a naive append.
    """
    idx = os.path.join(dirpath, "index.md")
    title = os.path.basename(os.path.abspath(dirpath))
    if not os.path.isfile(idx):
        write_file(idx, "# {}\n\n## Contents\n\n{}\n{}\n".format(title, MARK_START, MARK_END))


def init_indexes(root, target, dry_run=False, force=False):
    """Walk the target subtree and migrate each marker-less flat index.md.

    Returns a sorted list of (relpath-from-root, status) from convert_flat_index.
    Writes converted files only when dry_run is False. With force=True, pure
    multi-section listings are flattened too (prose/tables still refuse).
    """
    results = []
    for dp, dn, fn in os.walk(target):
        dn[:] = [d for d in dn if not d.startswith(".") and d != "assets"]
        idx_name = _find_reserved_name(fn)
        if not idx_name:
            continue
        idx = os.path.join(dp, idx_name)
        rel = os.path.relpath(idx, root).replace(os.sep, "/")
        new, status = convert_flat_index(read_file(idx), force=force)
        if status == "converted" and not dry_run:
            write_file(idx, new)
        results.append((rel, status))
    results.sort()
    return results


def uncovered_index_dirs(root, target):
    """Marker-less index.md dirs that DO hold concept files — no coverage net
    proves those files appear in the index. Returns sorted rel index.md paths.
    """
    out = []
    for dp, dn, fn in os.walk(os.path.join(root, target)):
        dn[:] = [d for d in dn if not d.startswith(".") and d != "assets"]
        idx_name = _find_reserved_name(fn)
        if not idx_name:
            continue
        idx = os.path.join(dp, idx_name)
        text = read_file(idx)
        if MARK_START in text or EXEMPT in text:   # managed or deliberately exempt
            continue
        if list_dir_concepts(dp):
            out.append(os.path.relpath(idx, root).replace(os.sep, "/"))
    out.sort()
    return out


def cmd_reindex(root, args):
    target = args.target.rstrip("/")
    tp = os.path.join(root, target)
    if not os.path.isdir(tp):
        print("not a directory: {}".format(target), file=sys.stderr)
        sys.exit(1)
    if args.init:
        if not args.check:
            ensure_markers(tp)                    # create-only, named target
        conv = init_indexes(root, tp, dry_run=args.check, force=getattr(args, "force", False))
        verb = "would convert" if args.check else "converted"
        for rel, status in conv:
            if status == "converted":
                print("{:<14} {}".format(verb, rel))
            elif status != "already-managed":
                print("{:<14} {}  ({})".format("skipped", rel, status))
        n_conv = sum(1 for _, s in conv if s == "converted")
        n_skip = sum(1 for _, s in conv if s not in ("converted", "already-managed"))
        print("init: {} {}, {} skipped".format(n_conv, verb, n_skip))
        if args.check:
            sys.exit(0)                           # --init --check = conversion preview only
    dirs = []
    for dp, dn, fn in os.walk(tp):
        dn[:] = [d for d in dn if not d.startswith(".") and d != "assets"]
        for name in ("index.md", "index-map.md"):
            idx_name = _find_reserved_name(fn, name)
            if idx_name:
                dirs.append((dp, idx_name))
    changed, skipped, stale = [], [], []
    for dp, idx_name in sorted(dirs):
        idx = os.path.join(dp, idx_name)
        text = read_file(idx)
        rel = os.path.relpath(idx, root)
        if MARK_START not in text:
            skipped.append(rel)
            continue
        block = managed_block_for(dp, root, idx_name)
        new_text, _ = replace_managed_block(text, block)
        if new_text == text:
            continue
        if args.check:
            stale.append(rel)
        else:
            write_file(idx, new_text)
            changed.append(rel)
    if args.check:
        un = uncovered_index_dirs(root, tp)
        for p in stale:
            print("STALE        {}".format(p))
        for p in un:
            print("UNCOVERED    {}".format(p))
        print("reindex --check: {} stale, {} uncovered, {} without markers".format(
            len(stale), len(un), len(skipped)))
        sys.exit(1 if (stale or un) else 0)
    for p in changed:
        print("updated       {}".format(p))
    for p in skipped:
        print("skipped (no markers)  {}".format(p))
    print("reindex: {} updated, {} skipped".format(len(changed), len(skipped)))


# --- canon block synchronisation -------------------------------------------
# A canonical concept declares addressable blocks; a consumer carries
# materialised copies of them and stays verifiably in sync. There is no index
# and no staleness store: the relationship is derived by a catalogue walk at
# command time, exactly as `check` derives its own, so there is no second
# truth source that can go stale (PO decision 2026-09-13).

SYNC_STATUSES = ("synced", "source-changed", "consumer-modified",
                 "both-changed", "source-missing", "malformed")


def _canon_payload(root, concept, block_id):
    """(abspath, rel, payload) of one canon block, or exit 1 naming what is
    missing. Shared by sync-export and sync-insert so both refuse identically."""
    ap = resolve_concept(root, concept)
    rel = os.path.relpath(ap, root).replace(os.sep, "/")
    _, body = split_frontmatter(read_file(ap))
    for blk in parse_canon_blocks(body):
        if blk["id"] != block_id:
            continue
        if blk["payload"] is None:
            print("canon block `{}` in {} has no closing {}".format(
                block_id, rel, CANON_END), file=sys.stderr)
            sys.exit(1)
        return ap, rel, blk["payload"]
    print("no canon block `{}` in {}".format(block_id, rel), file=sys.stderr)
    sys.exit(1)


def scan_sync_blocks(root, target, source=None, block_id=None):
    """[(rel, ap, rec, status)] for every materialised canon block under
    `target`, filtered by exact `source`/`block_id` when given.

    Scope semantics are `check`'s, deliberately: the two surfaces must agree
    on which files carry a sync block, or a block `check` errors on is one
    `sync-update` cannot reach."""
    canon = build_canon_block_index(root)
    out = []
    for _, bp in resolve_scopes(root, target):
        for ap in iter_all_md(bp):
            _, body = split_frontmatter(read_file(ap))
            if SYNC_OPEN_LIT not in body:
                continue
            rel = os.path.relpath(ap, root).replace(os.sep, "/")
            for rec in parse_sync_blocks(body):
                if source is not None and rec["source"] != source:
                    continue
                if block_id is not None and rec["id"] != block_id:
                    continue
                out.append((rel, ap, rec, classify_sync_block(rec, canon)))
    return canon, out


def _sync_addr(rec):
    """`/bundle/owner.md#block-id` — the human-readable address of one block,
    degraded but still printable when the marker itself is malformed."""
    return "{}#{}".format(rec["source"] or "?", rec["id"] or "?")


def cmd_sync_export(root, args):
    _, _, payload = _canon_payload(root, args.concept, args.block_id)
    # Payload only, nothing else, so the output pipes.
    sys.stdout.write(payload.strip("\n") + "\n")


def cmd_sync_insert(root, args):
    owner_ap, owner_rel, payload = _canon_payload(root, args.concept, args.block_id)
    source = "/" + owner_rel
    cap = resolve_concept(root, args.consumer)
    consumer_rel = os.path.relpath(cap, root).replace(os.sep, "/")
    if cap == owner_ap:
        print("{} owns `{}` — a canon owner does not consume its own block"
              .format(consumer_rel, args.block_id), file=sys.stderr)
        sys.exit(1)
    text = read_file_verbatim(cap)
    if text is None:
        print("not valid UTF-8: {}".format(consumer_rel), file=sys.stderr)
        sys.exit(1)
    _, body = split_frontmatter(text)
    head = text[:len(text) - len(body)]
    for rec in parse_sync_blocks(body):
        if rec["id"] != args.block_id:
            continue
        if rec["source"] == source:
            print("{} already carries `{}` from {} — use sync-update to "
                  "refresh it".format(consumer_rel, args.block_id, source),
                  file=sys.stderr)
        else:
            # Two blocks with one id read as one block to a human, and
            # `sync-status --block` could not tell them apart either.
            print("{} already carries a block `{}` from {} — the id would be "
                  "ambiguous in this concept".format(
                      consumer_rel, args.block_id, rec["source"] or "?"),
                  file=sys.stderr)
        sys.exit(1)
    block = render_sync_block(args.block_id, source, payload)
    new_body = body.rstrip("\n") + "\n\n" + block + "\n"
    if not args.apply:
        print("would insert    {}   {}#{}".format(
            consumer_rel, source, args.block_id))
        print("sync-insert (dry-run): re-run with --apply.")
        return
    write_file_verbatim(cap, head + new_body)
    print("inserted        {}   {}#{}".format(
        consumer_rel, source, args.block_id))


def cmd_sync_status(root, args):
    target = getattr(args, "target", None)
    if target and not os.path.isdir(os.path.join(root, os.path.normpath(target))):
        # Same gate as cmd_check: a typo'd bundle scanned nothing and exited 0.
        print("not a directory: {}".format(target), file=sys.stderr)
        sys.exit(1)
    _, found = scan_sync_blocks(root, target, source=args.source,
                                block_id=args.block)
    totals = {s: 0 for s in SYNC_STATUSES}
    rows = []
    for rel, _ap, rec, status in found:
        totals[status] += 1
        rows.append({"consumer": rel, "id": rec["id"], "source": rec["source"],
                     "status": status})
    if getattr(args, "json", False):
        print(json.dumps({"blocks": rows, "totals": totals}))
    else:
        for row in rows:
            print("{:<18} {:<32} {}#{}".format(
                row["status"], row["consumer"], row["source"] or "?",
                row["id"] or "?"))
        print("sync-status: " + ", ".join(
            "{} {}".format(totals[s], s) for s in SYNC_STATUSES))
    sys.exit(1 if any(r["status"] != "synced" for r in rows) else 0)


def cmd_sync_update(root, args):
    target = getattr(args, "target", None)
    if target and not os.path.isdir(os.path.join(root, os.path.normpath(target))):
        print("not a directory: {}".format(target), file=sys.stderr)
        sys.exit(1)
    canon, found = scan_sync_blocks(root, target, source=args.source,
                                    block_id=args.block)
    verb = "updated" if args.apply else "would update"
    per_file, refused, unresolvable = {}, [], []
    for rel, ap, rec, status in found:
        if status == "synced":
            continue
        if status in ("source-missing", "malformed"):
            # Never written, always reported: repairing or deleting a block
            # whose owner is gone, or whose markers a human broke, is a human
            # decision, not a rewrite.
            unresolvable.append((rel, rec, status))
            continue
        if status in ("consumer-modified", "both-changed") and not args.force:
            refused.append((rel, rec, status))
            continue
        per_file.setdefault(ap, []).append((rel, rec))
    updated = []
    for ap, recs in per_file.items():
        text = read_file_verbatim(ap)
        if text is None:
            print("note: skipping {} — not valid UTF-8".format(ap),
                  file=sys.stderr)
            continue
        _, body = split_frontmatter(text)
        head = text[:len(text) - len(body)]
        out, last = [], 0
        for rel, rec in sorted(recs, key=lambda t: t[1]["span"][0]):
            a, b = rec["span"]
            payload = canon[(rec["source"].lstrip("/"), rec["id"])]
            out.append(body[last:a])
            out.append(render_sync_block(rec["id"], rec["source"], payload))
            last = b
            updated.append((rel, rec))
        out.append(body[last:])
        if args.apply:
            write_file_verbatim(ap, head + "".join(out))
    for rel, rec in updated:
        print("{:<14} {}   {}".format(verb, rel, _sync_addr(rec)))
    for rel, rec, _status in refused:
        print("refused        {}   {}  (consumer copy modified — reconcile "
              "into the canon owner first, or --force to discard)".format(
                  rel, _sync_addr(rec)))
    for rel, rec, status in unresolvable:
        print("{:<14} {}   {}".format(status, rel, _sync_addr(rec)))
    print("sync-update: {} {}, {} refused, {} unresolvable.{}".format(
        len(updated), verb, len(refused), len(unresolvable),
        "" if args.apply else " Re-run with --apply."))
    sys.exit(1 if (refused or unresolvable) else 0)


# --- recent: concepts by the commit that added them ------------------------
# `log` answers "what moved" at commit granularity; `recent` answers "what is
# new" at concept granularity. The date source is git and only git: the
# frontmatter `timestamp` covers 1789 of 2559 concepts (qm-wiki, 30% of the
# catalogue, carries two) and where it exists it is a migration batch stamp —
# 510 distinct values over 1789 concepts, the most frequent one repeated 125
# times to the second, so a batch has no internal order. mtime is likewise out:
# normalize-tags/reindex/fix-crosslinks rewrite files wholesale and a fresh
# clone flattens every mtime to checkout time.
#
# git as a source is SPEC-sanctioned, not a layering break: SPEC.md §2 names a
# git repository as the recommended shape ("provides history, attribution,
# diffs") and §7 defines `**Creation**` as a log entry type. Recent and other
# read git since the beginning.
RECENT_TS_RE = re.compile(r"^@(\d+)$")
UNCOMMITTED = "(uncommitted)"
CREATED_FMT = "%Y-%m-%d %H:%M"


def parse_add_events(stdout):
    """{repo_rel_path: unix_ts} from the stanza stream of
    `git log --no-renames --diff-filter=A --format=@%at --name-only`.

    A stanza is one `@<unixtime>` line, a blank line, then the paths that
    commit added. git emits newest-commit-first, so the FIRST sighting of a
    path is its LATEST add and setdefault keeps it: a path deleted and re-added
    dates from the re-add (D11). Only `@<digits>` opens a stanza — `@notes/x.md`
    is a path. Paths before any stanza header have no timestamp and are dropped.
    """
    events, ts = {}, None
    for line in stdout.splitlines():
        if not line.strip():
            continue
        m = RECENT_TS_RE.match(line)
        if m:
            ts = int(m.group(1))
        elif ts is not None:
            events.setdefault(line, ts)
    return events


def concept_git_key(prefix, cid):
    """The repo-relative path git prints for one concept: `docs/x-okf/a/b.md`.

    Composed from the bundle's repo-relative prefix and the bundle-relative
    concept id iter_concepts() already yields — never derived via
    os.path.relpath(abspath, repo). relpath is purely lexical and does not
    resolve symlinks, so for a symlinked bundle it returns
    `../../Obsidian/Knowledge-Catalogue/<bundle>/x.md`, a path git never prints:
    measured 78 of 78 symlinked concepts undated. Building the key instead of
    deriving it is what makes the foreign-repo path work at all."""
    return "{}/{}.md".format(prefix, cid) if prefix else "{}.md".format(cid)


def group_scopes_by_repo(scopes):
    """[(bundle, repo_top, prefix), …] → [(repo_top, [(bundle, prefix), …]), …]
    in first-seen order. One entry per repo means one git process per repo,
    however many bundles it owns. Scopes with no repo are dropped — their
    concepts still list, undated, and cmd_recent has already noted why."""
    grouped, order = {}, []
    for bundle, repo, prefix in scopes:
        if repo is None:
            continue
        if repo not in grouped:
            grouped[repo] = []
            order.append(repo)
        grouped[repo].append((bundle, prefix))
    return [(repo, grouped[repo]) for repo in order]


def rank_recent(entries, limit):
    """Top-`limit` of [(path, ts_or_None), …], newest first.

    Undated rows sort after every dated one (D09): during an _inbox drain —
    the very session this command serves — dozens of concepts are untracked at
    once, and sorting them first would spend the whole `--limit` on scratch
    files. Equal timestamps break by path so the output is reproducible; one
    commit adding forty concepts is the common case, not the exception."""
    if limit <= 0:
        return []
    ordered = sorted(entries,
                     key=lambda e: (-(e[1] if e[1] is not None else -1), e[0]))
    return ordered[:limit]


def format_created(ts, tz=None):
    """`2026-08-05 18:48`, or a placeholder padded to the same width when the
    concept has no add-event. `tz` is injectable so tests are timezone-proof;
    production passes None, i.e. local time — which is what someone reading
    their own catalogue means by "when did I write this"."""
    if ts is None:
        return UNCOMMITTED.ljust(len(datetime.datetime(2026, 1, 1).strftime(CREATED_FMT)))
    return datetime.datetime.fromtimestamp(ts, tz).strftime(CREATED_FMT)


def render_recent_lines(rows, tz=None):
    """rows: [(ts_or_None, type, path), …] already ranked → one line each.

    The type column is padded to the widest type IN THIS RESULT SET, not to a
    fixed width — a listing of ten Runbooks should not carry the whitespace of
    a `LessonLearned` that is not there."""
    if not rows:
        return []
    width = max(len(t) for _ts, t, _p in rows)
    return ["{}  {}  {}".format(format_created(ts, tz), ctype.ljust(width), path)
            for ts, ctype, path in rows]


def iso_created(ts, tz=None):
    """ISO-8601 with offset, or None. The json branch carries this next to the
    raw unix int: one field a human or an LLM reads, one a consumer sorts on
    without parsing anything."""
    if ts is None:
        return None
    dt = datetime.datetime.fromtimestamp(ts, tz)
    return (dt if dt.tzinfo else dt.astimezone()).isoformat()


def _git_add_events(repo, prefixes):
    """(stdout, None) or (None, 'no-git'|'no-repo'). Exactly one git process.

    --no-renames is load-bearing, not tidiness: with git's default rename
    detection a `git mv` is classified R and --diff-filter=A drops it, so every
    concept `okf-cli rename` has ever moved becomes undatable. Measured against
    the real catalogue: 4 concepts missing with detection on, 0 with it off.

    core.quotepath=false so a path with an umlaut arrives raw instead of
    C-quoted — none in the catalogue today, but the parser must not silently
    lose the first one."""
    cmd = ["git", "-C", repo, "-c", "core.quotepath=false", "log",
           "--no-renames", "--diff-filter=A", "--format=@%at", "--name-only",
           "--"] + (list(prefixes) or ["."])
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
    except (FileNotFoundError, OSError):
        return None, "no-git"
    if res.returncode != 0:
        return None, "no-repo"
    return res.stdout, None


def _recent_scopes(root, target, notes):
    """[(bundle, bundle_path, repo_top_or_None, prefix_or_None), …].

    Classification is by realpath, not os.path.islink: islink only sees a link
    in the last component, so a bundle reached through a symlinked parent — or
    a link pointing back INTO the catalogue — would be filed under the wrong
    repo. The `+ os.sep` on the containment test keeps a sibling directory
    named `<catalogue>-old` from being mistaken for catalogue-owned."""
    realroot = os.path.realpath(root)
    root_top, reason = catalogue._git_toplevel(realroot)
    if reason == "no-git":
        print("recent: git binary not found — this command reads creation "
              "dates from git history", file=sys.stderr)
        sys.exit(1)
    if reason == "no-repo":
        print("recent: catalogue root is not a git repository — no history "
              "to read", file=sys.stderr)
        sys.exit(1)
    # The catalogue root need not be a repo root: okf-tools/docs has exactly
    # that shape, so its own prefix is not necessarily empty.
    root_prefix = os.path.relpath(realroot, root_top).replace(os.sep, "/")
    if root_prefix == ".":
        root_prefix = ""
    scopes = []
    for bundle, bp in resolve_scopes(root, target):
        real = os.path.realpath(bp)
        if not os.path.isdir(real):
            notes.append("note: scope `{}` is a broken symlink — nothing to "
                         "list; repoint or remove the link".format(bundle))
            continue
        if real == realroot or real.startswith(realroot + os.sep):
            sub = os.path.relpath(real, realroot).replace(os.sep, "/")
            sub = "" if sub == "." else sub
            prefix = "/".join(p for p in (root_prefix, sub) if p)
            scopes.append((bundle, bp, root_top, prefix))
            continue
        repo, why = catalogue._git_toplevel(real)
        if repo is None:
            notes.append(
                "note: bundle `{}` resolves outside any git repository — its "
                "concepts are listed undated; run `git init` in {}".format(
                    bundle, real if why == "no-repo" else real))
            scopes.append((bundle, bp, None, None))
            continue
        prefix = os.path.relpath(real, repo).replace(os.sep, "/")
        scopes.append((bundle, bp, repo, "" if prefix == "." else prefix))
    return scopes


def cmd_recent(root, args):
    notes = []
    scopes = _recent_scopes(root, args.scope, notes)
    by_repo = {}
    for repo, members in group_scopes_by_repo(
            [(b, repo, prefix) for b, _bp, repo, prefix in scopes]):
        stdout, why = _git_add_events(repo, [p for _b, p in members if p])
        if stdout is None:
            notes.append("note: git log failed in {} — its concepts are listed "
                         "undated; check the repository".format(repo))
            continue
        by_repo[repo] = parse_add_events(stdout)

    want_meta = bool(args.type or args.tag)
    entries, meta, dated_repo = [], {}, {}
    for bundle, bp, repo, prefix in scopes:
        events = by_repo.get(repo) if repo is not None else None
        for cid, ap in iter_concepts(bp):
            rel = os.path.relpath(ap, root).replace(os.sep, "/")
            path = rel[:-3] if rel.endswith(".md") else rel
            if want_meta:
                # One read feeding both frontmatter and tags; cmd_list still
                # reads twice, and that is not this change's business.
                text = read_file(ap)
                fm, _body = split_frontmatter(text)
                ctype = _dequote(fm.get("type", ""))
                if args.type and ctype != args.type:
                    continue
                if args.tag and args.tag not in extract_tags(text):
                    continue
                meta[path] = (ctype, _dequote(fm.get("title", "")) or cid,
                              _dequote(fm.get("description", "")))
            ts = events.get(concept_git_key(prefix, cid)) if events else None
            dated_repo[path] = events is not None
            entries.append((path, ts))

    total = len(entries)
    rows = rank_recent(entries, args.limit)
    # Without a filter no file was read yet: frontmatter is fetched for the
    # surviving rows only — ten reads instead of two and a half thousand.
    for path, _ts in rows:
        if path not in meta:
            ap = os.path.join(root, path + ".md")
            meta[path] = meta_of(ap)

    undated = sum(1 for path, ts in entries if ts is None and dated_repo.get(path))
    if undated:
        notes.append("note: {} concept(s) have no commit that added them — "
                     "listed undated at the end; commit them to give them a "
                     "creation date".format(undated))
    for note in notes:
        print(note, file=sys.stderr)

    if getattr(args, "json", False):
        print(json.dumps([
            {"created": iso_created(ts), "created_ts": ts,
             "title": meta[path][1], "type": meta[path][0],
             "path": path, "description": meta[path][2]}
            for path, ts in rows
        ]))
        return
    if not rows:
        print("(no matches)")
        return
    for line in render_recent_lines([(ts, meta[path][0], path)
                                     for path, ts in rows]):
        print(line)
    # `recent` truncates by default, so a bare count would read as "the
    # catalogue holds ten concepts". Both numbers, always.
    print("recent: {} of {} concept(s)".format(len(rows), total))



# --- check: pluggable conformance scan (§9 hard rules + local invariants) ---

FILENAME_FORBIDDEN_CHARS = set('#^[]|\\:?*"<>%')
GERMAN_FM_KEYS = {"titel", "beschreibung", "typ", "stichworte", "datum", "zusammenfassung"}


def gather_file_context(root, bundle, ap):
    text = read_file(ap)
    fm, body = split_frontmatter(text)
    has_fm = text.startswith(FM_DELIM) and text.find("\n" + FM_DELIM, len(FM_DELIM)) != -1
    fn = os.path.basename(ap)
    return {
        "root": root, "bundle": bundle, "ap": ap,
        "rel": os.path.relpath(ap, root).replace(os.sep, "/"),
        "fn": fn, "text": text, "fm": fm, "body": body,
        "has_fm": has_fm, "is_reserved": fn.lower() in RESERVED,
    }


def check_fm_parseable(ctx):
    if ctx["is_reserved"]:
        return []
    return [] if ctx["has_fm"] else ["no parseable frontmatter"]


def check_type_nonempty(ctx):
    if ctx["is_reserved"] or not ctx["has_fm"]:
        return []
    return [] if ctx["fm"].get("type", "").strip() else ["missing/empty `type`"]


def check_reserved_no_type(ctx):
    if not ctx["is_reserved"] or not ctx["has_fm"]:
        return []
    return ["reserved file must not carry `type`"] if ctx["fm"].get("type", "").strip() else []


def check_filename_chars(ctx):
    if ctx["is_reserved"]:
        return []
    bad = FILENAME_FORBIDDEN_CHARS & set(ctx["fn"][:-3])
    return ["forbidden char(s) in filename: {}".format("".join(sorted(bad)))] if bad else []


def check_type_registered(ctx, types_set):
    if ctx["is_reserved"] or not ctx["has_fm"] or types_set is None:
        return []
    t = ctx["fm"].get("type", "").strip()
    return ["type `{}` not registered in TYPES.md".format(t)] if t and t not in types_set else []


def check_tag_registered(ctx, tags_set):
    """Closed-vocabulary gate: every frontmatter tag must be in TAGS.md.
    No-op when TAGS.md is absent (tags_set is None). Severity is warning, so it
    surfaces new tags without blocking; `check --strict` escalates to error.
    Keeps agents from exploding the tag vocabulary with creative one-offs — a tag
    only aggregates content if it is reused, not minted fresh each write."""
    if ctx["is_reserved"] or not ctx["has_fm"] or tags_set is None:
        return []
    return ["tag `{}` not registered in TAGS.md".format(t)
            for t in extract_tags(ctx["text"]) if t not in tags_set]


def check_english_keys(ctx):
    if ctx["is_reserved"] or not ctx["has_fm"]:
        return []
    hits = GERMAN_FM_KEYS & set(ctx["fm"].keys())
    return ["German frontmatter key(s): {}".format(", ".join(sorted(hits)))] if hits else []


def check_tags_block_form(ctx):
    """Local convention (this catalogue, not OKF spec): `tags` must be a YAML
    block-list, not inline `[a, b]`. Empty `[]` is fine (nothing to convert)."""
    if ctx["is_reserved"] or not ctx["has_fm"]:
        return []
    raw = ctx["fm"].get("tags", "").strip()
    if raw.startswith("[") and raw.endswith("]") and raw[1:-1].strip():
        return ["tags field uses inline form — local convention requires YAML block-list"]
    return []


def check_crosslink_format(ctx):
    """Cross-links must be catalogue-root-absolute (`/bundle/subdir/concept.md`,
    leading `/` = catalogue root = Obsidian vault root). Flags (a) relative links
    that resolve inconsistently and orphan in Obsidian, and (b) leading-`/` links
    that do not resolve to a real file from the catalogue root (legacy bundle-
    relative `/subdir/x.md` or typos — the phantom-orphan class).

    D-rx51-01 (OKFT-rx51): RESERVED files (index.md, log.md, readme.md,
    index-map.md) are scanned as a link source too — they routinely carry
    hand-authored prose alongside or instead of the managed
    `<!-- okf:index -->` block, and a crosslink an author writes there is a
    real crosslink. The managed block itself is masked out first so its
    generated links never trigger a warning; fix_crosslinks is untouched by
    this — it still never rewrites a RESERVED file."""
    # Symlinked external bundles keep the portable bundle-relative OKF form and are
    # audited in their own repo — the catalogue-root convention does not apply here.
    if os.path.islink(os.path.join(ctx["root"], ctx["bundle"])):
        return []
    relative, dangling = [], []
    scan_body, _ = _mask_code_spans(_mask_managed_block(ctx["body"]))
    # fenced/inline example links and the managed index block are not hand-authored links
    for m in re.finditer(r"\[[^\]]+\]\(([^)]+)\)", scan_body):
        tgt = m.group(1).split("#")[0].split("?")[0].strip()
        if not tgt.endswith(".md") or tgt.startswith(("http://", "https://", "mailto:")):
            continue
        if not tgt.startswith("/"):
            relative.append(tgt)
        elif not os.path.isfile(os.path.join(ctx["root"], tgt.lstrip("/"))):
            dangling.append(tgt)
    msgs = []
    if relative:
        msgs.append("non catalogue-absolute link(s) (use /bundle/…): {}".format(", ".join(relative)))
    if dangling:
        msgs.append("catalogue-absolute link(s) not resolving from root: {}".format(", ".join(dangling)))
    return msgs


def check_superseded_by_resolves(ctx):
    """D01 (OKFT-gpcx) — `superseded_by` is a pointer, and a pointer to
    nothing is the same violation class as a dead crosslink: ERROR, part of
    the `0 violations` commit gate. Same catalogue-root-absolute resolution
    check_crosslink_format uses (leading `/` = catalogue root)."""
    if ctx["is_reserved"] or not ctx["has_fm"]:
        return []
    sb = _dequote(ctx["fm"].get("superseded_by", "").strip())
    if not sb:
        return []
    if os.path.isfile(os.path.join(ctx["root"], sb.lstrip("/"))):
        return []
    return ["superseded_by target does not resolve: {}".format(sb)]


def check_superseded_by_scope(ctx):
    """D01 (OKFT-gpcx) — the scope guard: `superseded_by` is defined only for
    `type: Decision` concepts. A concept of another type carrying the field
    is not a hard failure (it may be an intentional early use or a schema
    typo an author can fix at leisure) — WARNING, not ERROR."""
    if ctx["is_reserved"] or not ctx["has_fm"]:
        return []
    sb = _dequote(ctx["fm"].get("superseded_by", "").strip())
    if not sb:
        return []
    t = ctx["fm"].get("type", "").strip()
    if t == "Decision":
        return []
    return ["superseded_by used on non-Decision concept (type={})".format(
        t or "<empty>")]


_TAG = r"</?[A-Za-z][\w:-]*>"
XML_TAG_CHAIN_RE = re.compile(r"{t}(?:\.(?:{t}|[A-Za-z0-9_-]+))*".format(t=_TAG))
SAFE_HTML_TAGS = {"br", "hr", "sub", "sup", "kbd", "mark", "code", "wbr"}
AUTOLINK_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")


def _mask_managed_block(body):
    """Blank out the managed `<!-- okf:index -->`..`<!-- /okf:index -->` region
    so a hand-authored-crosslink scan of a RESERVED file never flags a
    generated link. Non-greedy: an unterminated/absent marker pair leaves
    body untouched (find/find-based _replace_block behaves the same way)."""
    return re.sub(re.escape(MARK_START) + r"[\s\S]*?" + re.escape(MARK_END), "", body)


def _split_managed_block(body):
    """Split `body` into (before, block, after) around the managed
    `<!-- okf:index -->`..`<!-- /okf:index -->` region, for a rewrite that
    must preserve the block byte-identical instead of deleting it like
    `_mask_managed_block` does. Three cases:
      - complete marker pair: `block` carries both markers and everything
        between them; `before`/`after` are the surrounding text.
      - `MARK_START` present without a matching `MARK_END` (malformed/
        truncated file): `block` carries everything from `MARK_START` to
        end-of-file — an unterminated marker cannot be told apart from a
        marker whose close tag was itself mid-edit, so the conservative
        choice protects it rather than guessing it is safe to rewrite.
      - no `MARK_START` at all: `before` is the whole body, `block` and
        `after` are empty — the caller rewrites everything, same as a
        non-RESERVED file, with no special-casing needed.
    A caller that only ever rewrites `before` and `after` gets the
    byte-identical-block guarantee by construction, not by comparison."""
    si = body.find(MARK_START)
    if si == -1:
        return body, "", ""
    ei = body.find(MARK_END, si)
    if ei == -1:
        return body[:si], body[si:], ""
    ei += len(MARK_END)
    return body[:si], body[si:ei], body[ei:]


def sync_hash(payload):
    """Fingerprint of a canon block payload. Normalised (CRLF folded, outer
    whitespace stripped) so a line-ending translation or a trailing newline
    gained in transit does not read as a content change. sha1, first 12 hex
    chars — same convention as concept_cache_key in embeddings/build_tagvec."""
    return hashlib.sha1(
        payload.replace("\r\n", "\n").strip().encode("utf-8")).hexdigest()[:12]


def parse_canon_blocks(body):
    """Every `okf:canon` block declared in one concept body, in document order:
    [{"id", "payload", "span"}]. `payload` is None when the opening marker has
    no matching CANON_END — an unterminated marker is reported, never guessed
    at, exactly as _split_managed_block refuses to guess for the index block.
    `span` is (start, end) in `body`, end past CANON_END (or end-of-body when
    unterminated)."""
    out = []
    for m in CANON_OPEN_RE.finditer(body):
        ei = body.find(CANON_END, m.end())
        if ei == -1:
            out.append({"id": m.group(1), "payload": None,
                        "span": (m.start(), len(body))})
            continue
        out.append({"id": m.group(1), "payload": body[m.end():ei],
                    "span": (m.start(), ei + len(CANON_END))})
    return out


def parse_sync_blocks(body):
    """Every materialised canon block in one consumer body, in document order:
    [{"id", "source", "hash", "payload", "span", "malformed"}].

    Scanning starts from each literal SYNC_OPEN_LIT occurrence rather than
    from the full-form regex, so a hand-edited marker still produces a record
    (malformed=True) instead of vanishing from every report — a block nobody
    can see is the one that silently turns a consumer authoritative.

    `span` is (start, end) in the ORIGINAL body, end past SYNC_END, so
    body[span[0]:span[1]] is the whole block verbatim. Same contract as
    parse_wikilinks' span: it is what the rewriters splice against."""
    out = []
    starts = []
    i = body.find(SYNC_OPEN_LIT)
    while i != -1:
        starts.append(i)
        i = body.find(SYNC_OPEN_LIT, i + 1)
    for n, start in enumerate(starts):
        # A malformed block must not swallow the next one: every structural
        # search is bounded by the following opening marker.
        limit = starts[n + 1] if n + 1 < len(starts) else len(body)
        rec = {"id": None, "source": None, "hash": None, "payload": None,
               "span": (start, limit), "malformed": True}
        m = SYNC_OPEN_RE.match(body, start)
        if not m or m.end() > limit:
            out.append(rec)
            continue
        rec["id"], rec["source"], rec["hash"] = (
            m.group("id"), m.group("source"), m.group("hash"))
        bi = body.find(SYNC_BODY, m.end(), limit)
        if bi == -1:
            out.append(rec)
            continue
        ei = body.find(SYNC_END, bi + len(SYNC_BODY), limit)
        if ei == -1:
            out.append(rec)
            continue
        rec["payload"] = body[bi + len(SYNC_BODY):ei]
        rec["span"] = (start, ei + len(SYNC_END))
        rec["malformed"] = False
        out.append(rec)
    return out


def render_sync_block(block_id, source, payload):
    """The one place the sync notation is authored — analogue of render_block
    for the index family. The visible callout is generated between the opening
    marker and SYNC_BODY, so an Obsidian reader sees the text is foreign Canon
    while the hash still covers the payload alone."""
    return (
        "<!-- okf:sync id={} source={} hash={} -->\n"
        "> [!quote] Synchronisiert aus `{}` — Canon-Owner, hier nicht bearbeiten.\n"
        "{}\n{}\n{}".format(block_id, source, sync_hash(payload), source,
                            SYNC_BODY, payload.strip("\n"), SYNC_END))


def build_canon_block_index(root):
    """{(concept_rel, block_id): payload} over the whole catalogue.

    `concept_rel` is spelled exactly like ctx["rel"], so a consumer's
    `source=/bundle/concept.md` compares by plain string after stripping the
    leading slash — no path arithmetic at classification time. Costs one
    catalogue walk, like check's basename index, which is why every caller
    builds it lazily."""
    idx = {}
    # include_archive: archiving an owner rewrites every consumer's `source=`
    # to the `/_archive/...` path, so the archived concept must stay a
    # resolvable owner — otherwise one archive turns every consumer into a
    # `source-missing` error. prune_staging=False (OKFT bug): "_"-prefixed
    # dirs (_inbox, _archive, any custom staging dir) are pruned by default,
    # so an owner living there was invisible here even though the file
    # exists — every consumer then misreported `source-missing`.
    for _, bp in resolve_scopes(root, None, include_archive=True):
        for ap in iter_all_md(bp, prune_staging=False):
            _, body = split_frontmatter(read_file(ap))
            if "okf:canon" not in body:
                continue
            rel = os.path.relpath(ap, root).replace(os.sep, "/")
            for blk in parse_canon_blocks(body):
                if blk["payload"] is None:
                    continue          # unterminated: check_canon_blocks reports it
                idx.setdefault((rel, blk["id"]), blk["payload"])
    return idx


def classify_sync_block(rec, canon):
    """One of six statuses for a parsed sync record against the canon index:
    malformed, source-missing, synced, source-changed, consumer-modified,
    both-changed.

    `consumer-modified` and `both-changed` outrank `source-changed`: a local
    edit to a materialised copy is the failure this whole mechanism exists to
    catch, and re-materialising over it would destroy the only copy of that
    edit."""
    if rec["malformed"] or not rec["source"].startswith("/"):
        return "malformed"
    payload = canon.get((rec["source"].lstrip("/"), rec["id"]))
    if payload is None:
        return "source-missing"
    src_matches = sync_hash(payload) == rec["hash"]
    local_matches = sync_hash(rec["payload"]) == rec["hash"]
    if src_matches and local_matches:
        return "synced"
    if local_matches:
        return "source-changed"
    return "consumer-modified" if src_matches else "both-changed"


def _sync_records(ctx, canon_index):
    """[(rec, status)] for one file, or [] without paying for the canon index.

    The early exit IS the performance contract of the two check entries: a
    catalogue with no materialised block must not trigger the catalogue walk
    build_canon_block_index costs."""
    if SYNC_OPEN_LIT not in ctx["body"]:
        return []
    canon = canon_index()
    return [(r, classify_sync_block(r, canon))
            for r in parse_sync_blocks(ctx["body"])]


def check_sync_integrity(ctx, canon_index):
    """Errors: a materialised canon block whose markers are broken, whose
    owner is gone, or whose payload was edited locally.

    `consumer-modified` is an error, not a warning: a consumer holding an
    edited copy of foreign Canon has silently become a second authority, which
    is precisely what this mechanism exists to prevent."""
    return ["sync block `{}` from {}: {}".format(
                rec["id"] or "?", rec["source"] or "?", status)
            for rec, status in _sync_records(ctx, canon_index)
            if status in ("malformed", "source-missing", "consumer-modified",
                          "both-changed")]


def check_sync_stale(ctx, canon_index):
    """Warning: the owner's block moved on while the local copy is untouched —
    mechanically repairable, so it never blocks."""
    return ["sync block `{}` from {} is outdated — run sync-update".format(
                rec["id"], rec["source"])
            for rec, status in _sync_records(ctx, canon_index)
            if status == "source-changed"]


def check_canon_blocks(ctx):
    """Owner-side integrity, index-free: an unterminated `okf:canon` marker,
    or one id declared twice in the same concept — which would make
    `(source, id)` addressing ambiguous for every consumer of it."""
    out, seen = [], set()
    for blk in parse_canon_blocks(ctx["body"]):
        if blk["payload"] is None:
            out.append("canon block `{}` has no closing {}".format(
                blk["id"], CANON_END))
        if blk["id"] in seen:
            out.append("canon block id `{}` declared twice".format(blk["id"]))
        seen.add(blk["id"])
    return out


def _mask_code_spans(body):
    """Stash materialised canon blocks, fenced code blocks and inline code so
    a pattern scan skips them.
    Frontmatter is already split off by the caller (ctx["body"]/split_frontmatter),
    so only sync blocks/fences/inline-code need masking here. Mirrors the
    Vault-side wrap-hex-tags.js mask/unmask convention for the same class of
    problem.

    The sync stash runs FIRST, and it is not cosmetic: a materialised canon
    block is owned by its canon concept, so every scanner reading through this
    mask must neither report nor rewrite inside it. _unmask restores the
    stashed text byte-identically, which is what keeps a rewriter (fix-
    crosslinks, fix-xml-tags) from turning a synced payload into a false
    `consumer-modified`."""
    tokens = []

    def stash(m):
        tokens.append(m.group(0))
        return "\x00{}\x00".format(len(tokens) - 1)

    body = SYNC_SPAN_RE.sub(stash, body)
    body = re.sub(r"(`{3,}|~{3,})[\s\S]*?\1", stash, body)
    body = re.sub(r"`[^`\n]+`", stash, body)
    return body, tokens


def _unmask(text, tokens):
    return re.sub(r"\x00(\d+)\x00", lambda m: tokens[int(m.group(1))], text)


def _is_ignorable_chain(chain):
    """Skip real HTML (`<br>`, `</br>`, ...) and markdown autolinks
    (`<https://...>`) — only placeholder-shaped chains are violations."""
    if "." not in chain and chain.strip("<>/").lower() in SAFE_HTML_TAGS:
        return True
    inner = chain.split(".", 1)[0][1:-1].lstrip("/")
    return bool(AUTOLINK_RE.match(inner))


def find_xml_like_tags(body):
    """Angle-bracket placeholder chains like `<info>.<other>` or `<tag>.<tag2>.go`
    outside code spans — Obsidian misreads these as unclosed XML/HTML tags."""
    masked, _ = _mask_code_spans(body)
    return [m for m in XML_TAG_CHAIN_RE.findall(masked) if not _is_ignorable_chain(m)]


def check_xml_like_tags(ctx):
    if ctx["is_reserved"]:
        return []
    hits = find_xml_like_tags(ctx["body"])
    return ["angle-bracket placeholder(s) not in code-fence: {}".format(", ".join(sorted(set(hits))))] if hits else []


def fix_xml_like_tags(root, target, dry_run=False):
    """Wrap angle-bracket placeholder chains in inline code across every
    non-reserved .md under `target` (bundle or bundle/subdir, or the whole
    catalogue when None). Returns [(rel, count), ...]."""
    touched = []
    for bundle, bp in resolve_scopes(root, target):
        for ap in iter_all_md(bp, prune_staging=False):
            if os.path.basename(ap).lower() in RESERVED:
                continue
            text = read_file(ap)
            _, body = split_frontmatter(text)
            head = text[:len(text) - len(body)]
            masked, tokens = _mask_code_spans(body)
            count = 0

            def repl(m):
                nonlocal count
                chain = m.group(0)
                if _is_ignorable_chain(chain):
                    return chain
                count += 1
                return "`" + chain + "`"

            new_masked = XML_TAG_CHAIN_RE.sub(repl, masked)
            new_body = _unmask(new_masked, tokens)
            if count:
                rel = os.path.relpath(ap, root).replace(os.sep, "/")
                touched.append((rel, count))
                if not dry_run:
                    write_file(ap, head + new_body)
    return touched


def cmd_fix_xml_tags(root, args):
    target = args.target
    if target:
        tp = os.path.join(root, target.rstrip("/"))
        if not os.path.isdir(tp):
            print("not a directory: {}".format(target), file=sys.stderr)
            sys.exit(1)
    touched = fix_xml_like_tags(root, target, dry_run=args.check)
    verb = "would wrap" if args.check else "wrapped"
    for rel, n in touched:
        print("{:<12} {}  ({} chain(s))".format(verb, rel, n))
    print("fix-xml-tags: {} file(s) {}, {} chain(s) total".format(
        len(touched), verb, sum(n for _, n in touched)))


def check_asset_placement(bundle_path):
    """Non-md, non-hidden files that live outside <bundle>/assets/. Returns
    a list of paths relative to bundle_path."""
    bad = []
    for dirpath, dirnames, filenames in os.walk(bundle_path):
        dirnames[:] = [d for d in dirnames
                       if not d.startswith(".") and not d.startswith("_") and d != "assets"]
        for fn in filenames:
            if fn.endswith(".md") or fn.startswith("."):
                continue
            bad.append(os.path.relpath(os.path.join(dirpath, fn), bundle_path).replace(os.sep, "/"))
    return bad


def check_entry_file_description(bundle_path):
    """A bundle's entry file (INDEX-MAP.md preferred, else index.md) must carry
    an H1 + a real intro paragraph — `index --full` surfaces this as the
    bundle's `description`. Returns a list of violation messages (0..2)."""
    for fn in ("INDEX-MAP.md", "index.md"):
        fp = os.path.join(bundle_path, fn)
        if os.path.isfile(fp):
            h1, desc = index_h1_and_desc(fp)
            msgs = []
            if not h1:
                msgs.append("{} missing H1".format(fn))
            if not desc.strip():
                msgs.append("{} missing intro paragraph (used as bundle description)".format(fn))
            return msgs
    return ["no entry file (INDEX-MAP.md/index.md) found"]


def resolve_crosslink_target(root, bundle, cdir, tgt):
    """Absolute filesystem path a link target `tgt` (found in bundle/cdir) points
    at, then re-expressed as the canonical catalogue-root-absolute form
    (`/bundle/subdir/concept.md`, leading `/` = catalogue root = Obsidian vault
    root). Interpretations are tried in order so the same rewriter both migrates
    legacy links and stays idempotent:
      1. leading `/` as LEGACY bundle-root (`/subdir/x.md` -> bundle/subdir/x.md)
      2. leading `/` as already-catalogue-root (`/bundle/subdir/x.md`)
      3. relative to cdir within the bundle (`x.md`, `sub/x.md`, `../other/x.md`)
    Returns the canonical `/…` string only if the target file really exists (the
    safety anchor that leaves doc examples on non-existent paths untouched)."""
    if tgt.startswith("/"):
        p = tgt.lstrip("/")
        dest = os.path.join(root, bundle, p)            # legacy bundle-root
        if not os.path.isfile(dest):
            dest = os.path.join(root, p)                 # already catalogue-root
    else:
        dest = os.path.normpath(os.path.join(root, bundle, cdir, tgt))
        if not os.path.isfile(dest):
            # mis-depthed cross-bundle relative link (`../other-bundle/x.md` whose
            # `..` count never reaches the catalogue root): repoint from root iff
            # the `../`-stripped tail is a real file — no guessing beyond existence.
            tail = re.sub(r"^(?:\.\.?/)+", "", tgt)
            cand = os.path.join(root, tail)
            if os.path.isfile(cand):
                dest = cand
    if not os.path.isfile(dest):
        return None
    return "/" + os.path.relpath(dest, root).replace(os.sep, "/")


def rewrite_crosslinks_in_body(root, bundle, cdir, body):
    """Rewrite every resolvable markdown link to canonical catalogue-root-absolute
    form (`/bundle/subdir/concept.md`). Migrates legacy bundle-relative (`/sub/x`)
    and path-relative (`x`, `../other/x`) links alike; already-canonical links are
    left byte-identical (idempotent). Skips http(s)/mailto/anchor-only, and
    everything inside fenced or inline code — a link written between backticks
    is prose *about* link syntax, which Obsidian never resolves. Masking it
    keeps the OKF documentation bundles from reporting their own examples as
    unresolved, and stops a fenced example whose path happens to resolve from
    being silently rewritten. Mirrors check_crosslink_format, which masks the
    same spans. Returns (new_body, changed_count, unresolved_targets)."""
    changed = 0
    unresolved = []

    def repl(m):
        nonlocal changed
        label, target = m.group(1), m.group(2)
        raw_tgt, _, anchor = target.partition("#")
        raw_tgt = raw_tgt.strip()
        if not raw_tgt.endswith(".md") or raw_tgt.startswith(("http://", "https://", "mailto:")):
            return m.group(0)
        resolved = resolve_crosslink_target(root, bundle, cdir, raw_tgt)
        if resolved is None:
            unresolved.append(raw_tgt)
            return m.group(0)
        new_target = resolved + ("#" + anchor if anchor else "")
        if new_target == target:
            return m.group(0)                            # already canonical
        changed += 1
        return "[{}]({})".format(label, new_target)

    masked, tokens = _mask_code_spans(body)
    new_body = _unmask(CROSSLINK_RE.sub(repl, masked), tokens)
    return new_body, changed, unresolved


def fix_crosslinks(root, target, dry_run=False, include_reserved=False):
    """Rewrite crosslinks in every non-reserved .md under `target` (bundle or
    bundle/subdir, or the whole catalogue when None) to catalogue-root-absolute
    form. `include_reserved=True` (D-fxcr-01) additionally rewrites RESERVED
    files (index.md, log.md, readme.md, index-map.md), narrowed to the text
    outside the managed `<!-- okf:index -->` block via `_split_managed_block` —
    the block itself is never handed to the rewriter, so it stays
    byte-identical. Default (`include_reserved=False`) leaves RESERVED files
    untouched, unchanged from before this parameter existed. Returns
    (touched, unresolved): touched = [(rel, changed_count), ...],
    unresolved = [(rel, target), ...]."""
    touched, unresolved = [], []
    for bundle, bp in resolve_scopes(root, target):
        for ap in iter_all_md(bp, prune_staging=False):
            is_reserved = os.path.basename(ap).lower() in RESERVED
            if is_reserved and not include_reserved:
                continue
            text = read_file(ap)
            _, body = split_frontmatter(text)
            head = text[:len(text) - len(body)]
            cdir = os.path.dirname(os.path.relpath(ap, bp))
            rel = os.path.relpath(ap, root).replace(os.sep, "/")
            if is_reserved:
                before, block, after = _split_managed_block(body)
                new_before, changed_before, unres_before = rewrite_crosslinks_in_body(
                    root, bundle, cdir, before)
                new_after, changed_after, unres_after = rewrite_crosslinks_in_body(
                    root, bundle, cdir, after)
                new_body = new_before + block + new_after
                changed = changed_before + changed_after
                unres = unres_before + unres_after
            else:
                new_body, changed, unres = rewrite_crosslinks_in_body(root, bundle, cdir, body)
            for u in unres:
                unresolved.append((rel, u))
            if changed:
                touched.append((rel, changed))
                if not dry_run:
                    write_file(ap, head + new_body)
    return touched, unresolved


def cmd_fix_crosslinks(root, args):
    target = args.target
    if target:
        tp = os.path.join(root, target.rstrip("/"))
        if not os.path.isdir(tp):
            print("not a directory: {}".format(target), file=sys.stderr)
            sys.exit(1)
    touched, unresolved = fix_crosslinks(root, target, dry_run=args.check,
                                          include_reserved=args.include_reserved)
    verb = "would rewrite" if args.check else "rewrote"
    for rel, n in touched:
        print("{:<14} {}  ({} link(s))".format(verb, rel, n))
    for rel, tgt in unresolved:
        print("unresolved     {}  -> {}".format(rel, tgt))
    print("fix-crosslinks: {} file(s) {}, {} unresolved link(s)".format(
        len(touched), verb, len(unresolved)))


# --- wikilinks -------------------------------------------------------------
# Obsidian's native link form. Every markdown-link scanner in this module
# anchors on "](" (CROSSLINK_RE plus its three inline copies), so none of them
# can see a [[…]] — a rename rewrites the markdown links, reports success and
# silently orphans every inbound wikilink. Everything below is the wikilink
# counterpart of that machinery: parse, resolve, report, rewrite.

WIKILINK_RE = re.compile(r"(!?)\[\[([^\[\]\n]+)\]\]")


def _split_wikilink_inner(inner):
    """(page, alias, suffix) for the text between `[[` and `]]`.

    Obsidian's grammar is `[[page#suffix|alias]]` — the `#` binds to the page
    part only. An alias may legitimately contain one (`[[dotnet|C#]]`,
    `[[issue|bug #42]]`), so the alias segment is never re-split."""
    page_part, sep, alias = inner.partition("|")
    page, hsep, suffix = page_part.partition("#")
    page = page.strip()
    if page.lower().endswith(".md"):
        # case-insensitively, like every other comparison here: `[[Old.MD]]`
        # must not be the one spelling that fails to resolve.
        page = page[:-3]
    return (page,
            alias.strip() if sep else None,
            suffix.strip() if hsep and suffix.strip() else None)


def parse_wikilinks(text, source=None):
    """Every `[[…]]` occurrence in one file's text as a record, minus the
    status/candidates the resolver fills in.

    `raw` excludes a leading `!` — the embed marker lives in its own field,
    which keeps `raw` a link token that can be substituted as-is. Each record
    also carries `span`, the (start, end) offsets of `raw` in the ORIGINAL
    text, which is what lets a rewrite touch exactly the occurrences this scan
    accepted and nothing else."""
    out = []
    fm_end = wikilink_regions(text)[0][2]
    for m in WIKILINK_RE.finditer(wikilink_scan_text(text)):
        # Cut from the ORIGINAL, not the masked copy: a dead zone nested inside
        # the brackets would otherwise put NUL bytes into `raw` and break the
        # contract that `text[span] == raw`.
        inner = text[m.start(2):m.end(2)]
        page, alias, suffix = _split_wikilink_inner(inner)
        if not page:
            continue               # [[#heading]] — an in-file anchor, no target
        out.append({
            "source": source,
            "region": "frontmatter" if m.start() < fm_end else "body",
            "raw": "[[{}]]".format(inner),
            "page": page,
            "alias": alias,
            "suffix": suffix,
            "embed": bool(m.group(1)),
            "span": (m.start(2) - 2, m.end(2) + 2),
        })
    return out


def _apply_archive_precedence(candidates):
    """R-06's precedence rule as a pure function over one basename's raw,
    possibly-mixed candidate list: active candidates win outright whenever
    at least one exists; archived candidates (`/_archive/<bundle>/...`) are
    the fallback only when none do. Shared by build_concept_basename_index
    (the real index) and _index_after_move (its move simulation, R-07,
    docs/okf-archive-lifecycle/SPEC.md) so a change to the rule cannot land
    in only one of the two — that drift is exactly what R-07 exists to
    close: a dry run reporting an ambiguity that never materialises, or the
    reverse."""
    active = [c for c in candidates if not c.lower().startswith("/_archive/")]
    return sorted(active) if active else sorted(candidates)


def _normalize_key(s):
    """Normalize and lowercase a basename key for case/NFC-insensitive matching.

    Order matters: first normalize to NFC (canonical composition), then lowercase
    (matching Obsidian's JavaScript toLowerCase()). This ensures keys derived from
    filenames on APFS (which deliver NFD) match links typed in NFC and vice versa.
    D06 is preserved: casefold() is avoided — [[STRASSE]] vs Straße stay unresolved.
    """
    return unicodedata.normalize('NFC', s).lower()


def build_concept_basename_index(root):
    """lowercased basename (no .md) -> sorted catalogue-root-absolute paths of
    every non-reserved concept. A wikilink carries no path, so the basename IS
    the address — this is the table it resolves against.

    Case-insensitive because the store's filesystem is: `open("TYPES.md")` and
    `open("types.MD")` reach the same file on macOS, and Obsidian resolves
    `[[YAML]]` to `yaml.md` accordingly. A case-sensitive table reports 96 live
    catalogue links as dead and lets `rename` orphan them unannounced — the
    exact failure this feature exists to close.

    `lower()`, not `casefold()`: Obsidian folds with JavaScript's
    `toLowerCase()`, which leaves ß alone where casefold maps it to ss. Under
    casefold `[[STRASSE]]` would resolve to `Straße.md` here and stay broken in
    the app, and on a case-sensitive checkout `Straße.md` and `Strasse.md` would
    collapse into one key and shadow each other.

    Traverses with iter_all_md (minus reserved files) rather than
    iter_concepts, so the set of resolution TARGETS is the same set of files
    the reporting and check surfaces scan as SOURCES: iter_concepts descends
    into `_`-prefixed staging directories, which would make a draft a valid
    link target that no surface ever reports on. Walks per bundle because
    os.walk does not descend into symlinked subdirectories and five catalogue
    bundles are symlinks.

    `_archive/<bundle>/**` is folded in as a second, lower-priority tier
    (docs/okf-archive-lifecycle/SPEC.md R-05/R-06): without it, archiving a
    concept turns every inbound `[[x]]` unresolved in files the archiver never
    touched. Existing at least one ACTIVE candidate for a basename means the
    archived candidates of that basename are dropped entirely, never merged
    in — otherwise archive-then-recreate-under-the-same-name would turn a
    clean resolution into `ambiguous` against a copy nobody meant to address,
    and two active concepts sharing a basename would stop being `ambiguous`
    the moment either one grew an archived namesake. Only a basename with NO
    active candidate falls through to its archived candidate(s)."""
    idx = {}
    for b in list_bundles(root):
        for ap in iter_all_md(os.path.join(root, b)):
            fn = os.path.basename(ap)
            if fn.lower() in RESERVED:
                continue
            idx.setdefault(_normalize_key(fn[:-3]), []).append(
                "/" + os.path.relpath(ap, root).replace(os.sep, "/"))
    archive_root = os.path.join(root, "_archive")
    if os.path.isdir(archive_root):
        for b in list_bundles(archive_root):
            for ap in iter_all_md(os.path.join(archive_root, b)):
                fn = os.path.basename(ap)
                if fn.lower() in RESERVED:
                    continue
                idx.setdefault(_normalize_key(fn[:-3]), []).append(
                    "/" + os.path.relpath(ap, root).replace(os.sep, "/"))
    for k in idx:
        idx[k] = _apply_archive_precedence(idx[k])
    return idx


def resolve_wikilink(index, source_rel, page):
    """(status, candidates) for one page part seen in `source_rel`.

    Resolution order, matching how Obsidian narrows a target:
      1. every concept whose basename equals the page part's last segment,
         compared case-insensitively;
      2. if the page part carries a path (`[[dir/name]]`), only the candidates
         whose own path ends in that path — an author who spelled the directory
         out meant it. A path matching nothing is `unresolved`, not a fallback
         to the bare basename: the fallback answered with the very candidate the
         spelling excludes, which is the failure this step exists to prevent;
      3. on a remaining collision, the linking file's own bundle wins when
         exactly one candidate lives there."""
    cands = index.get(_normalize_key(page.rsplit("/", 1)[-1]), [])
    if not cands:
        return "unresolved", []
    if "/" in page:
        tail = "/{}.md".format(page.strip("/"))
        cands = [c for c in cands if _normalize_key(c).endswith(_normalize_key(tail))]
        if not cands:
            return "unresolved", []
    if len(cands) == 1:
        return "resolved", list(cands)
    own = (source_rel or "").split("/", 1)[0].lower()
    same = [c for c in cands if c.lstrip("/").split("/", 1)[0].lower() == own]
    if len(same) == 1:
        return "resolved", same
    return "ambiguous", list(cands)


def resolve_wikilink_records(index, records):
    """Fill status/candidates into parse_wikilinks() records, in place."""
    for rec in records:
        rec["status"], rec["candidates"] = resolve_wikilink(
            index, rec["source"], rec["page"])
    return records


def scan_wikilinks(root, target=None, index=None):
    """Every resolved wikilink record under `target` (bundle or bundle/subdir,
    whole catalogue when None). Traverses with iter_all_md, so `_`-prefixed
    staging dirs and assets/ are excluded and reserved files are included."""
    if index is None:
        index = build_concept_basename_index(root)
    out = []
    for _bundle, bp in resolve_scopes(root, target):
        for ap in iter_all_md(bp):
            rel = os.path.relpath(ap, root).replace(os.sep, "/")
            out += resolve_wikilink_records(
                index, parse_wikilinks(read_file(ap), rel))
    return out


def wikilink_checked_bundles(config, root=None):
    """The opt-in set for the wikilink-resolvable check. Absent key or absent
    .okf.toml means the empty set: the rule ships silent and is switched on per
    bundle, so introducing it cannot bury a clean catalogue in warnings.

    A value the gate cannot honour is announced on stderr rather than silently
    disabling the rule — a config that reads as if it opted a bundle in, but
    does not, is worse than no config at all."""
    if "wikilink_checked_bundles" not in config:
        return set()
    v = config["wikilink_checked_bundles"]
    if not isinstance(v, (list, tuple)) or not all(isinstance(x, str) for x in v):
        sys.stderr.write("note: wikilink_checked_bundles must be an array of "
                         "bundle names; got {!r} — wikilink check stays off\n".format(v))
        return set()
    # Casefolded: the store's filesystem is, so `check A` reaches bundle `a`
    # and its ctx["bundle"] reads "A". An exact-string gate switched this one
    # check off there while every other check kept firing.
    out = {x.lower() for x in v}
    if root is not None:
        known = {b.lower() for b in list_bundles(root)}
        unknown = sorted(x for x in v if x.lower() not in known)
        if unknown:
            sys.stderr.write("note: wikilink_checked_bundles names non-bundle(s): "
                             "{} — no file will be checked for them\n".format(", ".join(unknown)))
    return out


def check_wikilink_resolvable(ctx, checked, index):
    """One warning per file carrying at least one unresolved or ambiguous
    wikilink, naming every such target. Reserved files and symlinked bundles
    participate — unlike check_crosslink_format, whose early returns are
    specific to the catalogue-absolute markdown convention."""
    if not checked or ctx["bundle"].lower() not in checked:
        return []
    # iter_all_md prunes staging and assets from `dirnames`, never from the
    # directory it is handed, so `check <bundle>/_plan` walked straight into a
    # tree the Non-Goals exclude from every reporting surface.
    if any(s.startswith((".", "_")) or s == "assets"
           for s in ctx["rel"].split("/")[1:-1]):
        return []
    bad = [r["raw"] for r in resolve_wikilink_records(
        index, parse_wikilinks(ctx["text"], ctx["rel"]))
        if r["status"] != "resolved"]
    if not bad:
        return []
    return ["unresolved wikilink target(s): {}".format(", ".join(bad))]


def cmd_wikilinks(root, args):
    if args.target:
        norm = os.path.normpath(args.target).replace(os.sep, "/").strip("/")
        segments = [s for s in norm.split("/") if s not in (".", "")]
        tp = os.path.join(root, norm)
        if not os.path.isdir(tp):
            print("not a directory: {}".format(args.target), file=sys.stderr)
            sys.exit(1)
        # The target must name a bundle, or a subdirectory of one that
        # iter_all_md would actually traverse. Without this, `wikilinks ..`
        # walks out of the catalogue, and `wikilinks <bundle>/_plan` scans
        # staging that the reporting surface is defined to exclude —
        # iter_all_md prunes those names from `dirnames`, never from the
        # directory it is handed as a starting point.
        excluded = [s for s in segments if s.startswith((".", "_")) or s == "assets"]
        if not segments or segments[0] not in list_bundles(root) or excluded:
            print("not a scannable bundle path: {}".format(args.target), file=sys.stderr)
            sys.exit(1)
    links = scan_wikilinks(root, args.target)
    totals = {"resolved": 0, "ambiguous": 0, "unresolved": 0}
    for r in links:
        totals[r["status"]] += 1
    shown = [r for r in links if r["status"] != "resolved"] if args.unresolved else links
    if args.json:
        import json
        # by_bundle counts what `links` carries, so the two never contradict
        # each other; `totals` is always the unfiltered census and `filtered`
        # says which of the two a consumer is looking at.
        by_bundle = {}
        for r in shown:
            b = r["source"].split("/", 1)[0]
            by_bundle.setdefault(b, {"resolved": 0, "ambiguous": 0, "unresolved": 0})
            by_bundle[b][r["status"]] += 1
        print(json.dumps({"links": shown, "by_bundle": by_bundle,
                          "totals": totals, "filtered": bool(args.unresolved)}))
        return
    for r in shown:
        line = "{:<10} {:<11} {}  {}{}".format(
            r["status"], r["region"], r["source"], r["raw"],
            "  (embed)" if r["embed"] else "")
        if r["status"] == "ambiguous":
            line += "  candidates: {}".format(", ".join(r["candidates"]))
        print(line)
    print("wikilinks: {} link(s), {} resolved, {} ambiguous, {} unresolved".format(
        len(links), totals["resolved"], totals["ambiguous"], totals["unresolved"]))


def _ctx_check_of(c, i):
    if c["bundle"] != CTX_DIR or c["is_reserved"]:
        return []
    return ctx_findings(c["root"], c["ap"])[i]


def run_checks(root, target, types_source=None):
    """Run the full pluggable conformance scan over `target` (bundle or
    bundle/subdir), or the whole catalogue when target is None.

    types_source overrides <root>/TYPES.md; absent, falls back to the
    .okf.toml `types_source` config key, then to <root>/TYPES.md.

    Returns (errors, warnings), each a list of (check_name, rel_path, message).
    """
    scopes = resolve_scopes(root, target)
    config = load_okf_config(root)
    if types_source is None:
        types_source = config.get("types_source")
    types_set = load_types(root, types_source)
    tags_set = load_tags(root)
    # The basename index costs a full catalogue walk, so it is built only when
    # a bundle IN THIS RUN'S SCOPE has opted in — an unconfigured catalogue, or
    # a scan targeting a bundle that did not opt in, pays nothing.
    wl_checked = (wikilink_checked_bundles(config, root)
                  & {b.lower() for b, _ in scopes})
    wl_index = build_concept_basename_index(root) if wl_checked else {}
    # Same deliberate laziness as wl_index above: the canon index costs a full
    # catalogue walk, and a catalogue with no materialised block never asks
    # for it — check_sync_* return before calling this on such a file.
    canon = {"loaded": False, "idx": {}}

    def canon_index():
        if not canon["loaded"]:
            canon["idx"] = build_canon_block_index(root)
            canon["loaded"] = True
        return canon["idx"]

    per_file_checks = [
        ("frontmatter-parseable", "error", check_fm_parseable),
        ("type-nonempty", "error", check_type_nonempty),
        ("reserved-no-type", "error", check_reserved_no_type),
        ("filename-chars", "error", check_filename_chars),
        ("type-registered", "warning", lambda c: check_type_registered(c, types_set)),
        ("tag-registered", "warning", lambda c: check_tag_registered(c, tags_set)),
        ("english-keys", "warning", check_english_keys),
        ("crosslink-format", "warning", check_crosslink_format),
        ("superseded-by-resolves", "error", check_superseded_by_resolves),
        ("superseded-by-scope", "warning", check_superseded_by_scope),
        ("tags-block-form", "warning", check_tags_block_form),
        ("xml-like-tags", "warning", check_xml_like_tags),
        ("wikilink-resolvable", "warning",
         lambda c: check_wikilink_resolvable(c, wl_checked, wl_index)),
        ("sync-block", "error", lambda c: check_sync_integrity(c, canon_index)),
        ("sync-stale", "warning", lambda c: check_sync_stale(c, canon_index)),
        ("canon-block", "error", check_canon_blocks),
        ("ctx", "error", lambda c: _ctx_check_of(c, 0)),
        ("ctx", "warning", lambda c: _ctx_check_of(c, 1)),
    ]

    errors, warnings = [], []
    for bundle, bp in scopes:
        for ap in iter_all_md(bp):
            ctx = gather_file_context(root, bundle, ap)
            for name, sev, fn in per_file_checks:
                for msg in fn(ctx):
                    (errors if sev == "error" else warnings).append((name, ctx["rel"], msg))
        for rel in check_asset_placement(bp):
            errors.append(("asset-placement", "{}/{}".format(bundle, rel), "non-md file outside assets/"))
        for msg in check_entry_file_description(bp):
            warnings.append(("entry-file-description", bundle, msg))
    return errors, warnings


def cmd_check(root, args):
    target = getattr(args, "target", None)
    if target and not os.path.isdir(os.path.join(root, os.path.normpath(target))):
        # Without this a typo'd or renamed bundle scanned nothing and exited 0 —
        # a clean bill of health for a directory that does not exist.
        print("not a directory: {}".format(target), file=sys.stderr)
        sys.exit(1)
    errors, warnings = run_checks(root, getattr(args, "target", None),
                                  types_source=getattr(args, "types", None))
    if args.strict:
        errors, warnings = errors + warnings, []
    _print_findings(errors, warnings, args.json)
    sys.exit(1 if errors else 0)


def _print_findings(errors, warnings, as_json):
    if as_json:
        print(json.dumps({
            "errors": [{"check": n, "path": p, "message": m} for n, p, m in errors],
            "warnings": [{"check": n, "path": p, "message": m} for n, p, m in warnings],
        }))
    else:
        for name, path, msg in errors:
            print("ERROR    {:<20} {}  ({})".format(name, path, msg))
        for name, path, msg in warnings:
            print("WARNING  {:<20} {}  ({})".format(name, path, msg))
        print("OK — 0 violations" if not errors else "{} VIOLATIONS".format(len(errors)))


def bundle_of(root, abspath):
    """Top-level bundle dir a path lives in (its first component under root)."""
    rel = os.path.relpath(os.path.abspath(abspath), root).replace(os.sep, "/")
    return rel.split("/", 1)[0]


def link_expr(root, src_abs, dst_abs):
    """Canonical OKF link string FROM src file TO dst target: catalogue-root-
    absolute (`/bundle/subdir/concept.md`). Leading `/` = catalogue root =
    Obsidian vault root, so the same form addresses same- and cross-bundle
    targets and resolves identically for okf-cli and Obsidian. src_abs is kept
    in the signature for call-site symmetry with resolve_link_target."""
    dst_abs = os.path.abspath(dst_abs)
    return "/" + os.path.relpath(dst_abs, root).replace(os.sep, "/")


def _split_link_suffix(raw):
    """Split a link target into (path, suffix) where suffix is a #anchor/?query
    tail (kept verbatim so a rewrite preserves deep links)."""
    cut = len(raw)
    for ch in "#?":
        i = raw.find(ch)
        if i != -1:
            cut = min(cut, i)
    return raw[:cut], raw[cut:]


def resolve_link_target(root, src_abs, raw):
    """Absolute path a markdown link target resolves to, relative to src_abs's
    location. Handles catalogue-root-absolute (`/...`) and path-relative forms. Returns
    None for external / anchor-only / non-.md links."""
    path, _ = _split_link_suffix(raw.strip())
    if not path.endswith(".md") or re.match(r"^[a-z][a-z0-9+.-]*://", path) or path.startswith("mailto:"):
        return None
    if path.startswith("/"):
        # leading / = catalogue root (= Obsidian vault root), not the bundle root
        return os.path.abspath(os.path.join(root, path.lstrip("/")))
    return os.path.abspath(os.path.join(os.path.dirname(src_abs), path))


def _dedupe(pairs):
    seen, out = set(), []
    for p in pairs:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def canonical_case_path(root, abspath):
    """`abspath` respelled the way the filesystem stores it.

    On a case-insensitive filesystem the caller may name a file in any casing,
    and every downstream comparison — the basename index, the markdown ref
    matrix, the self-reference check in cmd_rename — then compares the caller's
    spelling against the scan's. Normalising once here is what keeps those
    comparisons exact rather than case-folded, which matters because a folded
    comparison would be wrong on a case-sensitive filesystem."""
    rel = os.path.relpath(abspath, root)
    if rel.startswith(".."):
        return abspath
    cur = root
    for seg in rel.replace(os.sep, "/").split("/"):
        try:
            match = next((e for e in os.listdir(cur) if e.lower() == seg.lower()), None)
        except OSError:
            match = None
        cur = os.path.join(cur, match or seg)
    return cur


def _rewrite_wikilink_raw(raw, new_link):
    """`[[old|Label]]` -> `[[new|Label]]`, given the target's new catalogue-root
    absolute path. Alias, heading/block suffix and an explicit `.md` carry over
    verbatim, so a deep link survives the rename.

    A path-qualified link keeps a path of the same depth, re-derived from the
    NEW location — carrying the old prefix over unchanged turned `[[a/old]]`
    into `[[a/new]]` after a move to bundle `b`, an address that resolves to
    nothing."""
    inner = raw[2:-2]
    cut = len(inner)
    for ch in "#|":
        i = inner.find(ch)
        if i != -1:
            cut = min(cut, i)
    head, rest = inner[:cut], inner[cut:]
    md = ".md" if head.endswith(".md") else ""
    depth = len((head[:-3] if md else head).split("/"))
    new_segments = new_link.lstrip("/")[:-3].split("/")
    page = "/".join(new_segments[-depth:])
    return "[[{}{}{}]]".format(page, md, rest)


def plan_wikilink_rewrites(root, old_abs, new_abs):
    """The wikilink half of plan_rename. Returns (records, collisions).

    Each record is a parse_wikilinks() record plus `status` (`rewrite` or
    `skipped-ambiguous`), `candidates` and `new_raw`. `collisions` are the
    concepts that ALREADY carry the new basename: renaming into an occupied
    basename turns every rewritten `[[old]]` — and every pre-existing
    `[[new]]` elsewhere — from a unique address into an ambiguous one, which
    is the very corruption the skipped-ambiguous rule refuses to commit. The
    caller decides; this function only refuses to hide it.

    A plain `[[name]]` carries no path, so a move keeping the basename leaves it
    valid — but a path-qualified `[[dir/name]]` does not survive one, which is
    why there is no basename short-circuit: every candidate occurrence is
    compared against the token the move would produce, and only a difference is
    planned. An occurrence whose page part is ambiguous is reported, never
    rewritten: guessing which of several same-named concepts the author meant is
    not a rename, it is a coin flip."""
    old_base, new_base = os.path.basename(old_abs)[:-3], os.path.basename(new_abs)[:-3]
    index = build_concept_basename_index(root)
    old_link = "/" + os.path.relpath(old_abs, root).replace(os.sep, "/")
    new_link = "/" + os.path.relpath(new_abs, root).replace(os.sep, "/")
    files = list(iter_rename_scan_md(root))
    # Collisions come from the rename scan's own reach, not from the resolution
    # index: the index skips staging, assets and root-level files, every one of
    # which this rename rewrites and Obsidian itself indexes.
    keep = {old_link.lower(), new_link.lower()}
    collisions = sorted(
        c for c in ("/" + os.path.relpath(ap, root).replace(os.sep, "/") for ap in files)
        if _normalize_key(os.path.basename(c)[:-3]) == _normalize_key(new_base)
        and c.lower() not in keep)
    # Casefolded, because resolve_wikilink is (D06). A case-sensitive filter
    # here silently excluded every case-variant inbound link from the plan — the
    # 96 live links D06 exists to rescue would have been orphaned by the very
    # rename that was supposed to carry them.
    old_key, new_key = _normalize_key(old_base), _normalize_key(new_base)
    after = _index_after_move(index, old_link, new_link, collisions)
    out = []
    for ap in files:
        rel = os.path.relpath(ap, root).replace(os.sep, "/")
        for rec in parse_wikilinks(read_file(ap), rel):
            key = _normalize_key(rec["page"].rsplit("/", 1)[-1])
            if key not in (old_key, new_key):
                continue
            # Resolve the occurrence against the catalogue as it is and as it
            # will be. Deciding from the token alone missed the case where the
            # token does not change but its meaning does — a basename-preserving
            # move into a bundle where another concept shares the name turned a
            # unique address ambiguous with nothing to rewrite and nothing said.
            status, cands = resolve_wikilink(index, rel, rec["page"])
            was_ours = status == "resolved" and _same_path(cands, old_link)
            new_raw = _rewrite_wikilink_raw(rec["raw"], new_link) if was_ours else rec["raw"]
            page_after = _split_wikilink_inner(new_raw[2:-2])[0]
            status_after, cands_after = resolve_wikilink(after, rel, page_after)
            turns = status == "resolved" and status_after != "resolved"
            if was_ours and new_raw != rec["raw"]:
                rec.update(status="rewrite", candidates=cands, new_raw=new_raw,
                           turns_ambiguous=turns)
            elif key == old_key and status == "ambiguous" and _contains_path(cands, old_link):
                rec.update(status="skipped-ambiguous", candidates=cands,
                           new_raw=None, turns_ambiguous=False)
            elif turns:
                # Either a bystander already pointing at the basename this move
                # is about to occupy, or a link whose token does not change but
                # whose target set does. Both lose a unique address without a
                # byte of them being touched.
                rec.update(status="collision-affected", candidates=cands_after,
                           new_raw=None, turns_ambiguous=True)
            else:
                continue
            out.append(rec)
    return out, collisions


def _index_after_move(index, old_link, new_link, collisions=()):
    """The basename index as it will look once the move has happened.

    `collisions` are folded in because they come from the rename scan's wider
    reach: a same-named draft in staging is invisible to the index but visible
    to Obsidian, so leaving it out made the simulation call an address unique
    that the app will show as ambiguous.

    `index` already carries R-06's precedence (it came out of
    build_concept_basename_index), so every key untouched by the move stays
    correct by construction. The slot the move LANDS in (`key`) is the one
    exception: it gains a brand-new candidate (`new_link`, plus any
    `collisions`) that was never subject to that precedence pass, so it is
    re-applied here via the same _apply_archive_precedence R-06 uses — this
    is R-07. Concretely: archiving a concept whose basename an active
    concept still holds must not leave the freshly archived path sitting
    next to that survivor as a second candidate; the survivor alone must
    win, exactly as it would in a freshly rebuilt index."""
    out = {}
    for k, v in index.items():
        kept = [c for c in v if c.lower() != old_link.lower()]
        if kept:
            out[k] = kept
    key = os.path.basename(new_link)[:-3].lower()
    out[key] = _apply_archive_precedence(
        set(out.get(key, [])) | {new_link} | set(collisions))
    return out


def _same_path(cands, link):
    return len(cands) == 1 and cands[0].lower() == link.lower()


def _contains_path(cands, link):
    return any(c.lower() == link.lower() for c in cands)


def plan_rename(root, old_abs, new_abs):
    """Compute the reference rewrites a move old->new requires, WITHOUT touching
    disk (so it also drives the dry-run preview). Returns:
      inbound  = [(source_rel, old_raw, new_raw), ...]  links pointing AT the file
      outbound = [(old_raw, new_raw), ...]              the moved file's own links
                 (only when the bundle changes; within a bundle they stay valid)
      wikilinks= [record, ...]                          see plan_wikilink_rewrites
      bundles  = sorted affected bundle names (reindex targets)
      sync_sources = [(consumer_rel, count), ...]  consumers whose materialised
                 canon blocks record the moved file as their `source=`."""
    old_abs, new_abs = os.path.abspath(old_abs), os.path.abspath(new_abs)
    inbound = []
    for source_rel, raw in linkscan.build_ref_matrix(root, old_abs):
        src_abs = os.path.join(root, source_rel)
        if os.path.abspath(src_abs) == old_abs:
            continue  # self-reference: handled by the outbound pass
        _, suffix = _split_link_suffix(raw)
        new_raw = link_expr(root, src_abs, new_abs) + suffix
        if new_raw != raw:
            inbound.append((source_rel, raw, new_raw))
    outbound = []
    if bundle_of(root, old_abs) != bundle_of(root, new_abs):
        src = old_abs if os.path.exists(old_abs) else new_abs
        # Same mask the applier uses, or the plan reports rewrites the applier
        # then declines to make: the old ```-only strip left inline-code and
        # indented examples in the plan and out of the file.
        src_text = read_file(src)
        for m in CROSSLINK_RE.finditer(wikilink_scan_text(src_text)):
            raw = src_text[m.start(2):m.end(2)]
            tgt = resolve_link_target(root, old_abs, raw)
            if tgt is None or not os.path.isfile(tgt):
                continue
            _, suffix = _split_link_suffix(raw)
            new_raw = link_expr(root, new_abs, tgt) + suffix
            if new_raw != raw:
                outbound.append((raw, new_raw))
        outbound = _dedupe(outbound)
    bundles = sorted({bundle_of(root, old_abs), bundle_of(root, new_abs)})
    wikilinks, collisions = plan_wikilink_rewrites(root, old_abs, new_abs)
    return {"inbound": inbound, "outbound": outbound,
            "wikilinks": wikilinks, "wikilink_collisions": collisions,
            "bundles": bundles,
            "sync_sources": find_sync_source_refs(
                root, "/" + os.path.relpath(old_abs, root).replace(os.sep, "/"))}


def find_sync_source_refs(root, source_value):
    """[(consumer_rel, block_count)] — every concept carrying at least one
    materialised canon block whose `source=` is exactly `source_value`.

    Without this a rename of a canonical concept breaks the whole ownership
    graph into `source-missing`: the markdown link rewriters never see a
    `source=` attribute, because it is not a link. prune_staging=False: a
    consumer in a staging dir (_inbox, _archive, ...) must also get its
    `source=` repointed, same reasoning as build_canon_block_index."""
    out = []
    for _, bp in resolve_scopes(root, None, include_archive=True):
        for ap in iter_all_md(bp, prune_staging=False):
            _, body = split_frontmatter(read_file(ap))
            if SYNC_OPEN_LIT not in body:
                continue
            n = sum(1 for r in parse_sync_blocks(body)
                    if r["source"] == source_value)
            if n:
                out.append((os.path.relpath(ap, root).replace(os.sep, "/"), n))
    return sorted(out)


def _apply_sync_source_rewrites(abspath, old_source, new_source):
    """Repoint every `source=old_source` sync marker in one file at
    `new_source`, splicing only that attribute's slice so the payload, the
    recorded hash and the attribution line stay byte-identical — the block was
    not re-materialised, only its owner moved.

    Re-scans at apply time rather than trusting a span computed during
    planning, the same idiom _apply_link_rewrites and _apply_wikilink_rewrites
    follow."""
    text = read_file_verbatim(abspath)
    if text is None:
        sys.stderr.write("note: skipping {} — not valid UTF-8\n".format(abspath))
        return 0
    out, last, n = [], 0, 0
    for m in SYNC_OPEN_RE.finditer(text):
        if m.group("source") != old_source:
            continue
        a, b = m.start("source"), m.end("source")
        out.append(text[last:a])
        out.append(new_source)
        last = b
        n += 1
    if not n:
        return 0
    out.append(text[last:])
    write_file_verbatim(abspath, "".join(out))
    return n


def _apply_link_rewrites(abspath, rewrites):
    """Rewrite one file's markdown link targets, splicing by offset over the
    same dead-zone mask build_ref_matrix used to find them.

    A whole-file `str.replace` edited bytes the planner never reported: a link
    inside a code fence was rewritten and not counted, so the run changed a
    documentation sample while claiming a smaller edit than it made."""
    text = read_file_verbatim(abspath)
    if text is None:
        sys.stderr.write("note: skipping {} — not valid UTF-8\n".format(abspath))
        return
    mapping = dict(rewrites)
    out, last = [], 0
    for m in CROSSLINK_RE.finditer(wikilink_scan_text(text)):
        a, b = m.start(2), m.end(2)
        new_raw = mapping.get(text[a:b])
        if new_raw is None:
            continue
        out.append(text[last:a])
        out.append(new_raw)
        last = b
    out.append(text[last:])
    write_file_verbatim(abspath, "".join(out))


def _apply_wikilink_rewrites(abspath, rename_map):
    """Rewrite one file's wikilinks. `rename_map` maps an old raw token to its
    replacement; every occurrence the scanner accepts and the map names is
    spliced in by offset.

    The file is re-scanned here rather than trusting offsets from planning
    time, so this is correct regardless of what else has already rewritten the
    file in this run. Splicing by offset — instead of replacing the token
    string — is what guarantees an identical-looking `[[old]]` inside a fence,
    an indented block or a comment is never touched: the scanner never returned
    it, so no offset points at it."""
    text = read_file_verbatim(abspath)
    if text is None:
        sys.stderr.write("note: skipping {} — not valid UTF-8\n".format(abspath))
        return
    out, last = [], 0
    for rec in parse_wikilinks(text):
        new_raw = rename_map.get(rec["raw"])
        if new_raw is None:
            continue
        a, b = rec["span"]
        out.append(text[last:a])
        out.append(new_raw)
        last = b
    out.append(text[last:])
    write_file_verbatim(abspath, "".join(out))


def _git_mv(root, old_abs, new_abs):
    """History-preserving, staged move.

    Tries `git mv` at `root` first. When that fails because the source lies
    beyond a symlinked bundle boundary — its real path leaves root's own
    tree, into the foreign project repo the bundle links to — it resolves
    that real repository and retries `git mv` there; that only succeeds when
    the destination ALSO resolves into that same repo, i.e. an ordinary
    rename that stays inside the bundle (AC1, okf-cli-mk7m). `archive`'s
    destination never does: `_archive/<bundle>/…` lives in the catalogue
    root, so the two repositories differ and a single `git mv` cannot span
    them. That case, and a plain untracked file where git declines for an
    unrelated reason (PO review 2026-08-10), both fall back to a plain fs
    rename.

    Returns (moved_via_git, repo, reason):
      moved_via_git — True once a `git mv` staged the move, at `root` or at
                      a resolved foreign repository.
      repo          — the real repository that received the write, whenever
                      it differs from `root` (AC2); None when it is the
                      same, or when none could be resolved.
      reason        — git's own stderr explaining why it declined, verbatim
                      (proc.stderr was captured and never read before this
                      fix); None when git succeeded or the git binary itself
                      is unavailable.
    """
    try:
        proc = subprocess.run(["git", "-C", root, "mv", "-f", old_abs, new_abs],
                              capture_output=True, text=True)
    except OSError:
        os.rename(old_abs, new_abs)
        return False, None, None
    if proc.returncode == 0:
        return True, None, None

    reason = proc.stderr.strip() or None
    real_root = os.path.realpath(root)
    real_old = os.path.realpath(old_abs)
    foreign_repo = None
    if not (real_old == real_root or real_old.startswith(real_root + os.sep)):
        top, why = catalogue._git_toplevel(os.path.dirname(real_old))
        if why is None and os.path.realpath(top) != real_root:
            foreign_repo = os.path.realpath(top)
            real_new_dir = os.path.realpath(os.path.dirname(new_abs))
            if (real_new_dir == foreign_repo
                    or real_new_dir.startswith(foreign_repo + os.sep)):
                real_new = os.path.join(real_new_dir, os.path.basename(new_abs))
                proc2 = subprocess.run(
                    ["git", "-C", foreign_repo, "mv", "-f", real_old, real_new],
                    capture_output=True, text=True)
                if proc2.returncode == 0:
                    return True, foreign_repo, None
                reason = proc2.stderr.strip() or reason

    os.rename(old_abs, new_abs)
    return False, foreign_repo, reason


def perform_rename(root, old_abs, new_abs, apply, force, verb="rename",
                   plan=None):
    """The validation, planning and application core shared by `rename` and
    (per okf-cli-16rg) `archive`/`archive --restore`. Callers pass already
    resolved absolute paths; `verb` only steers the prefix of error messages
    ("rename: " vs "archive: ") — every other line of output is unchanged.

    `plan` (okf-cli-h12o, D01): an already-computed plan_rename() result, so
    a caller that built one for its own reporting (cmd_archive's AC7 inbound
    count) does not pay for a second build_ref_matrix scan here. Absent, this
    recomputes exactly as before — cmd_rename's call site is unchanged,
    which is what keeps AC3 (rename byte-identical) cheap to satisfy."""

    def die(msg):
        sys.stderr.write("{}: {}\n".format(verb, msg))
        sys.exit(2)

    if not old_abs.endswith(".md") or not new_abs.endswith(".md"):
        die("both paths must be .md concept files")
    if not os.path.isfile(old_abs):
        die("source not found: {}".format(old_abs))
    if os.path.basename(old_abs).lower() in RESERVED:
        die("refusing to move a reserved file ({})".format(os.path.basename(old_abs)))
    if os.path.basename(new_abs).lower() in RESERVED:
        # A reserved name is not a concept, so nothing can resolve to it: every
        # inbound wikilink would be rewritten to an address that is dead on
        # arrival, and the report would still say it succeeded.
        die("refusing to rename onto a reserved name ({}) — no wikilink can "
            "resolve to it".format(os.path.basename(new_abs)))
    new_base_raw = os.path.basename(new_abs)[:-3]
    if not new_base_raw.strip():
        die("destination has an empty basename — `[[…]]` would become `[[]]`, "
            "which no scan can find again")
    if new_base_raw != new_base_raw.strip():
        # The scanner strips the page part, the index does not strip filenames,
        # so the two keys could never meet: the rewritten link would resolve to
        # nothing while the run reported success.
        die("destination basename has leading or trailing whitespace — the "
            "rewritten `[[{}]]` would resolve to nothing".format(new_base_raw))
    if any(ord(c) < 32 for c in new_base_raw):
        die("destination basename contains a control character — the rewritten "
            "link would be unmatchable by any later scan")
    if old_abs == new_abs:
        die("source and destination are identical")
    if os.path.commonpath([old_abs, root]) != root or os.path.commonpath([new_abs, root]) != root:
        die("both paths must live under the catalogue root")
    for p in (old_abs, new_abs):
        if os.path.relpath(p, root).count(os.sep) < 1:
            die("path must be inside a bundle (<bundle>/<concept>.md)")
    badchars = FILENAME_FORBIDDEN_CHARS & set(os.path.basename(new_abs)[:-3])
    if badchars:
        die("forbidden char(s) in new filename: {}".format("".join(sorted(badchars))))
    # samefile: on a case-insensitive filesystem a case-only rename has a
    # destination that "exists" because it IS the source. Refusing that would
    # make `Foo.md` -> `foo.md` impossible without --force overwriting itself.
    if (os.path.exists(new_abs) and apply and not force
            and not os.path.samefile(old_abs, new_abs)):
        die("destination exists (use --force to overwrite): {}".format(new_abs))

    # From here on the source is addressed exactly as the filesystem spells it,
    # so the two halves of the rename and the self-reference check all compare
    # the same string. The destination keeps the caller's spelling of its own
    # basename — that is the rename — but its directory part is canonicalised
    # for the same reason.
    old_abs = canonical_case_path(root, old_abs)
    new_abs = os.path.join(canonical_case_path(root, os.path.dirname(new_abs)),
                           os.path.basename(new_abs))

    if plan is None:
        plan = plan_rename(root, old_abs, new_abs)
    old_rel = os.path.relpath(old_abs, root).replace(os.sep, "/")
    new_rel = os.path.relpath(new_abs, root).replace(os.sep, "/")
    ctx_hits = ctx_memberships(root, old_rel)
    ctx_where = ["{} ({})".format(s, "reference" if e["pos"] is None
                                  else "pos {}".format(e["pos"])) for s, e in ctx_hits]

    wl_rewrite = [r for r in plan["wikilinks"] if r["status"] == "rewrite"]
    wl_skipped = [r for r in plan["wikilinks"] if r["status"] == "skipped-ambiguous"]
    collisions = plan["wikilink_collisions"]

    # Every occurrence the plan says loses its unique target, whether or not a
    # byte of it changes. Derived from resolving each one against the catalogue
    # before AND after the move, so the tie-break is honoured on both sides:
    # counting rewrites blindly refused renames that broke nothing, and looking
    # only at rewrites missed the ones that break without being rewritten.
    wl_ambiguous = [r for r in plan["wikilinks"] if r.get("turns_ambiguous")]

    def _print_skipped():
        for r in wl_skipped:
            print("  skipped-ambiguous  {} [{}]  {}  candidates: {}".format(
                r["source"], r["region"], r["raw"], ", ".join(r["candidates"])))
        for c in collisions:
            print("  wikilink-collision  new basename already taken by {}".format(c))
        for r in wl_ambiguous:
            print("  turns-ambiguous  {} [{}]  {}  candidates after the move: {}"
                  .format(r["source"], r["region"], r["raw"],
                          ", ".join(r["candidates"])))

    if apply and wl_ambiguous and not force:
        die("this move leaves {} inbound wikilink(s) ambiguous: {} — the same "
            "corruption `skipped-ambiguous` declines to commit, so it may not "
            "happen by accident either (use --force to proceed)"
            .format(len(wl_ambiguous),
                    ", ".join(sorted({r["source"] for r in wl_ambiguous}))))

    if not apply:
        print("would move   {}  ->  {}".format(old_rel, new_rel))
        for src, oraw, nraw in plan["inbound"]:
            print("  inbound    {}   {}  ->  {}".format(src, oraw, nraw))
        for oraw, nraw in plan["outbound"]:
            print("  outbound   {}  ->  {}".format(oraw, nraw))
        for r in wl_rewrite:
            print("  wikilink   {} [{}]   {}  ->  {}".format(
                r["source"], r["region"], r["raw"], r["new_raw"]))
        for consumer_rel, n in plan["sync_sources"]:
            print("  sync-source  {}   {} block(s)".format(consumer_rel, n))
        for w in ctx_where:
            print("  ctx        " + w)
        _print_skipped()
        print("  reindex    {}".format(", ".join(plan["bundles"])))
        print("rename (dry-run): {} inbound, {} outbound link(s), {} wikilink(s) "
              "({} skipped-ambiguous), {} bundle(s), {} sync source(s). "
              "Re-run with --apply.".format(
                  len(plan["inbound"]), len(plan["outbound"]), len(wl_rewrite),
                  len(wl_skipped), len(plan["bundles"]),
                  len(plan["sync_sources"])))
        return

    if os.path.exists(new_abs) and not os.path.samefile(old_abs, new_abs):
        # --force got us here. Say what it costs: the destination's content is
        # gone and every reference to it now addresses different content.
        clobbered = linkscan.build_ref_matrix(root, new_abs)
        print("overwrote      {}  ({} inbound markdown reference(s) now point at "
              "different content)".format(new_rel, len(clobbered)))
    os.makedirs(os.path.dirname(new_abs), exist_ok=True)
    moved, git_repo, git_reason = _git_mv(root, old_abs, new_abs)
    if plan["outbound"]:
        _apply_link_rewrites(new_abs, plan["outbound"])
    by_src = {}
    for src, oraw, nraw in plan["inbound"]:
        by_src.setdefault(src, []).append((oraw, nraw))
    for src, rw in by_src.items():
        _apply_link_rewrites(os.path.join(root, src), _dedupe(rw))
    wl_by_src = {}
    for r in wl_rewrite:
        # A self-reference lives in the file that just moved — rewrite it at its
        # new location, not at the path it no longer occupies.
        ap = new_abs if r["source"] == old_rel else os.path.join(root, r["source"])
        wl_by_src.setdefault(ap, {})[r["raw"]] = r["new_raw"]
    for ap, rename_map in wl_by_src.items():
        _apply_wikilink_rewrites(ap, rename_map)
    # The `source=` attribute of a materialised canon block is not a link, so
    # neither link rewriter touches it — without this the move silently breaks
    # every consumer of the moved concept's canon blocks into `source-missing`.
    old_source = "/" + old_rel
    new_source = "/" + new_rel
    n_sync = 0
    for consumer_rel, _ in plan["sync_sources"]:
        # A self-reference lives in the file that just moved — same rule as the
        # wikilink pass above.
        ap = new_abs if consumer_rel == old_rel else os.path.join(root, consumer_rel)
        n_sync += _apply_sync_source_rewrites(ap, old_source, new_source)
    ctx_notes = []
    for slug in dict.fromkeys(s for s, _ in ctx_hits):
        c = load_ctx(root, slug)
        if c["problems"]:
            ctx_notes.append("  ctx        {}: not refreshed, {} parse problem(s) — "
                             "run okf ctx check".format(slug, len(c["problems"])))
        else:
            save_ctx(root, c)
    reidx = []
    for b in plan["bundles"]:
        reidx += reindex_tree(root, os.path.join(root, b))
    print("moved ({})  {}  ->  {}".format("git mv" if moved else "fs", old_rel, new_rel))
    if moved:
        if git_repo:
            print("  tracked in {} (repository differs from --root)".format(git_repo))
    else:
        # AC3 (okf-cli-mk7m, widened by the PO review 2026-08-10): never say
        # this looks tracked, whichever of the two causes git declined for —
        # a symlinked-bundle boundary or a plain untracked file. Always name
        # git's own reason (point 4 of the gate: proc.stderr read, not
        # dropped) and, only when a different repository actually received
        # part of the write, name it (AC2).
        print("  untracked — git declined: {}".format(
            git_reason if git_reason else "git binary unavailable"))
        if git_repo:
            print("  the untracked change also touches {} (repository "
                  "differs from --root)".format(git_repo))
    print("rewrote {} inbound link(s) in {} file(s), {} outbound link(s)".format(
        len(plan["inbound"]), len(by_src), len(plan["outbound"])))
    print("rewrote {} wikilink(s) in {} file(s)".format(len(wl_rewrite), len(wl_by_src)))
    print("rewrote {} sync source(s) in {} file(s)".format(
        n_sync, len(plan["sync_sources"])))
    if ctx_where:
        print("listed in {} ctx bundle(s): {}".format(len(ctx_where), ", ".join(ctx_where)))
        for note in ctx_notes:
            print(note)
    _print_skipped()
    print("reindexed {} index file(s) across: {}".format(len(reidx), ", ".join(plan["bundles"])))
    print("staged for commit — run `okf-cli.py check` before committing.")


def cmd_rename(root, args):
    old_abs = os.path.abspath(args.old if os.path.isabs(args.old) else os.path.join(root, args.old))
    new_abs = os.path.abspath(args.new if os.path.isabs(args.new) else os.path.join(root, args.new))

    # D02 (okf-cli-tk33, PO decision on Q02): a rename whose source lies
    # under _archive/ reproduces, through this command, the invisible
    # empty-directory residue okf-cli-gqss closed for `archive --restore`.
    # Guarded HERE, not in perform_rename: that function is also
    # `archive --restore`'s own path back OUT of _archive/ (AC5) — a shared
    # guard would refuse the operation this message points users at
    # (SPEC.md §2 placement rule, same as the direction guards in
    # cmd_archive). Runs unconditionally, before the apply/dry-run branch,
    # so a preview never promises a move --apply would then decline (AC2).
    #
    # "Resolved source" (AC1): os.path.realpath, the same idiom
    # _prune_empty_archive_dirs (:4286-4288) and _git_mv (:4084-4087) already
    # use for a root/_archive boundary check. os.path.abspath alone already
    # collapses a `..`-traversal argument lexically, but only realpath also
    # follows a symlink whose target lands inside _archive/ even though
    # neither the argument nor old_abs ever spells "_archive/" — a prefix
    # match on the raw argument string would miss both.
    archive_root = os.path.realpath(os.path.join(root, "_archive"))
    resolved_old = os.path.realpath(old_abs)
    if resolved_old == archive_root or resolved_old.startswith(archive_root + os.sep):
        old_rel = os.path.relpath(old_abs, root).replace(os.sep, "/")
        sys.stderr.write(
            "rename: source lies under _archive/ — use archive --restore to "
            "bring it back: {}\n".format(old_rel))
        sys.exit(2)

    perform_rename(root, old_abs, new_abs, args.apply, args.force)


def _prune_empty_archive_dirs(root, freed_dir):
    """okf-cli-gqss (AC1/AC2): after a restore vacates `freed_dir` — the
    directory that held the concept before the move — remove every directory
    from there up to and including `_archive/` that the move has left empty.
    Stops at the first directory that still holds something (AC3, including a
    sibling concept's now-empty subdirectory of its own) and never touches
    anything outside `_archive/`.

    Git does not track empty directories, so a leftover here is invisible to
    `git status` — the defect this bean exists to close. This is why the walk
    is a plain `os.listdir`/`os.rmdir` filesystem operation, not a git one:
    there is nothing for git to be told, the directory was never tracked in
    the first place."""
    archive_root = os.path.realpath(os.path.join(root, "_archive"))
    d = os.path.realpath(freed_dir)
    while d == archive_root or d.startswith(archive_root + os.sep):
        try:
            if os.listdir(d):
                break
            os.rmdir(d)
        except OSError:
            break
        if d == archive_root:
            break
        d = os.path.dirname(d)


def cmd_archive(root, args):
    """R-01..R-03 (okf-cli-16rg): `archive <bundle>/<concept>[.md]` moves a
    concept to `_archive/<bundle>/<concept>.md`, preserving any subdirectory
    substructure of the concept id; `archive --restore
    _archive/<bundle>/<concept>[.md]` moves it back. The destination is
    derived, never typed (SPEC.md §1) — the three direction guards below are
    archive's own and run before perform_rename's shared guards, because they
    are not part of that shared core (SPEC.md §2)."""
    verb = "archive"

    def die(msg):
        sys.stderr.write("{}: {}\n".format(verb, msg))
        sys.exit(2)

    ref = args.path[:-3] if args.path.endswith(".md") else args.path
    p = ref + ".md"
    src_abs = os.path.abspath(p if os.path.isabs(p) else os.path.join(root, p))
    src_rel = os.path.relpath(src_abs, root).replace(os.sep, "/")
    segs = src_rel.split("/")

    if args.restore:
        if segs[0] != "_archive":
            die("--restore source must lie under _archive/, not: {}".format(src_rel))
        if len(segs) < 3:
            die("archive path carries no bundle segment — destination is not "
                "derivable from: {}".format(src_rel))
        dest_rel = "/".join(segs[1:])
    else:
        if segs[0] == "_archive":
            die("source already lies under _archive/ — use --restore to bring "
                "it back: {}".format(src_rel))
        dest_rel = "/".join(["_archive"] + segs)

    dest_abs = os.path.join(root, dest_rel)

    # okf-cli-5436 (AC1/AC2/AC4): a missing source whose derived counterpart
    # exists is not a bare miss — the tool already holds `dest_rel` at this
    # point, so a reader following a stale reference gets pointed at where
    # the concept actually is, instead of just being told it is gone. This
    # is archive-specific knowledge, not perform_rename's: it lives here,
    # same reasoning as the three direction guards above (SPEC.md §2).
    if not os.path.isfile(src_abs) and os.path.isfile(dest_abs):
        if args.restore:
            die("source not found: {} — the active copy already exists at "
                "{}".format(src_abs, dest_rel))
        die("source not found: {} — already archived at {} (use --restore "
            "to bring it back)".format(src_abs, dest_rel))

    # The inbound-reference count is a report line, not a guard: it must not
    # gate the move, only disclose what the move leaves behind (SPEC.md §1).
    # A nonexistent source with no archived counterpart is left to
    # perform_rename's own "source not found", so a plan is only built once
    # there is a file to plan a move for.
    plan = None
    if os.path.isfile(src_abs):
        plan = plan_rename(root, src_abs, dest_abs)
        n_concepts = len({src for src, _o, _n in plan["inbound"]})
        print("{} active concept(s) still link to this concept".format(n_concepts))

    perform_rename(root, src_abs, dest_abs, args.apply, args.force, verb=verb,
                   plan=plan)

    # okf-cli-gqss (AC1/AC2): only a restore can empty an _archive/ directory
    # — `archive` in the other direction only ever adds to one. perform_rename
    # already exited on failure above, so reaching here means the move
    # happened; freed_dir is the directory the concept just vacated.
    if args.restore and args.apply:
        _prune_empty_archive_dirs(root, os.path.dirname(src_abs))


def _ctx_list_rows(root, for_path):
    keep = None
    if for_path is not None:
        keep = {s for s, _e in ctx_memberships(root, for_path)}
    rows = []
    for slug in ctx_slugs(root):
        if keep is not None and slug not in keep:
            continue
        c = load_ctx(root, slug)
        rows.append({"slug": slug, "description": c["description"],
                     "entries": len(c["entries"]),
                     "required": sum(1 for e in c["entries"] if e["mode"] == "pflicht"),
                     "path": "{}/{}.md".format(CTX_DIR, slug)})
    return rows


def cmd_ctx_list(root, args):
    rows = _ctx_list_rows(root, args.for_path)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    if not rows:
        if args.for_path is None:
            print("no ctx bundles under {}".format(ctx_dir(root)))
        return
    w = max(len(r["slug"]) for r in rows)
    for r in rows:
        print("  {:<{w}}  {}  ({} entries, {} required)".format(
            r["slug"], r["description"], r["entries"], r["required"], w=w))


def cmd_ctx_create(root, args):
    problem = ctx_slug_problem(args.slug)
    if problem:
        _ctx_die('invalid slug "{}": {}'.format(args.slug, problem))
    if os.path.exists(ctx_file(root, args.slug)):
        _ctx_die("{} already exists".format(args.slug))
    raw = [(p, "") for p in args.paths]
    if args.import_file:
        if not os.path.isfile(args.import_file):
            _ctx_die("import file not found: {}".format(args.import_file))
        for line in read_file(args.import_file).splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            p, _t, comment = line.partition("\t")
            raw.append((p, comment.strip()))
    if not raw:
        _ctx_die("create needs at least one path")
    seen, entries, missing = set(), [], []
    for p, comment in raw:
        norm = ctx_normalize_path(root, p)
        if norm is None:
            missing.append(p)
        elif norm not in seen:
            seen.add(norm)
            entries.append({"mode": "pflicht", "path": norm, "comment": comment})
    if missing:
        for p in missing:
            print("ctx: not found: {}".format(p), file=sys.stderr)
        sys.exit(2)
    entries.sort(key=lambda e: e["path"].casefold())
    save_ctx(root, {"slug": args.slug, "description": args.description or "",
                    "entries": entries})
    print("created {}/{}.md ({} entries)".format(CTX_DIR, args.slug, len(entries)))


def _ctx_members(root, slug):
    """Entries of a ctx with live metadata; required first in pos order."""
    c = load_ctx(root, slug)
    out = []
    for e in c["entries"]:
        ap = ctx_entry_abspath(root, e["path"])
        alive = os.path.isfile(ap)
        typ, title, desc, chars = "", os.path.basename(ap), "", 0
        if alive:
            if ap.endswith(".md"):
                typ, title, desc = meta_of(ap)
            chars = len(read_file(ap))
        out.append({"pos": e["pos"], "mode": e["mode"],
                    "path": e["path"], "abspath": ap, "title": title, "type": typ,
                    "description": desc, "comment": e["comment"], "alive": alive,
                    "chars": chars,
                    # ponytail: chars/4 heuristic; use a tokenizer if budgets get tight
                    "tokens": (chars + 3) // 4})
    req = sorted((m for m in out if m["mode"] == "pflicht"), key=lambda m: m["pos"])
    return c, req + [m for m in out if m["mode"] != "pflicht"]


def _ctx_dead_warning(slug, k):
    return ("WARNING: {} dead entr{} — this list is incomplete; fix with `ctx edit {}`"
            .format(k, "y" if k == 1 else "ies", slug))


def cmd_ctx_show(root, args):
    c, ms = _ctx_members(root, args.slug)
    req = [m for m in ms if m["mode"] == "pflicht"]
    ref = [m for m in ms if m["mode"] != "pflicht"]
    dead = sum(1 for m in ms if not m["alive"])
    t_req = sum(m["tokens"] for m in req)
    if args.json:
        print(json.dumps({"slug": args.slug, "description": c["description"],
                          "path": "{}/{}.md".format(CTX_DIR, args.slug), "entries": ms,
                          "dead": dead, "tokens_required": t_req},
                         ensure_ascii=False, indent=2))
        if dead:
            print(_ctx_dead_warning(args.slug, dead), file=sys.stderr)
            sys.exit(1)
        return

    def block(m, head):
        if not m["alive"]:
            lines = ["{}[DEAD] {}".format(head, m["abspath"])]
        else:
            lines = ["{}{}{}  ~{} tok".format(
                head, m["abspath"], "  [{}] {}".format(m["type"], m["title"]) if m["type"]
                else "  " + m["title"], m["tokens"])]
            if m["description"] and m["mode"] == "pflicht":
                lines.append("     " + m["description"])
        if m["comment"]:
            lines.append("     why: " + m["comment"])
        return lines

    out = ["ctx {}{}".format(args.slug, " — " + c["description"] if c["description"] else ""),
           "", "required — read in this order:"]
    for m in req:
        out += block(m, "  {}. ".format(m["pos"]))
    if not req:
        out.append("  (none)")
    if ref:
        out.append("reference — query when needed:")
        for m in ref:
            out += block(m, "  - ")
    out += ["", "{} entries ({} required, {} reference), ~{} tokens for the required set".format(
        len(ms), len(req), len(ref), t_req)]
    if dead:
        out.append(_ctx_dead_warning(args.slug, dead))
    print("\n".join(out))
    if dead:
        sys.exit(1)


def cmd_ctx_read(root, args):
    _c, ms = _ctx_members(root, args.slug)
    req = [m for m in ms if m["mode"] == "pflicht"]
    r = len(ms) - len(req)
    dead = False
    for i, m in enumerate(req, 1):
        if not m["alive"]:
            dead = True
            print("===== {}/{} [DEAD] {} =====".format(i, len(req), m["abspath"]))
            continue
        print("===== {}/{} {} =====".format(i, len(req), m["abspath"]))
        text = read_file(m["abspath"])
        print(text, end="" if text.endswith("\n") else "\n")
    if r:
        print("===== {} reference entr{} not printed — ctx show {} =====".format(
            r, "y" if r == 1 else "ies", args.slug))
    if dead:
        sys.exit(1)


def cmd_ctx_toc(root, args):
    blocks = []
    for m in _ctx_members(root, args.slug)[1]:
        lines = ["# {}{}".format(m["path"], "" if m["alive"] else " [DEAD]")]
        if m["alive"]:
            hs = []
            if m["path"].endswith(".md"):
                body = split_frontmatter(read_file(m["abspath"]))[1]
                hs = ["{} {}".format("#" * min(lv + 1, 6), t) for lv, t in iter_headings(body)
                      if not args.depth or lv <= args.depth]
            lines += hs or ["(no headings)"]
        blocks.append("\n".join(lines))
    print("\n\n".join(blocks))


def _ctx_same_file(a, b):
    """build_ref_matrix rule: exact abspath, or case-insensitive equal and the same existing file."""
    return a == b or (a.lower() == b.lower() and os.path.exists(a) and os.path.samefile(a, b))


def _ctx_nav(root, args, direction):
    """Shared body of ctx inbound/outbound."""
    _c, ms = _ctx_members(root, args.slug)
    for m in ms:
        m["abs"] = os.path.abspath(m["abspath"])
    shown = ms
    if args.file:
        x = args.file.lower()
        shown = [m for m in ms if x in (m["title"].lower(), m["path"].lower(),
                                        os.path.splitext(os.path.basename(m["path"]))[0].lower())]
        if not shown:
            _ctx_die('no entry in {} matches --file "{}"'.format(args.slug, args.file))
        if len(shown) > 1:
            _ctx_die('--file "{}" matches several entries: {}'.format(
                args.file, ", ".join(m["path"] for m in shown)))
    by_lower = {}
    for m in ms:
        by_lower.setdefault(m["abs"].lower(), []).append(m)

    def owners(ap):
        return [m for m in by_lower.get(ap.lower(), []) if _ctx_same_file(ap, m["abs"])]

    links = {id(m): [] for m in ms}
    inbound = direction == "inbound"
    if inbound:
        # ponytail: one catalogue scan per call; links bucketed by member afterwards
        for rel, raw, resolved in iter_md_links(root):
            if rel.startswith(CTX_DIR + "/"):
                continue
            for m in owners(resolved):
                if args.include_internal or not owners(os.path.abspath(os.path.join(root, rel))):
                    links[id(m)].append({"source": rel, "link": raw})
    else:
        for m in shown:
            if m["alive"] and m["path"].endswith(".md"):
                for raw, target, exists in linkscan.outbound_links(root, m["abs"]):
                    if args.include_internal or not owners(target):
                        links[id(m)].append({"target": _refs_display(root, target),
                                             "link": raw, "exists": exists})
    if args.json:
        rows = []
        for m in shown:
            row = {"path": m["path"]}
            if not inbound:
                row["dead"] = not m["alive"]
            row["links"] = links[id(m)]
            rows.append(row)
        print(json.dumps({"slug": args.slug, "direction": direction,
                          "include_internal": args.include_internal, "members": rows},
                         ensure_ascii=False, indent=2))
        return
    out = ["{} \u2014 ctx {}, {} member(s), {}:".format(
        direction, args.slug, len(shown),
        "including internal links" if args.include_internal
        else "external {} only".format("sources" if inbound else "targets"))]
    for m in shown:
        if not inbound and not m["alive"]:
            out.append(m["path"] + " [DEAD]")
            continue
        out.append(m["path"])
        for l in links[id(m)]:
            out.append("  <- {}  ({})".format(l["source"], l["link"]) if inbound else
                       "  -> {}  ({}){}".format(l["target"], l["link"],
                                               "" if l["exists"] else "  [missing]"))
        if not links[id(m)]:
            out.append("  (none)")
    print("\n".join(out))


def cmd_ctx_inbound(root, args):
    _ctx_nav(root, args, "inbound")


def cmd_ctx_outbound(root, args):
    _ctx_nav(root, args, "outbound")


def _ctx_editable(root, slug):
    """Load a ctx for a row edit: refuse when rows are unparsable (a save would drop them).
    Returns (ctx, required entries in pos order, other entries)."""
    c = load_ctx(root, slug)
    if c["problems"]:
        _ctx_die("{} has {} parse problem(s) — fix with okf ctx edit, see okf ctx check"
                 .format(slug, len(c["problems"])))
    es = c["entries"]
    pf = sorted((e for e in es if e["mode"] == "pflicht"), key=lambda e: e["pos"])
    return c, pf, [e for e in es if e["mode"] != "pflicht"]


def _ctx_where(pf, e):
    return "pos {}".format(pf.index(e) + 1) if e in pf else "reference"


def _ctx_find(root, c, raw):
    norm = ctx_normalize_path(root, raw, must_exist=False)
    return norm, next((e for e in c["entries"] if e["path"] == norm), None)


def _ctx_put(root, c, pf, rest, e, mode, pos):
    """Place e (not in pf/rest) as mode/pos, save, return its `where`."""
    e["mode"] = mode
    if mode == "pflicht":
        pf.insert((len(pf) if pos is None else max(1, min(pos, len(pf) + 1)) - 1), e)
    else:
        rest.append(e)
    c["entries"] = pf + rest
    save_ctx(root, c)
    return _ctx_where(pf, e)


def cmd_ctx_add(root, args):
    c, pf, rest = _ctx_editable(root, args.slug)
    if args.pos is not None and args.mode != "pflicht":
        _ctx_die("--pos applies only to mode pflicht")
    norm = ctx_normalize_path(root, args.path)
    if norm is None:
        _ctx_die("not found: {}".format(args.path))
    old = next((e for e in c["entries"] if e["path"] == norm), None)
    if old:
        _ctx_die("{} is already in {} ({})".format(norm, args.slug, _ctx_where(pf, old)))
    where = _ctx_put(root, c, pf, rest, {"pos": None, "path": norm, "comment": args.comment},
                     args.mode, args.pos)
    print("added {} to {} ({})".format(norm, args.slug, where))


def cmd_ctx_drop(root, args):
    c, pf, rest = _ctx_editable(root, args.slug)
    norm, e = _ctx_find(root, c, args.path)
    if e is None:
        _ctx_die("{} is not in {}".format(norm, args.slug))
    c["entries"] = [x for x in pf + rest if x is not e]
    save_ctx(root, c)
    print("dropped {} from {}".format(norm, args.slug))


def cmd_ctx_move(root, args):
    c, pf, rest = _ctx_editable(root, args.slug)
    if args.pos is None and args.mode is None:
        _ctx_die("move needs --pos or --mode")
    norm, e = _ctx_find(root, c, args.path)
    if e is None:
        _ctx_die("{} is not in {}".format(norm, args.slug))
    mode = args.mode or e["mode"]
    if args.pos is not None and mode != "pflicht":
        _ctx_die("--pos applies only to mode pflicht")
    pf = [x for x in pf if x is not e]
    rest = [x for x in rest if x is not e]
    where = _ctx_put(root, c, pf, rest, e, mode, args.pos)
    print("moved {} in {} to {}".format(norm, args.slug, where))


def _ctx_report(root, slugs, stale, as_json):
    errors, warnings = [], []
    for s in slugs:
        es, ws = ctx_findings(root, ctx_file(root, s), stale)
        rel = "{}/{}.md".format(CTX_DIR, s)
        errors += [("ctx", rel, m) for m in es]
        warnings += [("ctx", rel, m) for m in ws]
    _print_findings(errors, warnings, as_json)
    sys.exit(1 if errors else 0)


def cmd_ctx_check(root, args):
    if args.slug:
        load_ctx(root, args.slug)
    _ctx_report(root, [args.slug] if args.slug else ctx_slugs(root), args.stale, args.json)


def cmd_ctx_edit(root, args):
    load_ctx(root, args.slug)
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi"
    rc = subprocess.call(shlex.split(editor) + [ctx_file(root, args.slug)])
    if rc:
        _ctx_die("editor exited {}".format(rc))
    reindex_tree(root, ctx_dir(root))
    _ctx_report(root, [args.slug], False, False)


def cmd_ctx_rename(root, args):
    c = load_ctx(root, args.old)
    problem = ctx_slug_problem(args.new)
    if problem:
        _ctx_die('invalid slug "{}": {}'.format(args.new, problem))
    if os.path.exists(ctx_file(root, args.new)):
        _ctx_die("{} already exists".format(args.new))
    perform_rename(root, ctx_file(root, args.old), ctx_file(root, args.new), True, False)
    if not c["problems"]:
        save_ctx(root, load_ctx(root, args.new))  # refreshes the H1 (D-pzho-16)


def cmd_ctx_remove(root, args):
    c = load_ctx(root, args.slug)
    f = ctx_file(root, args.slug)
    # one build_ref_matrix row per link: dedup by source file, first-seen order
    srcs = list(dict.fromkeys(s for s, _ in linkscan.build_ref_matrix(root, f)
                              if s.replace(os.sep, "/") != CTX_DIR + "/index.md"))
    os.remove(f)
    reindex_tree(root, ctx_dir(root))
    print("removed {}/{}.md ({} entries)".format(CTX_DIR, args.slug, len(c["entries"])))
    if srcs:
        print("warning: {} file(s) still link to {}/{}.md:".format(len(srcs), CTX_DIR, args.slug))
        for s in srcs:
            print("  " + s)


CTX_DISPATCH = {"add": cmd_ctx_add, "check": cmd_ctx_check, "create": cmd_ctx_create,
                "drop": cmd_ctx_drop, "edit": cmd_ctx_edit,
                "inbound": cmd_ctx_inbound, "list": cmd_ctx_list, "move": cmd_ctx_move,
                "outbound": cmd_ctx_outbound, "read": cmd_ctx_read,
                "remove": cmd_ctx_remove, "rename": cmd_ctx_rename, "show": cmd_ctx_show,
                "toc": cmd_ctx_toc}


def cmd_ctx(root, args):
    CTX_DISPATCH[args.ctx_verb](root, args)


def _ctx_shorthand(argv):
    """`ctx` -> `ctx list`, `ctx --list` -> `ctx list`, `ctx <slug>` -> `ctx show <slug>`.
    Acts only when the first command token (after global options) is `ctx`."""
    i = 0
    while i < len(argv) and argv[i].startswith("-"):
        i += 2 if argv[i] == "--root" else 1
    if i >= len(argv) or argv[i] != "ctx":
        return argv
    rest = argv[i + 1:]
    if not rest:
        rest = ["list"]
    elif rest[0] == "--list":
        rest = ["list"] + rest[1:]
    elif rest[0] not in CTX_VERBS and not rest[0].startswith("-"):
        rest = ["show"] + rest
    return argv[:i + 1] + rest


def _complete_ctx_slugs(parsed_args, **_):
    root = _completion_root(parsed_args)
    if root is None:
        return {}
    return {s: load_ctx(root, s)["description"] for s in ctx_slugs(root)}


def cmd_install(_root, args):
    """`install` never touches a catalogue (main() hands it no root). Its code
    lives in okf_install.py next to this file, loaded only when it runs. The
    path is resolved first: a symlink to okf-cli.py is how people put it on PATH."""
    path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "okf_install.py")
    if not os.path.isfile(path):  # okf-cli.py copied out of its clone on its own
        sys.exit("ERROR: install needs okf_install.py next to okf-cli.py ({}); run it from a full clone "
                 "or use pipx / uv tool install".format(os.path.dirname(path)))
    spec = importlib.util.spec_from_file_location("okf_install", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    code = mod.run(args)
    if code:
        sys.exit(code)


# commands main() runs without resolving a catalogue root
CATALOGUE_FREE = frozenset({"install"})


def command_overview(width=96):
    """The command directory as prime needs it: built from a fresh parser, so
    a newly registered subcommand reaches the onboarding text without anyone
    editing the onboarding text."""
    return render_command_overview(subcommand_parsers(build_parser()),
                                   footer=False, width=width)


_FIND_EPILOG = """\
rank / score lines:
  Every hit's headline number is `rank: N` — its 1-based position in the
  delivered list. It is the one scale comparable across a mixed-arm result,
  because it IS the list order, and it claims nothing about the two arms'
  raw scores being on one scale (D12: fuse_conditional hands the ranking to
  whichever arm owns it, it never blends the two by score). Those raw,
  non-comparable values stay out of the default output and show only with
  --breakdown, one `score:` line per hit naming which arm produced it:
    a/100        the FTS5/BM25 lexical arm, relative to this run's own top
                 hit.
    a/(6 * n)    the substring fallback used when no FTS index is available:
                 per query term 3 for a title hit, 2 for a tag hit, 1 for a
                 body hit, capped at one per field per term — so the maximum
                 is 6 * number of terms.
    cosine X.XX  the semantic arm's raw cosine similarity — printed on its
                 own line, not folded into an a/100 fraction, because that
                 shape would invite comparing it against a lexical score
                 (D12, same rule as above).
  `provenance:` names the arm that produced the line. Degradations (index
  absent or stale, embedding backend unavailable) are announced on stderr,
  one note per degraded arm.
"""


def _complete_block_ids(parsed_args, **_):
    """Canon block ids declared in the concept already on the line. An unknown
    concept makes resolve_concept exit, which ends the completion run with no
    candidates: the right answer."""
    root = _completion_root(parsed_args)
    concept = getattr(parsed_args, "concept", None)
    if root is None or not concept:
        return []
    _fm, body = split_frontmatter(read_file(resolve_concept(root, concept)))
    return [blk["id"] for blk in parse_canon_blocks(body)]


def _complete_canon_sources(parsed_args, **_):
    root = _completion_root(parsed_args)
    if root is None:
        return []
    return sorted({"/" + rel for rel, _bid in build_canon_block_index(root)})


def _complete_canon_block_ids(parsed_args, **_):
    """Every declared canon block id, narrowed to --source when given."""
    root = _completion_root(parsed_args)
    if root is None:
        return []
    source = getattr(parsed_args, "source", None)
    return sorted({bid for rel, bid in build_canon_block_index(root)
                   if not source or rel == source.lstrip("/")})


def add_archive_parser(sub):
    pah = _sub(sub, "archive", "maintenance",
               "move a concept into _archive/<bundle>/, or back with --restore (dry-run default)")
    pah.add_argument("path", help="<bundle>/<concept>[.md]; with --restore: "
                                   "_archive/<bundle>/<concept>[.md]. The other end is derived, "
                                   "never typed").completer = _complete_concepts
    pah.add_argument("--restore", action="store_true",
                     help="move the path back out of _archive/ instead of into it")
    pah.add_argument("--apply", action="store_true", help="perform the move (default: dry-run preview only)")
    pah.add_argument("--force", action="store_true",
                     help="overwrite an existing destination, and proceed when the new "
                          "basename is already taken and inbound wikilinks would turn ambiguous")


def add_build_index_parser(sub):
    pbi = _sub(sub, "build-index", "search",
               "(re)build the FTS5 lexical search index at "
               "<root>/.fts/fts.sqlite (local only, no network)")
    pbi.add_argument("--include-topics", action="store_true", help="widen beyond .okf.toml declared bundle to topic folders")
    pbi.add_argument("--if-stale", action="store_true",
                      help="skip the rebuild when the existing index is "
                           "already current (default: always rebuild)")


def add_build_semantic_index_parser(sub):
    pbs = _sub(sub, "build-semantic-index", "search",
               "fill <root>/.tagvec/tag_vectors.sqlite's concept_emb table "
               "for every concept still missing a voyage-3-large embedding "
               "(NETWORK, requires VOYAGE_API_KEY)")
    pbs.add_argument("--if-stale", action="store_true",
                      help="skip the run when semantic_coverage() already "
                           "reports every on-disk concept embedded "
                           "(default: always fill the delta)")


def add_check_parser(sub):
    pc = _sub(sub, "check", "maintenance",
              "conformance scan: §9 hard rules + local invariants")
    pc.add_argument("target", nargs="?", help="<bundle> or <bundle>/<subdir> (default: whole catalogue)").completer = _complete_scopes
    pc.add_argument("--strict", action="store_true", help="promote warnings to errors")
    pc.add_argument("--json", action="store_true", help="machine-readable output")
    pc.add_argument("--types", help="explicit TYPES.md path (overrides .okf.toml types_source)").completer = _complete_files


def add_ctx_parser(sub):
    pcx = _sub(sub, "ctx", "navigation",
               "context bundles: curated, ordered reading lists per topic "
               "(`ctx` lists them, `ctx <slug>` shows one)")
    ctx_verbs = pcx.add_subparsers(dest="ctx_verb", required=True, metavar="VERB",
                                   help="ctx verb; `ctx <slug>` is short for `ctx show <slug>`")
    pcxa = ctx_verbs.add_parser(
        "add", help="add one entry to a ctx bundle",
        description="add PATH as required entry (default: last position) or as reference entry")
    pcxa.add_argument("slug", help="ctx slug").completer = _complete_ctx_slugs
    pcxa.add_argument("path", metavar="PATH", help="concept or file path").completer = _complete_concepts
    pcxa.add_argument("--pos", type=int, help="required position (clamped to 1..n+1)")
    pcxa.add_argument("--mode", choices=CTX_MODES, default="pflicht", help="entry mode")
    pcxa.add_argument("--comment", default="", help="entry comment")
    pcxk = ctx_verbs.add_parser(
        "check", help="validate ctx bundles",
        description="report ctx errors and warnings in the `check` line format; exit 1 on any error")
    pcxk.add_argument("slug", nargs="?", help="ctx slug (default: all)").completer = _complete_ctx_slugs
    pcxk.add_argument("--stale", action="store_true",
                      help="warn for every member modified after the ctx file")
    pcxk.add_argument("--json", action="store_true", help="machine-readable output")
    pcxc = ctx_verbs.add_parser(
        "create", help="create a ctx bundle from paths and/or an import file",
        description="create _ctx/<slug>.md; every path becomes a required entry, "
                    "ordered alphabetically by normalised path")
    pcxc.add_argument("slug", help="new ctx slug: lowercase letters, digits, hyphens"
                      ).completer = _complete_ctx_slugs
    pcxc.add_argument("paths", nargs="*", metavar="PATH",
                      help="concept or file path to add as required entry"
                      ).completer = _complete_concepts
    pcxc.add_argument("--import", dest="import_file", metavar="FILE",
                      help="read one path per line (blank and # lines skipped, "
                           "text after a TAB is the entry comment)").completer = _complete_files
    pcxc.add_argument("--description", help="one-line description of the bundle")
    pcxd = ctx_verbs.add_parser(
        "drop", help="remove one entry from a ctx bundle",
        description="remove an entry (also when its file is gone); required positions are "
                    "renumbered 1..n")
    pcxd.add_argument("slug", help="ctx slug").completer = _complete_ctx_slugs
    pcxd.add_argument("path", metavar="PATH", help="entry path").completer = _complete_files
    pcxe = ctx_verbs.add_parser(
        "edit", help="open a ctx bundle in $VISUAL/$EDITOR/vi and validate it",
        description="open _ctx/<slug>.md in $VISUAL, else $EDITOR, else vi; afterwards refresh "
                    "the _ctx index and run `ctx check` on the file; exit 1 on errors")
    pcxe.add_argument("slug", help="ctx slug").completer = _complete_ctx_slugs
    pcxl = ctx_verbs.add_parser(
        "list", help="list ctx bundles with entry and required counts",
        description="list ctx bundles: slug, description, entry and required counts")
    pcxl.add_argument("--for", dest="for_path", metavar="PATH",
                      help="only bundles whose entries contain PATH (also when the file is gone)"
                      ).completer = _complete_files
    pcxl.add_argument("--json", action="store_true", help="machine-readable output")
    pcxm = ctx_verbs.add_parser(
        "move", help="reorder an entry or change its mode",
        description="move an entry to required position N (--pos) and/or change its mode; "
                    "required positions are renumbered 1..n")
    pcxm.add_argument("slug", help="ctx slug").completer = _complete_ctx_slugs
    pcxm.add_argument("path", metavar="PATH", help="entry path").completer = _complete_files
    pcxm.add_argument("--pos", type=int, help="required position (clamped to 1..n)")
    pcxm.add_argument("--mode", choices=CTX_MODES, help="new mode")
    pcxo = ctx_verbs.add_parser(
        "outbound", help="list the links each entry points to",
        description="per entry, markdown link targets; missing targets are marked [missing], "
                    "dead entries [DEAD]; other members are excluded unless --include-internal")
    pcxi = ctx_verbs.add_parser(
        "inbound", help="list the files that link to each entry",
        description="per entry, the files linking to it; other members are excluded unless "
                    "--include-internal; files under _ctx/ are always excluded")
    for pn in (pcxi, pcxo):
        pn.add_argument("slug", help="ctx slug").completer = _complete_ctx_slugs
        pn.add_argument("--file", metavar="X",
                        help="only the entry whose title, path or stem equals X (case-insensitive)")
        pn.add_argument("--include-internal", action="store_true",
                        help="also list links between members of the ctx")
        pn.add_argument("--json", action="store_true", help="machine-readable output")
    pcxr = ctx_verbs.add_parser(
        "read", help="print the full content of every required entry",
        description="print every required entry of a ctx in position order, each after a "
                    "`===== i/p <abspath> =====` separator; reference entries are not printed; "
                    "exit 1 when a required entry is dead")
    pcxr.add_argument("slug", help="ctx slug").completer = _complete_ctx_slugs
    pcxrm = ctx_verbs.add_parser(
        "remove", help="delete a ctx bundle and list files that still link to it",
        description="delete _ctx/<slug>.md, refresh the _ctx index and list every file "
                    "that still links to the removed ctx")
    pcxrm.add_argument("slug", help="ctx slug").completer = _complete_ctx_slugs
    pcxrn = ctx_verbs.add_parser(
        "rename", help="rename a ctx bundle and rewrite inbound links",
        description="move _ctx/<old>.md to _ctx/<new>.md; inbound links and the _ctx index follow")
    pcxrn.add_argument("old", help="current ctx slug").completer = _complete_ctx_slugs
    pcxrn.add_argument("new", help="new ctx slug: lowercase letters, digits, hyphens")
    pcxs = ctx_verbs.add_parser(
        "show", help="list a ctx in reading order with live metadata and token estimates",
        description="list the required entries in reading order, then the reference entries; "
                    "`ctx <slug>` is short for `ctx show <slug>`; exit 1 when an entry is dead")
    pcxs.add_argument("slug", help="ctx slug").completer = _complete_ctx_slugs
    pcxs.add_argument("--json", action="store_true",
                      help="machine-readable output (stdout carries only the JSON object)")
    pcxt = ctx_verbs.add_parser(
        "toc", help="print the headings of every entry",
        description="print per entry an H1 with the entry path, then the member's headings "
                    "demoted by one level; dead entries are marked [DEAD]")
    pcxt.add_argument("slug", help="ctx slug").completer = _complete_ctx_slugs
    pcxt.add_argument("--depth", type=int, default=0, metavar="N",
                      help="only headings of original level <= N (default 0 = all)")


def add_find_parser(sub):
    pf = _sub(sub, "find", "search",
              "hybrid ranked search: lexical FTS5/BM25 arm plus semantic arm",
              formatter_class=argparse.RawDescriptionHelpFormatter,
              epilog=_FIND_EPILOG)
    pf.add_argument("query", help="search terms; quote multi-word queries")
    pf.add_argument("--include-topics", action="store_true", help="widen beyond .okf.toml declared bundle to topic folders")
    pf.add_argument("--limit", type=int, default=10,
                    help="max results to print (default 10)")
    pf.add_argument("--type", help="filter by frontmatter `type` (exact match)").completer = _complete_types
    pf.add_argument("--tag", help="filter by tag (exact match)").completer = _complete_tags
    pf.add_argument("--scope", metavar="TARGET",
                    help="<bundle> or <bundle>/<subdir> to limit (default: whole catalogue)").completer = _complete_scopes
    pf.add_argument("--include-archive", action="store_true",
                    help="also search _archive/<bundle>/<cid>; excluded by "
                         "default (combine with --scope to reach the "
                         "archived concepts of one bundle)")
    pf.add_argument("--breakdown", action="store_true",
                    help="print per-hit contributing field(s)/term(s); "
                         "output is byte-identical to today without this flag")
    pf.add_argument("--expand-tags", action="store_true",
                    help="expand the query with semantically near registered "
                         "tags before lexical scoring; measured against the "
                         "full catalogue and found ineffective for the "
                         "vocabulary-mismatch class it was built for, so it "
                         "stays off by default (Q05/D17)")


def add_fix_crosslinks_parser(sub):
    pfx = _sub(sub, "fix-crosslinks", "maintenance",
               "rewrite links to catalogue-root-absolute form (/bundle/subdir/concept.md)")
    pfx.add_argument("target", nargs="?", help="<bundle> or <bundle>/<subdir> (default: whole catalogue)").completer = _complete_scopes
    pfx.add_argument("--check", action="store_true", help="dry-run: report without writing")
    pfx.add_argument("--include-reserved", action="store_true",
                      dest="include_reserved",
                      help="also rewrite RESERVED files (index.md, log.md, "
                           "readme.md, index-map.md), narrowed to the text "
                           "outside the managed <!-- okf:index --> block, "
                           "which stays byte-identical (D-fxcr-01, off by "
                           "default)")


def add_fix_xml_tags_parser(sub):
    pfxt = _sub(sub, "fix-xml-tags", "maintenance",
                "wrap `<tag>`/`<tag>.<tag2>` placeholders in inline code")
    pfxt.add_argument("target", nargs="?", help="<bundle> or <bundle>/<subdir> (default: whole catalogue)").completer = _complete_scopes
    pfxt.add_argument("--check", action="store_true", help="dry-run: report without writing")


def add_index_parser(sub):
    pi = _sub(sub, "index", "navigation",
              "catalogue TOC (bundle names + one-line descriptions), or one "
              "bundle's index.md")
    pi.add_argument("bundle", nargs="?",
                    help="bundle to print (default: the whole catalogue TOC)").completer = _complete_bundles
    pi.add_argument("--full", action="store_true",
                    help="catalogue TOC: print the structured per-bundle block "
                         "(description, concept count, directories, types, tags) "
                         "instead of the default one-line name+description "
                         "listing; with a bundle arg: print the structured "
                         "bundle summary instead of the raw index.md")
    pi.add_argument("--json", action="store_true", help="machine-readable output")


def add_info_parser(sub):
    _sub(sub, "info", "navigation",
         "print catalogue schema docs (TYPES.md + PROPERTIES.md)")


def add_install_parser(sub):
    pin = _sub(sub, "install", "maintenance",
               "register okf-cli, its agent skill, MCP server and shell completion with this "
               "machine's agents and shells (dry-run default; needs no catalogue)")
    pin.add_argument("--apply", action="store_true",
                     help="perform the plan (default: print the plan, change nothing)")
    pin.add_argument("--uninstall", action="store_true",
                     help="plan, or with --apply perform, the removal of everything install created")
    pin.add_argument("--only", metavar="NAMES",
                     help="comma-separated subset: claude, omp, codex, opencode, kimi, openclaw, hermes "
                          "(agents), zsh, bash, fish (shells). Default: install for every agent and "
                          "shell found on this machine; uninstall covers all of them")
    pin.add_argument("--json", action="store_true", help="machine-readable output")


def add_list_parser(sub):
    pls = _sub(sub, "list", "navigation",
               "list concepts filtered by frontmatter type and/or tag")
    pls.add_argument("--type", help="filter by frontmatter `type` (exact match)").completer = _complete_types
    pls.add_argument("--tag", help="filter by tag (exact match)").completer = _complete_tags
    pls.add_argument("--scope", metavar="TARGET",
                     help="<bundle> or <bundle>/<subdir> to limit (default: whole catalogue)").completer = _complete_scopes
    pls.add_argument("--include-archive", action="store_true",
                    help="also list _archive/<bundle>/<cid>; excluded by "
                         "default (combine with --scope to reach the "
                         "archived concepts of one bundle)")
    pls.add_argument("--json", action="store_true", help="machine-readable output")


def add_merge_tags_parser(sub):
    pmt = _sub(sub, "merge-tags", "tags",
               "merge/rename one or more tags into a target tag across concept frontmatter")
    pmt.add_argument("tags", nargs="+", help="source tag(s) to merge, e.g. workflow workflows").completer = _complete_tags
    pmt.add_argument("--into", required=True, metavar="TAG", help="destination tag name").completer = _complete_tags
    pmt.add_argument("--scope", metavar="TARGET",
                     help="<bundle> or <bundle>/<subdir> to limit the rewrite (default: whole catalogue)").completer = _complete_scopes
    pmt.add_argument("--apply", action="store_true", help="write changes (default: dry-run preview only)")


def add_normalize_tags_parser(sub):
    pnt = _sub(sub, "normalize-tags", "tags",
               "convert inline `tags: [...]` fields to YAML block-list form (local convention)")
    pnt.add_argument("--scope", metavar="TARGET",
                     help="<bundle> or <bundle>/<subdir> to limit the rewrite (default: whole catalogue)").completer = _complete_scopes
    pnt.add_argument("--apply", action="store_true", help="write changes (default: dry-run preview only)")


def add_prime_parser(sub):
    pp = _sub(sub, "prime", "navigation",
              "one-shot agent onboarding: usage guide, command directory, "
              "catalogue state and bundle TOC")
    pp.add_argument("--full", action="store_true",
                     help="add types+tags to each bundle block")
    pp.add_argument("--compact", action="store_true",
                     help="list bundles as name+count one-liners instead of the "
                          "`index` blocks (description+directories)")
    pp.add_argument("--check-semantic", action="store_true",
                     help="run the exact content-hash semantic coverage check "
                          "(~2s on a large catalogue) instead of reporting only "
                          "whether the semantic index is present")


def add_read_parser(sub):
    pr = _sub(sub, "read", "navigation", "print one concept page")
    pr.add_argument("path", help="<bundle>/<concept-id> of the page to print").completer = _complete_concepts


def add_recent_parser(sub):
    prc = _sub(sub, "recent", "navigation",
               "list the most recently created concepts, newest first")
    prc.add_argument("--limit", type=int, default=10,
                     help="max results to print (default 10)")
    prc.add_argument("--scope", metavar="TARGET",
                     help="<bundle> or <bundle>/<subdir> to limit (default: whole catalogue)").completer = _complete_scopes
    prc.add_argument("--type", help="filter by frontmatter `type` (exact match)").completer = _complete_types
    prc.add_argument("--tag", help="filter by tag (exact match)").completer = _complete_tags
    prc.add_argument("--json", action="store_true", help="machine-readable output")


def add_refs_parser(sub):
    prf = _sub(sub, "refs", "search",
               "list inbound and outbound markdown links of a file")
    prf.add_argument("path", help="target file (abs, or relative to --root)").completer = _complete_concept_files
    prf.add_argument("--scan-root", help="dir to scan (default: --root); pass repo root for repo-wide").completer = _complete_dirs
    prf.add_argument("--json", action="store_true",
                     help="machine-readable output")
    prf_dir = prf.add_mutually_exclusive_group()
    prf_dir.add_argument("--in", dest="only_in", action="store_true", help="only inbound links")
    prf_dir.add_argument("--out", dest="only_out", action="store_true", help="only outbound links")


def add_reindex_parser(sub):
    px = _sub(sub, "reindex", "maintenance",
              "(re)generate marker-bounded index listings: index.md one level, "
              "index-map.md the whole subtree")
    px.add_argument("target", help="<bundle> or <bundle>/<subdir>").completer = _complete_scopes
    px.add_argument("--init", action="store_true",
                    help="recursively migrate marker-less flat index.md in the subtree to "
                         "managed marker blocks (bespoke multi-section indexes are skipped + flagged)")
    px.add_argument("--check", action="store_true",
                    help="dry-run: with --init preview conversions; else report stale + uncovered. No writes")
    px.add_argument("--force", action="store_true",
                    help="with --init, also flatten a pure multi-section listing (prose/tables still refuse)")


def add_remove_tags_parser(sub):
    prt = _sub(sub, "remove-tags", "tags",
               "remove one or more tags from concept frontmatter (no merge target)")
    prt.add_argument("tags", nargs="+", help="tag(s) to remove, e.g. stale draft").completer = _complete_tags
    prt.add_argument("--scope", metavar="TARGET",
                     help="<bundle> or <bundle>/<subdir> to limit the rewrite (default: whole catalogue)").completer = _complete_scopes
    prt.add_argument("--apply", action="store_true", help="write changes (default: dry-run preview only)")


def add_rename_parser(sub):
    prn = _sub(sub, "rename", "maintenance",
               "move a concept + rewrite every inbound/outbound link + reindex (dry-run default)")
    prn.add_argument("old", help="source concept path (<bundle>/<concept>.md, abs or --root-relative)").completer = _complete_concept_files
    prn.add_argument("new", help="destination path (same or different bundle)").completer = _complete_concept_files
    prn.add_argument("--apply", action="store_true", help="perform the move (default: dry-run preview only)")
    prn.add_argument("--force", action="store_true",
                     help="overwrite an existing destination, and proceed when the new "
                          "basename is already taken and inbound wikilinks would turn ambiguous")


def add_rewrite_path_parser(sub):
    prw = _sub(sub, "rewrite-path", "maintenance",
               "literal path-string rewrite across text files")
    prw.add_argument("old", help="literal path string to replace")
    prw.add_argument("new", help="replacement path string")
    prw.add_argument("--scan-root", help="dir to scan (default: --root)").completer = _complete_dirs
    prw.add_argument("--check", action="store_true", help="dry-run: report, write nothing")


def add_sync_export_parser(sub):
    pse = _sub(sub, "sync-export", "navigation",
               "print a canonical block's payload for materialisation elsewhere")
    pse.add_argument("concept", help="canonical concept (<bundle>/<concept-id>)").completer = _complete_concepts
    pse.add_argument("block_id", metavar="block-id",
                     help="canon block id declared in that concept").completer = _complete_block_ids


def add_sync_insert_parser(sub):
    psi = _sub(sub, "sync-insert", "maintenance",
               "materialise a canonical block inside a consumer concept (dry-run default)")
    psi.add_argument("consumer", help="consumer concept to insert into (<bundle>/<concept-id>)").completer = _complete_concepts
    psi.add_argument("concept", help="canonical owner concept (<bundle>/<concept-id>)").completer = _complete_concepts
    psi.add_argument("block_id", metavar="block-id", help="canon block id to materialise").completer = _complete_block_ids
    psi.add_argument("--apply", action="store_true",
                     help="write the block (default: dry-run preview only)")


def add_sync_status_parser(sub):
    pss = _sub(sub, "sync-status", "maintenance",
               "drift report for every materialised canon block")
    pss.add_argument("target", nargs="?",
                     help="<bundle> or <bundle>/<subdir> (default: whole catalogue)").completer = _complete_scopes
    pss.add_argument("--source",
                     help="only blocks whose canonical source is this path (/bundle/concept.md)").completer = _complete_canon_sources
    pss.add_argument("--block", metavar="BLOCK_ID", help="only blocks with this id").completer = _complete_canon_block_ids
    pss.add_argument("--json", action="store_true", help="machine-readable output")


def add_sync_update_parser(sub):
    psu = _sub(sub, "sync-update", "maintenance",
               "re-materialise outdated consumer blocks from their canon owner (dry-run default)")
    psu.add_argument("target", nargs="?",
                     help="<bundle> or <bundle>/<subdir> (default: whole catalogue)").completer = _complete_scopes
    psu.add_argument("--source",
                     help="only blocks whose canonical source is this path (/bundle/concept.md)").completer = _complete_canon_sources
    psu.add_argument("--block", metavar="BLOCK_ID", help="only blocks with this id").completer = _complete_canon_block_ids
    psu.add_argument("--apply", action="store_true",
                     help="write changes (default: dry-run preview only)")
    psu.add_argument("--force", action="store_true",
                     help="also overwrite a consumer copy that was modified locally (discards it)")


def add_tags_parser(sub):
    pg = _sub(sub, "tags", "tags",
              "list all tags with usage counts, or fuzzy-search candidate tags")
    pg.add_argument("query", nargs="*",
                    help="candidate tag(s) to fuzzy-search against the tag universe; omit for full audit dump")
    pg.add_argument("--limit", type=int, default=8, help="max matches per candidate (default 8)")
    pg.add_argument("--singletons", action="store_true",
                    help="full-dump mode only: show tags used exactly once")
    pg.add_argument("--register", nargs=2, action="append", metavar=("TAG", "DESCRIPTION"),
                    help="add a tag to the TAGS.md registry (closed-vocabulary allow-list); "
                         "DESCRIPTION is required, max 150 chars; repeat the option for several tags")
    pg.add_argument("--validate", nargs="+", metavar="TAG",
                    help="check tag(s) against TAGS.md; exit 1 if any are unregistered").completer = _complete_tags


def add_toc_parser(sub):
    pt = _sub(sub, "toc", "navigation",
              "print a concept's headings (default: h2 only)")
    pt.add_argument("path", help="<bundle>/<concept-id> to list headings for").completer = _complete_concepts
    pt.add_argument("--level", type=int, default=2,
                    help="heading level to list (default 2 = h2); 0 = full indented tree")


def add_visualize_parser(sub):
    pv = _sub(sub, "visualize", "navigation",
              "write a viz.html concept graph for a bundle "
              "(embeds every concept body; needs network for cytoscape/marked)")
    pv.add_argument("bundle", help="bundle to render the graph for").completer = _complete_bundles
    pv.add_argument("--out", help="output path (default: <bundle>/assets/viz.html)").completer = _complete_files


def add_wikilinks_parser(sub):
    pwl = _sub(sub, "wikilinks", "maintenance",
               "report Obsidian wikilinks ([[…]]) and whether each resolves to a concept")
    pwl.add_argument("target", nargs="?",
                     help="<bundle> or <bundle>/<subdir> (default: whole catalogue)").completer = _complete_scopes
    pwl.add_argument("--unresolved", action="store_true",
                     help="list only unresolved and ambiguous occurrences (summary stays complete)")
    pwl.add_argument("--json", action="store_true", help="machine-readable output")


COMMANDS = {
    "archive": (cmd_archive, add_archive_parser),
    "build-index": (cmd_build_index, add_build_index_parser),
    "build-semantic-index": (cmd_build_semantic_index, add_build_semantic_index_parser),
    "check": (cmd_check, add_check_parser),
    "ctx": (cmd_ctx, add_ctx_parser),
    "find": (cmd_find, add_find_parser),
    "fix-crosslinks": (cmd_fix_crosslinks, add_fix_crosslinks_parser),
    "fix-xml-tags": (cmd_fix_xml_tags, add_fix_xml_tags_parser),
    "index": (cmd_index, add_index_parser),
    "info": (cmd_info, add_info_parser),
    "install": (cmd_install, add_install_parser),
    "list": (cmd_list, add_list_parser),
    "merge-tags": (cmd_merge_tags, add_merge_tags_parser),
    "normalize-tags": (cmd_normalize_tags, add_normalize_tags_parser),
    "prime": (cmd_prime, add_prime_parser),
    "read": (cmd_read, add_read_parser),
    "recent": (cmd_recent, add_recent_parser),
    "refs": (cmd_refs, add_refs_parser),
    "reindex": (cmd_reindex, add_reindex_parser),
    "remove-tags": (cmd_remove_tags, add_remove_tags_parser),
    "rename": (cmd_rename, add_rename_parser),
    "rewrite-path": (cmd_rewrite_path, add_rewrite_path_parser),
    "sync-export": (cmd_sync_export, add_sync_export_parser),
    "sync-insert": (cmd_sync_insert, add_sync_insert_parser),
    "sync-status": (cmd_sync_status, add_sync_status_parser),
    "sync-update": (cmd_sync_update, add_sync_update_parser),
    "tags": (cmd_tags, add_tags_parser),
    "toc": (cmd_toc, add_toc_parser),
    "visualize": (cmd_visualize, add_visualize_parser),
    "wikilinks": (cmd_wikilinks, add_wikilinks_parser),
}


# Command modules under cli/okf/ that own their commands. Each defines COMMANDS in
# the same {name: (handler, add_parser)} form; moving a command means moving its
# COMMANDS entry into its module and listing the module here.
COMMAND_MODULES = ()

COMMAND_TABLE = merge_commands(COMMANDS, *(module.COMMANDS for module in COMMAND_MODULES))
COMMAND_DISPATCH = {name: handler for name, (handler, _add_parser) in COMMAND_TABLE.items()}


def build_parser():
    ap = argparse.ArgumentParser(prog="okf-cli.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", help="catalogue root (default: auto-detect from cwd; "
                    "hard-fails if none found)").completer = _complete_dirs
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in sorted(COMMAND_TABLE):
        COMMAND_TABLE[name][1](sub)
    ap.epilog = render_command_overview(sub.choices)
    return ap


def _silence_broken_pipe_streams():
    devnull = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(devnull, sys.stdout.fileno())
        os.dup2(devnull, sys.stderr.fileno())
    finally:
        os.close(devnull)


def main():
    ap = build_parser()
    if "_ARGCOMPLETE" in os.environ:
        # Shell TAB completion (glue installed by `install`): optional
        # dependency, imported only on a completion run, which argcomplete
        # ends via os._exit.
        import argcomplete
        argcomplete.autocomplete(ap, default_completer=argcomplete.SuppressCompleter())
    args = ap.parse_args(_ctx_shorthand(sys.argv[1:]))
    if args.cmd in CATALOGUE_FREE:
        return COMMAND_DISPATCH[args.cmd](None, args)
    root = catalogue_root(args.root)
    if root is None:
        sys.exit("ERROR: no catalogue found in cwd or its ancestors; pass --root <path>")
    if not os.path.isdir(root):
        sys.exit("ERROR: root not found: {} (pass --root <path>)".format(root))
    if args.root and not (
        os.path.isfile(os.path.join(root, ".okf.toml"))
        or (os.path.isfile(os.path.join(root, "SPEC.md")) and os.path.isfile(os.path.join(root, "TYPES.md")))
    ):
        # SC-002 (test_explicit_root_returns_abspath_unchanged) requires an
        # explicit --root to keep working with no marker present, so this
        # never blocks. But every write command below computes emitted paths
        # as "/" + relpath(dest, root) (resolve_crosslink_target and peers) —
        # a --root pointed one level above the real catalogue silently
        # prefixes every emitted link with the extra segment instead of
        # failing (OKFT-czm9: a vault-relative alias like
        # "SPF_Sproutling/docs/sproutling-okf/e2e-tests/README.md" got
        # written and committed unnoticed). Loud-but-non-blocking, matching
        # this file's stderr-degradation idiom (see find's stale-index note).
        print("note: --root {} carries no catalogue marker (.okf.toml or "
              "SPEC.md+TYPES.md) — if this is not the real catalogue root, "
              "write commands will silently emit wrong paths".format(root),
              file=sys.stderr)
    COMMAND_DISPATCH[args.cmd](root, args)


if __name__ == "__main__":
    try:
        main()
        # Explicit flush, still inside the try: stdout to a pipe is
        # block-buffered, not line-buffered, so a small answer (the common
        # case against the real catalogue, measured 2026-08-13) can finish
        # every print() into the buffer without ever attempting the OS-level
        # write() that would raise. Without this line the write only
        # happens implicitly at interpreter shutdown, OUTSIDE this
        # try/except, so BrokenPipeError is never caught at all and only
        # the "Exception ignored ..." shutdown noise appears — no
        # traceback, but still not clean. Confirmed against the real
        # catalogue: OKFT-0k55 Test-Output.
        sys.stdout.flush()
    except BrokenPipeError:
        _silence_broken_pipe_streams()
        sys.exit(0)
