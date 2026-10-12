"""Tag verbs: `tags` (usage listing, fuzzy search, registry validation and
registration with the best-effort bge-m3 embedding of new tags) and the
frontmatter rewriters merge-tags, remove-tags and normalize-tags."""

import difflib
import os
import subprocess
import sys
from okf.errors import OkfError
from okf.output import _add_output

from okf import catalogue
from okf.catalogue import (
    TAG_DESC_MAX, all_tags, flow_tags, iter_concepts, load_tags, read_file, read_file_verbatim, read_frontmatter,
    register_tags, render_frontmatter, resolve_scopes, scalar_text, tags_of, write_file_verbatim,
)
from okf.diffs import unified_diffs
from okf.find_filters import compile_where
from okf.parser_support import _add_filters, _complete_tags, _sub


_NOT_A_LIST = "tags field not in inline/block form"


def _selected_concepts(root, filters):
    """(path, relative path, Frontmatter, stored text) of every concept the --where expression selects; without an
    expression every concept is selected. prune_staging=False (OKFT-oe8t Review D02): the write verbs
    must reach staging content too, or a tag change silently leaves the old tag behind there."""
    for _bundle, bp in resolve_scopes(root, None, filters.include_archive):
        for _cid, ap in iter_concepts(bp, prune_staging=False):
            fm = read_frontmatter(read_file(ap))
            stored = read_file_verbatim(ap)  # None: not valid UTF-8, a rewrite would corrupt it
            rel = os.path.relpath(ap, root).replace(os.sep, "/")
            if filters and not filters.matches_loaded(rel[:-3] if rel.endswith(".md") else rel, fm.data):
                continue
            yield ap, rel, fm, stored


def _unparseable_reason(fm, stored):
    """Why a write verb leaves the file alone when its frontmatter does not parse or the file is not
    valid UTF-8, else None."""
    if stored is None:
        return "file is not valid UTF-8"
    if fm.head and fm.data is None:
        return "frontmatter does not parse: {}".format(fm.error)


def _retag(data, rename):
    """Apply `rename` (tag -> new tag, or None to drop it) to the tag list of `data` in place, one item
    at a time, so the comment and quoting of every other item stay. Returns whether the list changed,
    or None when `tags` is not a YAML list."""
    tags = data.get("tags")
    if not isinstance(tags, list):
        return None
    edits = []
    for i, item in enumerate(tags):
        old = scalar_text(item)
        new = rename(old)
        if new != old:
            edits.append((i, new))
    for i, new in reversed(edits):
        if new is None:
            del tags[i]
        else:
            tags[i] = new
    return bool(edits)


def _write_result(root, args, plan, unparseable, result):
    """Render the plan of (rel path, stored text, new text) as unified diffs, write exactly the new
    texts on --apply, and return `result` with `files` (the diffs) or print the text report.
    Returns (result, verb, files)."""
    files = unified_diffs(plan)
    if args.apply:
        for rel, _old, new in plan:
            write_file_verbatim(os.path.join(root, rel), new)
    verb = "rewrote" if args.apply else "would rewrite"
    result["files"] = files
    if not getattr(args, "json", False):
        for entry in files:
            print(entry["diff"], end="")
        for rel, reason in unparseable.items():
            print("unparseable    {}  ({} — skipped)".format(rel, reason))
    return result, verb, len(files)


def cmd_merge_tags(root, args):
    filters = compile_where(args.where)
    sources = set(args.tags)
    plan, unparseable = [], {}
    for ap, rel, fm, stored in _selected_concepts(root, filters):
        reason = _unparseable_reason(fm, stored)
        if reason:
            unparseable[rel] = reason
            continue
        if not any(t in sources for t in tags_of(fm.data)):
            continue
        seen = set()

        def merged(tag):
            new = args.into if tag in sources else tag
            if new in seen:
                return None
            seen.add(new)
            return new
        changed = _retag(fm.data, merged)
        if changed is None:
            unparseable[rel] = _NOT_A_LIST
        elif changed:
            plan.append((rel, stored, render_frontmatter(fm)))
    result, verb, n = _write_result(root, args, plan, unparseable, {
        "applied": bool(args.apply), "unparseable": list(unparseable),
        "from": sorted(sources), "into": args.into})
    if getattr(args, "json", False):
        return result
    print("merge-tags: {} file(s) {}, {} unparseable — {} -> {}".format(
        n, verb, len(unparseable), ", ".join(sorted(sources)), args.into))


def cmd_remove_tags(root, args):
    """Remove one or more tags from concept frontmatter (no merge target).
    Symmetric to merge-tags: dry-run default, --where-limited, --apply writes.
    Emptying the tag list strips the whole `tags:` field (no dangling key)."""
    filters = compile_where(args.where)
    targets = set(args.tags)
    plan, emptied, unparseable = [], [], {}
    for ap, rel, fm, stored in _selected_concepts(root, filters):
        reason = _unparseable_reason(fm, stored)
        if reason:
            unparseable[rel] = reason
            continue
        if not any(t in targets for t in tags_of(fm.data)):
            continue
        changed = _retag(fm.data, lambda tag: None if tag in targets else tag)
        if changed is None:
            unparseable[rel] = _NOT_A_LIST
            continue
        if not fm.data["tags"]:
            del fm.data["tags"]
            emptied.append(rel)
        plan.append((rel, stored, render_frontmatter(fm)))
    result, verb, n = _write_result(root, args, plan, unparseable, {
        "applied": bool(args.apply), "emptied": emptied,
        "unparseable": list(unparseable), "removed": sorted(targets)})
    if getattr(args, "json", False):
        return result
    print("remove-tags: {} file(s) {}, {} emptied, {} unparseable — removed {}".format(
        n, verb, len(emptied), len(unparseable), ", ".join(sorted(targets))))


def cmd_normalize_tags(root, args):
    """Turn every non-empty flow-style `tags: [a, b]` list into a block list. Local convention (this
    catalogue), not an OKF spec requirement: both forms stay valid OKF. A file whose frontmatter does
    not parse is never written."""
    filters = compile_where(args.where)
    plan, unparseable = [], {}
    for ap, rel, fm, stored in _selected_concepts(root, filters):
        reason = _unparseable_reason(fm, stored)
        if reason:
            unparseable[rel] = reason
            continue
        tags = flow_tags(fm.data)
        if tags is None:
            continue
        tags.fa.set_block_style()
        plan.append((rel, stored, render_frontmatter(fm)))
    result, verb, n = _write_result(root, args, plan, unparseable, {
        "applied": bool(args.apply), "unparseable": list(unparseable)})
    if getattr(args, "json", False):
        return result
    print("normalize-tags: {} file(s) {}, {} unparseable".format(n, verb, len(unparseable)))


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
    as_json = getattr(args, "json", False)
    if getattr(args, "register", None):
        try:
            added, already = register_tags(root, args.register)
        except ValueError as e:
            raise OkfError("invalid_input", "ERROR: {}".format(e))
        if added:
            if not as_json:
                print("registered {} new tag(s) in TAGS.md: {}".format(len(added), ", ".join(added)))
            auto_embed_new_tags(root, added)
        if already and not as_json:
            print("already registered: {}".format(", ".join(already)))
        return {"registered": added, "already_registered": already}
    if getattr(args, "validate", None):
        tags_set = load_tags(root)
        if tags_set is None:
            if not as_json:
                print("(no TAGS.md — closed vocabulary not enabled)")
            return {"closed_vocabulary": False, "unknown": []}
        unknown = [t for t in args.validate if t not in tags_set]
        if not as_json:
            for t in unknown:
                print("UNKNOWN  {}".format(t))
            print("OK — all {} known".format(len(args.validate)) if not unknown
                  else "{} UNKNOWN — register with: okf-cli.py tags --register <tag> \"<description, max {} chars>\"".format(
                      len(unknown), TAG_DESC_MAX))
        result = {"closed_vocabulary": True, "unknown": unknown}
        if unknown:
            raise OkfError("non_conformant", "", result)
        return result
    counts = all_tags(root)
    if not args.query:
        items = counts.items()
        if args.singletons:
            items = [(t, n) for t, n in items if n == 1]
        rows = sorted(items, key=lambda kv: (-kv[1], kv[0]))
        if as_json:
            return {"tags": [{"tag": t, "count": n} for t, n in rows]}
        if not counts:
            print("(no tags found)")
        elif not rows:
            print("(no singleton tags)")
        else:
            width = max(len(t) for t, _n in rows)
            for t, n in rows:
                print("  {:<{w}}  {}".format(t, n, w=width))
        return
    universe = sorted(counts.keys())
    searches = [{"query": q, "matches": [{"tag": m, "count": counts[m]}
                                         for m in fuzzy_matches(q, universe, limit=args.limit)]}
                for q in args.query]
    if as_json:
        return {"searches": searches}
    for search in searches:
        print(f"== searched: {search['query']} ==")
        if not search["matches"]:
            print("  (no match — new tag)")
        for m in search["matches"]:
            print("  - {}  ({})".format(m["tag"], m["count"]))
        print()


def add_merge_tags_parser(sub):
    pmt = _sub(sub, "merge-tags", "tags",
               "merge/rename one or more tags into a target tag across concept frontmatter")
    pmt.add_argument("tags", nargs="+", help="source tag(s) to merge, e.g. workflow workflows").completer = _complete_tags
    pmt.add_argument("--into", required=True, metavar="TAG", help="destination tag name").completer = _complete_tags
    _add_filters(pmt)
    pmt.add_argument("--apply", action="store_true", help="write changes (default: dry-run preview only)")
    _add_output(pmt)


def add_normalize_tags_parser(sub):
    pnt = _sub(sub, "normalize-tags", "tags",
               "convert inline `tags: [...]` fields to YAML block-list form (local convention)")
    _add_filters(pnt)
    pnt.add_argument("--apply", action="store_true", help="write changes (default: dry-run preview only)")
    _add_output(pnt)


def add_remove_tags_parser(sub):
    prt = _sub(sub, "remove-tags", "tags",
               "remove one or more tags from concept frontmatter (no merge target)")
    prt.add_argument("tags", nargs="+", help="tag(s) to remove, e.g. stale draft").completer = _complete_tags
    _add_filters(prt)
    prt.add_argument("--apply", action="store_true", help="write changes (default: dry-run preview only)")
    _add_output(prt)


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
    _add_output(pg)


COMMANDS = {
    "merge-tags": (cmd_merge_tags, add_merge_tags_parser),
    "normalize-tags": (cmd_normalize_tags, add_normalize_tags_parser),
    "remove-tags": (cmd_remove_tags, add_remove_tags_parser),
    "tags": (cmd_tags, add_tags_parser),
}
