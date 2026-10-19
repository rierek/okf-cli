#!/usr/bin/env python3
"""End-to-end zsh completion check (OKFT-qg0o): a real zsh in a PTY, set up by `okf install --apply`.

Per implementation (the Go binary, and the Python CLI as reference) the check
  1. makes a throwaway HOME and runs `install --apply --only zsh` into it (J1 writes ~/.zsh/completions/_okf,
     the rc block with fpath + compinit, and the ~/.local/bin/okf wrapper),
  2. starts `zsh -i` in a PTY on that HOME (clean zcompdump) and presses TAB after each input,
  3. records the candidate list that the completion function `_okf` hands to `_describe`: a wrapper of
     `_describe` appends it to a log file, so the check waits on that log, never on a sleep.
The Go leg runs with PATH = the wrapper dir plus an empty dir: no python3, no uv, no argcomplete in the shell.
The check then requires equal candidate sets for Go and Python on each input, and, for the `--root` form
run from an unrelated cwd, candidates that come from that root. HOME and the catalogue are throwaway copies.

Usage: completion_check.py --binary go/bin/okf --fixture tests/golden/catalogue
"""
import argparse
import fcntl
import os
import pty
import re
import select
import shutil
import struct
import subprocess
import sys
import tempfile
import termios
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TIMEOUT = 90  # one TAB runs the Python reference through `uv run`, seconds on a cold cache
# The completion function ends in `_describe okf completions ...`; argv[2] names the candidate array.
WRAP = ('autoload +X _describe; functions[_describe_orig]=$functions[_describe]; '
        '_describe() { print -rl -- "@@BEGIN ${(j: :)words}" "${(@P)2}" @@END >> "$COMPLOG"; _describe_orig "$@" }')


class Session:
    """One interactive zsh behind a PTY."""

    def __init__(self, env, cwd):
        self.buf = b""
        self.pid, self.fd = pty.fork()
        if self.pid == 0:
            os.chdir(cwd)
            os.execve(shutil.which("zsh"), ["zsh", "-i"], env)
        fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack("HHHH", 50, 200, 0, 0))

    def wait(self, pattern, what):
        end = time.time() + TIMEOUT
        while not re.search(pattern, self.buf):
            if time.time() > end:
                raise SystemExit("FAIL: timeout waiting for {}; output so far: {!r}".format(what, self.buf[-400:]))
            if select.select([self.fd], [], [], 0.2)[0]:
                try:
                    self.buf += os.read(self.fd, 65536)
                except OSError:
                    raise SystemExit("FAIL: zsh exited while waiting for {}: {!r}".format(what, self.buf[-400:]))
        self.buf = self.buf[re.search(pattern, self.buf).end():]

    def run(self, line, marker):
        """Type a command, wait for its marker: `print OK$[n]` echoes `$[n]` but prints `OK<n>`."""
        os.write(self.fd, line.encode() + b"\r")
        self.wait(marker.encode(), line)

    def close(self):
        os.close(self.fd)
        os.waitpid(self.pid, 0)


def installed_home(t, name, install_cmd, env):
    home = os.path.join(t, name)
    os.mkdir(home)
    env = dict(env, HOME=home, SHELL=shutil.which("zsh"))
    proc = subprocess.run(install_cmd + ["install", "--apply", "--only", "zsh"], env=env, capture_output=True, text=True)
    if proc.returncode != 0 or not os.path.isfile(os.path.join(home, ".zsh", "completions", "_okf")):
        raise SystemExit("FAIL: {} install --apply --only zsh (exit {}): {}".format(name, proc.returncode, proc.stdout + proc.stderr))
    return home


def candidates(env, cwd, inputs, log, expect_no_python):
    """Press TAB after each input in one zsh session; return {input: set of candidate lines}."""
    s = Session(dict(env, COMPLOG=log), cwd)
    try:
        s.run("print OK$[1+1]", "OK2")  # the rc block ran: prompt is live
        s.run(WRAP + "; LISTMAX=100000; unsetopt beep; print OK$[2+1]", "OK3")
        if expect_no_python:
            s.run("print N${#commands[python3]}${#commands[uv]}${#commands[python]}X$[0+1]", "N000X1")
        found = {}
        for n, line in enumerate(inputs):
            before = open(log).read().count("@@END\n") if os.path.exists(log) else 0
            os.write(s.fd, line.encode() + b"\t")
            end = time.time() + TIMEOUT
            while not (os.path.exists(log) and open(log).read().count("@@END\n") > before):
                if time.time() > end:
                    raise SystemExit("FAIL: no completion record for {!r}; output {!r}".format(line, s.buf[-300:]))
                if select.select([s.fd], [], [], 0.2)[0]:
                    s.buf += os.read(s.fd, 65536)
            record = open(log).read().split("@@END\n")[before]
            lines = record.splitlines()
            found[line] = set(lines[1:])
            os.write(s.fd, b"\x15")  # kill the line; ^C would flush the typed-ahead sentinel command
            s.run("print OK$[{}+4]".format(n + 1000), "OK{}".format(n + 1004))
        return found
    finally:
        s.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--binary", required=True, help="the Go okf binary")
    ap.add_argument("--fixture", required=True, help="a catalogue to copy, e.g. tests/golden/catalogue")
    a = ap.parse_args()
    binary, fixture = os.path.realpath(a.binary), os.path.realpath(a.fixture)
    if not os.path.isfile(binary) or not shutil.which("zsh") or not shutil.which("uv"):
        raise SystemExit("FAIL: need the built binary {}, zsh and uv (the Python reference runs through uv)".format(binary))
    t = tempfile.mkdtemp()
    try:
        cat = os.path.join(t, "cat")
        shutil.copytree(fixture, cat)
        other = os.path.join(t, "elsewhere")
        os.mkdir(other)
        empty = os.path.join(t, "emptybin")
        os.mkdir(empty)
        ctx_slug = next(f[:-3] for f in sorted(os.listdir(os.path.join(cat, "_ctx"))) if f.endswith(".md") and f != "index.md")
        plain = ["okf rea", "okf check ", "okf ctx add {} ".format(ctx_slug)]
        rooted = [l.replace("okf ", "okf --root {} ".format(cat), 1) for l in plain]

        base = {k: v for k, v in os.environ.items() if k not in ("HOME", "COMPLOG")}
        uv_env = {k: v for k, v in base.items() if k.startswith("UV_")}
        uv_env.setdefault("UV_CACHE_DIR", subprocess.check_output(["uv", "cache", "dir"], text=True).strip())
        uv_env.setdefault("UV_PYTHON_INSTALL_DIR", subprocess.check_output(["uv", "python", "dir"], text=True).strip())
        # Go leg: the shell sees the wrapper dir and an empty dir, nothing else.
        go_home = installed_home(t, "home-go", [binary], {"PATH": empty})
        go_env = {"HOME": go_home, "PATH": os.path.join(go_home, ".local", "bin") + os.pathsep + empty,
                  "TERM": "xterm", "SHELL": shutil.which("zsh"), "LANG": "C.UTF-8"}
        # Python reference leg: the same zsh, the Python CLI behind the wrapper.
        py_cmd = ["uv", "run", "--script", os.path.join(REPO, "cli", "okf-cli.py")]
        py_home = installed_home(t, "home-py", py_cmd, base | uv_env)
        py_env = base | uv_env | {"HOME": py_home, "TERM": "xterm", "SHELL": shutil.which("zsh"),
                                  "PATH": os.path.join(py_home, ".local", "bin") + os.pathsep + base["PATH"]}

        go = candidates(go_env, cat, plain, os.path.join(t, "go-plain.log"), True)
        go |= candidates(go_env, other, rooted, os.path.join(t, "go-root.log"), True)
        py = candidates(py_env, cat, plain, os.path.join(t, "py-plain.log"), False)
        py |= candidates(py_env, other, rooted, os.path.join(t, "py-root.log"), False)

        bad = 0
        for line in plain + rooted:
            short = line.replace(cat, "<fixture>")
            if not go[line]:
                print("FAIL {}: the binary offers no candidates".format(short)); bad += 1
            elif go[line] != py[line]:
                print("FAIL {}: only binary {}, only python {}".format(short, sorted(go[line] - py[line])[:5], sorted(py[line] - go[line])[:5])); bad += 1
            else:
                print("ok   {}: {} candidates equal".format(short, len(go[line])))
        bundles = {d for d in os.listdir(cat) if os.path.isdir(os.path.join(cat, d)) and not d.startswith(".")}
        for line in rooted[1:]:  # `check <TAB>` and `ctx add <slug> <TAB>` list paths of the root, cwd holds none
            if not any(c.split(":")[0].strip("/").split("/")[0] in bundles for c in go[line]):
                print("FAIL {}: no candidate from the --root catalogue".format(line.replace(cat, "<fixture>"))); bad += 1
        if not bad:
            print("ok   --root: candidates come from the fixture root; the shell had no python3, uv or argcomplete")
        return 1 if bad else 0
    finally:
        shutil.rmtree(t, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
