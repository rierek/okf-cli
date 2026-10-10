"""Helpers shared by several test modules. Not a test module: the name has no
test_ prefix, so unittest discovery never collects it."""
from okf import find as okf_find


def run_find(root, query, **kw):
    """Module-level twin of the per-class _run() helper at
    cli/test_okf_cli.py:1381 — same in-process convention (SimpleNamespace
    args, cmd_find, redirected streams), but parameterised by root so the new
    suites can each use their own temp catalogue. Returns stdout."""
    import io
    import contextlib
    import types
    args = types.SimpleNamespace(
        query=query, limit=10, type=None, tag=None, scope=None,
        breakdown=False,
    )
    for k, v in kw.items():
        setattr(args, k, v)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
        okf_find.cmd_find(root, args)
    return buf.getvalue()
