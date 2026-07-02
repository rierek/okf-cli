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
    args = ap.parse_args()
    root = catalogue_root(args.root)
    {"bundles": cmd_bundles, "index": cmd_index, "find": cmd_find,
     "read": cmd_read, "toc": cmd_toc}[args.cmd](root, args)


if __name__ == "__main__":
    main()
