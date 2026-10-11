"""migrate: replace the frontmatter `timestamp` of every concept by `generated {by, at}` (OKF 0.2),
with `at` read from git (the concept's last body-changing commit, OKF D18) and never from
`timestamp`. Dry-run by default: the preview is the plan, `--apply` writes exactly that plan."""

import os

from okf.catalogue import (
    iter_concepts, load_okf_config, read_file_verbatim, read_frontmatter, render_frontmatter,
    require_bundle_dir, resolve_scopes, write_file_verbatim,
)
from okf.diffs import unified_diffs
from okf.errors import OkfError
from okf.history import History
from okf.output import _add_output, _note
from okf.parser_support import _complete_scopes, _sub
from okf.spec import parse_actor


# D37: the binding, complete per-value `status` decision.
STATUS_MAP = {
    "obsolete": "deprecated", "deleted": "deprecated", "archived": "deprecated",
    "accepted": "stable", "active": "stable", "passive": "stable", "stable": "stable",
    "todo": "draft", "planned": "draft", "in-bearbeitung": "draft", "experimental": "draft",
    "draft": "draft", "deprecated": "deprecated",
}


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
