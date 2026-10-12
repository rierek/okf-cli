"""Index commands: `index` (catalogue TOC, or one bundle's index.md) with the
bundle summary renderers prime shares, and `reindex` (marker-bounded index.md
and index-map.md generation, the --init migration and the --check report)."""

import os
import re
import sys

from okf import spec
from okf.diffs import unified_diffs, write_plan
from okf.errors import OkfError
from okf.catalogue import (
    EXEMPT, MARK_END, MARK_START, REAL_FS, _collapse, _find_reserved_name, fm_text, index_h1_and_desc,
    iter_headings, iter_concepts, list_bundles, list_dir_concepts, managed_block_for, meta_and_fm, meta_of, read_file,
    read_file_verbatim, read_frontmatter, replace_managed_block, require_bundle_dir, tags_of,
)
from okf.output import _add_output
from okf.parser_support import _complete_bundles, _complete_scopes, _sub


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
        data = read_frontmatter(read_file(ap)).data
        t = fm_text(data, "type")
        if t:
            types.add(t)
        tags.update(tags_of(data))
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
    """[{id, title, type, description, tier, stale}, ...] for every concept under `bp`,
    sorted by concept id (F02 dedup, prelude 2026-07-25 on okf-cli-83vq)."""
    now = spec.utcnow()
    concepts = []
    for cid, ap in sorted(iter_concepts(bp)):
        (t, title, desc), fm = meta_and_fm(ap)
        concepts.append({"id": cid, "title": title, "type": t, "description": desc,
                         **spec.trust_fields(fm, now)})
    return concepts


def cmd_index(root, args):
    if args.bundle:
        require_bundle_dir(root, args.bundle)
    if getattr(args, "json", False):
        if args.bundle:
            bp = os.path.join(root, args.bundle)
            return {"bundle": args.bundle, "concepts": _concepts_json(bp)}
        return {"bundles": [_bundle_summary_json(root, b, full=args.full)
                            for b in list_bundles(root)]}
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
    h2_idxs = [line for level, _text, line in iter_headings(text) if level == 2]
    if len(h2_idxs) == 0:
        return text, "skip-no-list"
    multi = len(h2_idxs) >= 2
    if multi and not force:
        return text, "skip-multi-section"
    h2 = h2_idxs[0]
    saw_bullet = saw_prose = False
    for i, ln in enumerate(lines[h2 + 1:], h2 + 1):
        s = ln.strip()
        if not s or i in h2_idxs:            # blank / sub-section heading: allowed
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


def index_stub(dirpath):
    """Text of the index.md `reindex --init` creates in dirpath when it has none: a title and an
    empty marker block. An existing marker-less index.md is never touched here — its hand-curated
    content is migrated by convert_flat_index (via init_indexes), never by a naive append."""
    title = os.path.basename(os.path.abspath(dirpath))
    return "# {}\n\n## Contents\n\n{}\n{}\n".format(title, MARK_START, MARK_END)


def init_indexes(root, target, force=False):
    """Walk the target subtree and migrate each marker-less flat index.md. Writes nothing.

    Returns (results, plan): results = sorted (relpath-from-root, status) from convert_flat_index
    (status "unreadable" for a file that is not valid UTF-8), plan = [(rel, stored_text,
    converted_text), ...] for the converted files. With force=True, pure multi-section listings
    are flattened too (prose/tables still refuse).
    """
    results, plan = [], []
    for dp, dn, fn in os.walk(target):
        dn[:] = [d for d in dn if not d.startswith(".") and d != "assets"]
        idx_name = _find_reserved_name(fn)
        if not idx_name:
            continue
        idx = os.path.join(dp, idx_name)
        rel = os.path.relpath(idx, root).replace(os.sep, "/")
        text = read_file_verbatim(idx)
        if text is None:
            results.append((rel, "unreadable"))
            continue
        new, status = convert_flat_index(text, force=force)
        if status == "converted":
            plan.append((rel, text, new))
        results.append((rel, status))
    results.sort()
    return results, plan


def plan_reindex(root, tp, init=False, force=False, fs=REAL_FS):
    """The final text of every index file the `reindex` write run changes or creates: with `init`
    the stub of a missing index.md in tp, then the flat-index conversions, then the refreshed
    managed blocks, one (rel, stored_text, new_text) entry per file (stored_text None for a
    created file). Writes nothing. Returns (plan, info); info holds `init` = (results from
    init_indexes, or None), `stale` = rels whose managed block is out of date, `skipped` = rels
    without markers, `unreadable` = rels that are not valid UTF-8."""
    stored, final = {}, {}
    info = {"init": None, "stale": [], "skipped": [], "unreadable": []}
    created = None
    if init:
        idx = os.path.join(tp, "index.md")
        if not os.path.isfile(idx):
            created = os.path.relpath(idx, root).replace(os.sep, "/")
            stored[created], final[created] = None, index_stub(tp)
        results, conv = init_indexes(root, tp, force=force)
        info["init"] = results
        for rel, old, new in conv:
            stored[rel], final[rel] = old, new
    dirs = []
    for dp, dn, fn in fs.walk(tp):
        dn[:] = [d for d in dn if not d.startswith(".") and d != "assets"]
        if created and dp == tp and "index.md" not in fn:
            fn = fn + ["index.md"]                    # the write run walks the file it created
        for name in ("index.md", "index-map.md"):
            idx_name = _find_reserved_name(fn, name)
            if idx_name:
                dirs.append((dp, idx_name))
    for dp, idx_name in sorted(dirs):
        idx = os.path.join(dp, idx_name)
        rel = os.path.relpath(idx, root).replace(os.sep, "/")
        if rel in final:
            text = final[rel]
        else:
            text = fs.read_verbatim(idx)
            if text is None:
                info["unreadable"].append(rel)
                continue
        if MARK_START not in text:
            info["skipped"].append(rel)
            continue
        new_text, _ = replace_managed_block(text, managed_block_for(dp, root, idx_name, fs))
        if new_text == text:
            continue
        info["stale"].append(rel)
        stored.setdefault(rel, text)
        final[rel] = new_text
    return [(rel, stored[rel], final[rel]) for rel in final], info


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
        raise OkfError("not_found", "not a directory: {}".format(target))
    as_json = getattr(args, "json", False)
    plan, info = plan_reindex(root, tp, init=args.init, force=getattr(args, "force", False))
    files = unified_diffs(plan)
    if not args.check:
        write_plan(root, plan)
    stale, skipped = info["stale"], info["skipped"]
    changed = [] if args.check else stale
    result = {"applied": not args.check, "init": None, "updated": changed, "skipped": skipped,
              "stale": stale if args.check and not args.init else [], "uncovered": [],
              "unreadable": info["unreadable"], "files": files}
    conv = info["init"]
    if args.init:
        verb = "would convert" if args.check else "converted"
        n_conv = sum(1 for _, s in conv if s == "converted")
        n_skip = sum(1 for _, s in conv if s not in ("converted", "already-managed"))
        result["init"] = {
            "converted": [rel for rel, status in conv if status == "converted"],
            "skipped": [{"path": rel, "reason": status} for rel, status in conv
                        if status not in ("converted", "already-managed")]}
    if not as_json:
        for entry in files:
            print(entry["diff"], end="")
        for rel in info["unreadable"]:
            print("skipped (not valid UTF-8)  {}".format(rel))
        if args.init:
            for rel, status in conv:
                if status == "converted":
                    print("{:<14} {}".format(verb, rel))
                elif status != "already-managed":
                    print("{:<14} {}  ({})".format("skipped", rel, status))
            print("init: {} {}, {} skipped".format(n_conv, verb, n_skip))
    if args.check:
        if args.init:
            return result                       # --init --check = final-text preview of the write run
        un = uncovered_index_dirs(root, tp)
        result["uncovered"] = un
        if not as_json:
            for p in stale:
                print("STALE        {}".format(p))
            for p in un:
                print("UNCOVERED    {}".format(p))
            print("reindex --check: {} stale, {} uncovered, {} without markers".format(
                len(stale), len(un), len(skipped)))
        if stale or un:
            raise OkfError("drift", "", result)
    if as_json:
        return result
    for p in changed:
        print("updated       {}".format(p))
    for p in skipped:
        print("skipped (no markers)  {}".format(p))
    print("reindex: {} updated, {} skipped".format(len(changed), len(skipped)))


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
    _add_output(pi)


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
    _add_output(px)


COMMANDS = {
    "index": (cmd_index, add_index_parser),
    "reindex": (cmd_reindex, add_reindex_parser),
}
