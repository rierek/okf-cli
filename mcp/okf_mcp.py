#!/usr/bin/env python3
"""okf-MCP — mechanical okf-cli verbs as MCP tools. Thin subprocess wrapper;
all correctness logic lives in okf-cli.py."""
import os

# command -> (positional param names, supports --json)
_COMMANDS = {
    "find":  (["query"], False),
    "read":  (["path"], False),
    "toc":   (["path"], False),
    "index": (["bundle"], True),
    "list":  ([], True),
    "check": (["target"], True),
    "reindex": (["target"], False),
    "refs":  (["path"], True),
    "rename": (["old", "new"], False),
}
# optional value-flag params: tool-key -> okf-cli flag
_FLAGS = {"scan_root": "--scan-root", "type": "--type", "tag": "--tag", "limit": "--limit"}
# optional boolean-flag params: tool-key -> okf-cli flag (emitted when truthy)
_BOOL_FLAGS = {"apply": "--apply", "force": "--force"}


def build_argv(root, command, params):
    if command not in _COMMANDS:
        raise ValueError("unsupported okf command: {}".format(command))
    positional, supports_json = _COMMANDS[command]
    argv = ["--root", root, command]
    for name in positional:
        val = params.get(name)
        if val is not None and val != "":
            argv.append(str(val))
    for key, flag in _FLAGS.items():
        if params.get(key) not in (None, ""):
            argv += [flag, str(params[key])]
    for key, flag in _BOOL_FLAGS.items():
        if params.get(key):
            argv.append(flag)
    if supports_json:
        argv.append("--json")
    return argv


import json
import subprocess

OKF_CLI = os.environ.get("OKF_CLI",
    os.path.join(os.path.expanduser("~"), "Obsidian", "tools", "okf-tools", "cli", "okf-cli.py"))


def run_okf(root, command, params):
    """Invoke okf-cli.py, return parsed JSON for --json commands else raw text.
    Note: check exits 1 on violations — that is data, not a crash, so exit code
    is only treated as an error for non-check commands."""
    argv = build_argv(root, command, params)
    proc = subprocess.run(["python3", OKF_CLI] + argv, capture_output=True, text=True)
    if proc.returncode != 0 and command != "check":
        raise RuntimeError("okf-cli {} failed: {}".format(command, proc.stderr.strip()))
    out = proc.stdout
    if _COMMANDS[command][1]:  # supports_json
        return json.loads(out) if out.strip() else {}
    return out


def _register(server):
    @server.tool()
    def okf_find(root: str, query: str, limit: int = 10) -> list:
        """Ranked keyword search across a catalogue/repo root."""
        return run_okf(root, "find", {"query": query, "limit": limit})

    @server.tool()
    def okf_read(root: str, path: str) -> str:
        """Print one concept page (bundle/concept-id)."""
        return run_okf(root, "read", {"path": path})

    @server.tool()
    def okf_toc(root: str, path: str) -> str:
        """Section headings of a concept."""
        return run_okf(root, "toc", {"path": path})

    @server.tool()
    def okf_index(root: str, bundle: str = "") -> dict:
        """Catalogue/bundle TOC."""
        return run_okf(root, "index", {"bundle": bundle})

    @server.tool()
    def okf_list(root: str, type: str = "", tag: str = "") -> dict:
        """Concepts filtered by frontmatter type and/or tag."""
        return run_okf(root, "list", {"type": type, "tag": tag})

    @server.tool()
    def okf_check(root: str, target: str = "") -> dict:
        """§9 conformance scan (config-aware TYPES). Returns {errors, warnings}."""
        return run_okf(root, "check", {"target": target})

    @server.tool()
    def okf_reindex(root: str, target: str) -> str:
        """Regenerate marker-bounded index listings for a bundle/subdir."""
        return run_okf(root, "reindex", {"target": target})

    @server.tool()
    def okf_refs(root: str, path: str, scan_root: str = "") -> dict:
        """Inbound markdown references to a file (reference-integrity step a)."""
        return run_okf(root, "refs", {"path": path, "scan_root": scan_root})

    @server.tool()
    def okf_rename(root: str, old: str, new: str, apply: bool = False,
                   force: bool = False) -> str:
        """Move a concept and keep every reference intact: rewrites inbound links
        repo-wide plus the file's own outbound links on a bundle change, then
        reindexes affected bundles. Defaults to a dry-run preview; pass apply=True
        to perform the move (git mv, staged). Reference-integrity step b."""
        return run_okf(root, "rename", {"old": old, "new": new, "apply": apply, "force": force})

    return server


if __name__ == "__main__":
    from mcp.server.fastmcp import FastMCP
    _register(FastMCP("okf")).run()
