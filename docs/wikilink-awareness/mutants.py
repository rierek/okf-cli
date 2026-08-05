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
