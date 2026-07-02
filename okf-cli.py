#!/usr/bin/env python3
"""okf-cli.py — dependency-free navigation/search for an OKF Knowledge Catalogue.

Catalogue-aware fork inspired by Cole Medin's single-bundle okf-cli.py.
A *catalogue* is a directory whose immediate subdirectories (not starting with
'.' or '_') are OKF *bundles*. Standard library only — no install required.

Commands:
    okf-cli.py bundles                     list bundles + concept counts
    okf-cli.py index [bundle]              catalogue TOC, or one bundle's index
    okf-cli.py find "<query>"              ranked keyword search across all bundles
    okf-cli.py read <bundle>/<concept-id>  print one concept page

Run from the catalogue root, or pass --root <path>.
"""
import argparse
import os
import re
import sys

RESERVED = {"index.md", "log.md", "readme.md", "index-map.md"}
FM_DELIM = "---"


def catalogue_root(explicit):
    return os.path.abspath(explicit or os.path.dirname(os.path.abspath(__file__)))


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


def meta_of(ap):
    fm, _ = split_frontmatter(read_file(ap))
    title = fm.get("title") or os.path.basename(ap)[:-3]
    return fm.get("type", ""), title, fm.get("description", "")


def cmd_bundles(root, _args):
    bundles = list_bundles(root)
    if not bundles:
        print("(no bundles found)")
        return
    width = max(len(b) for b in bundles)
    for b in bundles:
        n = sum(1 for _ in iter_concepts(os.path.join(root, b)))
        print("  {:<{w}}  {} concepts".format(b, n, w=width))


def cmd_index(root, args):
    if args.bundle:
        bp = os.path.join(root, args.bundle)
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
    # catalogue TOC
    print("# Knowledge Catalogue\n")
    for b in list_bundles(root):
        bp = os.path.join(root, b)
        n = sum(1 for _ in iter_concepts(bp))
        entry = "* **{}** ({} concepts)".format(b, n)
        for fn in ("INDEX-MAP.md", "index.md"):
            if os.path.isfile(os.path.join(bp, fn)):
                entry += " → {}".format(fn)
                break
        print(entry)


def tokenize(s):
    return [t for t in re.split(r"[^a-z0-9]+", s.lower()) if t]


def cmd_find(root, args):
    terms = tokenize(args.query)
    if not terms:
        print("(empty query)")
        return
    hits = []
    for b in list_bundles(root):
        for cid, ap in iter_concepts(os.path.join(root, b)):
            fm, body = split_frontmatter(read_file(ap))
            title = fm.get("title", cid)
            tags = fm.get("tags", "")
            hay_title = title.lower()
            hay_tags = tags.lower()
            hay_body = body.lower()
            score = 0
            for t in terms:
                score += 3 * hay_title.count(t) + 2 * hay_tags.count(t) + hay_body.count(t)
            if score:
                snip = make_snippet(body, terms)
                hits.append((score, "{}/{}".format(b, cid), title, fm.get("type", ""), snip))
    hits.sort(key=lambda x: -x[0])
    if not hits:
        print("(no matches for: {})".format(args.query))
        return
    for score, path, title, typ, snip in hits[: args.limit]:
        print("{:>4}  {}  [{}]\n      {}\n      {}\n".format(score, title, typ, path, snip))


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
                dest = tgt[1:-3]
            else:
                dest = os.path.normpath(os.path.join(cdir, tgt))[:-3] if False else \
                       os.path.normpath(os.path.join(cdir, tgt[:-3]))
            dest = dest.replace(os.sep, "/")
            if dest in concepts and dest != cid:
                edges.append({"source": cid, "target": dest})
    return nodes, edges


def cmd_visualize(root, args):
    import json
    nodes, edges = bundle_graph(root, args.bundle)
    out = args.out or os.path.join(root, args.bundle, "viz.html")
    data = json.dumps({"name": args.bundle, "nodes": nodes, "edges": edges})
    html = _VIZ_TEMPLATE.replace("__DATA__", data).replace("__NAME__", args.bundle)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print("wrote {} ({} nodes, {} edges)".format(out, len(nodes), len(edges)))


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


def main():
    ap = argparse.ArgumentParser(prog="okf-cli.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", help="catalogue root (default: script directory)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("bundles")
    pi = sub.add_parser("index")
    pi.add_argument("bundle", nargs="?")
    pf = sub.add_parser("find")
    pf.add_argument("query")
    pf.add_argument("--limit", type=int, default=10)
    pr = sub.add_parser("read")
    pr.add_argument("path")
    pt = sub.add_parser("toc", help="print a concept's headings (default: h2 only)")
    pt.add_argument("path")
    pt.add_argument("--level", type=int, default=2,
                    help="heading level to list (default 2 = h2); 0 = full indented tree")
    pv = sub.add_parser("visualize", help="write a self-contained viz.html graph for a bundle")
    pv.add_argument("bundle")
    pv.add_argument("--out", help="output path (default: <bundle>/viz.html)")
    args = ap.parse_args()
    root = catalogue_root(args.root)
    {"bundles": cmd_bundles, "index": cmd_index, "find": cmd_find,
     "read": cmd_read, "toc": cmd_toc, "visualize": cmd_visualize}[args.cmd](root, args)


if __name__ == "__main__":
    main()
