"""Unified diffs of a planned set of file changes: the one preview shape of the commands that rewrite
files (`data.files` of their envelope)."""

import difflib


def _lines(text):
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n\\ No newline at end of file\n"
    return lines


def unified_diffs(plan):
    """[{path, old_path, diff}, ...] ordered by path for a plan of (path, old_text, new_text)
    entries: one entry per changed file, headed `a/<path>` and `b/<path>`; entries whose old and
    new text are equal are omitted. `old_path` is None: no entry is a rename."""
    return [{"path": path, "old_path": None,
             "diff": "".join(difflib.unified_diff(_lines(old), _lines(new), "a/" + path, "b/" + path))}
            for path, old, new in sorted(plan) if old != new]
