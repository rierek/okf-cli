"""Modules behind cli/okf-cli.py.

catalogue, linkscan and parser_support are the shared foundation. A command
module defines COMMANDS, {name: (handler, add_parser)}; cli/okf-cli.py merges
them (parser_support.merge_commands) and registers every command in sorted name
order. Package modules import only package modules, never the entry file.
"""
