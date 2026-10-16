"""Golden-output harness: runs every case of tests/golden/cases.txt against an okf
implementation and compares stdout, stderr, exit code and file-tree effect with
tests/golden/expected/<case>.out. Not a test module: tests/test_golden.py drives it in
`just test`, `just golden` runs it directly.

The implementation under test is a black box: `--cmd` / OKF_GOLDEN_CMD (shell-quoted),
default this interpreter plus cli/okf-cli.py. A port passes when it reproduces the goldens.

cases.txt: one case per line, `<name> [KEY=VALUE ...] <args...>` (shlex); `#` lines and
blank lines are skipped. The harness runs `<cmd> --root <copy> <args>` with cwd = <copy>;
`{ROOT}` inside an arg becomes the copy's path. Every case gets a fresh copy of a git
template built from tests/golden/catalogue/: one commit per file in sorted path order,
pinned author/committer and dates 2026-01-01 plus one day per file; each file's mtime is
its commit date, so mtime comparisons (ctx staleness, build-index --if-stale) do not depend
on the checkout.

Network block: no case reaches a network service, loopback included, whatever the language
of the implementation and whatever it does with proxy variables. The harness starts every
case through an OS-level block that needs no root and no tool beyond a stock runner: on
macOS `sandbox-exec` with `(deny network*)`; on Linux a seccomp-bpf filter (stdlib ctypes,
installed by `okf_golden.py --exec-blocked -- <cmd>` right before exec) that makes
socket(AF_INET|AF_INET6) fail with EPERM, while AF_UNIX stays allowed. Both are inherited
by child processes. Before the first case `run_all` probes the block against a listener of
its own; if the probe connects, or the block cannot be established, the run stops with the
cause and no case runs. The failing syscall text differs by language and OS, so the
error detail of the auto-embed warning of `tags --register` is pinned as <network error>
(see `_stderr`); the rest of the line, exit code, stdout and file effect stay pinned."""
import argparse
import concurrent.futures
import datetime
import difflib
import functools
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
from collections import namedtuple

HERE = os.path.dirname(os.path.abspath(__file__))
GOLDEN = os.path.join(HERE, "golden")
FIXTURE = os.path.join(GOLDEN, "catalogue")
CASES = os.path.join(GOLDEN, "cases.txt")
EXPECTED = os.path.join(GOLDEN, "expected")
DEFAULT_CMD = [sys.executable, os.path.join(os.path.dirname(HERE), "cli", "okf-cli.py")]

_NAME = re.compile(r"[a-z0-9][a-z0-9-]*\Z")
_ENV = re.compile(r"[A-Z_][A-Z0-9_]*=")
_EPOCH = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
_GIT_ID = {"GIT_AUTHOR_NAME": "Golden", "GIT_AUTHOR_EMAIL": "golden@example.org",
           "GIT_COMMITTER_NAME": "Golden", "GIT_COMMITTER_EMAIL": "golden@example.org"}
_SANDBOX_PROFILE = "(version 1)(allow default)(deny network*)"
_PROBE = ("import socket,sys\n"
          "try: socket.create_connection(('127.0.0.1', int(sys.argv[1])), 5)\n"
          "except OSError: print('blocked')\n")

Case = namedtuple("Case", "name env args")


def load_cases(path=CASES):
    cases, seen = [], set()
    with open(path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            name, *rest = shlex.split(line)
            if not _NAME.match(name) or name in seen:
                raise ValueError("{}:{}: bad or duplicate case name {!r}".format(path, n, name))
            seen.add(name)
            env = {}
            while rest and _ENV.match(rest[0]):
                key, value = rest.pop(0).split("=", 1)
                env[key] = value
            cases.append(Case(name, env, rest))
    return cases


def command(cmd=None):
    """argv prefix of the implementation under test; a relative executable path resolves against
    the caller's cwd, not the case's temp copy."""
    argv = shlex.split(cmd or os.environ.get("OKF_GOLDEN_CMD") or "")
    if not argv:
        return DEFAULT_CMD
    return [os.path.abspath(argv[0]) if os.sep in argv[0] else argv[0]] + argv[1:]


def _git(cwd, *argv, env=None):
    subprocess.run(["git", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", *argv],
                   cwd=cwd, check=True, capture_output=True,
                   env={**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
                        **(env or {})})


def _files(root):
    """Sorted root-relative paths of every file under root, .git/ excluded."""
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        if dirpath == root and ".git" in dirnames:
            dirnames.remove(".git")
        out += [os.path.relpath(os.path.join(dirpath, f), root).replace(os.sep, "/") for f in filenames]
    return sorted(out)


def build_template(dest):
    """The fixture as a git repository with one pinned commit per file, each file's mtime set
    to its commit date; returns dest."""
    shutil.copytree(FIXTURE, dest, symlinks=True)
    _git(dest, "init", "-q", "-b", "main")
    for i, rel in enumerate(_files(dest)):
        instant = _EPOCH + datetime.timedelta(days=i)
        when = instant.strftime("%Y-%m-%dT%H:%M:%S+0000")
        os.utime(os.path.join(dest, rel), (instant.timestamp(),) * 2, follow_symlinks=False)
        _git(dest, "add", "--", rel)
        _git(dest, "commit", "-q", "-m", "add " + rel,
             env={**_GIT_ID, "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when})
    return dest


def _snapshot(root):
    snap = {}
    for rel in _files(root):
        path = os.path.join(root, rel)
        if os.path.islink(path):
            snap[rel] = ("link:" + os.readlink(path)).encode()
        else:
            with open(path, "rb") as fh:
                snap[rel] = fh.read()
    return snap


def _text(data):
    if b"\0" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _tree_effect(before, after):
    """Lines describing what the command did to the tree: R(ename), D, A, M, text diffs."""
    deleted = {p: before[p] for p in before.keys() - after.keys()}
    added = {p: after[p] for p in after.keys() - before.keys()}
    lines = []
    for old in sorted(deleted):
        new = next((p for p in sorted(added) if added[p] == deleted[old]), None)
        if new:
            lines.append("R {} -> {}".format(old, new))
            del added[new]
        else:
            lines.append("D " + old)
    for path in sorted(added.keys() | {p for p in before.keys() & after.keys() if before[p] != after[p]}):
        old, new = before.get(path, b""), after[path]
        lines.append(("M " if path in before else "A ") + path)
        old_text, new_text = _text(old), _text(new)
        if old_text is None or new_text is None:
            lines.append("  (binary)")
            continue
        # a last line without newline gets git's marker, so a dropped final newline shows
        lines += [d[:-1] if d.endswith("\n") else d + "\n\\ No newline at end of file"
                  for d in difflib.unified_diff(old_text.splitlines(True), new_text.splitlines(True),
                                                "a/" + path, "b/" + path)]
    return lines


def _stream(data):
    text = data.decode("utf-8", "backslashreplace")
    return text if not text or text.endswith("\n") else text + "\n\\ no newline at end\n"


def _stderr(stderr):
    """argparse's usage-error text changes between Python releases (3.11 to 3.14, even patch
    releases) and a port cannot reproduce it: such stderr pins only as <usage error>; the
    exit code stays. The error detail of the auto-embed warning (exception class and text of
    the denied connection) differs by language and OS and pins only as <network error>."""
    stderr = re.sub(r"(auto-embed skipped for new tag\(s\) )\(.*\)( \u2014 run )", r"\1(<network error>)\2", stderr)
    return "<usage error>\n" if re.match(r"usage: okf\b", stderr) else stderr


def run_case(case, cmd, template, workdir):
    """The golden record of one case: host paths become <ROOT> and <HOME>, an instant of the run's
    own day (e.g. `verify`'s `at`) becomes <NOW>; the fixture's dates lie in the past and stay."""
    root, home = os.path.join(workdir, "root"), os.path.join(workdir, "home")
    shutil.copytree(template, root, symlinks=True)
    os.makedirs(home)
    env = {"PATH": os.environ.get("PATH", ""), "HOME": home,
           "XDG_CONFIG_HOME": os.path.join(home, ".config"), "LC_ALL": "C.UTF-8", "TZ": "UTC",
           "COLUMNS": "100", "NO_COLOR": "1", "TERM": "dumb",
           **case.env}
    args = [a.replace("{ROOT}", root) for a in case.args]
    before = _snapshot(root)
    days = {_today()}
    proc = subprocess.run(blocked(cmd) + ["--root", root] + args, cwd=root, env=env, capture_output=True,
                          timeout=120)
    days.add(_today())
    record = "$ okf {}\n".format(shlex.join(case.args))
    if case.env:
        record += "env: {}\n".format(" ".join("{}={}".format(k, v) for k, v in case.env.items()))
    record += "exit: {}\n--- stdout\n{}--- stderr\n{}--- files\n".format(
        proc.returncode, _stream(proc.stdout), _stderr(_stream(proc.stderr)))
    record += "".join(line + "\n" for line in _tree_effect(before, _snapshot(root)))
    for path, token in ((root, "<ROOT>"), (home, "<HOME>")):
        for form in sorted({os.path.realpath(path), path}, key=len, reverse=True):
            record = record.replace(form, token)
    now = re.compile(r"(?:{})T\d\d:\d\d:\d\dZ".format("|".join(sorted(days))))
    return now.sub("<NOW>", record)


def _seccomp_no_inet():
    """Install a seccomp filter: socket(AF_INET|AF_INET6) fails with EPERM. A syscall of a foreign
    architecture or of the x32 ABI kills the process, so the filter cannot be sidestepped.
    ponytail: blocks socket creation only, not an inherited socket fd; the harness passes none."""
    import ctypes
    import platform
    arch, nr_socket = {"x86_64": (0xC000003E, 41), "aarch64": (0xC00000B7, 198),
                       "arm64": (0xC00000B7, 198)}[platform.machine()]
    LD, JEQ, JGE, RET = 0x20, 0x15, 0x35, 0x06
    allow, errno_eperm, kill = 0x7FFF0000, 0x00050000 | 1, 0x80000000
    prog = [(LD, 0, 0, 4), (JEQ, 0, 8, arch),            # arch must be ours, else kill
            (LD, 0, 0, 0), (JGE, 6, 0, 0x40000000),      # x32 syscall numbers: kill
            (JEQ, 0, 3, nr_socket), (LD, 0, 0, 16),      # socket(): inspect domain
            (JEQ, 2, 0, 2), (JEQ, 1, 0, 10),             # AF_INET, AF_INET6: EPERM
            (RET, 0, 0, allow), (RET, 0, 0, errno_eperm), (RET, 0, 0, kill)]

    class Insn(ctypes.Structure):
        _fields_ = [("code", ctypes.c_ushort), ("jt", ctypes.c_ubyte), ("jf", ctypes.c_ubyte),
                    ("k", ctypes.c_uint)]

    class Prog(ctypes.Structure):
        _fields_ = [("len", ctypes.c_ushort), ("filter", ctypes.POINTER(Insn))]

    insns = (Insn * len(prog))(*[Insn(c, t, f, k) for c, t, f, k in prog])
    libc = ctypes.CDLL(None, use_errno=True)
    if (libc.prctl(38, 1, 0, 0, 0) or  # PR_SET_NO_NEW_PRIVS
            libc.prctl(22, 2, ctypes.byref(Prog(len(prog), insns)), 0, 0)):  # PR_SET_SECCOMP, FILTER
        raise OSError(ctypes.get_errno(), os.strerror(ctypes.get_errno()))


def blocked(cmd):
    """cmd behind the network block of this OS; the block holds for its child processes too."""
    if sys.platform == "darwin":
        return ["/usr/bin/sandbox-exec", "-p", _SANDBOX_PROFILE] + cmd
    if sys.platform.startswith("linux"):
        return [sys.executable, os.path.abspath(__file__), "--exec-blocked", "--"] + cmd
    raise SystemExit("golden harness: no network block for platform {!r} (macOS and Linux only)"
                     .format(sys.platform))


def _exec_blocked(argv):
    try:
        _seccomp_no_inet()
    except (OSError, KeyError) as e:
        sys.exit("golden harness: cannot install the network block (seccomp): {!r}".format(e))
    os.execvp(argv[0], argv)


@functools.lru_cache(maxsize=None)
def check_block():
    """Fail closed: a process started through `blocked` must not reach a listener of ours."""
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        server.setblocking(False)
        port = server.getsockname()[1]
        try:
            proc = subprocess.run(blocked([sys.executable, "-c", _PROBE, str(port)]),
                                  capture_output=True, timeout=60)
        except OSError as e:
            raise SystemExit("golden harness: cannot start the network block: {!r}".format(e))
        try:
            server.accept()[0].close()
            accepted = True
        except BlockingIOError:
            accepted = False
    if accepted or proc.returncode or proc.stdout.strip() != b"blocked":
        raise SystemExit("golden harness: the network block does not hold (probe exit {}, "
                         "connection accepted: {}, stderr: {}); no case ran".format(
                             proc.returncode, accepted, proc.stderr.decode("utf-8", "replace").strip()))


def _today():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


def expected_path(case):
    return os.path.join(EXPECTED, case.name + ".out")


def diff(case, actual):
    """None when the golden matches, else a unified diff golden -> actual."""
    try:
        with open(expected_path(case), encoding="utf-8") as fh:
            expected = fh.read()
    except FileNotFoundError:
        expected = ""
    if expected == actual:
        return None
    return "".join(difflib.unified_diff(expected.splitlines(True), actual.splitlines(True),
                                        "golden/" + case.name, "actual/" + case.name))


def run_all(cases, cmd):
    """{case name: record}, cases run in parallel, each in its own temp dir."""
    check_block()
    with tempfile.TemporaryDirectory() as tmp:
        template = build_template(os.path.join(tmp, "template"))

        def one(item):
            i, case = item
            return case.name, run_case(case, cmd, template, os.path.join(tmp, str(i)))

        with concurrent.futures.ThreadPoolExecutor(os.cpu_count()) as pool:
            return dict(pool.map(one, enumerate(cases)))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:2] == ["--exec-blocked", "--"]:
        _exec_blocked(argv[2:])
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--update", action="store_true", help="rewrite the goldens from the implementation")
    parser.add_argument("--cmd", help="implementation under test, shell-quoted (default: OKF_GOLDEN_CMD, "
                                      "else this interpreter + cli/okf-cli.py)")
    parser.add_argument("--only", help="run only cases whose name contains this text")
    opts = parser.parse_args(argv)
    cases = [c for c in load_cases() if not opts.only or opts.only in c.name]
    records = run_all(cases, command(opts.cmd))
    if opts.update:
        os.makedirs(EXPECTED, exist_ok=True)
        if not opts.only:
            names = {c.name + ".out" for c in cases}
            for stale in sorted(set(os.listdir(EXPECTED)) - names):
                os.remove(os.path.join(EXPECTED, stale))
                print("removed", stale)
        for case in cases:
            if diff(case, records[case.name]):
                with open(expected_path(case), "w", encoding="utf-8") as fh:
                    fh.write(records[case.name])
                print("updated", case.name)
        return 0
    deltas = {c.name: diff(c, records[c.name]) for c in cases}
    failed = [name for name, delta in deltas.items() if delta]
    for name in failed:
        sys.stdout.write(deltas[name])
    print("{} of {} cases differ{}".format(len(failed), len(cases), ": " + " ".join(failed) if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
