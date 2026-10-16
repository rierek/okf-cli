#!/usr/bin/env python3
"""Parity check of `okf install`: the Python CLI (the reference) and the Go binary, side by side.

For every fixture the same machine (a throwaway HOME, a PATH of logging stub CLIs, an installed-
package or source-tree layout) is built twice in the same place: first the Python CLI runs the
command sequence on it, then the machine is reset and the binary runs the same sequence. Per
command the exit code, stdout, stderr, the stub CLI calls and the whole machine state (file set,
bytes, modes, symlink targets, directories) must be equal, except the two allowed deviations:

  1. the PATH wrapper ~/.local/bin/okf starts the binary instead of `uv run --script cli/okf-cli.py`
     (D01, R-01: no interpreter or `uv` at CLI runtime);
  2. the content of the completion files comes from go/internal/complete instead of argcomplete
     (the zsh file is a plain file with the script instead of a symlink to / copy of cli/_okf).

Everything lives in one temporary directory that is removed at the end. The environment of every
run is built from scratch (HOME, PATH of the stubs, SHELL, the location variables a fixture sets
inside the temporary directory); the real `okf` is never on PATH. The real HOME's agent and shell
config paths are listed before and after: any change fails the run.

Usage: just install-parity [--only NAME] [--go-bin PATH] [--python PATH] [--list]
Exit 0: no difference outside the deviation list; 1: differences; 2: the check itself could not run.
"""
import argparse
import contextlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STEP_TIMEOUT = 150  # a stub that sleeps past the 30 s harness timeout is killed by install itself

HARNESSES = ("claude", "omp", "codex", "opencode", "kimi", "openclaw", "hermes")
HARNESS_DIR = {"claude": ".claude", "omp": ".omp/agent", "codex": ".codex", "opencode": ".config/opencode",
               "kimi": ".kimi-code", "openclaw": ".openclaw", "hermes": ".hermes"}
LOCATION_VARS = ("CLAUDE_CONFIG_DIR", "PI_CODING_AGENT_DIR", "PI_CONFIG_DIR", "CODEX_HOME", "OPENCODE_CONFIG",
                 "XDG_CONFIG_HOME", "XDG_DATA_HOME", "KIMI_CODE_HOME", "OPENCLAW_STATE_DIR", "HERMES_HOME",
                 "ZDOTDIR")

# --- stub CLIs (as in tests/test_okf_install.py, plus failure and sleep switches) --------------------------

STUB_HEAD = ('#!%s\nimport json, os, re, sys, time\n'
             'open(os.environ["OKF_STUB_LOG"], "a").write('
             'json.dumps([os.path.basename(sys.argv[0])] + sys.argv[1:]) + "\\n")\n'
             'if os.fstat(0).st_rdev != os.stat(os.devnull).st_rdev:\n'
             '    sys.exit("stdin is not /dev/null: a prompt could hang")\n'
             'time.sleep(float(os.environ.get("OKF_STUB_SLEEP", "0")))\n'
             'if os.path.basename(sys.argv[0]) in os.environ.get("OKF_STUB_FAIL", "").split(","):\n'
             '    sys.exit("boom: " + os.path.basename(sys.argv[0]) + " failed")\n')
STUBS = {
    "uv": "",
    "okf": "",
    "claude": '''
cfg = os.path.join(os.path.expanduser("~"), ".claude.json")
doc = json.load(open(cfg)) if os.path.exists(cfg) else {}
a = sys.argv[1:]
if a[:2] == ["mcp", "add"]:
    cmd = a[a.index("--") + 1:]
    servers = doc.setdefault("mcpServers", {})
    if a[a.index("--") - 1] in servers:
        sys.exit("already exists")
    servers[a[a.index("--") - 1]] = {"type": "stdio", "command": cmd[0], "args": cmd[1:], "env": {}}
elif a[:2] == ["mcp", "remove"]:
    if a[2] not in doc.get("mcpServers", {}):
        sys.exit("no such server")
    del doc["mcpServers"][a[2]]
json.dump(doc, open(cfg, "w"), indent=2)
''',
    "codex": '''
cfg = os.path.join(os.environ.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex"), "config.toml")
text = open(cfg).read() if os.path.exists(cfg) else ""
a = sys.argv[1:]
if a[:2] == ["mcp", "add"]:
    cmd = a[a.index("--") + 1:]
    if "[mcp_servers.okf]" in text:
        sys.exit("already exists")
    text += ("\\n" if text and not text.endswith("\\n") else "") + \\
        "[mcp_servers.okf]\\ncommand = %s\\nargs = %s\\n" % (json.dumps(cmd[0]), json.dumps(cmd[1:]))
elif a[:2] == ["mcp", "remove"]:
    text = re.sub(r"\\[mcp_servers\\.okf\\]\\n(?:(?!\\[).*\\n)*", "", text)
os.makedirs(os.path.dirname(cfg), exist_ok=True)
open(cfg, "w").write(text)
''',
    "openclaw": '''
cfg = os.path.join(os.environ.get("OPENCLAW_STATE_DIR") or os.path.join(os.path.expanduser("~"), ".openclaw"),
                   "openclaw.json")
a = sys.argv[1:]
os.makedirs(os.path.dirname(cfg), exist_ok=True)
doc = json.load(open(cfg)) if os.path.exists(cfg) else {}
servers = doc.setdefault("mcp", {}).setdefault("servers", {})
if a[:2] == ["mcp", "set"]:
    servers[a[2]] = json.loads(a[3])
elif a[:2] == ["mcp", "unset"]:
    servers.pop(a[2], None)
json.dump(doc, open(cfg, "w"))
''',
}


# --- one machine --------------------------------------------------------------------------------------------


class Machine:
    """tmp/m (home and everything a fixture puts around it), tmp/bin (stubs), tmp/pkg (the package)."""

    def __init__(self, tmp, layout, py_cli_src, go_bin, stub_python):
        self.tmp = tmp
        self.m = os.path.join(tmp, "m")
        self.home = os.path.join(self.m, "home")
        self.bin = os.path.join(tmp, "bin")
        self.cwd = os.path.join(tmp, "cwd")
        self.log = os.path.join(tmp, "calls.log")
        self.stub_python = stub_python
        for d in (self.home, self.bin, self.cwd):
            os.makedirs(d)
        self.layout = layout
        self.pkg, self.go_exe, self.py_cli = self.make_pkg(layout, py_cli_src, go_bin)
        self.env = {"HOME": self.home, "PATH": self.bin, "SHELL": "/bin/zsh", "OKF_STUB_LOG": self.log,
                    "PYTHONDONTWRITEBYTECODE": "1", "LANG": "C.UTF-8"}

    def make_pkg(self, layout, py_cli_src, go_bin):
        """source: a checkout (pyproject.toml, link mode); installed: a wheel layout (copy mode); brew: an
        installed package under <prefix>/Cellar/okf/1.0 with the opt symlink and the binary reached through
        <prefix>/bin/okf; source-link: a checkout whose binary is started through a symlink."""
        if layout == "brew":
            prefix = os.path.join(self.tmp, "brew")
            root = os.path.join(prefix, "Cellar", "okf", "1.0")
            os.makedirs(os.path.join(prefix, "opt"))
            os.makedirs(os.path.join(prefix, "bin"))
            os.symlink(os.path.join("..", "Cellar", "okf", "1.0"), os.path.join(prefix, "opt", "okf"))
            os.symlink(os.path.join("..", "Cellar", "okf", "1.0", "bin", "okf"), os.path.join(prefix, "bin", "okf"))
            go_exe = os.path.join(prefix, "bin", "okf")
            pkg_shown = os.path.join(prefix, "opt", "okf")
        else:
            root = os.path.join(self.tmp, "pkg")
            go_exe = os.path.join(root, "bin", "okf")
            pkg_shown = root
        self.put(os.path.join(root, "skills", "okf", "SKILL.md"), "---\nname: okf\ndescription: test skill\n---\nbody\n")
        self.put(os.path.join(root, "skills", "okf", "references", "a.md"), "ref\n")
        self.put(os.path.join(root, "skills", "okf", ".DS_Store"), "junk\n")
        self.put(os.path.join(root, "skills", "okf", "__pycache__", "x.pyc"), "junk\n")
        self.put(os.path.join(root, "mcp", "okf_mcp.py"), "# stub\n")
        shutil.copytree(py_cli_src, os.path.join(root, "cli"), ignore=shutil.ignore_patterns("__pycache__"))
        os.makedirs(os.path.join(root, "bin"), exist_ok=True)
        shutil.copy2(go_bin, os.path.join(root, "bin", "okf"))
        if layout in ("source", "source-link"):
            self.put(os.path.join(root, "pyproject.toml"), "")
        if layout == "source-link":
            link = os.path.join(self.tmp, "link")
            os.makedirs(link)
            os.symlink(os.path.join(root, "bin", "okf"), os.path.join(link, "okf"))
            go_exe = os.path.join(link, "okf")
        return pkg_shown, go_exe, os.path.join(root, "cli", "okf-cli.py")

    # fixtures
    def path(self, *parts):
        return os.path.join(self.home, *parts)

    def put(self, path, text, mode=None):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        if mode:
            os.chmod(path, mode)
        return path

    def link(self, path, target):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        os.symlink(target, path)

    def mkdir(self, *parts):
        os.makedirs(os.path.join(self.home, *parts), exist_ok=True)

    def stub(self, *names):
        for name in names:
            path = self.put(os.path.join(self.bin, name), STUB_HEAD % self.stub_python + STUBS[name])
            os.chmod(path, 0o755)

    def harness_dirs(self, *names):
        for n in names or HARNESSES:
            self.mkdir(*HARNESS_DIR[n].split("/"))

    def extra(self, *parts):
        """A directory inside the machine, outside HOME (for the location variables)."""
        p = os.path.join(self.m, "extra", *parts)
        os.makedirs(p, exist_ok=True)
        return p

    # running
    def argv(self, tool, args):
        return ([self.py, self.py_cli] if tool == "py" else [self.go_exe]) + list(args)

    def run(self, tool, args):
        open(self.log, "w").close()
        p = subprocess.run(self.argv(tool, args), env=self.env, cwd=self.cwd, stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, timeout=STEP_TIMEOUT)
        with open(self.log, encoding="utf-8") as f:
            calls = [json.loads(line) for line in f if line.strip()]
        return {"code": p.returncode, "out": p.stdout, "err": p.stderr, "calls": calls}


def snapshot(root):
    """Every path under root: kind, mode, bytes or link target."""
    out = {}
    for d, dirs, files in os.walk(root):
        for n in dirs + files:
            p = os.path.join(d, n)
            rel = os.path.relpath(p, root)
            st = os.lstat(p)
            if stat.S_ISLNK(st.st_mode):
                out[rel] = ("link", os.readlink(p))
            elif stat.S_ISDIR(st.st_mode):
                out[rel] = ("dir", stat.S_IMODE(st.st_mode))
            else:
                with open(p, "rb") as f:
                    out[rel] = ("file", stat.S_IMODE(st.st_mode), f.read())
    return out


def reset(machine, pristine):
    shutil.rmtree(machine.m)
    shutil.copytree(pristine, machine.m, symlinks=True)


# --- comparison ---------------------------------------------------------------------------------------------

DEVIATION_STEP = re.compile(r"^(PATH|(zsh|bash|fish) completion)$")
DETAIL_STATUS = {"create", "update", "remove", "ok"}
TEXT_LINE = re.compile(r"^(  )(create|created|update|updated|remove|removed|unchanged)(\s+)(PATH|(?:zsh|bash|fish) completion)(\s+).*$")
SUMMARY = re.compile(r"^(\d+ step\(s\) planned\.|done: \d+ step\(s\) changed\.|nothing to (do|remove): already up to date)")


class Tally:
    def __init__(self):
        self.wrapper = 0
        self.completion = 0
        self.diffs = []

    def diff(self, case, label, what, a, b):
        self.diffs.append("{} / {}: {}\n    python: {}\n    go:     {}".format(case, label, what, _short(a), _short(b)))


def _short(v, n=400):
    s = v if isinstance(v, str) else repr(v)
    return s if len(s) <= n else s[:n] + "...[{} more chars]".format(len(s) - n)


def mask_text(text, tally, interop):
    out = []
    for line in text.split("\n"):
        m = TEXT_LINE.match(line)
        if m:
            tally.completion += "completion" in m.group(4)
            tally.wrapper += m.group(4) == "PATH"
            if interop:  # a HOME the Python CLI installed: the binary updates these steps, the summary counts follow
                continue
            line = "{}{}{}{}{}<deviation>".format(m.group(1), m.group(2), m.group(3), m.group(4), m.group(5))
        elif interop and SUMMARY.match(line):
            continue
        out.append(line)
    text = "\n".join(out)
    return text


def mask_json(text, tally, interop):
    """The envelope with the details of deviation steps blanked; non-JSON text compared as text."""
    try:
        doc = json.loads(text)
    except ValueError:
        return mask_text(text, tally, interop)
    steps = (doc.get("data") or {}).get("steps", [])
    for s in steps:
        if DEVIATION_STEP.match(s["subject"]) and s["group"] == "shell" and s["status"] in DETAIL_STATUS:
            tally.completion += "completion" in s["subject"]
            tally.wrapper += s["subject"] == "PATH"
            s["detail"] = "<deviation>"
            if interop:
                s["status"] = "~"
                s["done"] = "~"
    if interop:
        doc["error"] = None if doc.get("error") is None else {"kind": doc["error"]["kind"], "code": doc["error"]["code"]}
        doc["ok"] = "~"
    return json.dumps(doc, ensure_ascii=False)


def exempt_paths(machine):
    """Paths whose content is a deviation: wrapper and completion files, relative to tmp/m."""
    env, home = machine.env, os.path.relpath(machine.home, machine.m)
    data = env.get("XDG_DATA_HOME") or os.path.join(machine.home, ".local", "share")
    conf = env.get("XDG_CONFIG_HOME") or os.path.join(machine.home, ".config")
    rel = lambda p: os.path.relpath(p, machine.m)  # noqa: E731 (all paths are inside the machine)
    return {rel(os.path.join(machine.home, ".local", "bin", "okf")): "wrapper",
            rel(os.path.join(machine.home, ".zsh", "completions", "_okf")): "zsh",
            rel(os.path.join(data, "bash-completion", "completions", "okf")): "file",
            rel(os.path.join(conf, "fish", "completions", "okf.fish")): "file"}


def compare_states(case, label, machine, a, b, tally, interop):
    exempt = exempt_paths(machine)
    for rel in sorted(set(a) | set(b)):
        x, y = a.get(rel), b.get(rel)
        kind = exempt.get(rel)
        if kind and x and y:
            tally.completion += kind != "wrapper"
            tally.wrapper += kind == "wrapper"
            if x[0] == "file" and y[0] == "file" and x[1] != y[1]:
                tally.diff(case, label, "mode of " + rel, oct(x[1]), oct(y[1]))
            if kind != "zsh" and x[0] != y[0]:
                tally.diff(case, label, "kind of " + rel, x[0], y[0])
            continue
        if x != y:
            tally.diff(case, label, "state of " + rel, x if x is None or x[0] != "file" else x[:2] + (x[2][:200],),
                       y if y is None or y[0] != "file" else y[:2] + (y[2][:200],))


def compare_runs(case, label, machine, py, go, tally, interop):
    for key in ("code", "calls"):
        if py[key] != go[key]:
            tally.diff(case, label, key, py[key], go[key])
    for key in ("out", "err"):
        a, b = mask_json(py[key], tally, interop), mask_json(go[key], tally, interop)
        if a != b:
            tally.diff(case, label, key, a, b)


def check_go_deviations(case, label, machine, py_state, go_state, tally):
    """What the Go side must keep of the two deviations: the wrapper runs the binary without python or
    uv, is mode 0755 and starts with the managed header; the completion files carry okf's ownership marks."""
    home = os.path.relpath(machine.home, machine.m)
    wrapper_path = os.path.join(home, ".local", "bin", "okf")
    wrapper = go_state.get(wrapper_path)
    if wrapper and wrapper[0] == "file" and wrapper != py_state.get(wrapper_path):  # equal: a foreign file both left alone
        text = wrapper[2].decode()
        head = "#!/bin/sh\n# managed by `okf install`; undo with `okf install --uninstall --apply`\n"
        if not text.startswith(head) or "python3" in text or " uv " in text or wrapper[1] != 0o755:
            tally.diff(case, label, "wrapper", oct(wrapper[1]) + " " + text, "the managed header, the binary, no python3/uv, 0755")
    for rel, kind in exempt_paths(machine).items():
        entry = go_state.get(rel)
        if entry is None or kind == "wrapper" or entry == py_state.get(rel):
            continue
        if entry[0] == "link" or (kind == "zsh" and not entry[2].decode().startswith("#compdef okf\n")) or \
                (kind == "file" and not entry[2].decode().startswith("# managed by `okf install`; undo with `okf install --uninstall --apply`\n")):
            tally.diff(case, label, "ownership mark of " + rel, "", entry[:2])


# --- cases --------------------------------------------------------------------------------------------------

PLAN = ("plan", ["install"])
DEFAULT_SEQ = [
    PLAN,
    ("plan json", ["install", "--json"]),
    ("apply", ["install", "--apply"]),
    ("apply again", ["install", "--apply"]),
    ("apply again json", ["install", "--apply", "--json"]),
    ("uninstall plan", ["install", "--uninstall"]),
    ("uninstall plan json", ["install", "--uninstall", "--json"]),
    ("uninstall apply", ["install", "--uninstall", "--apply"]),
    ("uninstall again", ["install", "--uninstall", "--apply", "--json"]),
]


def only_seq(*names):
    n = ",".join(names)
    return [("plan --only " + n, ["install", "--only", n]), ("apply --only " + n, ["install", "--apply", "--only", n]),
            ("apply again --only " + n, ["install", "--apply", "--only", n, "--json"]),
            ("uninstall --only " + n, ["install", "--uninstall", "--only", n]),
            ("uninstall apply --only " + n, ["install", "--uninstall", "--apply", "--only", n]),
            ("uninstall apply all", ["install", "--uninstall", "--apply"])]


CASES = {}


def case(name, layout="source", seq=None, pre=None, interop=False, slow=False):
    def register(setup):
        CASES[name] = dict(setup=setup, layout=layout, seq=seq or DEFAULT_SEQ, pre=pre, interop=interop, slow=slow)
        return setup
    return register


def shells_present(m):
    m.put(m.path(".zshrc"), "# my zshrc\n")
    m.put(m.path(".bashrc"), "# my bashrc\n")
    m.mkdir(".config", "fish")


def everything(m):
    m.stub("uv", "claude", "codex", "openclaw")
    m.harness_dirs()
    shells_present(m)


@case("empty-home")
def _(m):
    m.stub("uv")


@case("empty-home-only", seq=only_seq("claude"))
def _(m):
    m.stub("uv")


@case("empty-home-no-uv", seq=[PLAN, ("apply", ["install", "--apply"])])
def _(m):
    pass


@case("stubs-source-link", layout="source-link")
def _(m):
    everything(m)


@case("stubs-installed", layout="installed")
def _(m):
    everything(m)


@case("stubs-brew", layout="brew")
def _(m):
    everything(m)


@case("dirs-without-cli")
def _(m):
    m.stub("uv")
    m.harness_dirs()
    shells_present(m)


@case("okf-on-path", seq=[PLAN, ("apply", ["install", "--apply"]), ("uninstall apply", ["install", "--uninstall", "--apply"])])
def _(m):
    m.stub("uv", "okf")
    shells_present(m)


@case("installed-no-okf-on-path", layout="installed", seq=[PLAN, ("apply", ["install", "--apply"])])
def _(m):
    m.stub("uv")
    shells_present(m)


@case("all-location-vars")
def _(m):
    everything(m)
    m.env.update(CLAUDE_CONFIG_DIR=m.extra("claude"), PI_CODING_AGENT_DIR=m.extra("omp-agent"),
                 PI_CONFIG_DIR=".omp-ignored", CODEX_HOME=m.extra("codex"),
                 OPENCODE_CONFIG=os.path.join(m.extra("oc"), "custom.json"), XDG_CONFIG_HOME=m.extra("xdg-config"),
                 XDG_DATA_HOME=m.extra("xdg-data"), KIMI_CODE_HOME=m.extra("kimi"),
                 OPENCLAW_STATE_DIR=m.extra("openclaw"), HERMES_HOME=m.extra("hermes"), ZDOTDIR=m.extra("zdot"))
    m.put(os.path.join(m.env["ZDOTDIR"], ".zshrc"), "# zdotdir zshrc\n")
    m.mkdir(".config", "fish")


@case("pi-config-dir")
def _(m):
    m.stub("uv")
    m.env["PI_CONFIG_DIR"] = ".omp-alt"
    m.mkdir(".omp-alt", "agent")
    shells_present(m)
    m.env["XDG_CONFIG_HOME"] = m.extra("xdg")  # the codex/opencode dirs are absent, fish dir is not
    m.env["ZDOTDIR"] = m.extra("zdot")


@case("pi-config-dir-absolute")
def _(m):
    m.stub("uv")
    m.env["PI_CONFIG_DIR"] = m.extra("abs-pi")
    m.mkdir(".omp", "agent")


@case("login-shell-fallback", seq=[PLAN, ("apply", ["install", "--apply"]), ("uninstall apply", ["install", "--uninstall", "--apply"])])
def _(m):
    m.stub("uv")
    del m.env["SHELL"]


@case("login-shell-fish", seq=[PLAN])
def _(m):
    m.stub("uv")
    m.env["SHELL"] = "/usr/bin/fish"


JSON_HOSTILE = ('{\n\t"zeta": 1.50,\n\t"alpha": "a<b>&c \u00e9 \u2028 \u00fc",\n\t"mcpServers": {\n\t\t"other": '
                '{"command": "x", "n": 1e3, "ratio": 0.1, "neg": -0.0, "big": 12345678901234567890}\n\t},\n'
                '\t"list": [1, 2.5e-7, true, null, "\\u00e9\\n"]\n}\n')


@case("user-content", seq=DEFAULT_SEQ + [("apply after", ["install", "--apply"]), ("uninstall after", ["install", "--uninstall", "--apply"])])
def _(m):
    m.stub("uv")
    m.harness_dirs("omp", "codex", "opencode", "kimi", "hermes", "openclaw")
    m.put(m.path(".claude.json"), JSON_HOSTILE)
    m.mkdir(".claude")
    m.put(m.path(".omp", "agent", "mcp.json"), '{\n    "mcpServers": {"b": {"command": "y"}, "a": {}},\n    "zz": "\u00e9"\n}\n')
    m.put(m.path(".config", "opencode", "opencode.json"), '{\n  "theme": "dark",\n  "mcp": {"foreign": {"type": "local", "command": ["z"]}}\n}\n')
    m.put(m.path(".kimi-code", "mcp.json"), "  \n")
    m.put(m.path(".codex", "config.toml"), '# codex\nmodel = "x"\n\n[projects."/a"]\ntrust = "t"\n')
    m.put(m.path(".hermes", "config.yaml"), "model: x\nmcp_servers:\n    other:\n        command: foo\n\n# tail\nterminal:\n  a: 1\n")
    m.put(m.path("dotfiles", "zshrc"), "export PATH=$HOME/.local/bin:$PATH\nfpath=(~/.zsh/completions $fpath)\nautoload -Uz compinit\ncompinit\n")
    m.link(m.path(".zshrc"), os.path.join("dotfiles", "zshrc"))
    m.put(m.path(".bashrc"), "export PATH=\"$HOME/.local/bin:$PATH\"\nalias ll='ls -l'", mode=0o600)
    m.mkdir(".config", "fish", "conf.d")
    m.put(m.path(".config", "fish", "conf.d", "mine.fish"), "set -x A 1\n")
    m.put(m.path(".agents", "skills", "other", "SKILL.md"), "---\nname: other\n---\n")


@case("compinit-without-fpath")
def _(m):
    m.stub("uv")
    m.put(m.path(".zshrc"), "autoload -Uz compinit && compinit\n# fpath=(~/.zsh/completions $fpath)\n")
    m.put(m.path(".bashrc"), "")


@case("symlink-targets-abs")
def _(m):
    m.stub("uv")
    m.put(os.path.join(m.extra("dot"), "zshrc"), "# dot\n")
    m.link(m.path(".zshrc"), os.path.join(m.extra("dot"), "zshrc"))
    m.link(m.path(".bashrc"), "dangling-target")
    m.harness_dirs("claude")
    m.link(m.path(".claude.json"), os.path.join(m.extra("dot"), "claude.json"))


@case("foreign-and-blocked", seq=DEFAULT_SEQ + [("uninstall after", ["install", "--uninstall", "--apply"])])
def _(m):
    m.stub("uv")
    m.harness_dirs()
    m.put(m.path(".claude.json"), '{"mcpServers": {"okf": {"command": "other", "args": []}}}\n')
    m.put(m.path(".omp", "agent", "mcp.json"), '{\n  // comment\n  "mcpServers": {}\n}\n')
    m.put(m.path(".kimi-code", "mcp.json"), "[1, 2]\n")
    m.put(m.path(".config", "opencode", "opencode.json"), '{"mcp": {"okf": {"command": ["x"]}}}\n')
    m.put(m.path(".codex", "config.toml"), '[mcp_servers.okf]\ncommand = "other"\n')
    m.put(m.path(".hermes", "config.yaml"), "mcp_servers:\n  okf:\n    command: other\n")
    m.put(m.path(".zshrc"), "# a\n# >>> okf-cli >>>\n")
    m.put(m.path(".bashrc"), "a\r\nb\r\n")
    m.put(m.path(".local", "bin", "okf"), "#!/bin/sh\necho mine\n", mode=0o755)
    m.put(m.path(".zsh", "completions", "_okf"), "#compdef other\n")
    m.put(m.path(".local", "share", "bash-completion", "completions", "okf"), "# mine\ncomplete -F x okf\n")
    m.put(m.path(".config", "fish", "completions", "okf.fish"), "# mine\n")
    m.put(m.path(".config", "fish", "conf.d", "okf.fish"), "# mine\n")
    m.put(m.path(".claude", "skills", "okf", "SKILL.md"), "---\nname: not-okf\n---\n")
    m.put(m.path(".agents", "skills", "okf"), "a file in the way\n")
    m.put(m.path(".hermes", "skills", "okf", "SKILL.md"), "---\nname: okf\n---\nolder\n")


@case("invalid-toml", seq=[PLAN, ("apply", ["install", "--apply"]), ("uninstall", ["install", "--uninstall", "--apply"])])
def _(m):
    m.stub("uv")
    m.harness_dirs("codex")
    m.put(m.path(".codex", "config.toml"), "this is not toml\n")


@case("toml-not-up-to-date", seq=[PLAN, ("apply", ["install", "--apply"])])
def _(m):
    m.stub("uv")
    m.harness_dirs("codex")
    m.put(m.path(".codex", "config.toml"), '[mcp_servers.okf]\ncommand = "uv"\nargs = ["old", "okf_mcp.py"]\n')


@case("stale-json-entries", seq=[PLAN, ("apply", ["install", "--apply"]), ("uninstall apply", ["install", "--uninstall", "--apply"])])
def _(m):
    m.stub("uv")
    m.harness_dirs()
    entry = '{"type": "stdio", "command": "uv", "args": ["run", "/old/okf_mcp.py"], "env": {"A": "b"}, "keep": 1}'
    m.put(m.path(".claude.json"), '{\n  "mcpServers": {"okf": %s}\n}\n' % entry)
    m.put(m.path(".omp", "agent", "mcp.json"), '{"$schema": "s", "mcpServers": {"okf": %s}}\n' % entry)
    m.put(m.path(".config", "opencode", "opencode.json"), '{"$schema": "https://opencode.ai/config.json", "mcp": {"okf": {"command": ["uv", "run", "/old/okf_mcp.py"], "x": 1}}}\n')


YAML_VARIANTS = {
    "plain": "mcp_servers:\n    other:\n        command: foo\n",
    "empty-mapping-header": "mcp_servers:\nmodel: x\n",
    "flow": "mcp_servers: {a: 1}\n",
    "list": "mcp_servers:\n- a\n- b\n",
    "anchors": "base: &b\n  x: 1\nmcp_servers:\n  other: *b\n",
    "two-keys": "mcp_servers:\n  a: 1\nmcp_servers:\n  b: 2\n",
    "foreign-okf": "mcp_servers:\n  okf:\n    command: other\n",
    "own-entry-old": "mcp_servers:\n  other: {a: 1}\n  okf:\n    command: \"uv\"\n    args: [\"run\", \"/old/okf_mcp.py\"]\n  later: 1\n\nnext: 1\n",
    "own-only-entry": "model: x\nmcp_servers:\n  okf:\n    command: \"uv\"\n    args: [\"run\", \"/old/okf_mcp.py\"]\n# trailing\nterm: 1\n",
    "own-block": "model: x\n# >>> okf-cli >>>\nmcp_servers:\n  okf:\n    command: \"uv\"\n    args: [\"run\", \"/old/okf_mcp.py\"]\n# <<< okf-cli <<<\n",
    "own-child-block": "mcp_servers:\n  # >>> okf-cli >>>\n  okf:\n    command: old\n  # <<< okf-cli <<<\n",
    "crlf": "model: x\r\n",
    "quoted-key": "\"mcp_servers\":\n  a: 1\n",
    "comment-header": "mcp_servers:  # servers\n  # none yet\n",
    "tab-indent": "mcp_servers:\n\ta: 1\n",
    "no-newline": "model: x",
}
for _name, _text in YAML_VARIANTS.items():
    def _setup(m, _text=_text):
        m.stub("uv")
        m.harness_dirs("hermes")
        m.put(m.path(".hermes", "config.yaml"), _text)
    CASES["hermes-" + _name] = dict(setup=_setup, layout="source", interop=False, slow=False, pre=None,
                                    seq=[("plan", ["install", "--only", "hermes"]), ("apply", ["install", "--apply", "--only", "hermes"]),
                                         ("apply again", ["install", "--apply", "--only", "hermes", "--json"]),
                                         ("uninstall", ["install", "--uninstall", "--apply", "--only", "hermes"])])


@case("stub-exits-nonzero", seq=[PLAN, ("apply", ["install", "--apply"]), ("apply again", ["install", "--apply", "--json"])])
def _(m):
    everything(m)
    m.env["OKF_STUB_FAIL"] = "claude,codex"


@case("stub-timeout", seq=[("apply", ["install", "--apply", "--only", "claude"])], slow=True)
def _(m):
    m.stub("uv", "claude")
    m.env["OKF_STUB_SLEEP"] = "31"


@case("stubs-uninstall-state", seq=[("apply", ["install", "--apply"]), ("uninstall", ["install", "--uninstall", "--apply"]),
                                    ("uninstall again", ["install", "--uninstall"])])
def _(m):
    everything(m)
    m.env["OPENCLAW_STATE_DIR"] = m.extra("openclaw")


@case("only-subsets", seq=only_seq("codex", "zsh") + only_seq("hermes") + only_seq("fish") + only_seq("claude", "bash", "omp"))
def _(m):
    everything(m)


@case("only-bad", seq=[("unknown", ["install", "--only", "nope"]), ("empty", ["install", "--only", ""]),
                       ("blanks", ["install", "--only", " , "]), ("mixed json", ["install", "--only", "claude,bogus,x", "--json"]),
                       ("padded", ["install", "--only", " claude , zsh "]), ("bad flag", ["install", "--nope"]),
                       ("help", ["install", "--help"])])
def _(m):
    m.stub("uv")


@case("no-catalogue", seq=[("root missing", ["--root", "/does/not/exist", "install", "--only", "claude", "--json"]),
                           ("root missing text", ["--root", "/does/not/exist", "install", "--only", "claude"]),
                           ("global", ["install", "--only", "claude", "--json", "--root", "/also/missing"])])
def _(m):
    m.stub("uv")


@case("interop-source", pre=[["install", "--apply"]], interop=True)
def _(m):
    everything(m)


@case("interop-installed", layout="installed", pre=[["install", "--apply"]], interop=True)
def _(m):
    everything(m)


@case("interop-brew", layout="brew", pre=[["install", "--apply"]], interop=True)
def _(m):
    everything(m)


@case("interop-user-content", pre=[["install", "--apply"]], interop=True)
def _(m):
    m.stub("uv", "codex")
    m.harness_dirs("claude", "omp", "codex", "opencode", "kimi", "hermes")
    m.put(m.path(".claude.json"), JSON_HOSTILE)
    m.put(m.path(".zshrc"), "autoload -Uz compinit\ncompinit\n")
    m.put(m.path(".hermes", "config.yaml"), "mcp_servers:\n  other:\n    command: x\n")


# --- generated variants: one hostile config file per case -----------------------------------------------------

SHORT_SEQ = [PLAN, ("apply", ["install", "--apply"]), ("apply again", ["install", "--apply", "--only", "{only}", "--json"]),
             ("uninstall", ["install", "--uninstall", "--apply", "--only", "{only}"])]


def variant_case(name, only, setup, seq=None):
    seq = [(label, [a.replace("{only}", only) for a in argv]) for label, argv in (seq or SHORT_SEQ)]
    seq = [(l, a) if "--only" in a or l == "plan" else (l, a + ["--only", only]) for l, a in seq]
    CASES[name] = dict(setup=setup, layout="source", interop=False, slow=False, pre=None, seq=seq)


# JSON: text -> what json.loads says and what the editor does with it (omp's mcp.json, file fallback)
JSON_VARIANTS = {
    "trailing-comma-object": '{"mcpServers": {},}',
    "trailing-comma-array": '{"mcpServers": [1,]}',
    "single-quotes": "{'a': 1}",
    "missing-colon": '{"a" 1}',
    "missing-comma": '{"a": 1 "b": 2}',
    "missing-value": '{"a": }',
    "open-bracket": "[",
    "open-brace": "{",
    "open-brace-space": "{ \n ",
    "unterminated-string": '{"a": "unterminated',
    "bad-escape": '{"a": "bad \\x escape"}',
    "control-char": '{"a": "ctrl \x01 char"}',
    "bom": '\ufeff{"a": 1}',
    "extra-data": '{"a": 1} {"b": 2}',
    "nan-infinity": '{"a": NaN, "b": Infinity, "c": -Infinity}',
    "floats": '{"a": 1e999, "b": 1E5, "c": 0.0001, "d": 1.5e16, "e": 123456789012345678901234567890.5, "f": -1, "g": 1e-7, "h": 100.0}',
    "unicode-escapes": '{"a": "\\ud83d\\ude00 \\u00e9 \\u0041", "emoji": "\U0001f600", "tab\\t": "\\u2028\\u007f"}',
    "bad-unicode-escape": '{"a": "\\u12"}',
    "bad-unicode-digit": '{"a": "\\u12zz rest"}',
    "tru": '{"a": tru}',
    "nul": '{"a": nul}',
    "lone-minus": "-",
    "leading-zero": '{"a": 01}',
    "dot-five": '{"a": .5}',
    "one-dot": '{"a": 1.}',
    "one-e": '{"a": 1e}',
    "string-top": '"str"',
    "array-top": "[]",
    "null-top": "null",
    "container-string": '{"mcpServers": "x"}',
    "container-list": '{"mcpServers": []}',
    "indent-two-lines": '{\n  "a": 1,\n    "b": [\n\t2]\n}',
    "indent-tab-nested": '{\n\t"a": {\n\t\t"b": 1\n\t}\n}\n',
    "whitespace-only": " \n\t",
    "empty-object": "{}",
    "empty-file": "",
    "duplicate-keys": '{"": 1, "mcpServers": {"x": {"y": {}}}, "dup": 1, "dup": 2, "dup2": 0, "dup2": 5}',
    "crlf-lines": '{\r\n  "a": 1\r\n}\r\n',
    "no-trailing-newline": '{"a": 1}',
    "html-chars": '{"a": "<script>&amp;</script>", "k<>": "v"}',
    "deep": '{"a": ' + "[" * 30 + "]" * 30 + "}",
    "only-schema": '{"$schema": "x"}',
    "big-int": '{"a": 123456789012345678901234567890, "b": -0, "c": -0.0}',
    "foreign-okf-key": '{"mcpServers": {"okf": {"command": "other"}}}',
    "differs-entry": '{"mcpServers": {"okf": {"command": "uv", "args": ["old/okf_mcp.py"], "extra": [1, {"z": 2}]}}}',
}
for _name, _text in JSON_VARIANTS.items():
    def _setup(m, _text=_text):
        m.stub("uv")
        m.harness_dirs("omp")
        m.put(m.path(".omp", "agent", "mcp.json"), _text)
        m.put(m.path(".claude.json"), _text)
        m.put(m.path(".config", "opencode", "opencode.json"), _text)
    variant_case("json-" + _name, "omp", _setup)
    variant_case("json-claude-" + _name, "claude", _setup)
    variant_case("json-opencode-" + _name, "opencode", _setup)


def invalid_utf8(m):
    m.stub("uv")
    m.harness_dirs("omp", "codex", "hermes")
    for p in (m.path(".omp", "agent", "mcp.json"), m.path(".codex", "config.toml"), m.path(".hermes", "config.yaml"), m.path(".zshrc")):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(b'{"a": "\xff\xfe"}\n')


variant_case("invalid-utf8-omp", "omp", invalid_utf8)
variant_case("invalid-utf8-codex", "codex", invalid_utf8)
variant_case("invalid-utf8-hermes", "hermes", invalid_utf8)
variant_case("invalid-utf8-zsh", "zsh", invalid_utf8)

TOML_VARIANTS = {
    "empty-file": "",
    "no-trailing-newline": 'model = "x"',
    "other-table": '[mcp_servers.other]\ncommand = "a"\n',
    "inline-table": 'mcp_servers = { other = { command = "a" } }\n',
    "stale-block": '# >>> okf-cli >>>\n[mcp_servers.okf]\ncommand = "uv"\nargs = ["old"]\n# <<< okf-cli <<<\n',
    "end-only": "# <<< okf-cli <<<\n",
    "crlf": "a = 1\r\n",
    "dotted-keys": 'mcp_servers.okf.command = "uv"\nmcp_servers.okf.args = ["x", "okf_mcp.py"]\n',
    "unicode": 'model = "\u00e9"\n# \u00fc\n',
    "block-in-middle": 'a = 1\n# >>> okf-cli >>>\n[mcp_servers.okf]\ncommand = "x"\n# <<< okf-cli <<<\n[other]\nb = 2\n',
    "foreign-table": '[mcp_servers.okf]\ncommand = "other"\n',
    "unterminated-string": 'a = """open\n',
    "duplicate-table": '[mcp_servers]\nx = 1\n[mcp_servers]\ny = 2\n',
}
for _name, _text in TOML_VARIANTS.items():
    def _setup(m, _text=_text):
        m.stub("uv")
        m.harness_dirs("codex")
        m.put(m.path(".codex", "config.toml"), _text)
    variant_case("toml-" + _name, "codex", _setup)


def own_toml_entry(m):
    m.stub("uv")
    m.harness_dirs("codex")
    m.put(m.path(".codex", "config.toml"), '[mcp_servers.okf]\ncommand = "uv"\nargs = ["run", "--with", "mcp<2", "%s/mcp/okf_mcp.py"]\n' % m.pkg)


variant_case("toml-own-entry-without-block", "codex", own_toml_entry)

RC_VARIANTS = {
    "empty": "",
    "newline": "\n",
    "block-only": "# >>> okf-cli >>>\nx\n# <<< okf-cli <<<\n",
    "block-after-blank": "a\n\n# >>> okf-cli >>>\nx\n# <<< okf-cli <<<\n",
    "block-middle": "a\n# >>> okf-cli >>>\nx\n# <<< okf-cli <<<\nb\n",
    "two-begins": "# >>> okf-cli >>>\n# >>> okf-cli >>>\n# <<< okf-cli <<<\n",
    "indented-markers": "  # >>> okf-cli >>>\n  # <<< okf-cli <<<\n",
    "own-everything": "export PATH=$HOME/.local/bin:$PATH\nfpath=($HOME/.zsh/completions $fpath)\ncompinit\n",
    "commented-lines": "# export PATH=$HOME/.local/bin:$PATH\n  # compinit\n",
    "compinit-word": "my_compinit_wrapper\nzcompinit2\n",
    "lone-cr": "a\rb\n",
    "no-newline": "alias a=b",
    "unicode": "# \u00e9\u00fc\nexport X=\u00e4\n",
}
for _name, _text in RC_VARIANTS.items():
    def _setup(m, _text=_text):
        m.stub("uv")
        m.put(m.path(".zshrc"), _text)
        m.put(m.path(".bashrc"), _text)
        m.mkdir(".config", "fish")
        m.put(m.path(".config", "fish", "conf.d", "okf.fish"), "# mine\n")
    variant_case("rc-" + _name, "zsh,bash,fish", _setup)


@case("bash-profile-only")
def _(m):
    m.stub("uv")
    m.put(m.path(".profile"), "# profile\n")
    m.put(m.path(".bash_login"), "# login\n")


@case("bash-profile-and-bashrc")
def _(m):
    m.stub("uv")
    m.put(m.path(".bash_profile"), "# bp\n")
    m.put(m.path(".bashrc"), "# rc\n")
    m.put(m.path(".profile"), "# profile\n")
    m.put(m.path(".zshrc"), "# z\n")
    m.env["ZDOTDIR"] = m.extra("zdot")
    m.put(os.path.join(m.env["ZDOTDIR"], ".zshrc"), "# zdot\n")


# --- run ----------------------------------------------------------------------------------------------------

# the paths install writes (dotfiles of agents and shells, its destinations), relative to the real HOME
AGENT_PATHS = (".claude.json", ".claude/skills/okf", ".omp/agent/mcp.json", ".codex/config.toml",
               ".config/opencode/opencode.json", ".config/opencode/opencode.jsonc", ".kimi-code/mcp.json",
               ".openclaw/openclaw.json", ".openclaw/skills/okf", ".hermes/config.yaml", ".hermes/skills/okf",
               ".agents/skills/okf", ".zshrc", ".bashrc", ".bash_profile", ".bash_login", ".profile", ".zsh/completions/_okf",
               ".local/bin/okf", ".local/share/bash-completion/completions/okf", ".config/fish/conf.d/okf.fish",
               ".config/fish/completions/okf.fish")


def real_home_listing():
    """Fingerprint of the real HOME's agent and shell config paths, their backups and temporaries (SC-03)."""
    home = os.path.expanduser("~")
    out = {}

    def note(p):
        with contextlib.suppress(OSError):
            st = os.lstat(p)
            out[p] = (st.st_mode, st.st_size, st.st_mtime_ns, os.readlink(p) if stat.S_ISLNK(st.st_mode) else "")

    for rel in AGENT_PATHS:
        top = os.path.join(home, rel)
        for extra in (top + ".okf-cli.bak", os.path.join(os.path.dirname(top), ".okf-cli.tmp." + os.path.basename(top))):
            note(extra)
        note(top)
        if os.path.isdir(top) and not os.path.islink(top):
            for d, dirs, files in os.walk(top):
                for n in dirs + files:
                    note(os.path.join(d, n))
    return out


def run_case(name, spec, args, tally):
    with tempfile.TemporaryDirectory(prefix="okf-install-parity-") as tmp:
        m = Machine(tmp, spec["layout"], os.path.join(ROOT, "cli"), args.go_bin, args.stub_python)
        m.py = args.python
        spec["setup"](m)
        shutil.copytree(m.m, os.path.join(tmp, "pristine"), symlinks=True)
        pristine = os.path.join(tmp, "pristine")
        records = {}
        for tool in ("py", "go"):
            reset(m, pristine)
            for pre in spec["pre"] or ():
                r = m.run("py", pre)
                if r["code"] not in (0, 1):
                    raise SystemExit("{}: the Python pre-install failed: {}".format(name, r))
            before = snapshot(m.m)
            steps = []
            for label, argv in spec["seq"]:
                r = m.run(tool, argv)
                steps.append((label, r, snapshot(m.m)))
            records[tool] = (before, steps)
        interop = spec["interop"]
        if args.show:
            for tool in ("py", "go"):
                for label, r, _ in records[tool][1]:
                    print("--- {} / {} / {}: exit {} calls {}\n{}{}".format(name, tool, label, r["code"], r["calls"], r["out"], r["err"]))
        for (label, py, py_state), (_, go, go_state) in zip(records["py"][1], records["go"][1]):
            compare_runs(name, label, m, py, go, tally, interop)
            compare_states(name, label, m, py_state, go_state, tally, interop)
        applied = False  # the deviation files are the binary's own only once it has applied an install
        for (label, argv), (_, py, py_state), (_, go, go_state) in zip(spec["seq"], records["py"][1], records["go"][1]):
            if "--apply" in argv:
                applied = "--uninstall" not in argv
            if applied:
                check_go_deviations(name, label, m, py_state, go_state, tally)
        # AC1: a plan changes nothing and starts no harness CLI
        state = records["go"][0]
        for (label, argv), (_, go, go_state) in zip(spec["seq"], records["go"][1]):
            if "--apply" not in argv:
                if go["calls"]:
                    tally.diff(name, label, "a plan started harness CLIs", [], go["calls"])
                if go_state != state:
                    tally.diff(name, label, "a plan changed the machine", "", "")
            state = go_state
            for stream in ("out", "err"):
                if "stdin is not /dev/null" in go[stream]:
                    tally.diff(name, label, "a stub saw a stdin that is not /dev/null", "", go[stream])


def reference_python(venv):
    """An interpreter with the dependencies of cli/okf-cli.py (its PEP 723 header), in a throwaway venv."""
    with open(os.path.join(ROOT, "cli", "okf-cli.py"), encoding="utf-8") as f:
        block = re.search(r"^# /// script\n((?:#.*\n)+?)# ///$", f.read(), re.M).group(1)
    meta = tomllib.loads("".join(line[2:] if line.startswith("# ") else line[1:] for line in block.splitlines(True)))
    subprocess.run(["uv", "venv", "-q", "--python", meta["requires-python"], venv], check=True, capture_output=True)
    python = os.path.join(venv, "bin", "python")
    subprocess.run(["uv", "pip", "install", "-q", "--python", python, *meta["dependencies"]], check=True, capture_output=True)
    return python


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--only", help="run the cases whose name contains this text")
    ap.add_argument("--go-bin", default=os.path.join(ROOT, "go", "bin", "okf"))
    ap.add_argument("--python", help="reference interpreter (default: the one `uv run` builds for cli/okf-cli.py)")
    ap.add_argument("--show", action="store_true", help="print every run's stdout and stderr")
    ap.add_argument("--list", action="store_true", help="list the cases and exit")
    ap.add_argument("--fast", action="store_true", help="skip the slow cases (the 30 s timeout)")
    args = ap.parse_args()
    if args.list:
        print("\n".join(CASES))
        return 0
    if sys.platform == "win32":
        print("install parity: macOS and Linux only", file=sys.stderr)
        return 2
    if not os.access(args.go_bin, os.X_OK):
        print("install parity: no binary at {} (run `just go-build`)".format(args.go_bin), file=sys.stderr)
        return 2
    args.stub_python = os.path.realpath(sys.executable)
    venv = tempfile.TemporaryDirectory(prefix="okf-install-parity-venv-")
    if not args.python:
        try:
            args.python = reference_python(venv.name)
        except (OSError, subprocess.CalledProcessError, KeyError) as e:
            print("install parity: no reference interpreter ({})".format(e), file=sys.stderr)
            return 2
    names = [n for n in CASES if (not args.only or args.only in n) and not (args.fast and CASES[n]["slow"])]
    if not names:
        print("install parity: no case matches", file=sys.stderr)
        return 2
    before = real_home_listing()
    tally, failed = Tally(), []
    for n in names:
        mark = len(tally.diffs)
        try:
            run_case(n, CASES[n], args, tally)
        except subprocess.TimeoutExpired as e:
            tally.diffs.append("{}: timed out: {}".format(n, e))
        print("{:<6}{}".format("FAIL" if len(tally.diffs) > mark else "ok", n), flush=True)
        if len(tally.diffs) > mark:
            failed.append(n)
    after = real_home_listing()
    if after != before:
        tally.diffs.append("the real HOME's agent or shell config paths changed during the run: " +
                           ", ".join(sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))))
    print("\nallowed deviations (exempted occurrences in this run):")
    print("  1. PATH wrapper starts the binary, not `uv run --script cli/okf-cli.py` (D01, R-01): {} step/file comparisons".format(tally.wrapper))
    print("  2. completion files come from go/internal/complete, not argcomplete (zsh: file, not link to cli/_okf): {} step/file comparisons".format(tally.completion))
    if tally.diffs:
        print("\n{} difference(s) outside the deviation list:".format(len(tally.diffs)))
        for d in tally.diffs[:60]:
            print("- " + d)
        return 1
    print("\n{} case(s), no difference outside the deviation list".format(len(names)))
    return 0


if __name__ == "__main__":
    with contextlib.suppress(BrokenPipeError):
        sys.exit(main())
