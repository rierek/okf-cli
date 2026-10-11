import difflib
import os

from okf.catalogue import write_file_verbatim


def _lines(text):
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n\\ No newline at end of file\n"
    return lines


def unified_diffs(plan, moves=None):
    """[{path, old_path, diff}, ...] ordered by path for a plan of (path, old_text, new_text)
    entries: one entry per changed file, headed `a/<path>` and `b/<path>`; entries whose old and
    new text are equal are omitted. An `old_text` of None is a file the write run creates: its
    diff is headed `/dev/null` and `b/<path>`, as git prints it; a `new_text` of None is a file
    the write run deletes, headed `a/<path>` and `/dev/null`. `moves` maps the path of a moved
    file to the path it came from: that entry's old_text is the text at the old path, its diff
    starts with git's `rename from` / `rename to` lines and is kept even when the text is
    unchanged, and `old_path` carries the old path. Other entries have `old_path` None."""
    moves = moves or {}
    out = []
    for path, old, new in sorted(plan):
        src = moves.get(path)
        if old == new and src is None:
            continue
        head = "rename from {}\nrename to {}\n".format(src, path) if src else ""
        body = "".join(difflib.unified_diff(
            _lines(old or ""), _lines(new or ""),
            "/dev/null" if old is None else "a/" + (src or path),
            "/dev/null" if new is None else "b/" + path)) if old != new else ""
        out.append({"path": path, "old_path": src, "diff": head + body})
    return out


def write_plan(root, plan):
    """Write the new text of every (path, old_text, new_text) entry under `root`, byte for byte,
    creating missing directories; entries whose texts are equal are left alone and entries that
    delete a file (new text None) are skipped: the caller removes or moves that file."""
    for path, old, new in plan:
        if old != new and new is not None:
            ap = os.path.join(root, path)
            os.makedirs(os.path.dirname(ap), exist_ok=True)
            write_file_verbatim(ap, new)
