"""Obsidian wikilinks: the `[[…]]` parser, the basename index and resolver, the
scan behind the `wikilinks` command, and the opt-in `kc/link/wikilink-resolvable` rule
that `check` runs."""

import os
import re
import unicodedata
from okf.errors import OkfError

from okf.catalogue import RESERVED, iter_all_md, list_bundles, read_file, resolve_scopes
from okf.linkscan import wikilink_regions, wikilink_scan_text
from okf.output import _add_output, _note
from okf.parser_support import _complete_scopes, _sub


# --- wikilinks -------------------------------------------------------------
# Obsidian's native link form. The markdown-link scanners (okf.linkscan, with
# CROSSLINK_RE in okf.catalogue) anchor on "](", so none of them can see a
# [[…]] — a rename that rewrote only the markdown links would report success and
# silently orphan every inbound wikilink. Everything below is the wikilink
# counterpart of that machinery for reading: parse, resolve, report. The rewrite
# half lives in okf.rename (plan_wikilink_rewrites, _apply_wikilink_rewrites).

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
    """The opt-in set for the `kc/link/wikilink-resolvable` check. Absent key or absent
    .okf.toml means the empty set: the rule ships silent and is switched on per
    bundle, so introducing it cannot bury a clean catalogue in warnings.

    A value the gate cannot honour is announced as a call note rather than silently
    disabling the rule — a config that reads as if it opted a bundle in, but
    does not, is worse than no config at all."""
    if "wikilink_checked_bundles" not in config:
        return set()
    v = config["wikilink_checked_bundles"]
    if not isinstance(v, (list, tuple)) or not all(isinstance(x, str) for x in v):
        _note("wikilink_checked_bundles must be an array of "
              "bundle names; got {!r} — wikilink check stays off".format(v))
        return set()
    # Casefolded: the store's filesystem is, so `check A` reaches bundle `a`
    # and its ctx["bundle"] reads "A". An exact-string gate switched this one
    # check off there while every other check kept firing.
    out = {x.lower() for x in v}
    if root is not None:
        known = {b.lower() for b in list_bundles(root)}
        unknown = sorted(x for x in v if x.lower() not in known)
        if unknown:
            _note("wikilink_checked_bundles names non-bundle(s): "
                  "{} — no file will be checked for them".format(", ".join(unknown)))
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
            raise OkfError("not_found", "not a directory: {}".format(args.target))
        # The target must name a bundle, or a subdirectory of one that
        # iter_all_md would actually traverse. Without this, `wikilinks ..`
        # walks out of the catalogue, and `wikilinks <bundle>/_plan` scans
        # staging that the reporting surface is defined to exclude —
        # iter_all_md prunes those names from `dirnames`, never from the
        # directory it is handed as a starting point.
        excluded = [s for s in segments if s.startswith((".", "_")) or s == "assets"]
        if not segments or segments[0] not in list_bundles(root) or excluded:
            raise OkfError("invalid_input",
                           "not a scannable bundle path: {}".format(args.target))
    links = scan_wikilinks(root, args.target)
    totals = {"resolved": 0, "ambiguous": 0, "unresolved": 0}
    for r in links:
        totals[r["status"]] += 1
    shown = [r for r in links if r["status"] != "resolved"] if args.unresolved else links
    if args.json:
        # by_bundle counts what `links` carries, so the two never contradict
        # each other; `totals` is always the unfiltered census and `filtered`
        # says which of the two a consumer is looking at.
        by_bundle = {}
        for r in shown:
            b = r["source"].split("/", 1)[0]
            by_bundle.setdefault(b, {"resolved": 0, "ambiguous": 0, "unresolved": 0})
            by_bundle[b][r["status"]] += 1
        return {"links": shown, "by_bundle": by_bundle,
                "totals": totals, "filtered": bool(args.unresolved)}
    for r in shown:
        line = "{:<10} {:<11} {}  {}{}".format(
            r["status"], r["region"], r["source"], r["raw"],
            "  (embed)" if r["embed"] else "")
        if r["status"] == "ambiguous":
            line += "  candidates: {}".format(", ".join(r["candidates"]))
        print(line)
    print("wikilinks: {} link(s), {} resolved, {} ambiguous, {} unresolved".format(
        len(links), totals["resolved"], totals["ambiguous"], totals["unresolved"]))


def add_wikilinks_parser(sub):
    pwl = _sub(sub, "wikilinks", "maintenance",
               "report Obsidian wikilinks ([[…]]) and whether each resolves to a concept")
    pwl.add_argument("target", nargs="?",
                     help="<bundle> or <bundle>/<subdir> (default: whole catalogue)").completer = _complete_scopes
    pwl.add_argument("--unresolved", action="store_true",
                     help="list only unresolved and ambiguous occurrences (summary stays complete)")
    _add_output(pwl)


COMMANDS = {
    "wikilinks": (cmd_wikilinks, add_wikilinks_parser),
}
