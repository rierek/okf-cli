#!/usr/bin/env python3
"""okf-cli.py — dependency-free navigation/search for an OKF Knowledge Catalogue.

Catalogue-aware fork inspired by Cole Medin's single-bundle okf-cli.py.
A *catalogue* is a directory whose immediate subdirectories (not starting with
'.' or '_') are OKF *bundles*. Standard library only — no install required.

Commands:
    okf-cli.py prime [--full]              one-shot agent onboarding: CLAUDE.md guide + catalogue TOC
                                            (start here in a new session)
    okf-cli.py index [bundle] [--full]     catalogue TOC (bundle/description/concepts/directories),
                                            or one bundle's index; --full adds types+tags per bundle
    okf-cli.py list [--type <T>] [--tag <T>] [--scope <target>]
                                            list concepts filtered by frontmatter type and/or tag (exact match,
                                            AND-combined), structured per-hit block (title/type/path/description)
    okf-cli.py find "<query>"              ranked keyword search across all bundles; structured per-hit block
                                            (score/title/type/path/description/body-snippet). score shown as
                                            achieved/max ("4/6") — 3 title-hit + 2 tag-hit + 1 body-hit per term,
                                            capped at 1 per field per term, max = 6 * number of terms
    okf-cli.py read <bundle>/<concept-id>  print one concept page
    okf-cli.py info                        print catalogue schema docs (TYPES.md + PROPERTIES.md)
    okf-cli.py reindex <target> [--init] [--check]  (re)generate index.md listings
    okf-cli.py log [bundle] [--since] [--write]  render git history as a SPEC §7 changelog
    okf-cli.py tags [--singletons]          full tag audit dump (tag + usage count), or singleton-only
    okf-cli.py tags <tag1> <tag2> …        fuzzy-search each candidate against the tag universe
    okf-cli.py tags --register <tag> …      add tag(s) to the TAGS.md closed-vocabulary registry
    okf-cli.py tags --validate <tag> …      exit 1 if any tag is unregistered (agent pre-write gate)
    okf-cli.py merge-tags <tag1> [<tag2> …] --into <tag> [--scope <target>] [--apply]
                                            merge/rename tags across concept frontmatter (dry-run default)
    okf-cli.py remove-tags <tag1> [<tag2> …] [--scope <target>] [--apply]
                                            remove tags from concept frontmatter, no merge target (dry-run default)
    okf-cli.py normalize-tags [--scope <target>] [--apply]
                                            convert inline `tags: [...]` to YAML block-list (local convention,
                                            dry-run default)
    okf-cli.py check [target] [--strict] [--json] [--types <path>]  conformance scan (§9 + local
                                            invariants); honors .okf.toml types_source / --types for TYPES.md
    okf-cli.py fix-crosslinks [target] [--check]   rewrite links to catalogue-root-absolute form
    okf-cli.py fix-xml-tags [target] [--check]     wrap `<tag>`/`<tag>.<tag2>` placeholders in inline
                                            code so Obsidian doesn't misparse them as XML/HTML
    okf-cli.py refs <path> [--scan-root <dir>] [--json]  inbound markdown references to a file
    okf-cli.py rewrite-path <old> <new> [--scan-root <dir>] [--check]  literal path-string rewrite
                                            across text files (non-md too); dry-run with --check
    okf-cli.py rename <old> <new> [--apply] [--force]  move a concept and rewrite every inbound link
                                            (repo-wide) + the file's own outbound links on a bundle
                                            change, then reindex affected bundles; dry-run default

Run from the catalogue root, or pass --root <path>.
"""
import argparse
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


def iter_concepts(bundle_path):
    """Yield (concept_id, abspath) for every non-reserved .md under a bundle."""
    for dirpath, dirnames, filenames in os.walk(bundle_path):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d != "assets"]
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
        for _cid, ap in iter_concepts(bp):
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
        for _cid, ap in iter_concepts(bp):
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
        for _cid, ap in iter_concepts(bp):
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


def _concepts_json(bp):
    """[{id, title, type, description}, ...] for every concept under `bp`,
    sorted by concept id. Shared by both cmd_index --json branches (F02
    dedup, prelude 2026-07-25 on okf-cli-83vq)."""
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
        bundles = [
            {"bundle": b, "concepts": _concepts_json(os.path.join(root, b))}
            for b in list_bundles(root)
        ]
        print(json.dumps({"bundles": bundles}))
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
    # catalogue TOC — structured per-bundle blocks
    for b in list_bundles(root):
        print(render_bundle_block(root, b, full=args.full))
        print("-----")


def tokenize(s):
    return [t for t in re.split(r"[^a-z0-9]+", s.lower()) if t]


def cmd_list(root, args):
    if not args.type and not args.tag:
        print("(error: pass --type and/or --tag)", file=sys.stderr)
        sys.exit(1)
    hits = []
    for _bundle, bp in resolve_scopes(root, args.scope):
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


# 8c (D04) — semantic backstop. Fires only as a fallback (zero/weak keyword
# hits), reads .tagvec's concept_emb table (title+body scope, cli/embeddings/
# build_tagvec.py) via stdlib sqlite3, and embeds the query with a LOCAL
# Ollama bge-m3 call — best-effort: any failure (cache absent, backend
# unreachable) degrades to keyword-only with a one-line stderr note, never
# raises, never blocks the keyword path (Global Constraints).
# Post-review fix (F01, 2026-07-25): the original absolute score/max_score
# ratio gate misclassified legitimate literal top-1 hits as "weak" — this
# repo's OWN golden fixtures have literal min_score_ratio well below any
# sane absolute threshold (S1=0.30, S2=0.25, S4=0.55), because a partial
# multi-term title/tag/body match is a perfectly confident top-1, not a weak
# one; the ratio depends on term count and per-field weighting, not on
# actual retrieval confidence. Replaced with a margin gate: fire the
# backstop on zero hits OR when the keyword top-1 has no clear lead over
# the runner-up (ambiguous ranking) — never on an absolute ratio.
SEMANTIC_MARGIN_RATIO = 0.5  # top-1 must lead the runner-up by at least this
                              # fraction of its own score to count as
                              # "confident" (top1 >= (1+ratio) * top2)
SEMANTIC_NOISE_RATIO = 0.25   # P12 re-measure finding: below this
                              # score/max_score the keyword top-1 is noise
                              # (stray body-word matches), regardless of its
                              # margin over the runner-up — the backstop must
                              # fire or paraphrase queries never get rescued
                              # against a real catalogue (8c EARS, S3).
                              # Strictly below every legitimate literal
                              # golden ratio (S2 floor is 0.25, S1 0.30).
SEMANTIC_MODEL = "bge-m3"
OLLAMA_EMBED_URL = "http://localhost:11434/api/embed"
OLLAMA_EMBED_TIMEOUT = 5


def _tagvec_db_path(root):
    return os.path.join(root, ".tagvec", "tag_vectors.sqlite")


def _load_concept_vectors(db_path, model):
    """[(path, [float, ...]), ...] for every concept_emb row of `model`, or
    None if the cache file/table is absent or has no rows for this model
    (the graceful-skip signal semantic_backstop() acts on)."""
    if not os.path.isfile(db_path):
        return None
    try:
        conn = sqlite3.connect(db_path)
        try:
            rows = conn.execute(
                "SELECT path, dim, vec FROM concept_emb WHERE model = ?", (model,)
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.DatabaseError:
        return None
    if not rows:
        return None
    return [(path, list(struct.unpack("<{}f".format(dim), vec_blob)))
            for path, dim, vec_blob in rows]


def _embed_query_bge_m3(text):
    """Best-effort LOCAL Ollama embed call for the query string. NETWORK —
    reached only when the semantic pass actually fires (never at import
    time, never unconditionally). Any failure propagates so the caller
    degrades gracefully; this function never catches."""
    req = urllib.request.Request(
        OLLAMA_EMBED_URL,
        data=json.dumps({"model": SEMANTIC_MODEL, "input": text}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=OLLAMA_EMBED_TIMEOUT) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return body["embeddings"][0]


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _keyword_top1_is_confident(hits):
    """Post-review (F01) margin gate — replaces the old absolute-ratio
    check. True when the keyword top-1 clearly leads the runner-up (no
    ambiguity to resolve semantically); False when there's no runner-up to
    compare (a single hit is trusted as-is) is NOT covered here — callers
    treat `len(hits) <= 1` as its own case. Only meaningful for
    `len(hits) >= 2`."""
    top1, top2 = hits[0]["score"], hits[1]["score"]
    if top1 <= 0:
        return False
    margin = (top1 - top2) / top1
    return margin >= SEMANTIC_MARGIN_RATIO


def semantic_backstop(root, query, exclude_paths, limit):
    """[(cosine, path), ...] sorted descending, excluding exclude_paths, or
    [] with one stderr note on any degradation (cache/table absent, backend
    unreachable) — see module docstring above."""
    vectors = _load_concept_vectors(_tagvec_db_path(root), SEMANTIC_MODEL)
    if vectors is None:
        print("note: semantic backstop skipped (.tagvec cache/concept "
              "embeddings absent) — keyword-only results", file=sys.stderr)
        return []
    try:
        qvec = _embed_query_bge_m3(query)
    except Exception as exc:
        print("note: semantic backstop skipped (embedding backend "
              "unavailable: {}) — keyword-only results".format(exc),
              file=sys.stderr)
        return []
    ranked = sorted(
        ((_cosine(qvec, vec), path) for path, vec in vectors if path not in exclude_paths),
        key=lambda x: -x[0],
    )
    return ranked[:limit]


def _semantic_hit_dicts(root, query, exclude_paths, limit, max_score):
    """semantic_backstop() results, re-hydrated with title/type/description/
    snippet (read from the concept's own file) into the same hit-dict shape
    cmd_find's keyword loop produces, so both can be printed uniformly."""
    terms = tokenize(query)
    out = []
    for cosine, path in semantic_backstop(root, query, exclude_paths, limit):
        ap = os.path.join(root, path + ".md")
        if not os.path.isfile(ap):
            continue
        fm, body = split_frontmatter(read_file(ap))
        title = fm.get("title", path.rsplit("/", 1)[-1])
        typ = fm.get("type", "")
        desc = _dequote(fm.get("description", ""))
        snip = make_snippet(body, terms)
        out.append({
            "score": round(cosine * max_score), "path": path, "title": title,
            "type": typ, "desc": desc, "snip": snip, "provenance": "semantic",
            "cosine": cosine,
        })
    return out


def cmd_find(root, args):
    terms = tokenize(args.query)
    if not terms:
        print("(empty query)")
        return
    breakdown = getattr(args, "breakdown", False)
    type_filter = getattr(args, "type", None)
    tag_filter = getattr(args, "tag", None)
    # 8a (FIL03/FIL04): --scope and --bundle both narrow via resolve_scopes;
    # --scope wins if both are given. Without either, behavior is unchanged
    # (resolve_scopes(root, None) == list_bundles(root) iteration, as before).
    target = getattr(args, "scope", None) or getattr(args, "bundle", None)
    hits = []
    for b, bp in resolve_scopes(root, target):
        for cid, ap in iter_concepts(bp):
            text = read_file(ap)
            fm, body = split_frontmatter(text)
            t = fm.get("type", "")
            if type_filter and t != type_filter:
                continue
            if tag_filter and tag_filter not in extract_tags(text):
                continue
            title = fm.get("title", cid)
            tags = fm.get("tags", "")
            hay_title = title.lower()
            hay_tags = tags.lower()
            hay_body = body.lower()
            score = 0
            # 8b (SCO03): contrib records which field(s) each term hit, for
            # --breakdown; the score arithmetic itself is unchanged.
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
                snip = make_snippet(body, terms)
                desc = _dequote(fm.get("description", ""))
                hits.append({
                    "score": score, "path": "{}/{}".format(b, cid), "title": title,
                    "type": t, "desc": desc, "snip": snip, "contrib": contrib,
                })
    hits.sort(key=lambda h: -h["score"])
    max_score = 6 * len(terms)

    # 8c: semantic backstop gate (post-review F01) — fire on zero keyword
    # hits, or when there IS a keyword ranking but it's ambiguous (top-1 has
    # no clear margin over the runner-up). A single keyword hit has no
    # runner-up to be ambiguous against, so it is trusted as-is (no fire) —
    # this also means the backstop only ever spends a network call when it
    # can plausibly add value, not on every merely-partial literal match.
    # P12 re-measure finding (8c EARS, S3 rescue): a real catalogue almost
    # never yields ZERO hits for a paraphrase query — it yields NOISE (stray
    # body-word matches, e.g. 3/24), which can carry a deceptively clear
    # margin over an even weaker runner-up. An absolute noise floor
    # (SEMANTIC_NOISE_RATIO) therefore fires the backstop regardless of
    # margin or hit count; the rank-1 pin below keeps the keyword top-1 in
    # place either way.
    semantic_hits = []
    fire_backstop = (
        not hits
        or hits[0]["score"] < SEMANTIC_NOISE_RATIO * max_score
        or (len(hits) >= 2 and not _keyword_top1_is_confident(hits))
    )
    if fire_backstop:
        exclude = {h["path"] for h in hits}
        semantic_hits = _semantic_hit_dicts(root, args.query, exclude, args.limit, max_score)

    # Fuse: the keyword top-1 (if any) is PINNED at rank 1 — this is an
    # absolute invariant, independent of the gate above, so "never replacing
    # a strong keyword top-hit" (EARS) holds even if the gate is ever mistuned
    # or a semantic candidate's converted score would otherwise outrank it
    # (post-review F01 repro: an unrelated concept at cosine ~0.7 converts to
    # a HIGHER raw score than a legitimate partial-match literal top-1).
    # Everything else — the remaining keyword hits plus all semantic hits —
    # is interleaved by score from rank 2 down (both scales are comparable,
    # 0..max_score; stable sort keeps keyword-before-semantic on exact ties,
    # per PLAN's "appended/interleaved" fusion rule).
    if hits:
        pinned_top1 = hits[0]
        rest = hits[1:] + semantic_hits
        rest.sort(key=lambda h: -h["score"])
        all_hits = [pinned_top1] + rest
    else:
        all_hits = semantic_hits

    if not all_hits:
        print("(no matches for: {})".format(args.query))
        return
    for h in all_hits[: args.limit]:
        print("------")
        print("score: {}/{}".format(h["score"], max_score))
        print("title: {}".format(h["title"]))
        print("type: {}".format(h["type"]))
        print("path: {}".format(h["path"]))
        print("description: {}".format(h["desc"]))
        print("body-snippet: {}".format(h["snip"]))
        if h.get("provenance") == "semantic":
            print("provenance: semantic (cosine={:.2f})".format(h["cosine"]))
        if breakdown:
            if h.get("provenance") == "semantic":
                print("contrib: semantic-only (cosine={:.2f}, no keyword field match)".format(h["cosine"]))
            else:
                print("contrib: {}".format(_format_contrib(h["contrib"])))
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
    ref = path[:-3] if path.endswith(".md") else path
    ap = os.path.join(root, ref + ".md")
    if not os.path.isfile(ap):
        print("not found: {}".format(path), file=sys.stderr)
        sys.exit(1)
    return ap


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
    for dirpath, dirnames, filenames in os.walk(scan_root):
        _prune_walk_dirs(dirnames)
        for fn in filenames:
            if not fn.endswith(".md"):
                continue
            ap = os.path.join(dirpath, fn)
            body = re.sub(r"```.*?```", "", read_file(ap), flags=re.S)
            for m in link_re.finditer(body):
                raw = m.group(1)
                tgt = raw.split("#", 1)[0].split("?", 1)[0].strip()
                if not tgt or re.match(r"^[a-z][a-z0-9+.-]*://", tgt) or tgt.startswith("mailto:"):
                    continue
                if tgt.startswith("/"):
                    # OKF (catalogue-root convention): leading / = scan_root
                    # (= catalogue root = Obsidian vault root), NOT the bundle.
                    resolved = os.path.abspath(os.path.join(scan_root, tgt.lstrip("/")))
                else:
                    resolved = os.path.abspath(os.path.join(dirpath, tgt))
                if resolved == target_abspath:
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
        data = tomllib.load(f)
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
    left byte-identical (idempotent). Skips http(s)/mailto/anchor-only. Returns
    (new_body, changed_count, unresolved_targets)."""
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

    new_body = CROSSLINK_RE.sub(repl, body)
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


def resolve_scopes(root, target):
    """[(bundle, bundle_path), ...] for `target` (<bundle> or <bundle>/<subdir>),
    or every bundle in the catalogue when target is None."""
    if target:
        tp = os.path.join(root, target.rstrip("/"))
        return [(target.split("/")[0], tp)]
    return [(b, os.path.join(root, b)) for b in list_bundles(root)]


def run_checks(root, target, types_source=None):
    """Run the full pluggable conformance scan over `target` (bundle or
    bundle/subdir), or the whole catalogue when target is None.

    types_source overrides <root>/TYPES.md; absent, falls back to the
    .okf.toml `types_source` config key, then to <root>/TYPES.md.

    Returns (errors, warnings), each a list of (check_name, rel_path, message).
    """
    scopes = resolve_scopes(root, target)
    if types_source is None:
        types_source = load_okf_config(root).get("types_source")
    types_set = load_types(root, types_source)
    tags_set = load_tags(root)
    per_file_checks = [
        ("frontmatter-parseable", "error", check_fm_parseable),
        ("type-nonempty", "error", check_type_nonempty),
        ("reserved-no-type", "error", check_reserved_no_type),
        ("filename-chars", "error", check_filename_chars),
        ("type-registered", "warning", lambda c: check_type_registered(c, types_set)),
        ("tag-registered", "warning", lambda c: check_tag_registered(c, tags_set)),
        ("english-keys", "warning", check_english_keys),
        ("crosslink-format", "warning", check_crosslink_format),
        ("tags-block-form", "warning", check_tags_block_form),
        ("xml-like-tags", "warning", check_xml_like_tags),
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


def plan_rename(root, old_abs, new_abs):
    """Compute the reference rewrites a move old->new requires, WITHOUT touching
    disk (so it also drives the dry-run preview). Returns:
      inbound  = [(source_rel, old_raw, new_raw), ...]  links pointing AT the file
      outbound = [(old_raw, new_raw), ...]              the moved file's own links
                 (only when the bundle changes; within a bundle they stay valid)
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
        body = re.sub(r"```.*?```", "", read_file(src), flags=re.S)
        for m in CROSSLINK_RE.finditer(body):
            raw = m.group(2)
            tgt = resolve_link_target(root, old_abs, raw)
            if tgt is None or not os.path.isfile(tgt):
                continue
            _, suffix = _split_link_suffix(raw)
            new_raw = link_expr(root, new_abs, tgt) + suffix
            if new_raw != raw:
                outbound.append((raw, new_raw))
        outbound = _dedupe(outbound)
    bundles = sorted({bundle_of(root, old_abs), bundle_of(root, new_abs)})
    return {"inbound": inbound, "outbound": outbound, "bundles": bundles}


def _apply_link_rewrites(abspath, rewrites):
    """Replace each `](old_raw)` occurrence with `](new_raw)` in one file. The
    `](...)` wrapper anchors the match to real link targets, never label text."""
    text = read_file(abspath)
    for old_raw, new_raw in rewrites:
        text = text.replace("]({})".format(old_raw), "]({})".format(new_raw))
    write_file(abspath, text)


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
    """History-preserving, staged move. Falls back to a plain fs rename when the
    file is untracked or git is unavailable. Returns True if git handled it."""
    try:
        proc = subprocess.run(["git", "-C", root, "mv", "-f", old_abs, new_abs],
                              capture_output=True, text=True)
        if proc.returncode == 0:
            return True
    except OSError:
        pass
    os.rename(old_abs, new_abs)
    return False


def cmd_rename(root, args):
    old_abs = os.path.abspath(args.old if os.path.isabs(args.old) else os.path.join(root, args.old))
    new_abs = os.path.abspath(args.new if os.path.isabs(args.new) else os.path.join(root, args.new))

    def die(msg):
        sys.stderr.write("rename: {}\n".format(msg))
        sys.exit(2)

    if not old_abs.endswith(".md") or not new_abs.endswith(".md"):
        die("both paths must be .md concept files")
    if not os.path.isfile(old_abs):
        die("source not found: {}".format(args.old))
    if os.path.basename(old_abs).lower() in RESERVED:
        die("refusing to move a reserved file ({})".format(os.path.basename(old_abs)))
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
    if os.path.exists(new_abs) and args.apply and not args.force:
        die("destination exists (use --force to overwrite): {}".format(args.new))

    plan = plan_rename(root, old_abs, new_abs)
    old_rel = os.path.relpath(old_abs, root).replace(os.sep, "/")
    new_rel = os.path.relpath(new_abs, root).replace(os.sep, "/")

    if not args.apply:
        print("would move   {}  ->  {}".format(old_rel, new_rel))
        for src, oraw, nraw in plan["inbound"]:
            print("  inbound    {}   {}  ->  {}".format(src, oraw, nraw))
        for oraw, nraw in plan["outbound"]:
            print("  outbound   {}  ->  {}".format(oraw, nraw))
        print("  reindex    {}".format(", ".join(plan["bundles"])))
        print("rename (dry-run): {} inbound, {} outbound link(s), {} bundle(s). "
              "Re-run with --apply.".format(
                  len(plan["inbound"]), len(plan["outbound"]), len(plan["bundles"])))
        return

    os.makedirs(os.path.dirname(new_abs), exist_ok=True)
    moved = _git_mv(root, old_abs, new_abs)
    if plan["outbound"]:
        _apply_link_rewrites(new_abs, plan["outbound"])
    by_src = {}
    for src, oraw, nraw in plan["inbound"]:
        by_src.setdefault(src, []).append((oraw, nraw))
    for src, rw in by_src.items():
        _apply_link_rewrites(os.path.join(root, src), _dedupe(rw))
    reidx = []
    for b in plan["bundles"]:
        reidx += reindex_tree(root, os.path.join(root, b))
    print("moved ({})  {}  ->  {}".format("git mv" if moved else "fs", old_rel, new_rel))
    print("rewrote {} inbound link(s) in {} file(s), {} outbound link(s)".format(
        len(plan["inbound"]), len(by_src), len(plan["outbound"])))
    print("reindexed {} index file(s) across: {}".format(len(reidx), ", ".join(plan["bundles"])))
    print("staged for commit — run `okf-cli.py check` before committing.")


def main():
    ap = argparse.ArgumentParser(prog="okf-cli.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", help="catalogue root (default: auto-detect from cwd; "
                    "hard-fails if none found)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pi = sub.add_parser("index")
    pi.add_argument("bundle", nargs="?")
    pi.add_argument("--full", action="store_true",
                    help="add per-bundle types+tags used (catalogue TOC), or print the "
                         "structured bundle summary instead of the raw index.md (with a bundle arg)")
    pi.add_argument("--json", action="store_true", help="machine-readable output")
    pls = sub.add_parser("list", help="list concepts filtered by frontmatter type and/or tag")
    pls.add_argument("--type", help="filter by frontmatter `type` (exact match)")
    pls.add_argument("--tag", help="filter by tag (exact match)")
    pls.add_argument("--scope", metavar="TARGET",
                     help="<bundle> or <bundle>/<subdir> to limit (default: whole catalogue)")
    pls.add_argument("--json", action="store_true", help="machine-readable output")
    pf = sub.add_parser("find")
    pf.add_argument("query")
    pf.add_argument("--limit", type=int, default=10)
    pf.add_argument("--type", help="filter by frontmatter `type` (exact match)")
    pf.add_argument("--tag", help="filter by tag (exact match)")
    pf.add_argument("--scope", metavar="TARGET",
                    help="<bundle> or <bundle>/<subdir> to limit (default: whole catalogue)")
    pf.add_argument("--bundle", metavar="BUNDLE",
                    help="alias for --scope (bundle-only); --scope wins if both are given")
    pf.add_argument("--breakdown", action="store_true",
                    help="print per-hit contributing field(s)/term(s); "
                         "output is byte-identical to today without this flag")
    pr = sub.add_parser("read")
    pr.add_argument("path")
    pp = sub.add_parser("prime", help="one-shot agent onboarding: CLAUDE.md guide + catalogue TOC")
    pp.add_argument("--full", action="store_true",
                     help="print full per-bundle blocks (description+directories+types+tags) "
                          "instead of the default compact name+count listing")
    sub.add_parser("info", help="print catalogue schema docs (TYPES.md + PROPERTIES.md)")
    pt = sub.add_parser("toc", help="print a concept's headings (default: h2 only)")
    pt.add_argument("path")
    pt.add_argument("--level", type=int, default=2,
                    help="heading level to list (default 2 = h2); 0 = full indented tree")
    pv = sub.add_parser("visualize", help="write a self-contained viz.html graph for a bundle")
    pv.add_argument("bundle")
    pv.add_argument("--out", help="output path (default: <bundle>/viz.html)")
    prf = sub.add_parser("refs", help="list inbound markdown references to a file")
    prf.add_argument("path", help="target file (abs, or relative to --root)")
    prf.add_argument("--scan-root", help="dir to scan (default: --root); pass repo root for repo-wide")
    prf.add_argument("--json", action="store_true")
    prw = sub.add_parser("rewrite-path", help="literal path-string rewrite across text files")
    prw.add_argument("old")
    prw.add_argument("new")
    prw.add_argument("--scan-root", help="dir to scan (default: --root)")
    prw.add_argument("--check", action="store_true", help="dry-run: report, write nothing")
    prn = sub.add_parser("rename",
                         help="move a concept + rewrite every inbound/outbound link + reindex (dry-run default)")
    prn.add_argument("old", help="source concept path (<bundle>/<concept>.md, abs or --root-relative)")
    prn.add_argument("new", help="destination path (same or different bundle)")
    prn.add_argument("--apply", action="store_true", help="perform the move (default: dry-run preview only)")
    prn.add_argument("--force", action="store_true", help="overwrite an existing destination")
    px = sub.add_parser("reindex", help="(re)generate marker-bounded index.md listings")
    px.add_argument("target", help="<bundle> or <bundle>/<subdir>")
    px.add_argument("--init", action="store_true",
                    help="recursively migrate marker-less flat index.md in the subtree to "
                         "managed marker blocks (bespoke multi-section indexes are skipped + flagged)")
    px.add_argument("--check", action="store_true",
                    help="dry-run: with --init preview conversions; else report stale + uncovered. No writes")
    px.add_argument("--force", action="store_true",
                    help="with --init, also flatten a pure multi-section listing (prose/tables still refuse)")
    pl = sub.add_parser("log", help="render git history for the catalogue or a bundle as a SPEC §7 changelog")
    pl.add_argument("bundle", nargs="?", help="bundle to scope to (default: whole catalogue)")
    pl.add_argument("--since", help="git --since filter, e.g. '3 months ago'")
    pl.add_argument("--write", action="store_true", help="materialize into <scope>/log.md instead of stdout")
    pg = sub.add_parser("tags", help="list all tags with usage counts, or fuzzy-search candidate tags")
    pg.add_argument("query", nargs="*",
                    help="candidate tag(s) to fuzzy-search against the tag universe; omit for full audit dump")
    pg.add_argument("--limit", type=int, default=8, help="max matches per candidate (default 8)")
    pg.add_argument("--singletons", action="store_true",
                    help="full-dump mode only: show tags used exactly once")
    pg.add_argument("--register", nargs="+", metavar="TAG",
                    help="add tag(s) to the TAGS.md registry (closed-vocabulary allow-list)")
    pg.add_argument("--validate", nargs="+", metavar="TAG",
                    help="check tag(s) against TAGS.md; exit 1 if any are unregistered")
    pmt = sub.add_parser("merge-tags",
                         help="merge/rename one or more tags into a target tag across concept frontmatter")
    pmt.add_argument("tags", nargs="+", help="source tag(s) to merge, e.g. workflow workflows")
    pmt.add_argument("--into", required=True, metavar="TAG", help="destination tag name")
    pmt.add_argument("--scope", metavar="TARGET",
                     help="<bundle> or <bundle>/<subdir> to limit the rewrite (default: whole catalogue)")
    pmt.add_argument("--apply", action="store_true", help="write changes (default: dry-run preview only)")
    prt = sub.add_parser("remove-tags",
                         help="remove one or more tags from concept frontmatter (no merge target)")
    prt.add_argument("tags", nargs="+", help="tag(s) to remove, e.g. stale draft")
    prt.add_argument("--scope", metavar="TARGET",
                     help="<bundle> or <bundle>/<subdir> to limit the rewrite (default: whole catalogue)")
    prt.add_argument("--apply", action="store_true", help="write changes (default: dry-run preview only)")
    pnt = sub.add_parser("normalize-tags",
                         help="convert inline `tags: [...]` fields to YAML block-list form (local convention)")
    pnt.add_argument("--scope", metavar="TARGET",
                     help="<bundle> or <bundle>/<subdir> to limit the rewrite (default: whole catalogue)")
    pnt.add_argument("--apply", action="store_true", help="write changes (default: dry-run preview only)")
    pc = sub.add_parser("check", help="conformance scan: §9 hard rules + local invariants")
    pc.add_argument("target", nargs="?", help="<bundle> or <bundle>/<subdir> (default: whole catalogue)")
    pc.add_argument("--strict", action="store_true", help="promote warnings to errors")
    pc.add_argument("--json", action="store_true", help="machine-readable output")
    pc.add_argument("--types", help="explicit TYPES.md path (overrides .okf.toml types_source)")
    pfx = sub.add_parser("fix-crosslinks",
                         help="rewrite links to catalogue-root-absolute form (/bundle/subdir/concept.md)")
    pfx.add_argument("target", nargs="?", help="<bundle> or <bundle>/<subdir> (default: whole catalogue)")
    pfx.add_argument("--check", action="store_true", help="dry-run: report without writing")
    pfxt = sub.add_parser("fix-xml-tags",
                          help="wrap `<tag>`/`<tag>.<tag2>` placeholders in inline code")
    pfxt.add_argument("target", nargs="?", help="<bundle> or <bundle>/<subdir> (default: whole catalogue)")
    pfxt.add_argument("--check", action="store_true", help="dry-run: report without writing")
    args = ap.parse_args()
    root = catalogue_root(args.root)
    if root is None:
        sys.exit("ERROR: no catalogue found in cwd or its ancestors; pass --root <path>")
    if not os.path.isdir(root):
        sys.exit("ERROR: root not found: {} (pass --root <path>)".format(root))
    {"prime": cmd_prime, "index": cmd_index, "find": cmd_find, "list": cmd_list,
     "read": cmd_read, "info": cmd_info, "toc": cmd_toc, "visualize": cmd_visualize,
     "refs": cmd_refs,
     "rewrite-path": cmd_rewrite_path, "rename": cmd_rename,
     "reindex": cmd_reindex, "log": cmd_log, "tags": cmd_tags, "merge-tags": cmd_merge_tags,
     "remove-tags": cmd_remove_tags,
     "normalize-tags": cmd_normalize_tags,
     "check": cmd_check, "fix-crosslinks": cmd_fix_crosslinks,
     "fix-xml-tags": cmd_fix_xml_tags}[args.cmd](root, args)


if __name__ == "__main__":
    main()
