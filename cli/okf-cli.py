#!/usr/bin/env python3
"""okf-cli.py — dependency-free navigation/search for an OKF Knowledge Catalogue.

Catalogue-aware fork inspired by Cole Medin's single-bundle okf-cli.py.
A *catalogue* is a directory whose immediate subdirectories (not starting with
'.' or '_') are OKF *bundles*. Standard library only — no install required.

Run `okf-cli.py --help` for the command directory (flat + grouped by purpose),
and `okf-cli.py <command> --help` for one command's options. Both are generated
from the parser — this file documents no command list by hand.

Run from the catalogue root, or pass --root <path>.
"""
import os
import sys

from okf.catalogue import catalogue_root
from okf.ctx import _ctx_shorthand
from okf.entry_support import _silence_broken_pipe_streams
from okf.errors import OkfError
from okf.install import CATALOGUE_FREE
from okf.parser import COMMAND_DISPATCH, build_parser


def main():
    try:
        ap = build_parser(__doc__)
        if "_ARGCOMPLETE" in os.environ:
            # Shell TAB completion (glue installed by `install`): optional
            # dependency, imported only on a completion run, which argcomplete
            # ends via os._exit.
            import argcomplete
            argcomplete.autocomplete(ap, default_completer=argcomplete.SuppressCompleter())
        args = ap.parse_args(_ctx_shorthand(sys.argv[1:]))
        if args.cmd in CATALOGUE_FREE:
            return COMMAND_DISPATCH[args.cmd](None, args)
        root = catalogue_root(args.root)
        if root is None:
            raise OkfError("not_found",
                           "ERROR: no catalogue found in cwd or its ancestors; pass --root <path>")
        if not os.path.isdir(root):
            raise OkfError("not_found",
                           "ERROR: root not found: {} (pass --root <path>)".format(root))
        if args.root and not (
            os.path.isfile(os.path.join(root, ".okf.toml"))
            or (os.path.isfile(os.path.join(root, "SPEC.md")) and os.path.isfile(os.path.join(root, "TYPES.md")))
        ):
            # SC-002 (test_explicit_root_returns_abspath_unchanged) requires an
            # explicit --root to keep working with no marker present, so this
            # never blocks. But every write command below computes emitted paths
            # as "/" + relpath(dest, root) (resolve_crosslink_target and peers) —
            # a --root pointed one level above the real catalogue silently
            # prefixes every emitted link with the extra segment instead of
            # failing (OKFT-czm9: a vault-relative alias like
            # "SPF_Sproutling/docs/sproutling-okf/e2e-tests/README.md" got
            # written and committed unnoticed). Loud-but-non-blocking, matching
            # this file's stderr-degradation idiom (see find's stale-index note).
            print("note: --root {} carries no catalogue marker (.okf.toml or "
                  "SPEC.md+TYPES.md) — if this is not the real catalogue root, "
                  "write commands will silently emit wrong paths".format(root),
                  file=sys.stderr)
        COMMAND_DISPATCH[args.cmd](root, args)
    except OkfError as error:
        sys.stdout.flush()
        if error.message:
            print(error.message, file=sys.stderr)
        raise SystemExit(error.code)


if __name__ == "__main__":
    try:
        main()
        # Explicit flush, still inside the try: stdout to a pipe is
        # block-buffered, not line-buffered, so a small answer (the common
        # case against the real catalogue, measured 2026-08-13) can finish
        # every print() into the buffer without ever attempting the OS-level
        # write() that would raise. Without this line the write only
        # happens implicitly at interpreter shutdown, OUTSIDE this
        # try/except, so BrokenPipeError is never caught at all and only
        # the "Exception ignored ..." shutdown noise appears — no
        # traceback, but still not clean. Confirmed against the real
        # catalogue: OKFT-0k55 Test-Output.
        sys.stdout.flush()
    except BrokenPipeError:
        _silence_broken_pipe_streams()
        sys.exit(0)
