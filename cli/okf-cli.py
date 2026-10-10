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
import importlib.util
import json
import os
import re
import subprocess
import sys
import shlex

from okf import (
    catalogue, check, find, fts, index, linkscan, recent, semantic, sync, tags, wikilinks,
)
from okf.catalogue import (
    CROSSLINK_RE, CTX_DIR, CTX_MODES, CTX_VERBS, RESERVED, SYNC_OPEN_LIT, SYNC_OPEN_RE, _ctx_die,
    _prune_walk_dirs, catalogue_root, ctx_dir, ctx_entry_abspath, ctx_file, ctx_findings,
    ctx_memberships, ctx_normalize_path, ctx_slug_problem, ctx_slugs, extract_tags, iter_all_md,
    iter_concepts, iter_headings, list_bundles, load_ctx, load_tags, meta_of, read_file,
    read_file_verbatim, reindex_tree, require_bundle_dir, resolve_concept, resolve_scopes,
    save_ctx, split_frontmatter, write_file_verbatim,
)
from okf.fts import _fts_db_path
from okf.index import render_bundle_block, render_bundle_line
from okf.linkscan import (
    _refs_display, iter_md_links, iter_rename_scan_md, wikilink_scan_text,
)
from okf.parser_support import (
    _complete_bundles, _complete_concept_files, _complete_concepts, _complete_dirs, _complete_files,
    _complete_scopes, _complete_tags, _complete_types, _completion_root, _sub, merge_commands,
    render_command_overview, subcommand_parsers,
)
from okf.semantic import _tagvec_db_path, semantic_coverage
from okf.sync import parse_sync_blocks


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
    index = wikilinks.build_concept_basename_index(root)
    old_link = "/" + os.path.relpath(old_abs, root).replace(os.sep, "/")
    new_link = "/" + os.path.relpath(new_abs, root).replace(os.sep, "/")
    files = list(iter_rename_scan_md(root))
    # Collisions come from the rename scan's own reach, not from the resolution
    # index: the index skips staging, assets and root-level files, every one of
    # which this rename rewrites and Obsidian itself indexes.
    keep = {old_link.lower(), new_link.lower()}
    collisions = sorted(
        c for c in ("/" + os.path.relpath(ap, root).replace(os.sep, "/") for ap in files)
        if wikilinks._normalize_key(os.path.basename(c)[:-3]) == wikilinks._normalize_key(new_base)
        and c.lower() not in keep)
    # Casefolded, because resolve_wikilink is (D06). A case-sensitive filter
    # here silently excluded every case-variant inbound link from the plan — the
    # 96 live links D06 exists to rescue would have been orphaned by the very
    # rename that was supposed to carry them.
    old_key, new_key = wikilinks._normalize_key(old_base), wikilinks._normalize_key(new_base)
    after = _index_after_move(index, old_link, new_link, collisions)
    out = []
    for ap in files:
        rel = os.path.relpath(ap, root).replace(os.sep, "/")
        for rec in wikilinks.parse_wikilinks(read_file(ap), rel):
            key = wikilinks._normalize_key(rec["page"].rsplit("/", 1)[-1])
            if key not in (old_key, new_key):
                continue
            # Resolve the occurrence against the catalogue as it is and as it
            # will be. Deciding from the token alone missed the case where the
            # token does not change but its meaning does — a basename-preserving
            # move into a bundle where another concept shares the name turned a
            # unique address ambiguous with nothing to rewrite and nothing said.
            status, cands = wikilinks.resolve_wikilink(index, rel, rec["page"])
            was_ours = status == "resolved" and _same_path(cands, old_link)
            new_raw = _rewrite_wikilink_raw(rec["raw"], new_link) if was_ours else rec["raw"]
            page_after = wikilinks._split_wikilink_inner(new_raw[2:-2])[0]
            status_after, cands_after = wikilinks.resolve_wikilink(after, rel, page_after)
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
    out[key] = wikilinks._apply_archive_precedence(
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
    for rec in wikilinks.parse_wikilinks(text):
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
    badchars = check.FILENAME_FORBIDDEN_CHARS & set(os.path.basename(new_abs)[:-3])
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
    check._print_findings(errors, warnings, as_json)
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


COMMANDS = {
    "archive": (cmd_archive, add_archive_parser),
    "ctx": (cmd_ctx, add_ctx_parser),
    "info": (cmd_info, add_info_parser),
    "install": (cmd_install, add_install_parser),
    "list": (cmd_list, add_list_parser),
    "prime": (cmd_prime, add_prime_parser),
    "read": (cmd_read, add_read_parser),
    "refs": (cmd_refs, add_refs_parser),
    "rename": (cmd_rename, add_rename_parser),
    "rewrite-path": (cmd_rewrite_path, add_rewrite_path_parser),
    "toc": (cmd_toc, add_toc_parser),
    "visualize": (cmd_visualize, add_visualize_parser),
}


# Command modules under cli/okf/ that own their commands. Each defines COMMANDS in
# the same {name: (handler, add_parser)} form; moving a command means moving its
# COMMANDS entry into its module and listing the module here.
COMMAND_MODULES = (check, find, fts, index, recent, semantic, sync, tags, wikilinks)

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
