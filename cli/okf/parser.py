"""The parser builder: the explicit list of command modules, the merged COMMAND_TABLE
and COMMAND_DISPATCH, build_parser and the command overview prime renders."""

import argparse

from okf import (
    check, ctx, find, fts, index, install, migrate, navigation, prime, recent, rename, semantic, sync,
    tags, verify, wikilinks,
)
from okf.parser_support import (
    _complete_dirs, merge_commands, render_command_overview, subcommand_parsers,
)


# Command modules under cli/okf/ that own their commands. Each defines COMMANDS in
# the same {name: (handler, add_parser)} form; moving a command means moving its
# COMMANDS entry into its module and listing the module here.
COMMAND_MODULES = (
    check, ctx, find, fts, index, install, migrate, navigation, prime, recent, rename, semantic, sync,
    tags, verify, wikilinks,
)

COMMAND_TABLE = merge_commands(*(module.COMMANDS for module in COMMAND_MODULES))
COMMAND_DISPATCH = {name: handler for name, (handler, _add_parser) in COMMAND_TABLE.items()}


def build_parser(description=None):
    ap = argparse.ArgumentParser(prog="okf", description=description,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", help="catalogue root (default: the nearest catalogue above cwd, "
                    "else root in ~/.config/okf/config.toml; hard-fails if neither)").completer = _complete_dirs
    ap.add_argument("--global", dest="use_global", action="store_true",
                    help="use the root in ~/.config/okf/config.toml, even when a catalogue lies above cwd "
                    "(not with --root)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in sorted(COMMAND_TABLE):
        COMMAND_TABLE[name][1](sub)
    ap.epilog = render_command_overview(sub.choices)
    return ap


def command_overview(width=96):
    """The command directory as prime needs it: built from a fresh parser, so
    a newly registered subcommand reaches the onboarding text without anyone
    editing the onboarding text."""
    return render_command_overview(subcommand_parsers(build_parser()),
                                   footer=False, width=width)
