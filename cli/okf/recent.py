"""recent: the git add-event parser, the repository grouping, the ranking and
rendering of the newest concepts, and the recent command."""

import datetime
import os
import re
import subprocess
from okf.errors import OkfError
from okf.output import _add_output, _note

from okf import catalogue
from okf.catalogue import (
    fm_meta, iter_concepts, meta_of, read_file, read_frontmatter, resolve_scopes,
)
from okf.find_filters import compile_where
from okf.parser_support import _add_filters, _sub


# --- recent: concepts by the commit that added them ------------------------
# `log` answers "what moved" at commit granularity; `recent` answers "what is
# new" at concept granularity. The date source is git and only git: the
# frontmatter `timestamp` covers 1789 of 2559 concepts (qm-wiki, 30% of the
# catalogue, carries two) and where it exists it is a migration batch stamp —
# 510 distinct values over 1789 concepts, the most frequent one repeated 125
# times to the second, so a batch has no internal order. mtime is likewise out:
# normalize-tags/reindex/fix-crosslinks rewrite files wholesale and a fresh
# clone flattens every mtime to checkout time.
#
# git as a source is SPEC-sanctioned, not a layering break: SPEC.md §2 names a
# git repository as the recommended shape ("provides history, attribution,
# diffs") and §7 defines `**Creation**` as a log entry type. Recent and other
# read git since the beginning.
RECENT_TS_RE = re.compile(r"^@(\d+)$")
UNCOMMITTED = "(uncommitted)"
CREATED_FMT = "%Y-%m-%d %H:%M"


def parse_add_events(stdout):
    """{repo_rel_path: unix_ts} from the stanza stream of
    `git log --no-renames --diff-filter=A --format=@%at --name-only`.

    A stanza is one `@<unixtime>` line, a blank line, then the paths that
    commit added. git emits newest-commit-first, so the FIRST sighting of a
    path is its LATEST add and setdefault keeps it: a path deleted and re-added
    dates from the re-add (D11). Only `@<digits>` opens a stanza — `@notes/x.md`
    is a path. Paths before any stanza header have no timestamp and are dropped.
    """
    events, ts = {}, None
    for line in stdout.splitlines():
        if not line.strip():
            continue
        m = RECENT_TS_RE.match(line)
        if m:
            ts = int(m.group(1))
        elif ts is not None:
            events.setdefault(line, ts)
    return events


def concept_git_key(prefix, cid):
    """The repo-relative path git prints for one concept: `docs/x-okf/a/b.md`.

    Composed from the bundle's repo-relative prefix and the bundle-relative
    concept id iter_concepts() already yields — never derived via
    os.path.relpath(abspath, repo). relpath is purely lexical and does not
    resolve symlinks, so for a symlinked bundle it returns
    `../../Obsidian/Knowledge-Catalogue/<bundle>/x.md`, a path git never prints:
    measured 78 of 78 symlinked concepts undated. Building the key instead of
    deriving it is what makes the foreign-repo path work at all."""
    return "{}/{}.md".format(prefix, cid) if prefix else "{}.md".format(cid)


def group_scopes_by_repo(scopes):
    """[(bundle, repo_top, prefix), …] → [(repo_top, [(bundle, prefix), …]), …]
    in first-seen order. One entry per repo means one git process per repo,
    however many bundles it owns. Scopes with no repo are dropped — their
    concepts still list, undated, and cmd_recent has already noted why."""
    grouped, order = {}, []
    for bundle, repo, prefix in scopes:
        if repo is None:
            continue
        if repo not in grouped:
            grouped[repo] = []
            order.append(repo)
        grouped[repo].append((bundle, prefix))
    return [(repo, grouped[repo]) for repo in order]


def rank_recent(entries, limit):
    """Top-`limit` of [(path, ts_or_None), …], newest first.

    Undated rows sort after every dated one (D09): during an _inbox drain —
    the very session this command serves — dozens of concepts are untracked at
    once, and sorting them first would spend the whole `--limit` on scratch
    files. Equal timestamps break by path so the output is reproducible; one
    commit adding forty concepts is the common case, not the exception."""
    if limit <= 0:
        return []
    ordered = sorted(entries,
                     key=lambda e: (-(e[1] if e[1] is not None else -1), e[0]))
    return ordered[:limit]


def format_created(ts, tz=None):
    """`2026-08-05 18:48`, or a placeholder padded to the same width when the
    concept has no add-event. `tz` is injectable so tests are timezone-proof;
    production passes None, i.e. local time — which is what someone reading
    their own catalogue means by "when did I write this"."""
    if ts is None:
        return UNCOMMITTED.ljust(len(datetime.datetime(2026, 1, 1).strftime(CREATED_FMT)))
    return datetime.datetime.fromtimestamp(ts, tz).strftime(CREATED_FMT)


def render_recent_lines(rows, tz=None):
    """rows: [(ts_or_None, type, path), …] already ranked → one line each.

    The type column is padded to the widest type IN THIS RESULT SET, not to a
    fixed width — a listing of ten Runbooks should not carry the whitespace of
    a `LessonLearned` that is not there."""
    if not rows:
        return []
    width = max(len(t) for _ts, t, _p in rows)
    return ["{}  {}  {}".format(format_created(ts, tz), ctype.ljust(width), path)
            for ts, ctype, path in rows]


def iso_created(ts, tz=None):
    """ISO-8601 with offset, or None. The json branch carries this next to the
    raw unix int: one field a human or an LLM reads, one a consumer sorts on
    without parsing anything."""
    if ts is None:
        return None
    dt = datetime.datetime.fromtimestamp(ts, tz)
    return (dt if dt.tzinfo else dt.astimezone()).isoformat()


def _git_add_events(repo, prefixes):
    """(stdout, None) or (None, 'no-git'|'no-repo'). Exactly one git process.

    --no-renames is load-bearing, not tidiness: with git's default rename
    detection a `git mv` is classified R and --diff-filter=A drops it, so every
    concept `okf-cli rename` has ever moved becomes undatable. Measured against
    the real catalogue: 4 concepts missing with detection on, 0 with it off.

    core.quotepath=false so a path with an umlaut arrives raw instead of
    C-quoted — none in the catalogue today, but the parser must not silently
    lose the first one."""
    cmd = ["git", "-C", repo, "-c", "core.quotepath=false", "log",
           "--no-renames", "--diff-filter=A", "--format=@%at", "--name-only",
           "--"] + (list(prefixes) or ["."])
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
    except (FileNotFoundError, OSError):
        return None, "no-git"
    if res.returncode != 0:
        return None, "no-repo"
    return res.stdout, None


def _recent_scopes(root, include_archive):
    """[(bundle, bundle_path, repo_top_or_None, prefix_or_None), …].

    Classification is by realpath, not os.path.islink: islink only sees a link
    in the last component, so a bundle reached through a symlinked parent — or
    a link pointing back INTO the catalogue — would be filed under the wrong
    repo. The `+ os.sep` on the containment test keeps a sibling directory
    named `<catalogue>-old` from being mistaken for catalogue-owned."""
    realroot = os.path.realpath(root)
    root_top, reason = catalogue._git_toplevel(realroot)
    if reason == "no-git":
        raise OkfError("internal", "recent: git binary not found — this command reads creation "
                       "dates from git history")
    if reason == "no-repo":
        raise OkfError("invalid_input",
                       "recent: catalogue root is not a git repository — no history to read")
    # The catalogue root need not be a repo root: okf-tools/docs has exactly
    # that shape, so its own prefix is not necessarily empty.
    root_prefix = os.path.relpath(realroot, root_top).replace(os.sep, "/")
    if root_prefix == ".":
        root_prefix = ""
    scopes = []
    for bundle, bp in resolve_scopes(root, None, include_archive):
        real = os.path.realpath(bp)
        if real == realroot or real.startswith(realroot + os.sep):
            sub = os.path.relpath(real, realroot).replace(os.sep, "/")
            sub = "" if sub == "." else sub
            prefix = "/".join(p for p in (root_prefix, sub) if p)
            scopes.append((bundle, bp, root_top, prefix))
            continue
        repo, why = catalogue._git_toplevel(real)
        if repo is None:
            _note("bundle `{}` resolves outside any git repository — its "
                  "concepts are listed undated; run `git init` in {}".format(
                      bundle, real if why == "no-repo" else real))
            scopes.append((bundle, bp, None, None))
            continue
        prefix = os.path.relpath(real, repo).replace(os.sep, "/")
        scopes.append((bundle, bp, repo, "" if prefix == "." else prefix))
    return scopes


def cmd_recent(root, args):
    filters = compile_where(args.where)
    scopes = _recent_scopes(root, filters.include_archive)
    by_repo = {}
    for repo, members in group_scopes_by_repo(
            [(b, repo, prefix) for b, _bp, repo, prefix in scopes]):
        stdout, why = _git_add_events(repo, [p for _b, p in members if p])
        if stdout is None:
            _note("git log failed in {} — its concepts are listed "
                  "undated; check the repository".format(repo))
            continue
        by_repo[repo] = parse_add_events(stdout)

    entries, meta, dated_repo = [], {}, {}
    for bundle, bp, repo, prefix in scopes:
        events = by_repo.get(repo) if repo is not None else None
        for cid, ap in iter_concepts(bp):
            rel = os.path.relpath(ap, root).replace(os.sep, "/")
            path = rel[:-3] if rel.endswith(".md") else rel
            if filters:
                # One read feeding the whole predicate and the frontmatter meta.
                text = read_file(ap)
                fm = read_frontmatter(text).data
                if not filters.matches_loaded(path, fm, text):
                    continue
                meta[path] = fm_meta(fm, cid)
            ts = events.get(concept_git_key(prefix, cid)) if events else None
            dated_repo[path] = events is not None
            entries.append((path, ts))

    total = len(entries)
    rows = rank_recent(entries, args.limit)
    # Without a filter no file was read yet: frontmatter is fetched for the
    # surviving rows only — ten reads instead of two and a half thousand.
    for path, _ts in rows:
        if path not in meta:
            ap = os.path.join(root, path + ".md")
            meta[path] = meta_of(ap)

    undated = sum(1 for path, ts in entries if ts is None and dated_repo.get(path))
    if undated:
        _note("{} concept(s) have no commit that added them — "
              "listed undated at the end; commit them to give them a "
              "creation date".format(undated))

    if getattr(args, "json", False):
        return [
            {"created": iso_created(ts), "created_ts": ts,
             "title": meta[path][1], "type": meta[path][0],
             "path": path, "description": meta[path][2]}
            for path, ts in rows
        ]
    if not rows:
        print("(no matches)")
        return
    for line in render_recent_lines([(ts, meta[path][0], path)
                                     for path, ts in rows]):
        print(line)
    # `recent` truncates by default, so a bare count would read as "the
    # catalogue holds ten concepts". Both numbers, always.
    print("recent: {} of {} concept(s)".format(len(rows), total))


def add_recent_parser(sub):
    prc = _sub(sub, "recent", "navigation",
               "list the most recently created concepts, newest first")
    prc.add_argument("--limit", type=int, default=10,
                     help="max results to print (default 10)")
    _add_filters(prc)
    _add_output(prc)


COMMANDS = {"recent": (cmd_recent, add_recent_parser)}
