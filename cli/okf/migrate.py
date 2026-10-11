"""migrate: replace the frontmatter `timestamp` of every concept by `generated {by, at}` (OKF 0.2),
with `at` read from git (the concept's last body-changing commit, OKF D18) and never from
`timestamp`. Dry-run by default: the preview is the plan, `--apply` writes exactly that plan."""

import os
import re

from okf.catalogue import (
    CROSSLINK_RE, fence_line_spans, iter_concepts, iter_headings, load_okf_config, read_file_verbatim,
    read_frontmatter, render_frontmatter, require_bundle_dir, resolve_scopes, write_file_verbatim,
)
from okf.diffs import unified_diffs
from okf.errors import OkfError
from okf.history import History
from okf.output import _add_output, _note
from okf.parser_support import _complete_scopes, _sub
from okf.spec import parse_actor
from okf.linkscan import LIST_ITEM_RE


# D37: the binding, complete per-value `status` decision.
STATUS_MAP = {
    "obsolete": "deprecated", "deleted": "deprecated", "archived": "deprecated",
    "accepted": "stable", "active": "stable", "passive": "stable", "stable": "stable",
    "todo": "draft", "planned": "draft", "in-bearbeitung": "draft", "experimental": "draft",
    "draft": "draft", "deprecated": "deprecated",
}

CITATION_HEADINGS = {"citations", "quellen", "sources"}
# A markdown link, an inline code span or a bare URL; the alternation keeps a URL inside a link
# target from counting twice.
RESOURCE_RE = re.compile(r"(?P<link>{})|(?P<code>(?P<ticks>`+)(?:(?!(?P=ticks)).)+?(?P=ticks))"
                         r"|(?P<url>https?://[^\s<>`)]+)".format(CROSSLINK_RE.pattern))
FILE_EXT_RE = re.compile(r"\.[A-Za-z0-9]{1,8}$")


def _resources(text):
    """The resources of one block text, in order of appearance."""
    out = []
    for m in RESOURCE_RE.finditer(text):
        if m.group("link"):
            target = CROSSLINK_RE.fullmatch(m.group("link")).group(2).strip().strip("<>").split()
            out.append(target[0] if target else "")
        elif m.group("code"):
            code = m.group("code").strip("`").strip()
            if "/" in code or FILE_EXT_RE.search(code):
                out.append(code)
        else:
            out.append(m.group("url").rstrip(".,;:!?"))
    return [r for r in out if r]


def _citation_blocks(lines):
    """The blocks (paragraph or list item, as text) of section lines, or (None, reason)."""
    if any(fence_line_spans(lines)):
        return None, "section holds fenced code"
    blocks, cur = [], None
    for line in lines:
        s = line.strip()
        if not s:
            cur = None
        elif s.startswith("|"):
            return None, "section holds a table"
        elif s.startswith(">"):
            return None, "section holds a quote"
        elif LIST_ITEM_RE.match(line):
            cur = [LIST_ITEM_RE.sub("", line, count=1).strip()]
            blocks.append(cur)
        elif cur is None:
            cur = [s]
            blocks.append(cur)
        else:
            cur.append(s)
    return [" ".join(b) for b in blocks], None


def _citation_sources(body):
    """(new body, sources entries, reason). Reason is None when every citation section of `body`
    migrates mechanically (D24): the sections are then cut out of the new body; with no citation
    section the body and the entries are empty; else new body is None and reason says why not."""
    lines, heads = body.splitlines(keepends=True), list(iter_headings(body))
    drop, entries, k = set(), [], 0
    while k < len(heads):
        level, text, start = heads[k]
        k += 1
        if text.casefold() not in CITATION_HEADINGS:
            continue
        end = len(lines)
        for lv, _t, ln in heads[k:]:
            if lv <= level:
                end = ln
                break
        if any(start < ln < end for _lv, _t, ln in heads[k:]):
            return None, [], "citation section {!r} holds a sub-heading".format(text)
        blocks, reason = _citation_blocks(lines[start + 1:end])
        if reason:
            return None, [], "citation section {!r}: {}".format(text, reason)
        if not blocks:
            return None, [], "citation section {!r} holds no block".format(text)
        for block in blocks:
            found = _resources(block)
            if not found:
                return None, [], "citation section {!r}: block without a resource: {}".format(text, block)
            entries += [{"resource": r} for r in found]
            entries[len(entries) - len(found)]["title"] = block
        drop.update(range(start, end))
    if not drop:
        return body, [], None
    return "".join(ln for i, ln in enumerate(lines) if i not in drop), entries, None


def _author_table(root):
    """The `git_authors` table of `.okf.toml` ({email: actor}); invalid_input when it or one of its
    values does not follow the actor convention, before any file is planned."""
    table = load_okf_config(root).get("git_authors", {})
    if not isinstance(table, dict):
        raise OkfError("invalid_input", "git_authors in .okf.toml is not a table of email = actor")
    for email, actor in table.items():
        if parse_actor(actor) is None:
            raise OkfError("invalid_input", "git_authors[{}] in .okf.toml is not an actor "
                           "(human:<id>, process:<id> or <producer>/<version>): {!r}".format(email, actor))
    return table


def _plan(root, target):
    """([(path, old_text, new_text), ...], [{path, field, reason}, ...], {old status: count})."""
    authors = _author_table(root)
    history = History(root)
    plan, unresolved, counts = [], [], {}
    try:
        for _bundle, bundle_path in resolve_scopes(root, target):
            for _cid, ap in iter_concepts(bundle_path):
                text = read_file_verbatim(ap)
                split = read_frontmatter(text) if text is not None else None
                if split is None or split.data is None:
                    continue
                path = os.path.relpath(ap, root).replace(os.sep, "/")
                data = split.data
                changed = False
                if "status" in data:
                    old = data["status"]
                    new = STATUS_MAP.get(old) if isinstance(old, str) else None
                    key = old if isinstance(old, str) else repr(old)
                    counts[key] = counts.get(key, 0) + 1
                    if new is None:
                        unresolved.append({"path": path, "field": "status",
                                           "reason": "no recorded decision for status value {!r}".format(old)})
                    elif new != old:
                        data["status"] = new
                        changed = True
                if "timestamp" in data:
                    if "generated" not in data:
                        commit = history.last_body_commit(ap)
                        if commit is None:
                            unresolved.append({"path": path, "field": "generated",
                                               "reason": "no body-changing commit found in git history"})
                            continue_ts = True
                        else:
                            by = authors.get(commit.email) or "human:" + commit.email.partition("@")[0]
                            if parse_actor(by) is None:
                                unresolved.append({"path": path, "field": "generated.by", "reason":
                                                   "author email {!r} maps to no actor; add it to git_authors"
                                                   .format(commit.email)})
                                continue_ts = True
                            else:
                                continue_ts = False
                                data.insert(list(data).index("timestamp"), "generated",
                                            {"by": by, "at": commit.time.isoformat()})
                    else:
                        continue_ts = False
                    if not continue_ts:
                        del data["timestamp"]
                        changed = True
                new_body, entries, reason = _citation_sources(split.body)
                if reason:
                    unresolved.append({"path": path, "field": "sources", "reason": reason})
                elif entries:
                    if data.get("sources"):
                        unresolved.append({"path": path, "field": "sources", "reason":
                                           "concept already carries sources; rework the citation section by hand"})
                    else:
                        data["sources"] = entries
                        split = split._replace(body=new_body)
                        changed = True
                if changed:
                    plan.append((path, text, render_frontmatter(split)))
    finally:
        history.close()
    for note in history.notes():
        _note(note)
    return plan, unresolved, counts


def cmd_migrate(root, args):
    if args.target:
        require_bundle_dir(root, args.target)
    plan, unresolved, counts = _plan(root, args.target)
    files = unified_diffs(plan)
    if args.apply:
        for path, _old, new in plan:
            write_file_verbatim(os.path.join(root, path), new)
    mapping = [{"old": old, "new": STATUS_MAP.get(old), "count": n} for old, n in sorted(counts.items())]
    if not getattr(args, "json", False):
        if mapping:
            print("status mapping:")
            for m in mapping:
                print("  {} -> {} ({} concept(s))".format(m["old"], m["new"] or "(no decision)", m["count"]))
        for entry in files:
            print(entry["diff"], end="")
        for entry in unresolved:
            print("unresolved {}: {}".format(entry["path"], entry["reason"]))
        print("migrate: {} {} file(s), {} unresolved{}".format(
            "migrated" if args.apply else "would migrate", len(files), len(unresolved),
            "" if args.apply else "; dry-run: re-run with --apply"))
    return {"applied": bool(args.apply), "files": files, "unresolved": unresolved,
            "status_mapping": mapping}


def add_migrate_parser(sub):
    pm = _sub(sub, "migrate", "maintenance",
              "migrate frontmatter to OKF 0.2: `timestamp` to `generated` (git), `status` per D37 (dry-run default)")
    pm.add_argument("target", nargs="?",
                    help="<bundle> or <bundle>/<subdir> (default: whole catalogue)").completer = _complete_scopes
    pm.add_argument("--apply", action="store_true",
                    help="write the previewed changes (default: dry-run preview only)")
    _add_output(pm)


COMMANDS = {"migrate": (cmd_migrate, add_migrate_parser)}
