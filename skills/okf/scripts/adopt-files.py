#!/usr/bin/env python3
"""Adopt project markdown files into an OKF bundle: the per-file move steps of
references/integrate-project-knowledge.md, section 5, in one run (stdlib only).

  adopt-files.py --repo <repo> --root <repo>/docs --bundle <bundle> --by <actor> \
      --move <old> <new> <Type> [--move ...] [--apply]

<old>, <new>: paths relative to <repo>, e.g. docs/runbook.md docs/shop/operations/restart-worker.md.
Without --apply it only prints the plan and every link it would rewrite. With --apply it
  1. `git mv`s every file (all moves first),
  2. prepends frontmatter (type, title from the H1, description from the first sentence,
     generated: { by: <actor>, at: <UTC now> }) unless the file has one; REVIEW title and description,
  3. rewrites every markdown link to a moved file and every relative link inside a moved file
     (links inside <root>/<bundle> become /<bundle>/...; others stay relative, so `../` links too),
  4. runs `okf-cli rewrite-path <old> <new> --scan-root <repo>` for plain mentions (code, config),
  5. runs `fix-crosslinks <bundle>` and `check <bundle>`, then lists leftover mentions of the old paths.
The destination directory must already hold an index.md (step 4 of the reference). Nothing is committed.
"""
import argparse, datetime, os, re, subprocess, sys

SKIP = {".git", ".fts", ".tagvec", "node_modules", ".venv", "__pycache__"}
LINK = re.compile(r"(\]\()([^)\s#]+)(#[^)\s]*)?(\))")


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def md_files(repo):
    for d, dirs, files in os.walk(repo):
        dirs[:] = [x for x in dirs if x not in SKIP]
        for f in files:
            if f.endswith(".md"):
                yield os.path.relpath(os.path.join(d, f), repo).replace(os.sep, "/")


def title_desc(text, fallback):
    body = re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S)
    h1 = re.search(r"^#\s+(.+)$", body, re.M)
    title = re.sub(r"^\d+[.)]?\s+", "", h1.group(1).strip()) if h1 else fallback
    para = next((l.strip() for l in body.splitlines() if l.strip() and not l.lstrip().startswith(("#", "|", "```", "-", "*", ">"))), "")
    desc = re.split(r"(?<=[.!?])\s", para, maxsplit=1)[0] if para else title
    return title, desc[:200]


def q(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--root", required=True, help="catalogue root, usually <repo>/docs")
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--by", required=True, help="actor for generated.by: your own agent/model id, or human:<id> if the user wrote the text")
    ap.add_argument("--move", nargs=3, action="append", metavar=("OLD", "NEW", "TYPE"), required=True)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    repo, root = os.path.abspath(a.repo), os.path.abspath(a.root)
    rootrel = os.path.relpath(root, repo).replace(os.sep, "/")
    bundle_prefix = f"{rootrel}/{a.bundle}/"
    cli = ["okf-cli", "--root", root]
    moves = {}
    types = {}
    for old, new, typ in a.move:
        if not os.path.isfile(os.path.join(repo, old)):
            sys.exit(f"ERROR: {old} does not exist")
        if os.path.exists(os.path.join(repo, new)):
            sys.exit(f"ERROR: {new} exists already (pick another slug)")
        if not os.path.isfile(os.path.join(repo, os.path.dirname(new), "index.md")):
            sys.exit(f"ERROR: {os.path.dirname(new)}/index.md missing: create it first (reference step 4)")
        moves[old], types[new] = new, typ
    where = {v: k for k, v in moves.items()}  # new -> old

    def rel(dest, from_new):  # link text from file at from_new to repo path dest
        if from_new.startswith(bundle_prefix) and dest.startswith(rootrel + "/"):
            return "/" + dest[len(rootrel) + 1:]
        return os.path.relpath(dest, os.path.dirname(from_new) or ".").replace(os.sep, "/")

    edits, report = {}, []
    for f in md_files(repo):
        text = open(os.path.join(repo, f), encoding="utf-8").read()
        base = os.path.dirname(f)  # links resolve from where the file is NOW
        at = moves.get(f, f)       # and must work from where it will be
        def sub(m):
            t = m.group(2)
            if re.match(r"^[a-z][a-z0-9+.-]*:|^/|^#", t):
                return m.group(0)
            tgt = os.path.normpath(os.path.join(base, t)).replace(os.sep, "/")
            dest = moves.get(tgt)
            if dest is None:
                if at == f or not os.path.exists(os.path.join(repo, tgt)):
                    return m.group(0)
                dest = tgt
            new_t = rel(dest, at)
            if new_t == t:
                return m.group(0)
            report.append(f"  {f}: ]({t}) -> ]({new_t})")
            return m.group(1) + new_t + (m.group(3) or "") + m.group(4)
        new_text = LINK.sub(sub, text)
        if new_text != text:
            edits[f] = new_text
    print("plan:")
    for old, new in moves.items():
        print(f"  {old} -> {new} ({types[new]})")
    print("link rewrites:" if report else "link rewrites: none")
    print("\n".join(report))
    if not a.apply:
        print("\nPreview only. Repeat with --apply.")
        return
    for old, new in moves.items():
        os.makedirs(os.path.join(repo, os.path.dirname(new)), exist_ok=True)
        r = run(["git", "-C", repo, "mv", old, new])
        if r.returncode:
            sys.exit(f"ERROR: git mv {old} {new}: {r.stderr.strip()}")
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for f in md_files(repo):
        cur = f
        old = where.get(f)
        src = edits.get(old if old else f)
        path = os.path.join(repo, cur)
        if old is None and src is None:
            continue
        text = src if src is not None else open(path, encoding="utf-8").read()
        if old is not None and not text.startswith("---\n"):
            title, desc = title_desc(text, os.path.splitext(os.path.basename(f))[0])
            text = (f"---\ntype: {types[f]}\ntitle: {q(title)}\ndescription: {q(desc)}\n"
                    f"generated: {{ by: {a.by}, at: {now} }}\n---\n\n{text}")
            print(f"frontmatter added: {f} (title {title!r}: review title and description)")
        open(path, "w", encoding="utf-8").write(text)
    for old, new in moves.items():
        r = run(cli + ["rewrite-path", old, new, "--scan-root", repo])
        print((r.stdout + r.stderr).strip())
    for step in (["fix-crosslinks", a.bundle], ["check", a.bundle]):
        r = run(cli + step)
        print(f"$ okf-cli --root {root} {' '.join(step)}\n" + (r.stdout + r.stderr).strip())
    left = []
    for d, dirs, files in os.walk(repo):
        dirs[:] = [x for x in dirs if x not in SKIP]
        for f in files:
            p = os.path.join(d, f)
            try:
                t = open(p, encoding="utf-8").read()
            except (UnicodeDecodeError, OSError):
                continue
            for old in moves:
                if old in t:
                    left.append(f"  {os.path.relpath(p, repo)} still mentions {old}")
    print("leftover mentions of old paths (fix by hand, e.g. a ../ form this script could not resolve):" if left else "no leftover mentions of old paths")
    print("\n".join(left))


if __name__ == "__main__":
    main()
