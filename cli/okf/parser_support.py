"""Parser registration shared by every command: the group registry, the _sub
subparser factory, the COMMANDS merge, the grouped command overview and the
generic completers."""

import argparse
import os
import re
import textwrap

from okf.catalogue import (
    all_tags, catalogue_root, iter_concepts, list_bundles, load_okf_config, read_file,
)


def subcommand_parsers(ap):
    """{name: parser} for a built parser's subcommands. argparse exposes the
    individual subparsers only through the subparsers action, so the private
    attribute access is contained here rather than spread across tests."""
    for action in ap._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action.choices
    return {}


def parser_actions(parser):
    """Every argparse action of a parser except the auto-added -h/--help.
    Same contained-private-access rationale as subcommand_parsers()."""
    return [a for a in parser._actions
            if not isinstance(a, argparse._HelpAction)]


_GROUP_ORDER = ("navigation", "search", "tags", "maintenance")

# command name -> group; filled by _sub() at registration time, so it can
# never disagree with the parser it describes.
COMMAND_GROUPS = {}


def _sub(sub, name, group, summary, **kwargs):
    """Register one subcommand. The summary is authored exactly once, here,
    and reaches both help levels: argparse prints it in the top-level command
    directory (help=) and at the top of `okf-cli.py <command> --help`
    (description=). The group feeds the rendered overview in the epilog.

    A command cannot ship undocumented: summary and group are required
    positionals, and CommandHelpConformance asserts the rest."""
    if group not in _GROUP_ORDER:
        raise ValueError("unknown command group: {}".format(group))
    COMMAND_GROUPS[name] = group
    return sub.add_parser(name, help=summary, description=summary, **kwargs)


def merge_commands(*mappings):
    """One {name: (handler, add_parser)} table from several COMMANDS mappings.
    A command owned by two mappings is a registration bug and fails fast, as
    _sub does for an unknown group."""
    table = {}
    for mapping in mappings:
        for name, entry in mapping.items():
            if name in table:
                raise ValueError("command registered twice: {}".format(name))
            table[name] = entry
    return table


def render_command_overview(parsers, footer=True, width=96):
    """The purpose-grouped command directory, rendered from the registered
    parsers (D02/D03). argparse's own listing above it is flat and
    alphabetical; this block answers "what can this CLI do" by purpose. Both
    come from the same registrations, so neither can drift from the other.

    `parsers` is the {name: parser} mapping from subcommand_parsers(). The
    same block is the command section of `prime` (okf-cli-3hjr), which is why
    the footer — a --help cross-reference — is optional there. `width` is the
    wrap column; `prime --compact` raises it so each command costs one line
    instead of two-plus a 21-space continuation indent."""
    lines = ["commands by purpose:"]
    for group in _GROUP_ORDER:
        names = sorted(n for n, g in COMMAND_GROUPS.items() if g == group)
        if not names:
            continue
        lines.append("  {}:".format(group))
        for name in names:
            lines.append(textwrap.fill(
                parsers[name].description, width=width,
                initial_indent="    {:<16} ".format(name),
                subsequent_indent=" " * 21))
    if footer:
        lines.append("")
        lines.append("run `okf-cli.py <command> --help` for one command's options.")
    return "\n".join(lines)


# --- shell TAB completion (argcomplete; optional dependency) ---------------
# main() hands the parser to argcomplete only when a shell's completion glue
# (cli/_okf-cli for zsh; argcomplete's own shellcode for bash and fish, all
# placed by `install`) runs us with _ARGCOMPLETE set; a normal run never
# imports it. Each value-taking argument names its completer via
# `.completer` in build_parser;
# argcomplete calls it as completer(prefix=, action=, parser=, parsed_args=).
# Arguments without one complete to nothing (main() passes SuppressCompleter
# as the default): free text like a find query must not offer cwd files.


def _completion_root(parsed_args):
    """The catalogue root a completer reads, or None. --root arrives as the raw
    shell word: the glue joins zsh's alias-expanded $words, so
    `alias okf='okf-cli --root ~/…'` delivers an unexpanded `~`."""
    explicit = getattr(parsed_args, "root", None)
    root = catalogue_root(os.path.expanduser(explicit) if explicit else None)
    return root if root and os.path.isdir(root) else None


def _complete_types(parsed_args, **_):
    root = _completion_root(parsed_args)
    if root is None:
        return []
    # Same source resolution as run_checks: .okf.toml types_source, else <root>/TYPES.md.
    src = load_okf_config(root).get("types_source") or os.path.join(root, "TYPES.md")
    if not os.path.isfile(src):
        return []
    out = {}
    for line in read_file(src).splitlines():
        m = re.match(r"\|\s*`([^`]+)`\s*\|(.*)\|\s*$", line)
        if m:
            # Description = last table cell, first sentence (rank/mapping cells sit before it).
            cells = [c.strip() for c in m.group(2).split("|") if c.strip()]
            out[m.group(1)] = re.split(r"(?<=[.!?])\s", cells[-1], maxsplit=1)[0][:100] if cells else ""
    return dict(sorted(out.items()))


def _complete_tags(parsed_args, **_):
    """Tags in use, most used first, usage count as the description."""
    root = _completion_root(parsed_args)
    if root is None:
        return {}
    ranked = sorted(all_tags(root).items(), key=lambda kv: (-kv[1], kv[0]))
    return {tag: "concepts: {}".format(n) for tag, n in ranked}


def _complete_bundles(parsed_args, **_):
    root = _completion_root(parsed_args)
    return list_bundles(root) if root else []


def _complete_scopes(parsed_args, **_):
    """<bundle> and every <bundle>/<subdir> that holds a concept."""
    root = _completion_root(parsed_args)
    if root is None:
        return []
    out = set()
    for b in list_bundles(root):
        out.add(b)
        for cid, _ap in iter_concepts(os.path.join(root, b)):
            parts = cid.split("/")[:-1]
            for i in range(1, len(parts) + 1):
                out.add("/".join([b] + parts[:i]))
    return sorted(out)


def _complete_concepts(prefix, parsed_args, suffix="", **_):
    """<bundle>/<concept-id> refs; the `_archive/` mirror once the prefix
    starts with `_archive/` or `archive --restore` is on the line."""
    root = _completion_root(parsed_args)
    if root is None:
        return []
    lead = ""
    if prefix.startswith("_archive/") or getattr(parsed_args, "restore", False):
        root, lead = os.path.join(root, "_archive"), "_archive/"
        if not os.path.isdir(root):
            return []
    return sorted("{}{}/{}{}".format(lead, b, cid, suffix)
                  for b in list_bundles(root)
                  for cid, _ap in iter_concepts(os.path.join(root, b)))


def _complete_concept_files(**kwargs):
    """The same refs with `.md`, for arguments that take a file path."""
    return _complete_concepts(suffix=".md", **kwargs)


def _complete_files(**kwargs):
    import argcomplete
    return argcomplete.FilesCompleter()(**kwargs)


def _complete_dirs(**kwargs):
    import argcomplete
    return argcomplete.DirectoriesCompleter()(**kwargs)
