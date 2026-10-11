"""One output path for every command: the `--json` flag, the one-envelope emitter around
the entry point, and the call note.

A command registered through `_add_output` answers `--json` with exactly one envelope
{command, ok, data, warnings, error} on stdout. Its handler returns `data` and prints
nothing in that mode; a classified failure is an OkfError, whose optional result becomes
`data`. Every note a call raises goes through `_note`: a stderr line in text mode, an entry
of the envelope's `warnings` in envelope mode.
"""

import json
import sys
import traceback

from okf.errors import EXIT_CODES, OkfError

_warnings = None  # the notes of the running envelope call; None in text mode


def _add_output(parser):
    """Register `--json` and mark the parser as envelope-emitting. The one place that
    registers `--json` for a converted command."""
    parser.add_argument("--json", action="store_true",
                        help="print one JSON envelope {command, ok, data, warnings, error}")
    parser.set_defaults(envelope=True)


def _note(message):
    """The one call-note path. `message` is the note text without the `note: ` prefix."""
    if _warnings is None:
        print("note: " + message, file=sys.stderr)
    else:
        _warnings.append(message)


def wants_envelope(args):
    return bool(getattr(args, "envelope", False) and getattr(args, "json", False))


def command_name(args):
    """The subcommand as typed; a ctx verb is `ctx <verb>`."""
    verb = getattr(args, "ctx_verb", None)
    return "{} {}".format(args.cmd, verb) if verb else args.cmd


def run_envelope(args, call):
    """Run `call()`, print the one envelope and return the exit code."""
    global _warnings
    _warnings = warnings = []
    error = None
    try:
        try:
            data = call()
        except OkfError as failure:
            data, error = failure.result, _error(failure.kind, failure.message or failure.kind)
        document = _dumps(args, data, warnings, error)
    except Exception as failure:  # unclassified, or data that JSON cannot hold
        traceback.print_exc()
        error = _error("internal", "{}: {}".format(type(failure).__name__, failure))
        document = _dumps(args, None, warnings, error)
    finally:
        _warnings = None
    print(document)
    return error["code"] if error else 0


def _error(kind, message):
    return {"kind": kind, "code": EXIT_CODES[kind], "message": message}


def _dumps(args, data, warnings, error):
    return json.dumps({"command": command_name(args), "ok": error is None, "data": data,
                       "warnings": warnings, "error": error}, ensure_ascii=False)
