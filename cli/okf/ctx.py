"""The ctx command: curated, ordered reading lists ("context bundles") per topic.
Holds its 14 verbs, the `ctx <slug>` shorthand, the slug completer and the parser
block; the ctx storage layer (load_ctx, save_ctx, ctx_findings, ...) stays in
okf.catalogue."""

import json
import os
import shlex
import subprocess
import sys
from okf.errors import OkfError

from okf import check, linkscan, rename
from okf.catalogue import (
    CTX_DIR, CTX_MODES, CTX_VERBS, _ctx_die, ctx_dir, ctx_entry_abspath, ctx_file, ctx_findings,
    ctx_memberships, ctx_normalize_path, ctx_slug_problem, ctx_slugs, iter_headings, load_ctx,
    meta_of, read_file, reindex_tree, save_ctx, split_frontmatter,
)
from okf.linkscan import _refs_display, iter_md_links
from okf.parser_support import _complete_concepts, _complete_files, _completion_root, _sub


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
            _ctx_die("import file not found: {}".format(args.import_file), "not_found")
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
        raise OkfError("not_found", "\n".join(
            "ctx: not found: {}".format(p) for p in missing))
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
            raise OkfError("non_conformant", _ctx_dead_warning(args.slug, dead))
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
        raise OkfError("non_conformant", "")


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
        raise OkfError("non_conformant", "")


def cmd_ctx_toc(root, args):
    blocks = []
    for m in _ctx_members(root, args.slug)[1]:
        lines = ["# {}{}".format(m["path"], "" if m["alive"] else " [DEAD]")]
        if m["alive"]:
            hs = []
            if m["path"].endswith(".md"):
                body = split_frontmatter(read_file(m["abspath"]))[1]
                hs = ["{} {}".format("#" * min(lv + 1, 6), t) for lv, t, _line in iter_headings(body)
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
            _ctx_die('no entry in {} matches --file "{}"'.format(args.slug, args.file), "not_found")
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
        _ctx_die("not found: {}".format(args.path), "not_found")
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
        _ctx_die("{} is not in {}".format(norm, args.slug), "not_found")
    c["entries"] = [x for x in pf + rest if x is not e]
    save_ctx(root, c)
    print("dropped {} from {}".format(norm, args.slug))


def cmd_ctx_move(root, args):
    c, pf, rest = _ctx_editable(root, args.slug)
    if args.pos is None and args.mode is None:
        _ctx_die("move needs --pos or --mode")
    norm, e = _ctx_find(root, c, args.path)
    if e is None:
        _ctx_die("{} is not in {}".format(norm, args.slug), "not_found")
    mode = args.mode or e["mode"]
    if args.pos is not None and mode != "pflicht":
        _ctx_die("--pos applies only to mode pflicht")
    pf = [x for x in pf if x is not e]
    rest = [x for x in rest if x is not e]
    where = _ctx_put(root, c, pf, rest, e, mode, args.pos)
    print("moved {} in {} to {}".format(norm, args.slug, where))


def _ctx_report(root, slugs, stale, as_json):
    findings = []
    for s in slugs:
        rel = "{}/{}.md".format(CTX_DIR, s)
        findings += [check.finding_of(rule, rel, m)
                     for rule, m in ctx_findings(root, ctx_file(root, s), stale)]
    check.report_findings(findings, False, as_json)


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
    rename.perform_rename(root, ctx_file(root, args.old), ctx_file(root, args.new), True, False)
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
    return CTX_DISPATCH[args.ctx_verb](root, args)


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


COMMANDS = {"ctx": (cmd_ctx, add_ctx_parser)}
