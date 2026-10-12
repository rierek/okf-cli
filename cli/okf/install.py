"""The install command: loads okf_install.py, the agent, skill, MCP and shell
registration code that lives next to cli/okf-cli.py, and registers the parser block."""

import importlib.util
import os
from okf.errors import OkfError

from okf.output import _add_output
from okf.parser_support import _sub


def cmd_install(_root, args):
    """`install` never touches a catalogue (main() hands it no root). Its code
    lives in okf_install.py next to okf-cli.py, one directory above this package,
    loaded only when it runs. The path is resolved first: a symlink to okf-cli.py
    is how people put it on PATH."""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "okf_install.py")
    if not os.path.isfile(path):  # okf-cli.py copied out of its clone on its own
        raise OkfError(
            "internal",
            "ERROR: install needs okf_install.py next to okf-cli.py ({}); run it from a full clone "
            "or use pipx / uv tool install".format(os.path.dirname(path)))
    spec = importlib.util.spec_from_file_location("okf_install", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    code, report = mod.run(args)
    if code:
        raise OkfError("internal", "install failed with exit code {}".format(code), report)
    return report


# commands main() runs without resolving a catalogue root
CATALOGUE_FREE = frozenset({"install"})


def add_install_parser(sub):
    pin = _sub(sub, "install", "maintenance",
               "register okf, its agent skill, MCP server and shell completion with this "
               "machine's agents and shells (dry-run default; needs no catalogue)")
    pin.add_argument("--apply", action="store_true",
                     help="perform the plan (default: print the plan, change nothing)")
    pin.add_argument("--uninstall", action="store_true",
                     help="plan, or with --apply perform, the removal of everything install created")
    pin.add_argument("--only", metavar="NAMES",
                     help="comma-separated subset: claude, omp, codex, opencode, kimi, openclaw, hermes "
                          "(agents), zsh, bash, fish (shells). Default: install for every agent and "
                          "shell found on this machine; uninstall covers all of them")
    _add_output(pin)


COMMANDS = {"install": (cmd_install, add_install_parser)}
