#!/usr/bin/env python3
"""Mutation harness for the wikilink-awareness work.

Each entry is a semantic weakening of one guard in `cli/okf-cli.py`. A mutant
that SURVIVES means no test distinguishes the weakened code from the real one,
i.e. that guard is unasserted. Run with no arguments for the whole set, or name
individual ids: `python3 docs/wikilink-awareness/mutants.py Q80 Q82`.

Working copies land in a scratch directory outside the repo; nothing here
writes to `cli/`.
"""
import os, shutil, subprocess, sys, tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(REPO, "cli")
BASE = os.path.join(tempfile.gettempdir(), "okf-mutants")
ORIG = open(os.path.join(SRC, "okf-cli.py"), encoding="utf-8").read()

MUTANTS = [
    ("Q09", "drop i==0 guard",
     "        if i == 0 or lines[i - 1].strip():",
     "        if lines[i - 1].strip():"),
    ("Q23", "yaml all-lines rule",
     "    return bool(YAML_LINE_RE.match(lines[0]))",
     "    return all(bool(YAML_LINE_RE.match(ln)) for ln in lines)"),
    ("Q23b", "yaml empty block is body",
     "        return True         # `---\\n---` is an empty frontmatter block, not prose",
     "        return False"),
    ("Q23c", "indented fence disqualifies",
     "    if any(FENCE_START_RE.match(ln) and not ln[:1].isspace() for ln in lines):",
     "    if any(FENCE_START_RE.match(ln) for ln in lines):"),
    ("Q38", "keep drops new_link",
     "    keep = {old_link.lower(), new_link.lower()}",
     "    keep = {old_link.lower()}"),
    ("Q47", "_contains_path exact",
     "    return any(c.lower() == link.lower() for c in cands)",
     "    return any(c == link for c in cands)"),
    ("Q52", "forbidden-char guard dropped",
     "    badchars = FILENAME_FORBIDDEN_CHARS & set(os.path.basename(new_abs)[:-3])",
     "    badchars = set()"),
    ("Q62", "fence-start pattern narrowed",
     'FENCE_START_RE = re.compile(r"^ {0,3}(?:`{3,}|~{3,})")',
     'FENCE_START_RE = re.compile(r"^ {0,3}(?:`{3,})")'),
    ("Q63", ".md guard dropped",
     '    if not old_abs.endswith(".md") or not new_abs.endswith(".md"):',
     "    if False:"),
    ("Q64", "catalogue-root guard dropped",
     "    if os.path.commonpath([old_abs, root]) != root or os.path.commonpath([new_abs, root]) != root:",
     "    if False:"),
    ("Q65", "bundle-depth guard dropped",
     "        if os.path.relpath(p, root).count(os.sep) < 1:",
     "        if False:"),
    ("Q76", "canonical case path is identity",
     "    rel = os.path.relpath(abspath, root)\n    if rel.startswith(\"..\"):",
     "    return abspath\n    rel = os.path.relpath(abspath, root)\n    if rel.startswith(\"..\"):"),
    ("Q78", "outbound old mask",
     "        for m in CROSSLINK_RE.finditer(wikilink_scan_text(src_text)):",
     "        for m in CROSSLINK_RE.finditer(src_text):"),
    ("Q80", "whitespace basename allowed",
     "    if new_base_raw != new_base_raw.strip():",
     "    if False:"),
    ("Q82", "frontmatter skips inline code",
     "    masked = _blank(masked,\n"
     "                    [(m.start(), m.end()) for m in INLINE_CODE_RE.finditer(masked)])\n"
     "    if yaml:\n        return masked",
     "    if yaml:\n        return masked\n"
     "    masked = _blank(masked,\n"
     "                    [(m.start(), m.end()) for m in INLINE_CODE_RE.finditer(masked)])"),

    # Round 5. The Q set targets guards a reviewer had already named, which
    # means its score says nothing about guards nobody thought to mutate. This
    # batch is the complementary sweep: 24 guards across the resolver, the
    # masking stages, the opt-in gate and the remaining cmd_rename refusals.
    # Only R11 was unasserted when it was written; the rest are kept as a
    # regression net, because a mutant that is killed today is the only evidence
    # that the test which kills it is not vacuous.
    #
    # Two candidates were dropped as EQUIVALENT rather than kept as noise:
    #   - `_same_path` losing its `len(cands) == 1` check. resolve_wikilink
    #     returns "resolved" only with a single-element list (either len 1
    #     outright or a one-element tie-break), and _same_path is reached only
    #     under that status, so the check cannot change an outcome.
    #   - `_indented_code_spans` losing its trailing-blank trim. The span already
    #     ends before the first non-blank unindented line; the trim only moves it
    #     back over whitespace-only lines, which carry nothing any scan reads.
    #     40 000 fuzzed documents over the line shapes that stage reacts to
    #     produced zero differing parses. The docstring's claim that the trim
    #     stops a link on the next line from being swallowed is too strong.
    ("R01", "reserved files become link targets",
     "            if fn.lower() in RESERVED:\n                continue",
     "            if False:\n                continue"),
    ("R02", "index key is case-sensitive",
     "            idx.setdefault(fn[:-3].lower(), []).append(",
     "            idx.setdefault(fn[:-3], []).append("),
    ("R03", "lookup key is case-sensitive",
     '    cands = index.get(page.rsplit("/", 1)[-1].lower(), [])',
     '    cands = index.get(page.rsplit("/", 1)[-1], [])'),
    ("R04", "path filter falls back to bare basename",
     "        cands = [c for c in cands if c.lower().endswith(tail)]",
     "        cands = [c for c in cands if c.lower().endswith(tail)] or cands"),
    ("R05", "tie-break accepts several in own bundle",
     "    if len(same) == 1:",
     "    if same:"),
    ("R06", "tie-break bundle compare is case-sensitive",
     '    own = (source_rel or "").split("/", 1)[0].lower()',
     '    own = (source_rel or "").split("/", 1)[0]'),
    ("R07", "in-file anchor becomes a target",
     "        if not page:\n            continue",
     "        if False:\n            continue"),
    ("R09", "control-char guard dropped",
     "    if any(ord(c) < 32 for c in new_base_raw):",
     "    if False:"),
    ("R10", "empty-basename guard dropped",
     "    if not new_base_raw.strip():",
     "    if False:"),
    ("R11", "moving a reserved source allowed",
     "    if os.path.basename(old_abs).lower() in RESERVED:",
     "    if False:"),
    ("R12", "renaming onto a reserved name allowed",
     "    if os.path.basename(new_abs).lower() in RESERVED:",
     "    if False:"),
    ("R13", "check no longer prunes staging/assets",
     '    if any(s.startswith((".", "_")) or s == "assets"\n'
     '           for s in ctx["rel"].split("/")[1:-1]):',
     "    if False:"),
    ("R14", "opt-in gate is case-sensitive",
     "    out = {x.lower() for x in v}",
     "    out = set(v)"),
    ("R15", "rename scan skips symlinked bundles",
     "    starts = [root] + [os.path.join(root, b) for b in list_bundles(root)\n"
     "                       if os.path.islink(os.path.join(root, b))]",
     "    starts = [root]"),
    ("R16", "_index_after_move ignores collisions",
     "    out[key] = sorted(set(out.get(key, [])) | {new_link} | set(collisions))",
     "    out[key] = sorted(set(out.get(key, [])) | {new_link})"),
    ("R17", "undecodable file is not skipped on wikilink apply",
     '    text = read_file_verbatim(abspath)\n'
     '    if text is None:\n'
     '        sys.stderr.write("note: skipping {} — not valid UTF-8\\n".format(abspath))\n'
     '        return\n'
     '    out, last = [], 0\n'
     '    for rec in parse_wikilinks(text):',
     '    text = read_file_verbatim(abspath)\n'
     '    if text is None:\n'
     '        text = read_file(abspath)\n'
     '    out, last = [], 0\n'
     '    for rec in parse_wikilinks(text):'),
    ("R18", "frontmatter block slice off by the delimiter",
     "            text[len(FM_DELIM):fm_end - len(FM_DELIM) - 1]",
     "            text[len(FM_DELIM):fm_end]"),
    ("R19", "path-qualified link loses its depth",
     '    page = "/".join(new_segments[-depth:])',
     "    page = new_segments[-1]"),
    ("R20", "explicit .md suffix is dropped by the rewrite",
     '    md = ".md" if head.endswith(".md") else ""',
     '    md = ""'),
    ("R21", "info string with a backtick opens a fence",
     '        if marker[0] == "`" and "`" in rest:',
     "        if False:"),
    ("R23", "list continuation is treated as code",
     "        if prev is not None and (LIST_ITEM_RE.match(prev) or indented(prev)):",
     "        if False:"),
    ("R24", "obsidian/html comments are not masked",
     "    masked = _blank(masked, [(m.start(), m.end()) for m in COMMENT_RE.finditer(masked)])",
     "    masked = masked"),
    ("R25", "case-only rename refused as existing destination",
     "    if (os.path.exists(new_abs) and args.apply and not args.force\n"
     "            and not os.path.samefile(old_abs, new_abs)):",
     "    if os.path.exists(new_abs) and args.apply and not args.force:"),
    ("R26", "turns-ambiguous refusal dropped",
     "    if args.apply and wl_ambiguous and not args.force:",
     "    if False:"),
]

only = sys.argv[1:]
shutil.rmtree(BASE, ignore_errors=True)
os.makedirs(BASE)
rows = []
for mid, label, old, new in MUTANTS:
    if only and mid not in only:
        continue
    if ORIG.count(old) != 1:
        rows.append(("BOTCHED", mid, label, "pattern count=%d" % ORIG.count(old)))
        continue
    d = os.path.join(BASE, mid)
    shutil.copytree(SRC, d, ignore=shutil.ignore_patterns("__pycache__"))
    open(os.path.join(d, "okf-cli.py"), "w", encoding="utf-8").write(ORIG.replace(old, new, 1))
    p = subprocess.run([sys.executable, "-m", "unittest", "test_okf_cli"],
                       cwd=d, capture_output=True, text=True)
    fails = [l for l in p.stderr.splitlines() if l.startswith(("FAIL:", "ERROR:"))]
    rows.append(("KILLED" if fails else "SURVIVED", mid, label,
                 fails[0][:100] if fails else ""))

for st, mid, label, det in rows:
    print("%-9s %-5s %-32s %s" % (st, mid, label, det))
print("\nkilled=%d survived=%d botched=%d" % (
    sum(1 for r in rows if r[0] == "KILLED"),
    sum(1 for r in rows if r[0] == "SURVIVED"),
    sum(1 for r in rows if r[0] == "BOTCHED")))
