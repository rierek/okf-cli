#!/usr/bin/env python3
"""Generate the Changes/Fixes block of a release page from a milestone's beans.

usage: scripts/release-notes.py <milestone-id> [--write wiki/releases/<v>.md]

Source: the `lif` CLI (read-only). Epics and features below the milestone are
"Changes"; bugs are "Fixes". Each line is "[bean-id] summary"; the title stands in
for a missing summary. Without --write the block prints to stdout. With --write only
the text between START and END in the page is replaced; the rest stays byte for byte.
"""
import json
import subprocess
import sys

START = "{/* generated:start */}"
END = "{/* generated:end */}"


def lif(*args):
    out = subprocess.run(["lif", *args, "--json"], check=True, capture_output=True, text=True).stdout
    return json.loads(out) or []


def summary(b):
    return (b.get("extra") or {}).get("summary") or b["title"]


def render_block(milestone, children):
    kids = [b for b in children if b["status"] in ("completed", "to-review")]
    changes = [b for b in kids if b["type"] in ("epic", "feature")]
    fixes = [b for b in kids if b["type"] == "bug"]
    parts = [summary(milestone)]
    if changes:
        parts.append("## Changes\n\n" + "\n".join(f"- [{b['id']}] {summary(b)}" for b in changes))
    if fixes:
        parts.append("## Fixes\n\n" + "\n".join(f"- [{b['id']}] {summary(b)}" for b in fixes))
    return "\n\n".join(parts) + "\n"


def splice(page_text, block):
    a = page_text.find(START)
    b = page_text.find(END)
    if a < 0 or b < 0 or b < a or page_text.count(START) != 1 or page_text.count(END) != 1:
        raise ValueError(f"page needs exactly one {START} ... {END} pair")
    return page_text[: a + len(START)] + "\n\n" + block + "\n" + page_text[b:]


def main(argv):
    if len(argv) not in (1, 3) or (len(argv) == 3 and argv[1] != "--write"):
        sys.exit(__doc__)
    m = lif("show", argv[0])
    if m["type"] != "milestone":
        sys.exit(f"{argv[0]} is a {m['type']}, not a milestone")
    block = render_block(m, lif("list", "--parent", argv[0]))
    if len(argv) == 1:
        print(block, end="")
        return
    with open(argv[2], encoding="utf-8", newline="") as f:
        text = f.read()
    try:
        new = splice(text, block)
    except ValueError as e:
        sys.exit(f"{argv[2]}: {e}")
    with open(argv[2], "w", encoding="utf-8", newline="") as f:
        f.write(new)


if __name__ == "__main__":
    main(sys.argv[1:])
