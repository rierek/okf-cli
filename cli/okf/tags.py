"""Tag verbs: `tags` (usage listing, fuzzy search, registry validation and
registration with the best-effort bge-m3 embedding of new tags) and the
frontmatter rewriters merge-tags, remove-tags and normalize-tags."""

import difflib
import os
import re
import subprocess
import sys

from okf import catalogue
from okf.catalogue import (
    FM_DELIM, TAG_DESC_MAX, all_tags, extract_tags, iter_concepts, load_tags, parse_tag_list,
    read_file, register_tags, resolve_scopes, write_file,
)
from okf.parser_support import _complete_scopes, _complete_tags, _sub


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


def add_remove_tags_parser(sub):
    prt = _sub(sub, "remove-tags", "tags",
               "remove one or more tags from concept frontmatter (no merge target)")
    prt.add_argument("tags", nargs="+", help="tag(s) to remove, e.g. stale draft").completer = _complete_tags
    prt.add_argument("--scope", metavar="TARGET",
                     help="<bundle> or <bundle>/<subdir> to limit the rewrite (default: whole catalogue)").completer = _complete_scopes
    prt.add_argument("--apply", action="store_true", help="write changes (default: dry-run preview only)")


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


COMMANDS = {
    "merge-tags": (cmd_merge_tags, add_merge_tags_parser),
    "normalize-tags": (cmd_normalize_tags, add_normalize_tags_parser),
    "remove-tags": (cmd_remove_tags, add_remove_tags_parser),
    "tags": (cmd_tags, add_tags_parser),
}
