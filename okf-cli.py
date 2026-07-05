#!/usr/bin/env python3
"""okf-cli.py — dependency-free navigation/search for an OKF Knowledge Catalogue.

Catalogue-aware fork inspired by Cole Medin's single-bundle okf-cli.py.
A *catalogue* is a directory whose immediate subdirectories (not starting with
'.' or '_') are OKF *bundles*. Standard library only — no install required.

Commands:
    okf-cli.py index [bundle] [--full]     catalogue TOC (bundle/description/concepts/directories),
                                            or one bundle's index; --full adds types+tags per bundle
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
    okf-cli.py merge-tags <tag1> [<tag2> …] --into <tag> [--scope <target>] [--apply]
                                            merge/rename tags across concept frontmatter (dry-run default)
    okf-cli.py normalize-tags [--scope <target>] [--apply]
                                            convert inline `tags: [...]` to YAML block-list (local convention,
                                            dry-run default)
    okf-cli.py check [target] [--strict] [--json]  conformance scan (§9 + local invariants)
    okf-cli.py fix-crosslinks [target] [--check]   rewrite relative links to bundle-relative form

Run from the catalogue root, or pass --root <path>.
"""
import argparse
import difflib
import os
import re
import subprocess
import sys
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
TAGS_BLOCK_RE = re.compile(r"^tags:[ \t]*\n((?:[ \t]*-[ \t]*.+\n)*)", re.M)


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


def cmd_tags(root, args):
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


def cmd_index(root, args):
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
                score += (3 * min(hay_title.count(t), 1)
                          + 2 * min(hay_tags.count(t), 1)
                          + min(hay_body.count(t), 1))
            if score:
                snip = make_snippet(body, terms)
                desc = _dequote(fm.get("description", ""))
                hits.append((score, "{}/{}".format(b, cid), title, fm.get("type", ""), desc, snip))
    hits.sort(key=lambda x: -x[0])
    if not hits:
        print("(no matches for: {})".format(args.query))
        return
    max_score = 6 * len(terms)
    for score, path, title, typ, desc, snip in hits[: args.limit]:
        print("------")
        print("score: {}/{}".format(score, max_score))
        print("title: {}".format(title))
        print("type: {}".format(typ))
        print("path: {}".format(path))
        print("description: {}".format(desc))
        print("body-snippet: {}".format(snip))
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
    out = args.out or os.path.join(root, args.bundle, "assets", "viz.html")
    data = json.dumps({"name": args.bundle, "nodes": nodes, "edges": edges})
    html = _VIZ_TEMPLATE.replace("__DATA__", data).replace("__NAME__", args.bundle)
    os.makedirs(os.path.dirname(out), exist_ok=True)
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
        idx = os.path.join(p, "index.md")
        if not os.path.isfile(idx):
            continue
        h1, desc = index_h1_and_desc(idx)
        out.append((h1 or name, name, desc))
    out.sort(key=lambda x: x[0].casefold())
    return out


def render_block(subdirs, concepts):
    """OKF bullet list: subdirectories first, then concept files."""
    lines = []
    for title, name, desc in subdirs:
        d = _collapse(desc)
        lines.append("* [{}]({}/index.md){}".format(title, name, " - " + d if d else ""))
    for title, slug, desc in concepts:
        d = _collapse(desc)
        lines.append("* [{}]({}.md){}".format(title, slug, " - " + d if d else ""))
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
        if "index.md" not in fn:
            continue
        idx = os.path.join(dp, "index.md")
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
        if "index.md" not in fn:
            continue
        idx = os.path.join(dp, "index.md")
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
        if "index.md" in fn:
            dirs.append(dp)
    changed, skipped, stale = [], [], []
    for dp in sorted(dirs):
        idx = os.path.join(dp, "index.md")
        text = read_file(idx)
        rel = os.path.relpath(idx, root)
        if MARK_START not in text:
            skipped.append(rel)
            continue
        block = render_block(list_subdirs_with_index(dp), list_dir_concepts(dp))
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


def load_types(root):
    """Set of registered `type` values from TYPES.md, or None if the file is missing."""
    p = os.path.join(root, "TYPES.md")
    if not os.path.isfile(p):
        return None
    return set(re.findall(r"^\|\s*`([^`]+)`", read_file(p), re.M))


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
    if ctx["is_reserved"]:
        return []
    bad = []
    for m in re.finditer(r"\[[^\]]+\]\(([^)]+)\)", ctx["body"]):
        tgt = m.group(1).split("#")[0].strip()
        if not tgt.endswith(".md") or tgt.startswith(("http://", "https://", "/", "..")):
            continue
        bad.append(tgt)
    return ["non bundle-relative link(s): {}".format(", ".join(bad))] if bad else []


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
    """Reuses bundle_graph's cdir-relative resolution formula. Returns the
    bundle-relative absolute form (`/dest.md`) only if the target file really
    exists — the safety anchor that leaves doc examples pointing at
    non-existent paths untouched instead of guessing."""
    dest = os.path.normpath(os.path.join(cdir, tgt[:-3])).replace(os.sep, "/")
    if not os.path.isfile(os.path.join(root, bundle, dest + ".md")):
        return None
    return "/" + dest + ".md"


def rewrite_crosslinks_in_body(root, bundle, cdir, body):
    """Rewrite same-bundle relative links to bundle-relative absolute form.
    Same detection filter as check_crosslink_format (skip http(s)://, leading
    `/`, leading `..`). Returns (new_body, changed_count, unresolved_targets)."""
    changed = 0
    unresolved = []

    def repl(m):
        nonlocal changed
        label, target = m.group(1), m.group(2)
        raw_tgt, _, anchor = target.partition("#")
        raw_tgt = raw_tgt.strip()
        if not raw_tgt.endswith(".md") or raw_tgt.startswith(("http://", "https://", "/", "..")):
            return m.group(0)
        resolved = resolve_crosslink_target(root, bundle, cdir, raw_tgt)
        if resolved is None:
            unresolved.append(raw_tgt)
            return m.group(0)
        changed += 1
        new_target = resolved + ("#" + anchor if anchor else "")
        return "[{}]({})".format(label, new_target)

    new_body = CROSSLINK_RE.sub(repl, body)
    return new_body, changed, unresolved


def fix_crosslinks(root, target, dry_run=False):
    """Rewrite crosslinks in every non-reserved .md under `target` (bundle or
    bundle/subdir, or the whole catalogue when None) to bundle-relative
    absolute form. Returns (touched, unresolved):
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


def run_checks(root, target):
    """Run the full pluggable conformance scan over `target` (bundle or
    bundle/subdir), or the whole catalogue when target is None.

    Returns (errors, warnings), each a list of (check_name, rel_path, message).
    """
    scopes = resolve_scopes(root, target)
    types_set = load_types(root)
    per_file_checks = [
        ("frontmatter-parseable", "error", check_fm_parseable),
        ("type-nonempty", "error", check_type_nonempty),
        ("reserved-no-type", "error", check_reserved_no_type),
        ("filename-chars", "error", check_filename_chars),
        ("type-registered", "warning", lambda c: check_type_registered(c, types_set)),
        ("english-keys", "warning", check_english_keys),
        ("crosslink-format", "warning", check_crosslink_format),
        ("tags-block-form", "warning", check_tags_block_form),
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
    errors, warnings = run_checks(root, getattr(args, "target", None))
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


def main():
    ap = argparse.ArgumentParser(prog="okf-cli.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", help="catalogue root (default: script directory)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pi = sub.add_parser("index")
    pi.add_argument("bundle", nargs="?")
    pi.add_argument("--full", action="store_true",
                    help="add per-bundle types+tags used (catalogue TOC), or print the "
                         "structured bundle summary instead of the raw index.md (with a bundle arg)")
    pf = sub.add_parser("find")
    pf.add_argument("query")
    pf.add_argument("--limit", type=int, default=10)
    pr = sub.add_parser("read")
    pr.add_argument("path")
    sub.add_parser("info", help="print catalogue schema docs (TYPES.md + PROPERTIES.md)")
    pt = sub.add_parser("toc", help="print a concept's headings (default: h2 only)")
    pt.add_argument("path")
    pt.add_argument("--level", type=int, default=2,
                    help="heading level to list (default 2 = h2); 0 = full indented tree")
    pv = sub.add_parser("visualize", help="write a self-contained viz.html graph for a bundle")
    pv.add_argument("bundle")
    pv.add_argument("--out", help="output path (default: <bundle>/viz.html)")
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
    pmt = sub.add_parser("merge-tags",
                         help="merge/rename one or more tags into a target tag across concept frontmatter")
    pmt.add_argument("tags", nargs="+", help="source tag(s) to merge, e.g. workflow workflows")
    pmt.add_argument("--into", required=True, metavar="TAG", help="destination tag name")
    pmt.add_argument("--scope", metavar="TARGET",
                     help="<bundle> or <bundle>/<subdir> to limit the rewrite (default: whole catalogue)")
    pmt.add_argument("--apply", action="store_true", help="write changes (default: dry-run preview only)")
    pnt = sub.add_parser("normalize-tags",
                         help="convert inline `tags: [...]` fields to YAML block-list form (local convention)")
    pnt.add_argument("--scope", metavar="TARGET",
                     help="<bundle> or <bundle>/<subdir> to limit the rewrite (default: whole catalogue)")
    pnt.add_argument("--apply", action="store_true", help="write changes (default: dry-run preview only)")
    pc = sub.add_parser("check", help="conformance scan: §9 hard rules + local invariants")
    pc.add_argument("target", nargs="?", help="<bundle> or <bundle>/<subdir> (default: whole catalogue)")
    pc.add_argument("--strict", action="store_true", help="promote warnings to errors")
    pc.add_argument("--json", action="store_true", help="machine-readable output")
    pfx = sub.add_parser("fix-crosslinks",
                         help="rewrite same-bundle relative links to bundle-relative absolute form")
    pfx.add_argument("target", nargs="?", help="<bundle> or <bundle>/<subdir> (default: whole catalogue)")
    pfx.add_argument("--check", action="store_true", help="dry-run: report without writing")
    args = ap.parse_args()
    root = catalogue_root(args.root)
    {"index": cmd_index, "find": cmd_find,
     "read": cmd_read, "info": cmd_info, "toc": cmd_toc, "visualize": cmd_visualize,
     "reindex": cmd_reindex, "log": cmd_log, "tags": cmd_tags, "merge-tags": cmd_merge_tags,
     "normalize-tags": cmd_normalize_tags,
     "check": cmd_check, "fix-crosslinks": cmd_fix_crosslinks}[args.cmd](root, args)


if __name__ == "__main__":
    main()
