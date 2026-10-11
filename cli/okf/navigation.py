"""The navigation commands: list, read, info, toc, visualize and refs, with the
concept graph and HTML template behind visualize and their parser blocks."""

import os
import re
import sys
from okf.errors import OkfError
from okf.output import _add_output

from okf import linkscan
from okf.catalogue import (
    extract_tags, iter_concepts, iter_headings, meta_of, read_file, require_bundle_dir,
    resolve_concept, resolve_scopes, split_frontmatter,
)
from okf.linkscan import _refs_display
from okf.parser_support import (
    _complete_bundles, _complete_concept_files, _complete_concepts, _complete_dirs, _complete_files,
    _complete_scopes, _complete_tags, _complete_types, _sub,
)


def cmd_list(root, args):
    if not args.type and not args.tag:
        raise OkfError("invalid_input", "(error: pass --type and/or --tag)")
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
        return [{"title": title, "type": t, "path": path, "description": desc}
                for (title, t, path, desc) in hits]
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


def _inside(heads, k):
    """Indexes of the headings inside the section of heads[k] (sub-sections included)."""
    out = []
    for j in range(k + 1, len(heads)):
        if heads[j][0] <= heads[k][0]:
            break
        out.append(j)
    return out


def _heading_path(heads, k):
    """Heading texts from the top-level ancestor down to heads[k], joined by " > "."""
    path, level = [heads[k][1]], heads[k][0]
    for level_j, text_j, _line in reversed(heads[:k]):
        if level_j < level:
            path.append(text_j)
            level = level_j
    return " > ".join(reversed(path))


def _read_section(body, section, first_file_line):
    """Lines of the one section `section` ("A" or "A > B > ...") names in `body`.
    A segment matches heading text case-insensitively and exactly; each later
    segment only inside the section of the previous match. Several matches are
    invalid_input listing every candidate's heading path and file line, none is
    not_found. `first_file_line` is the 1-based file line of the body's line 0."""
    lines, heads = body.splitlines(), list(iter_headings(body))
    segments = [s.strip().casefold() for s in section.split(">")]
    hits = [k for k, h in enumerate(heads) if h[1].casefold() == segments[0]]
    for seg in segments[1:]:
        hits = sorted({j for k in hits for j in _inside(heads, k)
                       if heads[j][1].casefold() == seg})
    if not hits:
        raise OkfError("not_found", "section not found: {}".format(section))
    if len(hits) > 1:
        candidates = [{"heading": _heading_path(heads, k), "line": first_file_line + heads[k][2]}
                      for k in hits]
        raise OkfError("invalid_input", "ambiguous section: {} matches {} headings\n{}".format(
            section, len(hits), "\n".join(
                "  line {}: {}".format(c["line"], c["heading"]) for c in candidates)),
            {"candidates": candidates})
    k = hits[0]
    after = max(_inside(heads, k), default=k) + 1       # first heading of equal or higher level
    return lines[heads[k][2]:heads[after][2] if after < len(heads) else None]


def _split_head_body(text):
    """(frontmatter block, rest) at the point split_frontmatter splits. The block
    keeps both delimiter lines and the last newline (split_frontmatter leaves
    that newline on the body side); without frontmatter it is "" and rest is text."""
    body = split_frontmatter(text)[1]
    head = text[:len(text) - len(body)]
    if head and body.startswith("\n"):
        return head + "\n", body[1:]
    return head, body


def _concept_path(root, ap):
    """The concept's `<bundle>/<concept-id>` path, as find and list print it."""
    rel = os.path.relpath(ap, root).replace(os.sep, "/")
    return rel[:-3] if rel.endswith(".md") else rel


def cmd_read(root, args):
    ap = resolve_concept(root, args.path)
    text = read_file(ap)
    head, body = _split_head_body(text)
    if args.section is not None:
        out, end = "\n".join(_read_section(body, args.section, head.count("\n") + 1)), "\n"
    elif args.frontmatter_only:
        out, end = head, ""
    elif args.body_only:
        out, end = body, "\n"
    else:
        out, end = text, "\n"
    if getattr(args, "json", False):
        return {"path": _concept_path(root, ap), "text": out}
    print(out, end=end)


def cmd_info(root, args):
    """Print the catalogue's schema docs (TYPES.md + PROPERTIES.md) so an
    agent can load the type vocabulary and property spec in one call."""
    files = []
    for fn in ("TYPES.md", "PROPERTIES.md"):
        p = os.path.join(root, fn)
        files.append({"name": fn, "text": read_file(p) if os.path.isfile(p) else None})
    if getattr(args, "json", False):
        return {"files": files}
    for f in files:
        print("------")
        print(f["text"] if f["text"] is not None else "(missing: {})".format(f["name"]))
    print("------")


def cmd_toc(root, args):
    ap = resolve_concept(root, args.path)
    fm, body = split_frontmatter(read_file(ap))
    title = fm.get("title") or os.path.basename(ap)[:-3]
    # --level 0: the full tree; otherwise only the headings of that level (default h2)
    heads = [(lvl, text) for lvl, text, _line in iter_headings(body)
             if args.level == 0 or lvl == args.level]
    if getattr(args, "json", False):
        return {"path": _concept_path(root, ap), "title": title, "type": fm.get("type", ""),
                "headings": [{"level": lvl, "text": text} for lvl, text in heads]}
    print("# {}  [{}]".format(title, fm.get("type", "")))
    for lvl, text in heads:
        print("  " * (lvl - 1) + "- " + text if args.level == 0 else "- " + text)
    if not heads:
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
    if getattr(args, "json", False):
        return {"applied": True, "path": out, "nodes": len(nodes), "edges": len(edges)}
    print("wrote {} ({} nodes, {} edges)".format(out, len(nodes), len(edges)))


def cmd_refs(root, args):
    scan_root = os.path.abspath(args.scan_root) if getattr(args, "scan_root", None) else root
    if os.path.isabs(args.path):
        target = args.path
    else:
        # resolve against scan_root (the tree the path lives in) when given,
        # else root; prefer whichever actually exists.
        cand_scan = os.path.join(scan_root, args.path)
        target = cand_scan if os.path.exists(cand_scan) else os.path.join(root, args.path)
    if not os.path.exists(target):
        raise OkfError("not_found", "refs: target not found: {}".format(args.path))
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
        return d
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


def add_info_parser(sub):
    pi = _sub(sub, "info", "navigation",
              "print catalogue schema docs (TYPES.md + PROPERTIES.md)")
    _add_output(pi)


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
    _add_output(pls)


def add_read_parser(sub):
    pr = _sub(sub, "read", "navigation", "print one concept page")
    pr.add_argument("path", help="<bundle>/<concept-id> of the page to print").completer = _complete_concepts
    only = pr.add_mutually_exclusive_group()
    only.add_argument("--section", metavar="HEADING",
                      help="print only this section: heading text (case-insensitive, exact) up to "
                           "the next heading of equal or higher level, sub-sections included; "
                           "'A > B' resolves B inside A")
    only.add_argument("--frontmatter-only", action="store_true",
                      help="print only the frontmatter block, delimiters included")
    only.add_argument("--body-only", action="store_true",
                      help="print everything after the frontmatter block")
    _add_output(pr)


def add_refs_parser(sub):
    prf = _sub(sub, "refs", "search",
               "list inbound and outbound markdown links of a file")
    prf.add_argument("path", help="target file (abs, or relative to --root)").completer = _complete_concept_files
    prf.add_argument("--scan-root", help="dir to scan (default: --root); pass repo root for repo-wide").completer = _complete_dirs
    prf_dir = prf.add_mutually_exclusive_group()
    prf_dir.add_argument("--in", dest="only_in", action="store_true", help="only inbound links")
    prf_dir.add_argument("--out", dest="only_out", action="store_true", help="only outbound links")
    _add_output(prf)


def add_toc_parser(sub):
    pt = _sub(sub, "toc", "navigation",
              "print a concept's headings (default: h2 only)")
    pt.add_argument("path", help="<bundle>/<concept-id> to list headings for").completer = _complete_concepts
    pt.add_argument("--level", type=int, default=2,
                    help="heading level to list (default 2 = h2); 0 = full indented tree")
    _add_output(pt)


def add_visualize_parser(sub):
    pv = _sub(sub, "visualize", "navigation",
              "write a viz.html concept graph for a bundle "
              "(embeds every concept body; needs network for cytoscape/marked)")
    pv.add_argument("bundle", help="bundle to render the graph for").completer = _complete_bundles
    pv.add_argument("--out", help="output path (default: <bundle>/assets/viz.html)").completer = _complete_files
    _add_output(pv)


COMMANDS = {
    "info": (cmd_info, add_info_parser),
    "list": (cmd_list, add_list_parser),
    "read": (cmd_read, add_read_parser),
    "refs": (cmd_refs, add_refs_parser),
    "toc": (cmd_toc, add_toc_parser),
    "visualize": (cmd_visualize, add_visualize_parser),
}
