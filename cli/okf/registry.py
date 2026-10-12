"""`registry convert`: rewrite the entries of TAGS.md or TYPES.md in table or block form."""

import os
import re
from okf.catalogue import (
    REGISTRY_FORMATS, REGISTRY_RANKS, TAGS_TABLE_HEAD, read_file_verbatim, render_registry_entry,
    scan_registry, write_file_verbatim,
)
from okf.diffs import unified_diffs
from okf.errors import OkfError
from okf.output import _add_output
from okf.parser_support import _sub

_RANK_LINE_RE = re.compile(r"^rank:\s*({})\s*$".format("|".join(REGISTRY_RANKS)))
_SEPARATOR_RE = re.compile(r"^\|[\s:|-]+\|?\s*$")
_HEADS = {
    ("TAGS.md", False): TAGS_TABLE_HEAD,
    ("TAGS.md", True): "| Tag | rank | Description |\n|-----|:----:|-------------|\n",
    ("TYPES.md", False): "| type | Meaning |\n|------|---------|\n",
    ("TYPES.md", True): "| type | rank | Meaning |\n|------|:----:|---------|\n",
}


def _refuse(filename, line_index, message):
    raise OkfError("invalid_input", "{}:{}: {}".format(filename, line_index + 1, message))


def _entry_fields(lines, e):
    """(rank or None, [description lines]) of one entry."""
    if e.kind == "table":
        cells = lines[e.start].strip().strip("|").split("|")
        if len(cells) >= 3 and cells[1].strip() in REGISTRY_RANKS:
            rank, desc = cells[1].strip(), "|".join(cells[2:]).strip()
        else:
            rank, desc = None, "|".join(cells[1:]).strip()
        return rank, [desc] if desc else []
    body = [l.strip() for l in lines[e.start + 1:e.end] if l.strip()]
    rank = None
    if body:
        m = _RANK_LINE_RE.match(body[0])
        if m:
            rank = m.group(1)
            body = body[1:]
    return rank, body


def _table_runs(lines, scan):
    """[(start, end)] maximal runs of non-fenced lines starting with `|` that hold a table entry."""
    starts = {e.start for e in scan.entries if e.kind == "table"}
    runs, i = [], 0
    while i < len(lines):
        if i in scan.fenced or not lines[i].startswith("|"):
            i += 1
            continue
        j = i
        while j < len(lines) and j not in scan.fenced and lines[j].startswith("|"):
            j += 1
        if any(k in starts for k in range(i, j)):
            runs.append((i, j))
        i = j
    return runs


def _to_block(lines, filename):
    scan = scan_registry(lines)
    entries = {e.start: e for e in scan.entries if e.kind == "table"}
    runs = _table_runs(lines, scan)
    plans = []
    for n, (a, b) in enumerate(runs):
        for i in range(a, b):
            if i in entries:
                continue
            is_head = (i == a and b - a > 1 and _SEPARATOR_RE.match(lines[a + 1])) or \
                      (i == a + 1 and a not in entries and _SEPARATOR_RE.match(lines[i]))
            if not is_head:
                _refuse(filename, i, "table mixes registry rows with other rows; convert it by hand")
        # Text after the table would become part of the last block (a block runs to
        # the next heading); the next table run is fine, it turns into blocks too.
        limit = min(next((h for h in scan.headings if h >= b), len(lines)),
                    runs[n + 1][0] if n + 1 < len(runs) else len(lines))
        for i in range(b, limit):
            if lines[i].strip():
                _refuse(filename, i, "text after the table would become part of the last block; "
                        "move it above the table or under its own heading")
        blocks = []
        for i in range(a, b):
            if i in entries:
                rank, desc = _entry_fields(lines, entries[i])
                if desc and "|" in desc[0]:
                    _refuse(filename, i, "row `{}` has more than one description cell; convert it by hand".format(entries[i].value))
                blocks.append(render_registry_entry("block", entries[i].value, desc[0] if desc else "", rank))
        plans.append((a, b, "\n".join(blocks), len(blocks)))
    for a, b, text, _ in reversed(plans):
        lines[a:b] = [text]
    return sum(p[3] for p in plans)


def _to_table(lines, filename):
    scan = scan_registry(lines)
    blocks = [e for e in scan.entries if e.kind == "block"]
    groups = []
    for e in blocks:
        if groups and groups[-1][-1].end == e.start:
            groups[-1].append(e)
        else:
            groups.append([e])
    plans = []
    for group in groups:
        rows = []
        for e in group:
            rank, desc = _entry_fields(lines, e)
            if len(desc) > 1:
                _refuse(filename, e.start, "block `{}` has a multi-line description; a table cell holds one line".format(e.value))
            if desc and "|" in desc[0]:
                _refuse(filename, e.start, "block `{}` description contains '|'".format(e.value))
            rows.append((e.value, desc[0] if desc else "", rank))
        ranked = any(r for _, _, r in rows)
        stop = group[-1].end
        while stop > group[-1].start + 1 and not lines[stop - 1].strip():
            stop -= 1
        start = group[0].start
        head = ("\n" if start > 0 and lines[start - 1].strip() else "") + _HEADS[(filename, ranked)]
        text = head + "".join(render_registry_entry("table", v, d, (r or "—") if ranked else None) for v, d, r in rows)
        plans.append((start, stop, text))
    for start, stop, text in reversed(plans):
        lines[start:stop] = [text]
    return len(blocks)


def convert_registry(text, filename, to):
    """(new text, number of entries rewritten). Text outside the converted entries stays byte for
    byte; every refusal is raised before anything is returned."""
    lines = text.splitlines(True)
    n = (_to_block if to == "block" else _to_table)(lines, filename)
    return "".join(lines), n


def cmd_registry(root, args):
    p = os.path.join(root, args.file)
    if not os.path.isfile(p):
        raise OkfError("not_found", "{} not found under {}".format(args.file, root))
    old = read_file_verbatim(p)
    if old is None:
        raise OkfError("invalid_input", "{} is not valid UTF-8".format(args.file))
    new, n = convert_registry(old, args.file, args.to)
    files = unified_diffs([(args.file, old, new)])
    if args.apply and new != old:
        write_file_verbatim(p, new)
    result = {"file": args.file, "to": args.to, "applied": bool(args.apply), "converted": n, "files": files}
    if getattr(args, "json", False):
        return result
    for entry in files:
        print(entry["diff"], end="")
    print("registry convert: {} entr{} in {} {} as {}".format(
        n, "y" if n == 1 else "ies", args.file, "rewrote" if args.apply else "would rewrite", args.to))


def add_registry_parser(sub):
    pr = _sub(sub, "registry", "maintenance",
              "reformat registry entries of TAGS.md or TYPES.md (table or block form); prose stays")
    verbs = pr.add_subparsers(dest="registry_verb", required=True, metavar="VERB", help="registry verb")
    pc = verbs.add_parser(
        "convert", help="rewrite every entry of one registry file in the target form",
        description="rewrite every entry of <root>/TAGS.md or <root>/TYPES.md in table or block form; "
                    "text outside the entries stays byte for byte; previews a unified diff unless --apply")
    pc.add_argument("file", choices=("TAGS.md", "TYPES.md"),
                    help="registry file under the catalogue root (types_source is not followed)")
    pc.add_argument("--to", required=True, choices=REGISTRY_FORMATS, help="target form")
    pc.add_argument("--apply", action="store_true", help="write changes (default: dry-run preview only)")
    _add_output(pc)


COMMANDS = {"registry": (cmd_registry, add_registry_parser)}
