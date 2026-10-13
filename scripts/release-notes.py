#!/usr/bin/env python3
"""Print a release-note draft for one release milestone bean.

usage: scripts/release-notes.py <milestone-bean-id> > releases/RELEASE-<version>.md

Source: the `lif` CLI. The milestone carries the tag rel-<x-y-z>; epics and features
below it are "Changes"; bugs directly below it (no epic/feature parent) are "Fixes".
Each line is "[bean-id] summary"; without a summary the title stands in.
"""
import json
import subprocess
import sys


def lif(*args):
    out = subprocess.run(["lif", *args, "--json"], check=True, capture_output=True, text=True).stdout
    return json.loads(out) or []


def summary(b):
    return (b.get("extra") or {}).get("summary") or b["title"]


def main(milestone):
    m = lif("show", milestone)
    if m["type"] != "milestone":
        sys.exit(f"{milestone} is a {m['type']}, not a milestone")
    kids = [b for b in lif("list", "--parent", milestone) if b["status"] in ("completed", "to-review")]
    changes = [b for b in kids if b["type"] in ("epic", "feature")]
    fixes = [b for b in kids if b["type"] == "bug"]
    print(f"## Summary\n\n{summary(m)}\n")
    print("## Changes\n\n" + "\n".join(f"- [{b['id']}] {summary(b)}" for b in changes) + "\n")
    if fixes:
        print("## Fixes\n\n" + "\n".join(f"- fixed [{b['id']}] {summary(b)}" for b in fixes) + "\n")


if len(sys.argv) != 2:
    sys.exit(__doc__)
main(sys.argv[1])
