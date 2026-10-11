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
import sys

from okf import (
    check, ctx, find, fts, index, linkscan, recent, rename, semantic, sync, tags, wikilinks,
)
from okf.catalogue import (
    catalogue_root, ctx_slugs, extract_tags, iter_concepts, iter_headings, list_bundles, load_tags,
    meta_of, read_file, require_bundle_dir, resolve_concept, resolve_scopes, split_frontmatter,
)
from okf.ctx import _ctx_shorthand
from okf.fts import _fts_db_path
from okf.index import render_bundle_block, render_bundle_line
from okf.linkscan import _refs_display
from okf.parser_support import (
    _complete_bundles, _complete_concept_files, _complete_concepts, _complete_dirs, _complete_files,
    _complete_scopes, _complete_tags, _complete_types, _sub, merge_commands,
    render_command_overview, subcommand_parsers,
)
from okf.semantic import _tagvec_db_path, semantic_coverage


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
    "info": (cmd_info, add_info_parser),
    "install": (cmd_install, add_install_parser),
    "list": (cmd_list, add_list_parser),
    "prime": (cmd_prime, add_prime_parser),
    "read": (cmd_read, add_read_parser),
    "refs": (cmd_refs, add_refs_parser),
    "toc": (cmd_toc, add_toc_parser),
    "visualize": (cmd_visualize, add_visualize_parser),
}


# Command modules under cli/okf/ that own their commands. Each defines COMMANDS in
# the same {name: (handler, add_parser)} form; moving a command means moving its
# COMMANDS entry into its module and listing the module here.
COMMAND_MODULES = (check, ctx, find, fts, index, recent, rename, semantic, sync, tags, wikilinks)

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
