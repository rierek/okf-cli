import difflib
import os

from okf.catalogue import write_file_verbatim


def _lines(text):
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n\\ No newline at end of file\n"
    return lines


def unified_diffs(plan):
    """[{path, old_path, diff}, ...] ordered by path for a plan of (path, old_text, new_text)
    entries: one entry per changed file, headed `a/<path>` and `b/<path>`; entries whose old and
    new text are equal are omitted. An `old_text` of None is a file the write run creates: its
    diff is headed `/dev/null` and `b/<path>`, as git prints it. `old_path` is None: no entry is
    a rename."""
    return [{"path": path, "old_path": None,
             "diff": "".join(difflib.unified_diff(
                 _lines(old or ""), _lines(new),
                 "/dev/null" if old is None else "a/" + path, "b/" + path))}
            for path, old, new in sorted(plan) if old != new]


def write_plan(root, plan):
    """Write the new text of every (path, old_text, new_text) entry under `root`, byte for byte,
    creating missing directories; entries whose texts are equal are left alone."""
    for path, old, new in plan:
        if old != new:
            ap = os.path.join(root, path)
            os.makedirs(os.path.dirname(ap), exist_ok=True)
            write_file_verbatim(ap, new)
