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
import importlib.util
import json
import math
import os
import re
import sqlite3
import struct
import subprocess
import sys
import textwrap
import urllib.error
import urllib.request
from collections import Counter

RESERVED = {"index.md", "log.md", "readme.md", "index-map.md"}
FM_DELIM = "---"
MARK_START = "<!-- okf:index -->"
MARK_END = "<!-- /okf:index -->"
LOG_START = "<!-- okf:log -->"
LOG_END = "<!-- /okf:log -->"
EXEMPT = "<!-- okf:index-exempt -->"
LOG_NOTICE = (
    "> **History lives in git.** This file is a portability snapshot, not the "
    "source of truth. Regenerate the block below with `python3 okf-cli.py log "
    "--write` (per bundle: `okf-cli.py log <bundle>`). Rationale for each change "
    "lives in its commit body; anything outside the markers is a frozen archive."
)


def catalogue_root(explicit):
    """Resolve the catalogue root. Explicit --root wins unchanged (abspath,
    even if nonexistent — main() validates that). Absent --root, auto-detect
    by walking cwd upward for a catalogue marker (.okf.toml, or SPEC.md +
    TYPES.md together); return None if no marker is found anywhere up to the
    filesystem root — never silently fall back to the script's own directory.
    """
    if explicit:
        return os.path.abspath(explicit)
    d = os.getcwd()
    while True:
        if os.path.isfile(os.path.join(d, ".okf.toml")) or (
            os.path.isfile(os.path.join(d, "SPEC.md"))
            and os.path.isfile(os.path.join(d, "TYPES.md"))
        ):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def is_bundle_dir(name):
    return not name.startswith(".") and not name.startswith("_")


def list_bundles(root):
    out = []
    for name in sorted(os.listdir(root)):
        p = os.path.join(root, name)
        if os.path.isdir(p) and is_bundle_dir(name):
            out.append(name)
    return out


def list_indexable_bundles(root, config_root=None):
    """The narrower bundle set for index/search call sites only -- build-index,
    the FTS/semantic staleness counters, and find's whole-catalogue scope
    (resolve_scopes). A repo docs root names exactly one real bundle in its
    `.okf.toml` `bundle` key among many TPIC-scaffolding directories that also
    pass is_bundle_dir()'s name filter; only the declared one belongs in the
    index/search corpus (OKFT-n8xz, epic OKFT-wmbu).

    Falls back to list_bundles(root) -- the catalogue behaviour, unchanged --
    when the key is absent, matching the central Knowledge-Catalogue's
    .okf.toml, which carries no `bundle` key.

    A declared bundle that does not exist on disk yields the EMPTY set, not a
    silent fallback to the name filter: `bundle` is a positive declaration of
    the one directory that counts, and falling back the moment its path goes
    missing would quietly resurrect every scaffolding directory into the
    index -- exactly the regression this split exists to prevent.

    `config_root` is where `.okf.toml` is read from when it differs from
    `root` -- the `_archive/<bundle>/` mirror of an indexed root has no
    config of its own (the declaration lives once, at the real root), so its
    callers pass the real root as `config_root` while still listing
    `_archive/` itself. Defaults to `root`.

    Deliberately NOT used for wikilink/crosslink resolution, `check`'s
    integrity scan, or any presentation surface -- those keep calling
    list_bundles() directly, so narrowing the corpus never narrows what a
    link can resolve to (okf-tools-okf/archive-lifecycle/
    active-beats-archived-in-wikilink-resolution)."""
    config = load_okf_config(root if config_root is None else config_root)
    bundle = config.get("bundle")
    if not isinstance(bundle, str) or not bundle:
        return list_bundles(root)
 
    return [bundle] if os.path.isdir(os.path.join(root, bundle)) else []
 
def list_search_bundles(root, include_topics=False):
    """Return the search corpus, widening to topic folders only explicitly."""
    return list_bundles(root) if include_topics else list_indexable_bundles(root)


def iter_concepts(bundle_path, prune_staging=True):
    """Yield (concept_id, abspath) for every non-reserved .md under a bundle.

    prune_staging=True (default): prunes "_"-prefixed staging dirs, same
    convention as iter_all_md (:2954, clause :2960-2961) — most callers feed
    index/search/list/presentation, never `check` (which walks iter_all_md
    exclusively), so the two functions diverging left in-bundle staging
    content reachable via index/list/find yet skipped by check (OKFT-oe8t
    D01: fixed here, at the shared function, because that read-path
    majority needed it and `check` was never affected).

    prune_staging=False (OKFT-oe8t Review, D02): the three tag-mutation
    writers — cmd_merge_tags, cmd_remove_tags, cmd_normalize_tags — pass
    this explicitly. They are not read paths; narrowing what a write
    command touches is a different question than narrowing what the
    retrieval surface returns, and this bean's mandate was retrieval only.
    Same shape as OKFT-n8xz's `indexable_only` on resolve_scopes(): one
    shared walk, the default serving the majority, the minority opting
    explicitly at its own call site rather than a second, duplicated walk."""
    for dirpath, dirnames, filenames in os.walk(bundle_path):
        if prune_staging:
            dirnames[:] = [d for d in dirnames
                           if not d.startswith(".") and not d.startswith("_")
                           and d != "assets"]
        else:
            dirnames[:] = [d for d in dirnames
                           if not d.startswith(".") and d != "assets"]
        for fn in filenames:
            if not fn.endswith(".md") or fn.lower() in RESERVED:
                continue
            ap = os.path.join(dirpath, fn)
            cid = os.path.relpath(ap, bundle_path)[:-3]  # strip .md
            yield cid.replace(os.sep, "/"), ap


def split_frontmatter(text):
    """Return (fm_dict, body). Minimal top-level YAML key parse — no deps."""
    fm, body = {}, text
    if text.startswith(FM_DELIM):
        end = text.find("\n" + FM_DELIM, len(FM_DELIM))
        if end != -1:
            block = text[len(FM_DELIM):end]
            body = text[end + len(FM_DELIM) + 1:]
            for line in block.splitlines():
                m = re.match(r"^([A-Za-z0-9_\-]+):\s?(.*)$", line)
                if m:
                    fm[m.group(1)] = m.group(2).strip()
    return fm, body


def read_file(ap):
    with open(ap, encoding="utf-8", errors="replace") as f:
        return f.read()


def _dequote(s):
    s = (s or "").strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        return s[1:-1]
    return s


def meta_of(ap):
    fm, _ = split_frontmatter(read_file(ap))
    title = _dequote(fm.get("title", "")) or os.path.basename(ap)[:-3]
    return fm.get("type", ""), title, _dequote(fm.get("description", ""))


def parse_tag_list(raw):
    """Parse a frontmatter `tags` value like `[a, b, "c d"]` into a list."""
    raw = (raw or "").strip()
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    if not raw.strip():
        return []
    return [_dequote(p) for p in raw.split(",") if p.strip()]


def extract_tags(text):
    """Read the `tags` frontmatter field, inline (`tags: [a, b]`) or as a
    YAML block list (`tags:\\n  - a\\n  - b`). split_frontmatter() only keeps
    single-line values, so this walks the raw frontmatter block itself."""
    if not text.startswith(FM_DELIM):
        return []
    end = text.find("\n" + FM_DELIM, len(FM_DELIM))
    if end == -1:
        return []
    lines = text[len(FM_DELIM):end].splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"^tags:\s*(.*)$", line)
        if not m:
            continue
        rest = m.group(1).strip()
        if rest:
            return parse_tag_list(rest)
        tags = []
        for cont in lines[i + 1:]:
            lm = re.match(r"^\s*-\s*(.+)$", cont)
            if not lm:
                break
            tags.append(_dequote(lm.group(1).strip()))
        return tags
    return []


def all_tags(root):
    """Return Counter of tag -> usage count across every concept in the catalogue."""
    counts = Counter()
    for b in list_bundles(root):
        bp = os.path.join(root, b)
        for _cid, ap in iter_concepts(bp):
            for t in extract_tags(read_file(ap)):
                counts[t] += 1
    return counts


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


_BUILD_TAGVEC_MODULE = None


def _load_build_tagvec():
    """Lazy-load cli/embeddings/build_tagvec.py (not a hard import — see its
    module docstring: offline/optional). Cached module-level so a test can
    monkeypatch the SAME object's embed_bge_m3 that auto_embed_new_tags() uses."""
    global _BUILD_TAGVEC_MODULE
    if _BUILD_TAGVEC_MODULE is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "embeddings", "build_tagvec.py")
        spec = importlib.util.spec_from_file_location("build_tagvec", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _BUILD_TAGVEC_MODULE = mod
    return _BUILD_TAGVEC_MODULE


def auto_embed_new_tags(root, tags):
    """Best-effort bge-m3 embedding of newly registered tags, scoped to just
    `tags` (never a full re-embed). Fix for PO-review reject 2026-07-25
    (bean okf-cli-3geg): registration and embedding coverage must not drift
    apart. Never raises — `tags --register` must succeed even if Ollama/
    network is unavailable; a failure here is a stderr warning, not an error."""
    if not tags:
        return
    try:
        bt = _load_build_tagvec()
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
        added, already = register_tags(root, args.register)
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
              else "{} UNKNOWN — register with: okf-cli.py tags --register {}".format(
                  len(unknown), " ".join(unknown)))
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
            for b in list_indexable_bundles(archive_root, root):
                n_archived += _index_bundle(
                    b, os.path.join(archive_root, b), "_archive/")

        conn.executemany(
            "INSERT OR REPLACE INTO fts_meta(k, v) VALUES (?, ?)",
            [("n_concepts", str(n_active)), ("n_archived", str(n_archived)),
             ("newest_mtime", repr(newest))])
        conn.commit()
    finally:
        conn.close()
    os.replace(tmp, db_path)
    return n_active + n_archived, db_path


def _fts_index_stale(root, conn):
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
    except (sqlite3.DatabaseError, KeyError, ValueError, TypeError):
        return True
    n_active = 0
    n_archived = 0
    newest = 0.0
    for b in list_indexable_bundles(root):
        for _cid, ap in iter_concepts(os.path.join(root, b)):
            n_active += 1
            mt = os.path.getmtime(ap)
            if mt > newest:
                newest = mt
    archive_root = os.path.join(root, "_archive")
    if os.path.isdir(archive_root):
        for b in list_indexable_bundles(archive_root, root):
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
                stale = _fts_index_stale(root, conn)
            finally:
                conn.close()
            if not stale:
                print("index is current, skipping rebuild -> {}".format(db_path))
                return
    n, db = build_fts_index(root)
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
    bt = _load_build_tagvec()
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

    __slots__ = ("scope", "type", "tag", "include_archive")

    _ARCHIVE_PREFIX = "_archive/"
    # Escaped once here rather than re-derived at each of the two LIKE call
    # sites (review B01 round 3, okf-cli-pn72): the constant's own leading
    # `_` is exactly as much a wildcard inside a bound LIKE pattern as a
    # user's scope value is, and two independent `_like_escape(...)` call
    # sites is how the first fix already missed one of them.
    _ARCHIVE_PREFIX_ESC = _like_escape(_ARCHIVE_PREFIX)

    def __init__(self, scope=None, type=None, tag=None, include_archive=False):
        # Normalize "" to None once, here: cmd_find reads these off argparse
        # and the MCP layer passes empty strings for "unset".
        self.scope = (scope or "").rstrip("/") or None
        self.type = type or None
        self.tag = tag or None
        self.include_archive = bool(include_archive)

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
        if archived and not self.include_archive:
            return False
        if not self.scope:
            return True
        compared = path[len(self._ARCHIVE_PREFIX):] if archived else path
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
    sql += " ORDER BY r LIMIT ?"
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
            if notify and _fts_index_stale(root, conn):
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

    indexable_only=True (OKFT-n8xz, Review 2026-08-13 D02): this is the ONE
    resolve_scopes() call that feeds the search corpus, so it is the ONE
    caller that opts into the narrower, declared-bundle traversal. Every
    other resolve_scopes() caller stays on the wide default."""
    hits = []
    for _b, bp in resolve_scopes(root, filters.scope, filters.include_archive,
                                  indexable_only=True):
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
                              # OWN the ranking (D12). Measured value —
                              # eval/hybrid_eval.py:151 — not a tuning knob.
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
    ranked = sorted(((_cosine(qvec, vec), path) for path, vec in vectors),
                    key=lambda x: -x[0])
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


def cmd_find(root, args):
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
    filters = FindFilters(
        scope=getattr(args, "scope", None),
        type=getattr(args, "type", None),
        tag=getattr(args, "tag", None),
        include_archive=getattr(args, "include_archive", False),
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


def resolve_concept(root, path):
    """<bundle>/<concept-id> to an absolute file. A reference that names a
    DIRECTORY resolves to that directory's index.md (okf-cli-3hjr), so the
    bundle names prime lists are usable verbatim as `toc <bundle>` /
    `read <bundle>`. The concept file wins over the directory reading, so the
    fallback can never shadow a page."""
    ref = path[:-3] if path.endswith(".md") else path
    ap = os.path.join(root, ref + ".md")
    if os.path.isfile(ap):
        return ap
    as_dir = os.path.join(root, ref)
    if os.path.isdir(as_dir):
        idx = _find_reserved_name(os.listdir(as_dir), "index.md")
        if idx:
            return os.path.join(as_dir, idx)
        print("not found: {} is a directory without an index.md".format(path),
              file=sys.stderr)
        sys.exit(1)
    print("not found: {}".format(path), file=sys.stderr)
    sys.exit(1)


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


def iter_headings(body):
    """Yield (level, text) for markdown headings, skipping fenced code blocks."""
    in_fence = False
    for line in body.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = re.match(r"^(#{1,6})\s+(.+?)\s*#*$", line)
        if m:
            yield len(m.group(1)), m.group(2).strip()


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
applies frontmatter and re-indexes. `index.md` listings and `log.md` are
marker-managed and generated (`reindex`, `log --write`) — never edit between the
`<!-- okf:... -->` markers. Tag edits go through `merge-tags` / `remove-tags`,
not a search-and-replace. A commit is allowed only once `check` reports zero
violations.
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
frontmatter and re-indexes. `index.md` listings and `log.md` are marker-managed
and generated — never edit between the `<!-- okf:... -->` markers. A commit is
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
        bt = _load_build_tagvec()
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
    nodes, edges = bundle_graph(root, args.bundle)
    out = args.out or os.path.join(root, args.bundle, "assets", "viz.html")
    data = json.dumps({"name": args.bundle, "nodes": nodes, "edges": edges})
    html = _VIZ_TEMPLATE.replace("__DATA__", data).replace("__NAME__", args.bundle)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print("wrote {} ({} nodes, {} edges)".format(out, len(nodes), len(edges)))


def _prune_walk_dirs(dirnames):
    """In-place os.walk prune: skip node_modules and dot-dirs."""
    dirnames[:] = [d for d in dirnames if d != "node_modules" and not d.startswith(".")]


def _find_reserved_name(filenames, name="index.md"):
    """Case-insensitive lookup of a reserved filename in an os.walk filenames
    list. Returns the actual on-disk filename (preserving its real case), or
    None. OKF's reserved-name recognition (RESERVED, above) is case-insensitive
    via .lower() — the index-discovery walks below now match that."""
    low = name.lower()
    for f in filenames:
        if f.lower() == low:
            return f
    return None


def build_ref_matrix(scan_root, target_abspath):
    """List every markdown link under scan_root that resolves to target_abspath.
    Returns [(source_rel, raw_link), ...]. Reuses the bundle_graph link regex,
    strips fenced code, ignores http(s)/mailto and anchors. Both relative and
    catalogue-root-absolute (leading /) links are resolved path-wise."""
    target_abspath = os.path.abspath(target_abspath)
    link_re = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    hits = []
    # Same traversal and same dead-zone mask as the wikilink half of a rename,
    # so the two halves of one move cannot disagree about which files and which
    # occurrences they cover. A root-level walk alone cannot enter a symlinked
    # bundle, which left a mounted file with its wikilink rewritten and its
    # markdown link dangling in the same line.
    for ap in iter_rename_scan_md(scan_root):
        dirpath = os.path.dirname(ap)
        text = read_file(ap)
        for m in link_re.finditer(wikilink_scan_text(text)):
            raw = text[m.start(1):m.end(1)]
            tgt = raw.split("#", 1)[0].split("?", 1)[0].strip()
            if not tgt or re.match(r"^[a-z][a-z0-9+.-]*://", tgt) or tgt.startswith("mailto:"):
                continue
            if tgt.startswith("/"):
                # OKF (catalogue-root convention): leading / = scan_root
                # (= catalogue root = Obsidian vault root), NOT the bundle.
                resolved = os.path.abspath(os.path.join(scan_root, tgt.lstrip("/")))
            else:
                resolved = os.path.abspath(os.path.join(dirpath, tgt))
            if resolved != target_abspath:
                # A link may spell its target in a different case than the disk
                # does; on a case-insensitive filesystem that link is live and
                # must be rewritten too. samefile only runs on a case-equal
                # near-miss, so this stays correct on a case-sensitive one.
                if (resolved.lower() != target_abspath.lower()
                        or not os.path.exists(resolved)
                        or not os.path.samefile(resolved, target_abspath)):
                    continue
            hits.append((os.path.relpath(ap, scan_root).replace(os.sep, "/"), raw))
    return hits


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
    hits = build_ref_matrix(scan_root, target)
    if getattr(args, "json", False):
        print(json.dumps({
            "target": os.path.relpath(os.path.abspath(target), scan_root).replace(os.sep, "/"),
            "inbound": [{"source": s, "link": l} for s, l in hits],
        }))
    else:
        if not hits:
            print("no inbound references")
        for s, l in hits:
            print("{}  ->  {}".format(s, l))


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

def write_file(ap, text):
    with open(ap, "w", encoding="utf-8") as f:
        f.write(text)


def _collapse(s):
    return re.sub(r"\s+", " ", s or "").strip()


def list_dir_concepts(dirpath):
    """(title, slug, description) for non-reserved .md directly in dirpath, by title."""
    out = []
    for fn in os.listdir(dirpath):
        if not fn.endswith(".md") or fn.lower() in RESERVED:
            continue
        ap = os.path.join(dirpath, fn)
        if not os.path.isfile(ap):
            continue
        _, title, desc = meta_of(ap)
        out.append((title, fn[:-3], desc))
    out.sort(key=lambda x: x[0].casefold())
    return out


def index_h1_and_desc(ap):
    """First H1 text and the intro paragraph of an index.md (no frontmatter).

    The intro is the first non-empty line after the H1 *only if* it is a real
    paragraph; if the body leads with a heading/list/comment there is no intro.
    """
    _, body = split_frontmatter(read_file(ap))
    lines = body.splitlines()
    h1, desc, i = None, "", 0
    while i < len(lines):
        m = re.match(r"^#\s+(.+?)\s*#*$", lines[i])
        i += 1
        if m:
            h1 = m.group(1).strip()
            break
    while i < len(lines):
        s = lines[i].strip()
        if not s:
            i += 1
            continue
        if not re.match(r"^(#|<!--|[*\-+>]|\d+\.)", s):
            desc = s
        break
    return h1, desc


def list_subdirs_with_index(dirpath):
    """(title, subdir_name, description) for immediate subdirs containing index.md."""
    out = []
    for name in sorted(os.listdir(dirpath)):
        p = os.path.join(dirpath, name)
        if not os.path.isdir(p) or name.startswith(".") or name == "assets":
            continue
        idx_name = _find_reserved_name(os.listdir(p))
        if not idx_name:
            continue
        idx = os.path.join(p, idx_name)
        h1, desc = index_h1_and_desc(idx)
        out.append((h1 or name, name, desc))
    out.sort(key=lambda x: x[0].casefold())
    return out


def render_block(subdirs, concepts, dir_rel=""):
    """OKF bullet list: subdirectories first, then concept files.

    Links are catalogue-root-absolute (`/bundle/subdir/concept.md`) so Obsidian
    resolves them from the vault root, not from the index's own folder. A bare
    relative target (`concept.md`) resolves inconsistently in Obsidian and shows
    phantom orphan nodes in the graph for files that do exist. `dir_rel` is the
    index directory's path relative to the catalogue root ("" / "." = root).
    """
    dir_rel = "" if dir_rel in ("", ".") else dir_rel.strip("/")
    prefix = "/" + dir_rel + "/" if dir_rel else "/"
    lines = []
    for title, name, desc in subdirs:
        d = _collapse(desc)
        lines.append("* [{}]({}{}/index.md){}".format(title, prefix, name, " - " + d if d else ""))
    for title, slug, desc in concepts:
        d = _collapse(desc)
        lines.append("* [{}]({}{}.md){}".format(title, prefix, slug, " - " + d if d else ""))
    return "\n".join(lines)


def replace_managed_block(text, block):
    """Replace content between the markers. Returns (new_text, found)."""
    si = text.find(MARK_START)
    if si == -1:
        return text, False
    ei = text.find(MARK_END, si)
    if ei == -1:
        return text, False
    inner = "\n" + block + "\n" if block else "\n"
    return text[:si + len(MARK_START)] + inner + text[ei:], True


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
    for dp, dn, fn in os.walk(target):
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
        idx_name = _find_reserved_name(fn)
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
        dir_rel = os.path.relpath(dp, root).replace(os.sep, "/")
        block = render_block(list_subdirs_with_index(dp), list_dir_concepts(dp), dir_rel)
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


def render_git_log(title, rows):
    """rows: [(date, subject), …] newest-first → SPEC §7 date-grouped flat list."""
    out = ["# {} Update Log".format(title)]
    last = None
    for date, subject in rows:
        if date != last:
            out.append("")
            out.append("## {}".format(date))
            last = date
        out.append("* {}".format(subject))
    return "\n".join(out).rstrip() + "\n"


def splice_log(existing, snapshot):
    """Insert/refresh the git snapshot inside <!-- okf:log --> markers.

    If markers exist, only the block between them is replaced (the hand-authored
    archive outside stays put). Otherwise a notice header + marker block is
    created and any prior content is preserved below as a frozen archive.
    """
    block = LOG_START + "\n" + snapshot.rstrip() + "\n" + LOG_END
    if existing and LOG_START in existing:
        si = existing.find(LOG_START)
        ei = existing.find(LOG_END, si) + len(LOG_END)
        return existing[:si] + block + existing[ei:]
    header = "# Catalogue Update Log\n\n" + LOG_NOTICE + "\n\n"
    archive = ""
    if existing and existing.strip():
        arch = re.sub(r"^#\s+.*\n+", "", existing.strip())  # drop duplicate H1
        archive = "\n\n## Archiv (hand-authored, eingefroren)\n\n" + arch + "\n"
    return header + block + archive + "\n"


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
# diffs") and §7 defines `**Creation**` as a log entry type. cmd_log below has
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


def _git_toplevel(path):
    """(toplevel_abspath, None) or (None, 'no-git'|'no-repo').

    rev-parse rather than an ancestor walk for `.git`: it also answers
    correctly for worktrees, submodules, `.git`-as-a-file and an inherited
    GIT_DIR. `git -C <symlink-to-dir>` chdirs physically, so a symlinked
    bundle resolves to the FOREIGN repo that actually holds its history."""
    try:
        res = subprocess.run(["git", "-C", path, "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True)
    except (FileNotFoundError, OSError):
        return None, "no-git"
    if res.returncode != 0:
        return None, "no-repo"
    return res.stdout.strip(), None


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
    root_top, reason = _git_toplevel(realroot)
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
        repo, why = _git_toplevel(real)
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


def cmd_log(root, args):
    bundle = getattr(args, "bundle", None)
    scope = os.path.join(root, bundle) if bundle else root
    title = bundle if bundle else "Catalogue"
    cmd = ["git", "-C", root, "log", "--date=short", "--format=%ad\t%s"]
    if args.since:
        cmd.append("--since={}".format(args.since))
    cmd += ["--", os.path.relpath(scope, root) if bundle else "."]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print("git log failed: {}".format(e), file=sys.stderr)
        sys.exit(1)
    rows = []
    for line in res.stdout.splitlines():
        if "\t" in line:
            d, s = line.split("\t", 1)
            rows.append((d, s))
    md = render_git_log(title, rows)
    if args.write:
        target = os.path.join(scope, "log.md")
        existing = read_file(target) if os.path.isfile(target) else ""
        snapshot = re.sub(r"^#\s+.*\n+", "", md)  # snapshot body without its own H1
        write_file(target, splice_log(existing, snapshot))
        print("wrote {}".format(os.path.relpath(target, root)))
    else:
        print(md, end="")


# --- check: pluggable conformance scan (§9 hard rules + local invariants) ---

FILENAME_FORBIDDEN_CHARS = set('#^[]|\\:?*"<>%')
GERMAN_FM_KEYS = {"titel", "beschreibung", "typ", "stichworte", "datum", "zusammenfassung"}


def load_types(root, types_source=None):
    """Set of registered `type` values, or None if the source is missing.
    types_source overrides the default <root>/TYPES.md so a repo bundle can
    point at the central catalogue's TYPES.md (config-aware, no local copy)."""
    p = types_source or os.path.join(root, "TYPES.md")
    if not os.path.isfile(p):
        return None
    return set(re.findall(r"^\|\s*`([^`]+)`", read_file(p), re.M))


def load_tags(root, tags_source=None):
    """Set of registered tag values from <root>/TAGS.md, or None if the file is
    missing (in which case the closed-vocabulary check is a no-op). TAGS.md is a
    pipe-table with a leading `` `tag` `` cell per row — same format as TYPES.md,
    so the extraction regex is shared. The registry is the allowed tag vocabulary;
    new tags enter it only via `okf-cli.py tags --register` (human-gated)."""
    p = tags_source or os.path.join(root, "TAGS.md")
    if not os.path.isfile(p):
        return None
    return set(re.findall(r"^\|\s*`([^`]+)`", read_file(p), re.M))


TAGS_HEADER = (
    "# TAGS.md — Registered Tag Vocabulary\n\n"
    "Closed vocabulary for concept `tags:`. The `tag-registered` conformance check\n"
    "(warning; `check --strict` escalates to error) flags any tag not listed here.\n"
    "Add a new tag only via `okf-cli.py tags --register <tag>` — reuse an existing\n"
    "tag over minting a near-duplicate. A tag earns its place by aggregating content.\n\n"
    "| Tag | Description |\n|-----|-------------|\n"
)


def _read_tag_rows(root):
    """Parse TAGS.md into an ordered {tag: description} dict ({} if absent)."""
    p = os.path.join(root, "TAGS.md")
    rows = {}
    if os.path.isfile(p):
        for tag, desc in re.findall(r"^\|\s*`([^`]+)`\s*\|(.*?)\|", read_file(p), re.M):
            rows[tag] = desc.strip()
    return rows


def write_tags_registry(root, rows):
    """Render {tag: description} to TAGS.md, tags casefold-sorted."""
    body = "".join("| `{}` | {} |\n".format(t, rows[t]) for t in sorted(rows, key=str.casefold))
    with open(os.path.join(root, "TAGS.md"), "w", encoding="utf-8") as f:
        f.write(TAGS_HEADER + body)


def register_tags(root, new_tags):
    """Add tags to TAGS.md (creating it if absent). Returns (added, already)."""
    rows = _read_tag_rows(root)
    added = [t for t in dict.fromkeys(new_tags) if t not in rows]
    already = [t for t in dict.fromkeys(new_tags) if t in rows]
    for t in added:
        rows[t] = ""
    if added:
        write_tags_registry(root, rows)
    return added, already


def load_okf_config(root):
    """Parse <root>/.okf.toml if present. Returns a dict ({} if absent).
    Leading-~ path values are expanduser-expanded. Requires Python 3.11+ (tomllib)."""
    p = os.path.join(root, ".okf.toml")
    if not os.path.isfile(p):
        return {}
    import tomllib
    with open(p, "rb") as f:
        try:
            data = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            # Every caller now reaches this on every run, so a parse failure has
            # to name the file and the reason instead of printing a traceback.
            sys.exit("ERROR: {} is not valid TOML: {}".format(p, e))
    for k in ("kc_root", "types_source"):
        if isinstance(data.get(k), str):
            data[k] = os.path.expanduser(data[k])
    return data


def iter_all_md(bundle_path):
    """Yield abspath for every .md under a bundle, reserved files included.

    Prunes "assets" (binary asset store) and "_"-prefixed dirs (staging, same
    convention as is_bundle_dir uses one level up for bundles)."""
    for dirpath, dirnames, filenames in os.walk(bundle_path):
        dirnames[:] = [d for d in dirnames
                       if not d.startswith(".") and not d.startswith("_") and d != "assets"]
        for fn in filenames:
            if fn.endswith(".md"):
                yield os.path.join(dirpath, fn)


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
    relative `/subdir/x.md` or typos — the phantom-orphan class)."""
    if ctx["is_reserved"]:
        return []
    # Symlinked external bundles keep the portable bundle-relative OKF form and are
    # audited in their own repo — the catalogue-root convention does not apply here.
    if os.path.islink(os.path.join(ctx["root"], ctx["bundle"])):
        return []
    relative, dangling = [], []
    scan_body, _ = _mask_code_spans(ctx["body"])   # fenced/inline example links are not real links
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


def _mask_code_spans(body):
    """Stash fenced code blocks + inline code so a pattern scan skips them.
    Frontmatter is already split off by the caller (ctx["body"]/split_frontmatter),
    so only fences/inline-code need masking here. Mirrors the Vault-side
    wrap-hex-tags.js mask/unmask convention for the same class of problem."""
    tokens = []

    def stash(m):
        tokens.append(m.group(0))
        return "\x00{}\x00".format(len(tokens) - 1)

    body = re.sub(r"(```|~~~)[\s\S]*?\1", stash, body)
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
        for ap in iter_all_md(bp):
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


CROSSLINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


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


def fix_crosslinks(root, target, dry_run=False):
    """Rewrite crosslinks in every non-reserved .md under `target` (bundle or
    bundle/subdir, or the whole catalogue when None) to catalogue-root-absolute
    form. Returns (touched, unresolved):
    touched = [(rel, changed_count), ...], unresolved = [(rel, target), ...]."""
    touched, unresolved = [], []
    for bundle, bp in resolve_scopes(root, target):
        for ap in iter_all_md(bp):
            if os.path.basename(ap).lower() in RESERVED:
                continue
            text = read_file(ap)
            _, body = split_frontmatter(text)
            head = text[:len(text) - len(body)]
            cdir = os.path.dirname(os.path.relpath(ap, bp))
            new_body, changed, unres = rewrite_crosslinks_in_body(root, bundle, cdir, body)
            rel = os.path.relpath(ap, root).replace(os.sep, "/")
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
    touched, unresolved = fix_crosslinks(root, target, dry_run=args.check)
    verb = "would rewrite" if args.check else "rewrote"
    for rel, n in touched:
        print("{:<14} {}  ({} link(s))".format(verb, rel, n))
    for rel, tgt in unresolved:
        print("unresolved     {}  -> {}".format(rel, tgt))
    print("fix-crosslinks: {} file(s) {}, {} unresolved link(s)".format(
        len(touched), verb, len(unresolved)))


def resolve_scopes(root, target, include_archive=False, indexable_only=False):
    """[(bundle, bundle_path), ...] for `target` (<bundle> or <bundle>/<subdir>),
    or every bundle in the catalogue when target is None.

    R-12 (okf-cli-iwx4): the ONE function ten commands traverse through —
    `cmd_merge_tags`, `cmd_remove_tags`, `cmd_normalize_tags`, `cmd_list`,
    `_substring_ranking` (find), `_recent_scopes`, `fix_xml_like_tags`,
    `fix_crosslinks`, `scan_wikilinks` (the `wikilinks` command) and
    `run_checks` (the `check` command) — AC1 is that the answer does not
    depend on which one called it, for a given set of arguments.

    `indexable_only` (OKFT-n8xz, Review 2026-08-13 B01/D02) narrows the
    unscoped enumeration to list_indexable_bundles() instead of
    list_bundles() — the declared `.okf.toml` `bundle` key, when present.
    Defaults to False and MUST default to False: this function is shared by
    write commands (a silently narrowed mutation command stops repairing
    files it used to reach), by the two integrity commands `check` and
    `wikilinks` (D17 names these explicitly as paths that must not narrow —
    narrowing them traded the loud defect this epic exists to close for a
    silent one: a real violation in an undeclared directory stops being
    reported at all, verified against a copy of the real okf-tools/docs,
    33 violations gone from an unscoped `check` run), and by presentation
    (`_recent_scopes`). Only the find/index path opts in explicitly
    (`_substring_ranking`), because it alone feeds the search corpus this
    epic is about narrowing. `cmd_list` stays wide too (Q03, undecided by
    design — raised to the PO, not this function).

    When include_archive is set, each resolved scope's archived counterpart
    is appended too, labelled `_archive/<bundle>[...]` and pointing at the
    real `_archive/...` directory below root — a caller that walks the
    returned pairs reaches the archive without a second traversal shape, and
    a hit's path stays its true position below root (AC3: `okf-cli read` on
    it resolves, SC-02). Unscoped, every bundle registered under `_archive/`
    is reached this way too, including one with no active counterpart — the
    same discovery R-05/R-06's wikilink basename index already does for the
    archive (build_concept_basename_index, above; that function's traversal
    is independent of this one and always stays wide — resolution never
    narrows regardless of `indexable_only` here). Scoped, the archived
    counterpart is derived WITHOUT an existence check, same as the active
    side already does for a scoped target: a directory that turns out not to
    exist yields no concepts from iter_concepts()'s os.walk, silently, the
    same contract as always — no special-casing needed here for that."""
    def _bundles(r, config_r=None):
        return (list_indexable_bundles(r, config_r) if indexable_only
                else list_bundles(r))

    if target:
        # An absolute target addresses a directory directly and must keep doing
        # so — os.path.join(root, "/x") discards root, and normalising it into a
        # relative segment would silently rescope the scan onto a path that does
        # not exist, reporting a clean run over nothing.
        if os.path.isabs(target):
            tp = os.path.normpath(target)
            rel = os.path.relpath(tp, root).replace(os.sep, "/")
            if rel.startswith(".."):
                return [("", tp)]
            scopes = [(rel.split("/")[0], tp)]
            norm = rel
        else:
            # normpath otherwise: an unnormalised `./a` yielded bundle "." and
            # silently defeated every bundle-name-keyed rule (the wikilink
            # opt-in gate found it) while the scan still ran over the right
            # directory.
            norm = os.path.normpath(target).replace(os.sep, "/").strip("/")
            if norm in (".", ""):
                scopes = [(b, os.path.join(root, b)) for b in _bundles(root)]
                norm = None
            else:
                scopes = [(norm.split("/")[0], os.path.join(root, norm))]
    else:
        scopes = [(b, os.path.join(root, b)) for b in _bundles(root)]
        norm = None
    if not include_archive:
        return scopes
    archive_root = os.path.join(root, "_archive")
    if norm is None:
        if not os.path.isdir(archive_root):
            return scopes
        return scopes + [("_archive/" + b, os.path.join(archive_root, b))
                         for b in _bundles(archive_root, root)]
    return scopes + [("_archive/" + norm.split("/")[0],
                      os.path.join(archive_root, norm))]


# --- wikilinks -------------------------------------------------------------
# Obsidian's native link form. Every markdown-link scanner in this module
# anchors on "](" (CROSSLINK_RE plus its three inline copies), so none of them
# can see a [[…]] — a rename rewrites the markdown links, reports success and
# silently orphans every inbound wikilink. Everything below is the wikilink
# counterpart of that machinery: parse, resolve, report, rewrite.

WIKILINK_RE = re.compile(r"(!?)\[\[([^\[\]\n]+)\]\]")


def _frontmatter_end(text):
    """Offset where split_frontmatter's `body` begins (0 when the file carries
    no frontmatter block). Same arithmetic as split_frontmatter, exposed so a
    scan can tag which region an occurrence sits in — Obsidian treats a
    frontmatter link property as a real link, so both regions count."""
    if text.startswith(FM_DELIM):
        end = text.find("\n" + FM_DELIM, len(FM_DELIM))
        if end != -1:
            return end + len(FM_DELIM) + 1
    return 0


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


# Spans Obsidian does not index as links. Fences are found line-based, not by
# regex: a regex pairs backtick runs left to right with no notion of line start
# or fence length, so one prose ``` mention or a 4-backtick fence shifts every
# later pairing by one and leaves a real code block exposed to the rewriter.
FENCE_LINE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})[ \t]*(.*)$")
COMMENT_RE = re.compile(r"%%[\s\S]*?%%|<!--[\s\S]*?-->")
INLINE_CODE_RE = re.compile(r"(`+)(?:(?!\1).)+?\1")
LIST_ITEM_RE = re.compile(r"^[ \t]*(?:[-*+]|\d+[.)])[ \t]")
# A YAML-looking line: a comment, a block-list item, an indented continuation,
# or a `key:` — where the key may hold spaces, umlauts and even a colon
# (`Übersicht … ISO 9001:2015:` is a real key in this catalogue), so the match
# runs to the LAST colon before whitespace or end of line.
YAML_LINE_RE = re.compile(r"^(?:[ \t]*#|[ \t]*-[ \t]|[ \t]+\S|[^\s:#][^\n]*:(?:[ \t]|$))")
FENCE_START_RE = re.compile(r"^ {0,3}(?:`{3,}|~{3,})")


def _split_lines_with_offsets(text):
    lines, offs, pos = [], [], 0
    for ln in text.splitlines(keepends=True):
        lines.append(ln)
        offs.append(pos)
        pos += len(ln)
    offs.append(pos)
    return lines, offs


def _fenced_code_spans(lines, offs):
    """CommonMark fenced blocks. An opener is up to three spaces of indent then
    three or more backticks or tildes; it closes on a line of at least as many
    of the same character carrying nothing else. An unclosed fence runs to end
    of file, which is how Obsidian renders it too."""
    spans, i, n = [], 0, len(lines)
    while i < n:
        m = FENCE_LINE_RE.match(lines[i].rstrip("\n"))
        if not m:
            i += 1
            continue
        marker, rest = m.group(1), m.group(2)
        if marker[0] == "`" and "`" in rest:
            i += 1                       # info string may not contain a backtick
            continue
        start, char, width = i, marker[0], len(marker)
        i += 1
        while i < n:
            cm = FENCE_LINE_RE.match(lines[i].rstrip("\n"))
            if (cm and cm.group(1)[0] == char and len(cm.group(1)) >= width
                    and not cm.group(2).strip()):
                i += 1
                break
            i += 1
        spans.append((offs[start], offs[i]))
    return spans


def _indented_code_spans(lines, offs):
    """4-space/tab indented code blocks.

    Indentation alone does not make one: the same shape is markdown's
    list-continuation form, which Obsidian renders as prose and does index. A
    run of indented lines opens a code block only when it follows a blank line
    whose own predecessor is neither a list item nor itself indented."""
    def indented(ln):
        return ln.startswith("    ") or ln.startswith("\t")

    spans, i, n = [], 0, len(lines)
    while i < n:
        if not lines[i].strip() or not indented(lines[i]):
            i += 1
            continue
        if i == 0 or lines[i - 1].strip():
            i += 1
            continue                                  # no blank line opens it
        prev = next((lines[j] for j in range(i - 2, -1, -1) if lines[j].strip()), None)
        if prev is not None and (LIST_ITEM_RE.match(prev) or indented(prev)):
            i += 1
            continue                                  # list continuation, not code
        start = i
        i += 1                                        # guaranteed progress
        while i < n and (not lines[i].strip() or indented(lines[i])):
            i += 1
        end = i
        while end > start and not lines[end - 1].strip():
            end -= 1
        spans.append((offs[start], offs[end]))
    return spans


def _blank(text, spans):
    """`text` with every span blanked to NUL, LENGTH PRESERVED, newlines kept.

    Length preservation is the point: offsets in the masked copy address the
    same bytes in the original, so a scan can report and rewrite against the
    real text without a stash/restore round trip. A stash lost content whenever
    one masked span held another's placeholder — `re.sub` does not rescan its
    replacement, so the inner token reached disk verbatim."""
    if not spans:
        return text
    out = list(text)
    for a, b in spans:
        for i in range(a, b):
            if out[i] != "\n":
                out[i] = "\x00"
    return "".join(out)


def _dead_zone_mask(text, yaml=False):
    """Blank every span Obsidian does not index, in stages.

    Each stage runs over the output of the previous one, so a construct inside
    an already-masked span cannot open a new one: no nesting, no pairing drift.

    `yaml=True` skips only the indented-code stage, because YAML indentation is
    structure — a block list under a blank line is not a code block. Inline code
    is masked in both regions: exempting it in frontmatter cost more than it
    bought, since a `---` thematic rule whose first line happens to read like
    `key: value` lands here and its prose backticks are then rewritable, while a
    genuine link property wrapped in backticks has zero occurrences catalogue-
    wide and would only be under-reported, never corrupted."""
    lines, offs = _split_lines_with_offsets(text)
    masked = _blank(text, _fenced_code_spans(lines, offs))
    masked = _blank(masked, [(m.start(), m.end()) for m in COMMENT_RE.finditer(masked)])
    masked = _blank(masked,
                    [(m.start(), m.end()) for m in INLINE_CODE_RE.finditer(masked)])
    if yaml:
        return masked
    lines, offs = _split_lines_with_offsets(masked)
    return _blank(masked, _indented_code_spans(lines, offs))


def is_yaml_frontmatter_block(block):
    """True when every non-blank line of a `---`-delimited block reads as YAML.

    This is what separates real frontmatter from a `---` thematic rule opening
    the body. Both look identical to split_frontmatter, and getting it wrong
    costs bytes in both directions: body rules applied to YAML swallow a link
    property, YAML rules applied to prose expose a fenced example to the
    rewriter."""
    lines = [ln for ln in block.splitlines() if ln.strip()]
    if not lines:
        return True         # `---\n---` is an empty frontmatter block, not prose
    # An UNINDENTED fence is never YAML, however key-like its neighbours. An
    # indented one may be the content of a block scalar (`example: |`), and
    # rejecting the whole block for it hid every link property in the file.
    if any(FENCE_START_RE.match(ln) and not ln[:1].isspace() for ln in lines):
        return False
    # The FIRST line decides, not every line: a plain scalar continued on an
    # unindented line is sloppy YAML but common here (432 qm-wiki files carry a
    # multi-line German description that way), while a `---` thematic rule
    # opening a body starts with prose that carries no `key:` at all.
    return bool(YAML_LINE_RE.match(lines[0]))


def wikilink_regions(text):
    """[(label, start, end)] — the frontmatter region, then the body.

    `_frontmatter_end` mirrors split_frontmatter, which cannot tell a YAML block
    from a thematic rule; this can, and a head that is not YAML is body text
    reported as such."""
    fm_end = _frontmatter_end(text)
    # The block BETWEEN the delimiters — _frontmatter_end points past the
    # closing one, and a `---` line is not itself YAML.
    if fm_end and not is_yaml_frontmatter_block(
            text[len(FM_DELIM):fm_end - len(FM_DELIM) - 1]):
        fm_end = 0
    return [("frontmatter", 0, fm_end), ("body", fm_end, len(text))]


def wikilink_scan_text(text):
    """The masked copy a wikilink scan reads, aligned byte-for-byte with `text`."""
    fm_end = wikilink_regions(text)[0][2]
    return (_dead_zone_mask(text[:fm_end], yaml=True)
            + _dead_zone_mask(text[fm_end:]))


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
            idx.setdefault(fn[:-3].lower(), []).append(
                "/" + os.path.relpath(ap, root).replace(os.sep, "/"))
    archive_root = os.path.join(root, "_archive")
    if os.path.isdir(archive_root):
        for b in list_bundles(archive_root):
            for ap in iter_all_md(os.path.join(archive_root, b)):
                fn = os.path.basename(ap)
                if fn.lower() in RESERVED:
                    continue
                idx.setdefault(fn[:-3].lower(), []).append(
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
    cands = index.get(page.rsplit("/", 1)[-1].lower(), [])
    if not cands:
        return "unresolved", []
    if "/" in page:
        tail = "/{}.md".format(page.strip("/")).lower()
        cands = [c for c in cands if c.lower().endswith(tail)]
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
    if args.json:
        import json
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
    sys.exit(1 if errors else 0)


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


def iter_rename_scan_md(root):
    """Every .md the rename inbound scan must see.

    build_ref_matrix's own traversal (a root-level walk under
    _prune_walk_dirs: dot-dirs and node_modules out, `_`-prefixed staging dirs
    and root-level files IN — unlike iter_all_md) plus a second pass over each
    symlinked bundle, because os.walk does not descend into a symlinked
    subdirectory and five catalogue bundles are symlinks. Either half alone
    leaves a stale reference behind: the root walk misses the mounts, a
    per-bundle walk misses root-level staging.

    Deliberately wider than the reporting surfaces: staging directories, root-
    level files and `assets/` are all rewritten. A stale reference in a file
    `wikilinks` never lists is still a stale reference, and the markdown half of
    the same rename already reaches every one of them — pruning here would leave
    a file with its markdown link updated and its wikilink dangling in the same
    line."""
    seen = set()
    starts = [root] + [os.path.join(root, b) for b in list_bundles(root)
                       if os.path.islink(os.path.join(root, b))]
    for start in starts:
        for dirpath, dirnames, filenames in os.walk(start):
            _prune_walk_dirs(dirnames)
            for fn in filenames:
                if not fn.endswith(".md"):
                    continue
                ap = os.path.join(dirpath, fn)
                if ap not in seen:
                    seen.add(ap)
                    yield ap


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
        if os.path.basename(c)[:-3].lower() == new_base.lower()
        and c.lower() not in keep)
    # Casefolded, because resolve_wikilink is (D06). A case-sensitive filter
    # here silently excluded every case-variant inbound link from the plan — the
    # 96 live links D06 exists to rescue would have been orphaned by the very
    # rename that was supposed to carry them.
    old_key, new_key = old_base.lower(), new_base.lower()
    after = _index_after_move(index, old_link, new_link, collisions)
    out = []
    for ap in files:
        rel = os.path.relpath(ap, root).replace(os.sep, "/")
        for rec in parse_wikilinks(read_file(ap), rel):
            key = rec["page"].rsplit("/", 1)[-1].lower()
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
      bundles  = sorted affected bundle names (reindex targets)."""
    old_abs, new_abs = os.path.abspath(old_abs), os.path.abspath(new_abs)
    inbound = []
    for source_rel, raw in build_ref_matrix(root, old_abs):
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
            "bundles": bundles}


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


def read_file_verbatim(abspath):
    """File text with line endings and bytes exactly as stored, or None when it
    is not valid UTF-8.

    read_file() translates CRLF to LF and replaces undecodable bytes with
    U+FFFD; harmless for a scan, destructive on a rewrite, because write_file
    then persists the translation across the whole file — not just the link it
    was asked to change."""
    try:
        with open(abspath, encoding="utf-8", newline="") as f:
            return f.read()
    except UnicodeDecodeError:
        return None


def write_file_verbatim(abspath, text):
    with open(abspath, "w", encoding="utf-8", newline="") as f:
        f.write(text)


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


def reindex_tree(root, tp):
    """Refresh every managed index block under tp (no --init/--check semantics).
    Returns the rel-paths of index files actually rewritten."""
    changed = []
    for dp, dn, fn in os.walk(tp):
        dn[:] = [d for d in dn if not d.startswith(".") and d != "assets"]
        idx_name = _find_reserved_name(fn)
        if not idx_name:
            continue
        idx = os.path.join(dp, idx_name)
        text = read_file(idx)
        if MARK_START not in text:
            continue
        dir_rel = os.path.relpath(dp, root).replace(os.sep, "/")
        block = render_block(list_subdirs_with_index(dp), list_dir_concepts(dp), dir_rel)
        new_text, _ = replace_managed_block(text, block)
        if new_text != text:
            write_file(idx, new_text)
            changed.append(os.path.relpath(idx, root).replace(os.sep, "/"))
    return changed


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
        top, why = _git_toplevel(os.path.dirname(real_old))
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
        _print_skipped()
        print("  reindex    {}".format(", ".join(plan["bundles"])))
        print("rename (dry-run): {} inbound, {} outbound link(s), {} wikilink(s) "
              "({} skipped-ambiguous), {} bundle(s). Re-run with --apply.".format(
                  len(plan["inbound"]), len(plan["outbound"]), len(wl_rewrite),
                  len(wl_skipped), len(plan["bundles"])))
        return

    if os.path.exists(new_abs) and not os.path.samefile(old_abs, new_abs):
        # --force got us here. Say what it costs: the destination's content is
        # gone and every reference to it now addresses different content.
        clobbered = build_ref_matrix(root, new_abs)
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


COMMAND_DISPATCH = {
    "prime": cmd_prime, "index": cmd_index, "find": cmd_find, "list": cmd_list,
    "read": cmd_read, "info": cmd_info, "toc": cmd_toc, "visualize": cmd_visualize,
    "refs": cmd_refs,
    "rewrite-path": cmd_rewrite_path, "rename": cmd_rename, "archive": cmd_archive,
    "build-index": cmd_build_index,
    "build-semantic-index": cmd_build_semantic_index,
    "reindex": cmd_reindex, "log": cmd_log, "recent": cmd_recent,
    "tags": cmd_tags,
    "merge-tags": cmd_merge_tags,
    "remove-tags": cmd_remove_tags,
    "normalize-tags": cmd_normalize_tags,
    "check": cmd_check, "fix-crosslinks": cmd_fix_crosslinks,
    "fix-xml-tags": cmd_fix_xml_tags,
    "wikilinks": cmd_wikilinks,
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


def render_command_overview(parsers, footer=True, width=96):
    """The purpose-grouped command directory, rendered from the registered
    parsers (D02/D03). argparse's own listing above it is flat and
    alphabetical; this block answers "what can this CLI do" by purpose. Both
    come from the same registrations, so neither can drift from the other.

    `parsers` is the {name: parser} mapping from subcommand_parsers(). The
    same block is the command section of `prime` (okf-cli-3hjr), which is why
    the footer — a --help cross-reference — is optional there. `width` is the
    wrap column; `prime --compact` raises it so each command costs one line
    instead of two-plus a 21-space continuation indent."""
    lines = ["commands by purpose:"]
    for group in _GROUP_ORDER:
        names = sorted(n for n, g in COMMAND_GROUPS.items() if g == group)
        if not names:
            continue
        lines.append("  {}:".format(group))
        for name in names:
            lines.append(textwrap.fill(
                parsers[name].description, width=width,
                initial_indent="    {:<16} ".format(name),
                subsequent_indent=" " * 21))
    if footer:
        lines.append("")
        lines.append("run `okf-cli.py <command> --help` for one command's options.")
    return "\n".join(lines)


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


def build_parser():
    ap = argparse.ArgumentParser(prog="okf-cli.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", help="catalogue root (default: auto-detect from cwd; "
                    "hard-fails if none found)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pah = _sub(sub, "archive", "maintenance",
               "move a concept into _archive/<bundle>/, or back with --restore (dry-run default)")
    pah.add_argument("path", help="<bundle>/<concept>[.md]; with --restore: "
                                   "_archive/<bundle>/<concept>[.md]. The other end is derived, "
                                   "never typed")
    pah.add_argument("--restore", action="store_true",
                     help="move the path back out of _archive/ instead of into it")
    pah.add_argument("--apply", action="store_true", help="perform the move (default: dry-run preview only)")
    pah.add_argument("--force", action="store_true",
                     help="overwrite an existing destination, and proceed when the new "
                          "basename is already taken and inbound wikilinks would turn ambiguous")
    pbi = _sub(sub, "build-index", "search",
               "(re)build the FTS5 lexical search index at "
               "<root>/.fts/fts.sqlite (local only, no network)")
    pbi.add_argument("--if-stale", action="store_true",
                      help="skip the rebuild when the existing index is "
                           "already current (default: always rebuild)")
    pbs = _sub(sub, "build-semantic-index", "search",
               "fill <root>/.tagvec/tag_vectors.sqlite's concept_emb table "
               "for every concept still missing a voyage-3-large embedding "
               "(NETWORK, requires VOYAGE_API_KEY)")
    pbs.add_argument("--if-stale", action="store_true",
                      help="skip the run when semantic_coverage() already "
                           "reports every on-disk concept embedded "
                           "(default: always fill the delta)")
    pc = _sub(sub, "check", "maintenance",
              "conformance scan: §9 hard rules + local invariants")
    pc.add_argument("target", nargs="?", help="<bundle> or <bundle>/<subdir> (default: whole catalogue)")
    pc.add_argument("--strict", action="store_true", help="promote warnings to errors")
    pc.add_argument("--json", action="store_true", help="machine-readable output")
    pc.add_argument("--types", help="explicit TYPES.md path (overrides .okf.toml types_source)")
    pf = _sub(sub, "find", "search",
              "hybrid ranked search: lexical FTS5/BM25 arm plus semantic arm",
              formatter_class=argparse.RawDescriptionHelpFormatter,
              epilog=_FIND_EPILOG)
    pf.add_argument("query", help="search terms; quote multi-word queries")
    pf.add_argument("--limit", type=int, default=10,
                    help="max results to print (default 10)")
    pf.add_argument("--type", help="filter by frontmatter `type` (exact match)")
    pf.add_argument("--tag", help="filter by tag (exact match)")
    pf.add_argument("--scope", metavar="TARGET",
                    help="<bundle> or <bundle>/<subdir> to limit (default: whole catalogue)")
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
    pfx = _sub(sub, "fix-crosslinks", "maintenance",
               "rewrite links to catalogue-root-absolute form (/bundle/subdir/concept.md)")
    pfx.add_argument("target", nargs="?", help="<bundle> or <bundle>/<subdir> (default: whole catalogue)")
    pfx.add_argument("--check", action="store_true", help="dry-run: report without writing")
    pfxt = _sub(sub, "fix-xml-tags", "maintenance",
                "wrap `<tag>`/`<tag>.<tag2>` placeholders in inline code")
    pfxt.add_argument("target", nargs="?", help="<bundle> or <bundle>/<subdir> (default: whole catalogue)")
    pfxt.add_argument("--check", action="store_true", help="dry-run: report without writing")
    pi = _sub(sub, "index", "navigation",
              "catalogue TOC (bundle names + one-line descriptions), or one "
              "bundle's index.md")
    pi.add_argument("bundle", nargs="?",
                    help="bundle to print (default: the whole catalogue TOC)")
    pi.add_argument("--full", action="store_true",
                    help="catalogue TOC: print the structured per-bundle block "
                         "(description, concept count, directories, types, tags) "
                         "instead of the default one-line name+description "
                         "listing; with a bundle arg: print the structured "
                         "bundle summary instead of the raw index.md")
    pi.add_argument("--json", action="store_true", help="machine-readable output")
    _sub(sub, "info", "navigation",
         "print catalogue schema docs (TYPES.md + PROPERTIES.md)")
    pls = _sub(sub, "list", "navigation",
               "list concepts filtered by frontmatter type and/or tag")
    pls.add_argument("--type", help="filter by frontmatter `type` (exact match)")
    pls.add_argument("--tag", help="filter by tag (exact match)")
    pls.add_argument("--scope", metavar="TARGET",
                     help="<bundle> or <bundle>/<subdir> to limit (default: whole catalogue)")
    pls.add_argument("--include-archive", action="store_true",
                    help="also list _archive/<bundle>/<cid>; excluded by "
                         "default (combine with --scope to reach the "
                         "archived concepts of one bundle)")
    pls.add_argument("--json", action="store_true", help="machine-readable output")
    pl = _sub(sub, "log", "navigation",
              "render git history for the catalogue or a bundle as a SPEC §7 changelog")
    pl.add_argument("bundle", nargs="?", help="bundle to scope to (default: whole catalogue)")
    pl.add_argument("--since", help="git --since filter, e.g. '3 months ago'")
    pl.add_argument("--write", action="store_true", help="materialize into <scope>/log.md instead of stdout")
    pmt = _sub(sub, "merge-tags", "tags",
               "merge/rename one or more tags into a target tag across concept frontmatter")
    pmt.add_argument("tags", nargs="+", help="source tag(s) to merge, e.g. workflow workflows")
    pmt.add_argument("--into", required=True, metavar="TAG", help="destination tag name")
    pmt.add_argument("--scope", metavar="TARGET",
                     help="<bundle> or <bundle>/<subdir> to limit the rewrite (default: whole catalogue)")
    pmt.add_argument("--apply", action="store_true", help="write changes (default: dry-run preview only)")
    pnt = _sub(sub, "normalize-tags", "tags",
               "convert inline `tags: [...]` fields to YAML block-list form (local convention)")
    pnt.add_argument("--scope", metavar="TARGET",
                     help="<bundle> or <bundle>/<subdir> to limit the rewrite (default: whole catalogue)")
    pnt.add_argument("--apply", action="store_true", help="write changes (default: dry-run preview only)")
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
    pr = _sub(sub, "read", "navigation", "print one concept page")
    pr.add_argument("path", help="<bundle>/<concept-id> of the page to print")
    prc = _sub(sub, "recent", "navigation",
               "list the most recently created concepts, newest first")
    prc.add_argument("--limit", type=int, default=10,
                     help="max results to print (default 10)")
    prc.add_argument("--scope", metavar="TARGET",
                     help="<bundle> or <bundle>/<subdir> to limit (default: whole catalogue)")
    prc.add_argument("--type", help="filter by frontmatter `type` (exact match)")
    prc.add_argument("--tag", help="filter by tag (exact match)")
    prc.add_argument("--json", action="store_true", help="machine-readable output")
    prf = _sub(sub, "refs", "search",
               "list inbound markdown references to a file")
    prf.add_argument("path", help="target file (abs, or relative to --root)")
    prf.add_argument("--scan-root", help="dir to scan (default: --root); pass repo root for repo-wide")
    prf.add_argument("--json", action="store_true",
                     help="machine-readable output")
    px = _sub(sub, "reindex", "maintenance",
              "(re)generate marker-bounded index.md listings")
    px.add_argument("target", help="<bundle> or <bundle>/<subdir>")
    px.add_argument("--init", action="store_true",
                    help="recursively migrate marker-less flat index.md in the subtree to "
                         "managed marker blocks (bespoke multi-section indexes are skipped + flagged)")
    px.add_argument("--check", action="store_true",
                    help="dry-run: with --init preview conversions; else report stale + uncovered. No writes")
    px.add_argument("--force", action="store_true",
                    help="with --init, also flatten a pure multi-section listing (prose/tables still refuse)")
    prt = _sub(sub, "remove-tags", "tags",
               "remove one or more tags from concept frontmatter (no merge target)")
    prt.add_argument("tags", nargs="+", help="tag(s) to remove, e.g. stale draft")
    prt.add_argument("--scope", metavar="TARGET",
                     help="<bundle> or <bundle>/<subdir> to limit the rewrite (default: whole catalogue)")
    prt.add_argument("--apply", action="store_true", help="write changes (default: dry-run preview only)")
    prn = _sub(sub, "rename", "maintenance",
               "move a concept + rewrite every inbound/outbound link + reindex (dry-run default)")
    prn.add_argument("old", help="source concept path (<bundle>/<concept>.md, abs or --root-relative)")
    prn.add_argument("new", help="destination path (same or different bundle)")
    prn.add_argument("--apply", action="store_true", help="perform the move (default: dry-run preview only)")
    prn.add_argument("--force", action="store_true",
                     help="overwrite an existing destination, and proceed when the new "
                          "basename is already taken and inbound wikilinks would turn ambiguous")
    prw = _sub(sub, "rewrite-path", "maintenance",
               "literal path-string rewrite across text files")
    prw.add_argument("old", help="literal path string to replace")
    prw.add_argument("new", help="replacement path string")
    prw.add_argument("--scan-root", help="dir to scan (default: --root)")
    prw.add_argument("--check", action="store_true", help="dry-run: report, write nothing")
    pg = _sub(sub, "tags", "tags",
              "list all tags with usage counts, or fuzzy-search candidate tags")
    pg.add_argument("query", nargs="*",
                    help="candidate tag(s) to fuzzy-search against the tag universe; omit for full audit dump")
    pg.add_argument("--limit", type=int, default=8, help="max matches per candidate (default 8)")
    pg.add_argument("--singletons", action="store_true",
                    help="full-dump mode only: show tags used exactly once")
    pg.add_argument("--register", nargs="+", metavar="TAG",
                    help="add tag(s) to the TAGS.md registry (closed-vocabulary allow-list)")
    pg.add_argument("--validate", nargs="+", metavar="TAG",
                    help="check tag(s) against TAGS.md; exit 1 if any are unregistered")
    pt = _sub(sub, "toc", "navigation",
              "print a concept's headings (default: h2 only)")
    pt.add_argument("path", help="<bundle>/<concept-id> to list headings for")
    pt.add_argument("--level", type=int, default=2,
                    help="heading level to list (default 2 = h2); 0 = full indented tree")
    pv = _sub(sub, "visualize", "navigation",
              "write a self-contained viz.html graph for a bundle")
    pv.add_argument("bundle", help="bundle to render the graph for")
    pv.add_argument("--out", help="output path (default: <bundle>/viz.html)")
    pwl = _sub(sub, "wikilinks", "maintenance",
               "report Obsidian wikilinks ([[…]]) and whether each resolves to a concept")
    pwl.add_argument("target", nargs="?",
                     help="<bundle> or <bundle>/<subdir> (default: whole catalogue)")
    pwl.add_argument("--unresolved", action="store_true",
                     help="list only unresolved and ambiguous occurrences (summary stays complete)")
    pwl.add_argument("--json", action="store_true", help="machine-readable output")
    ap.epilog = render_command_overview(sub.choices)
    return ap


def main():
    args = build_parser().parse_args()
    root = catalogue_root(args.root)
    if root is None:
        sys.exit("ERROR: no catalogue found in cwd or its ancestors; pass --root <path>")
    if not os.path.isdir(root):
        sys.exit("ERROR: root not found: {} (pass --root <path>)".format(root))
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
        # OKFT-0k55 D02: fixed centrally, around the single entrypoint,
        # rather than with a try/except duplicated inside cmd_find (and
        # then cmd_index, cmd_list, cmd_toc, cmd_wikilinks, ... — every
        # command that print()s a long answer shares this exact failure
        # mode; the observed call site, cmd_find's `type:` line, is not
        # special). Catching the exception alone is NOT sufficient: Python
        # flushes sys.stdout at interpreter shutdown, and flushing a
        # closed stdout raises again there, past any handler, printing
        # "Exception ignored ..." noise (wording differs across CPython
        # versions; observed 3.14: "Exception ignored while flushing
        # sys.stdout:"). Redirecting the stdout fd to os.devnull before
        # exit — the standard recipe, see
        # https://docs.python.org/3/library/signal.html#note-on-sigpipe —
        # makes that later flush a silent no-op.
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        # D01 (OKFT-0k55, revisable — Q02 open with the PO): a clean early
        # close (`| head`) is not a CLI error, so exit 0, silently. The
        # competing convention (141 = 128+SIGPIPE) is one line plus a test
        # constant away if the PO's D20 lands on it instead.
        sys.exit(0)
