"""okf install: put okf, its agent skill, its MCP server and TAB
completion where this machine's coding agents and shells look for them.
Standard library only; loaded lazily by `okf install`, which needs no
catalogue.

`install` builds a plan (a list of Steps) from what is on disk and changes
nothing; `--apply` performs it; `--uninstall` plans or performs the reverse.
Edits never guess: rc files, TOML and YAML get one marker-bounded block
(BEGIN..END), JSON gets a key-scoped merge, every write is atomic and keeps a
one-time `<file>.okf-cli.bak` of a file that existed. A config that cannot be
edited safely turns its step into BLOCKED and prints the manual edit instead.
"""
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tomllib

from okf.errors import OkfError

HARNESSES = ("claude", "omp", "codex", "opencode", "kimi", "openclaw", "hermes")
SHELLS = ("zsh", "bash", "fish")
# harnesses that read ~/.agents/skills: one shared install covers all of them
SHARED_READERS = ("codex", "opencode", "kimi", "omp", "openclaw")

BEGIN = "# >>> okf-cli >>>"
END = "# <<< okf-cli <<<"
MANAGED = "# managed by `okf install`; undo with `okf install --uninstall --apply`"
WRAPPER_HEAD = "#!/bin/sh\n" + MANAGED + "\n"
SCRIPT = "okf_mcp.py"  # an MCP entry that names this script is okf's own
CHANGES = ("create", "update", "remove")
IGNORED = shutil.ignore_patterns(".DS_Store", "__pycache__")


class Unsafe(Exception):
    """The file cannot be edited without guessing: the step is BLOCKED."""


class Skip(Exception):
    """Nothing to do for a reason the user should read: the step is skipped."""


class Failed(Exception):
    """A subprocess failed."""


def brew_opt_path(path):
    """Homebrew installs to <prefix>/Cellar/<formula>/<version>, which `brew upgrade` deletes; the
    symlink <prefix>/opt/<formula> stays. Config files must name that one."""
    path = os.path.abspath(path)
    m = re.match(r"(.*)/Cellar/([^/]+)/[^/]+(?=/|$)", path)
    opt = m and os.path.join(m[1], "opt", m[2])
    if opt and os.path.isdir(opt) and os.path.samefile(opt, m[0]):
        return opt + path[len(m[0]):]
    return path


class Ctx:
    """Everything install reads from the machine; tests inject tmp values."""

    def __init__(self, env=None, home=None, pkg_root=None, platform=None, timeout=30):
        self.env = dict(os.environ if env is None else env)
        self.home = os.path.abspath(home or self.env.get("HOME") or os.path.expanduser("~"))
        # same relative layout in a git checkout and in the installed wheel:
        # <pkg_root>/{cli/okf-cli.py, cli/_okf, mcp/okf_mcp.py, skills/okf}
        self.pkg_root = os.path.abspath(
            pkg_root or brew_opt_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)))
        self.platform = platform or sys.platform
        self.timeout = timeout  # seconds a harness CLI may take

    @property
    def source_tree(self):
        """A checkout (or unpacked sdist), not an installed wheel: its files stay
        where they are, so a symlink follows `git pull`; a wheel's may move."""
        return os.path.isfile(os.path.join(self.pkg_root, "pyproject.toml"))

    def path(self, *parts):
        return os.path.join(self.home, *parts)

    def which(self, name):
        return shutil.which(name, path=self.env.get("PATH", os.defpath))

    def short(self, path):
        h = self.home
        return "~" + path[len(h):] if path == h or path.startswith(h + os.sep) else path

    def run(self, argv):
        try:
            p = subprocess.run(argv, env=self.env, stdin=subprocess.DEVNULL,
                               capture_output=True, text=True, timeout=self.timeout)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise Failed("{}: {}".format(shlex.join(argv), e))
        if p.returncode:
            raise Failed("{} exited {}: {}".format(
                shlex.join(argv), p.returncode, (p.stderr or p.stdout).strip()[:300]))


class Step:
    def __init__(self, group, subject, status, detail="", apply=None):
        self.group, self.subject, self.status, self.detail, self.apply = group, subject, status, detail, apply
        self.done = False


# --- text helpers ------------------------------------------------------------


def read(path):
    try:
        with open(path, encoding="utf-8", newline="") as f:
            return f.read()
    except FileNotFoundError:
        return None
    except UnicodeDecodeError:
        raise Unsafe("{} is not UTF-8 text".format(path))


def lines_of(text):
    if "\r" in text:
        raise Unsafe("the file uses CRLF line endings")
    return text.split("\n")[:-1] if text.endswith("\n") else text.split("\n") if text else []


def join(lines):
    return "\n".join(lines) + "\n" if lines else ""


def find_block(lines):
    s = [i for i, l in enumerate(lines) if l.strip() == BEGIN]
    e = [i for i, l in enumerate(lines) if l.strip() == END]
    if not s and not e:
        return None
    if len(s) != 1 or len(e) != 1 or e[0] < s[0]:
        raise Unsafe("the okf begin/end markers are unbalanced; fix or remove them by hand")
    return s[0], e[0]


def put_block(lines, block, at=None):
    """lines with our block replaced, else inserted after line `at`, else appended
    after one blank separator line (drop_block takes that line out again)."""
    span = find_block(lines)
    if span:
        return lines[:span[0]] + block + lines[span[1] + 1:]
    if at is not None:
        return lines[:at + 1] + block + lines[at + 1:]
    return lines + ([""] if lines else []) + block


def drop_block(lines):
    span = find_block(lines)
    if not span:
        return lines
    s, e = span
    if s > 0 and lines[s - 1] == "" and e == len(lines) - 1:
        s -= 1
    return lines[:s] + lines[e + 1:]


def mentions(lines, needle):
    """needle in any non-comment line: what the user's own rc already does."""
    return any(needle in l for l in lines if not l.lstrip().startswith("#"))


def load_json(text, what):
    if text is None or not text.strip():
        return {}
    try:
        doc = json.loads(text)
    except ValueError as e:
        raise Unsafe("{} is not plain JSON ({}); comments and trailing commas "
                     "cannot be edited safely".format(what, e))
    if not isinstance(doc, dict):
        raise Unsafe("{} does not hold a JSON object".format(what))
    return doc


def dump_json(doc, old):
    m = re.search(r"^([ \t]+)\S", old or "", re.M)  # keep the file's own indentation
    return json.dumps(doc, indent=m.group(1) if m else 2, ensure_ascii=False) + "\n"


def entry_state(entry, ident):
    if entry is None:
        return "absent"
    if SCRIPT not in json.dumps(entry):
        return "foreign"
    return "ok" if all(entry.get(k) == v for k, v in ident.items()) else "differs"


def json_edit(container, entry, ident, un, what, new_doc=None):
    """transform(old text) -> new text for a key-scoped merge of
    doc[container]["okf"]; foreign keys and the file's indentation survive."""
    def t(old):
        doc = load_json(old, what) or dict(new_doc or {})
        servers = doc.get(container)
        if servers is not None and not isinstance(servers, dict):
            raise Unsafe("{}: {} is not an object".format(what, container))
        cur = (servers or {}).get("okf")
        state = entry_state(cur, ident)
        if un:
            if state == "foreign":
                raise Skip("{}: the okf entry is not okf's own; left alone".format(what))
            if state == "absent":
                return old
            del servers["okf"]
            if not servers:
                del doc[container]
            return None if set(doc) <= {"$schema"} else dump_json(doc, old)
        if state == "foreign":
            raise Unsafe("{}: {}.okf exists and is not okf's own; remove it, then re-run".format(what, container))
        if state == "ok":
            return old
        if state == "differs":
            cur.update(ident)
        else:
            doc.setdefault(container, {})["okf"] = dict(entry)
        return dump_json(doc, old)
    return t


def toml_entry(text):
    try:
        return tomllib.loads(text or "").get("mcp_servers", {}).get("okf")
    except tomllib.TOMLDecodeError:
        return None


def toml_edit(args, un):
    """Codex config.toml without the `codex` CLI: one marker block, text only
    (stdlib tomllib cannot write, and the file carries the user's comments)."""
    ident = {"command": "uv", "args": args}
    body = ["[mcp_servers.okf]", 'command = "uv"',
            "args = [{}]".format(", ".join(json.dumps(a, ensure_ascii=False) for a in args)),
            "startup_timeout_sec = 30"]  # uv resolves `mcp` on its first start
    block = [BEGIN] + body + [END]

    def t(old):
        lines = lines_of(old or "")
        span = find_block(lines)
        state = entry_state(toml_entry(old), ident)
        if un:
            if span:
                return join(drop_block(lines)) or None
            if state == "ok" or state == "differs":
                raise Skip("registered by `codex mcp add`, not by this installer; "
                           "remove it with `codex mcp remove okf`")
            if state == "foreign":
                raise Skip("[mcp_servers.okf] is not okf's own; left alone")
            return old
        if not span and state != "absent":
            if state == "ok":
                return old
            raise Unsafe("config.toml already has an [mcp_servers.okf] table that is not "
                         "up to date or not okf's own; edit or remove it, then re-run")
        new = join(put_block(lines, block))
        try:
            data = tomllib.loads(new)
        except tomllib.TOMLDecodeError as e:
            raise Unsafe("config.toml would not be valid TOML ({}); add the block by hand".format(e))
        if entry_state(data.get("mcp_servers", {}).get("okf"), ident) != "ok":
            raise Unsafe("config.toml would not register okf as expected; add the block by hand")
        return new
    return t, body


def yaml_edit(args, un):
    """Hermes config.yaml: text edits only (the stdlib has no YAML parser), never a
    whole-file rewrite. Anything unusual raises Unsafe."""
    flow = "[{}]".format(", ".join(json.dumps(a, ensure_ascii=False) for a in args))

    def child(ind):
        return [ind + BEGIN, ind + "okf:", ind + '  command: "uv"', ind + "  args: " + flow, ind + END]
    whole = [BEGIN, "mcp_servers:"] + ["  " + l for l in child("")[1:-1]] + [END]

    def t(old):
        try:
            return go(old)
        except Unsafe:
            if un:  # nothing of ours to find in a shape we cannot read
                return old
            raise

    def go(old):
        lines = lines_of(old or "")
        span = find_block(lines)
        if un and span:
            return join(drop_block(lines)) or None
        if span:  # ours: regenerate in place, in the shape it was written
            s = span[0]
            ind = lines[s][:len(lines[s]) - len(lines[s].lstrip())]
            return join(put_block(lines, whole if lines[s + 1].strip() == "mcp_servers:" else child(ind)))
        tops = [i for i, l in enumerate(lines) if re.match(r"""["']?mcp_servers["']?\s*:""", l)]
        if not tops:
            return old if un else join(put_block(lines, whole))
        if len(tops) > 1:
            raise Unsafe("config.yaml has more than one top-level mcp_servers key")
        k = tops[0]
        if not re.match(r"mcp_servers:[ \t]*(#.*)?$", lines[k]):
            raise Unsafe("mcp_servers in config.yaml is not a plain block mapping")
        end = next((i for i in range(k + 1, len(lines))
                    if lines[i] and not lines[i][0].isspace() and lines[i][0] != "#"), len(lines))
        if end == k + 1 and end < len(lines) and re.match(r"-( |$)", lines[end]):
            raise Unsafe("mcp_servers in config.yaml is a list")
        if any(re.search(r"(^|[\s:\[{,])[&*][\w-]+|<<:", l) for l in lines[k:end]):
            raise Unsafe("mcp_servers in config.yaml uses YAML anchors or aliases")
        kids = [l for l in lines[k + 1:end] if l.strip() and not l.lstrip().startswith("#")]
        ci = kids[0][:len(kids[0]) - len(kids[0].lstrip())] if kids else "  "
        for i in range(k + 1, end):
            if re.match(re.escape(ci) + r"okf[ \t]*:", lines[i]):
                j = i + 1
                while j < end and (not lines[j].strip() or len(lines[j]) - len(lines[j].lstrip()) > len(ci)):
                    j += 1
                while not lines[j - 1].strip():
                    j -= 1
                if SCRIPT not in "\n".join(lines[i:j]):
                    raise Unsafe("config.yaml already has an mcp_servers.okf entry that is not okf's own")
                if un:  # Hermes rewrites config.yaml on `hermes config set` and drops our markers
                    rest = lines[:i] + lines[j:]
                    left = [l for l in rest[k + 1:end - (j - i)] if l.strip() and not l.lstrip().startswith("#")]
                    return join(rest if left else rest[:k] + rest[end - (j - i):]) or None
                return join(lines[:i] + child(ci) + lines[j:])
        return old if un else join(put_block(lines, child(ci), at=k))
    return t, whole


# --- files -------------------------------------------------------------------


def edit(path, transform, backup, mode=None):
    """Atomic write of transform(old text) through a symlinked dotfile; the first
    edit of an existing file keeps `<file>.okf-cli.bak`."""
    real = os.path.realpath(path)  # a symlinked dotfile is written through, never replaced
    old = read(real)
    new = transform(old)
    if new == old:
        return
    if new is None:
        os.remove(real)
        return
    os.makedirs(os.path.dirname(real), exist_ok=True)
    if old is not None and backup and not os.path.exists(real + ".okf-cli.bak"):
        shutil.copy2(real, real + ".okf-cli.bak")
    tmp = os.path.join(os.path.dirname(real), ".okf-cli.tmp." + os.path.basename(real))
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(new)
    if old is not None:
        shutil.copymode(real, tmp)
    elif mode:
        os.chmod(tmp, mode)
    os.replace(tmp, real)


def file_step(ctx, group, subject, path, transform, what, manual="", backup=True, mode=None):
    """One file edited through transform(old text or None) -> new text or None.
    The same transform plans (dry) and applies (on fresh content)."""
    try:
        old = read(os.path.realpath(path))
        new = transform(old)
    except Skip as e:
        return Step(group, subject, "skip", str(e))
    except (Unsafe, OSError) as e:
        return Step(group, subject, "blocked", "{}\n{}".format(e, manual) if manual else str(e))
    if new == old:
        return Step(group, subject, "ok", what)
    status = "remove" if new is None else "create" if old is None else "update"
    return Step(group, subject, status, what, lambda: (
        edit(path, transform, backup, mode), new is None and prune(ctx, os.path.dirname(path))))


# --- symlinks / copies (skills, zsh glue) ------------------------------------


def clear(p):
    if os.path.islink(p) or os.path.isfile(p):
        os.unlink(p)
    elif os.path.isdir(p):
        shutil.rmtree(p)


def prune(ctx, d):
    """Remove the empty directories an uninstall left behind; never HOME, above it or an agent's own dir."""
    home = os.path.realpath(ctx.home)
    stop = {home} | {os.path.realpath(harness_dir(ctx, h)) for h in HARNESSES}
    while os.path.realpath(d).startswith(home + os.sep) and os.path.realpath(d) not in stop:
        try:
            os.rmdir(d)
        except OSError:
            return
        d = os.path.dirname(d)


def tree(path):
    out = {}
    for d, dirs, files in os.walk(path):
        dirs[:] = [x for x in dirs if x != "__pycache__"]
        for f in files:
            if f != ".DS_Store":
                p = os.path.join(d, f)
                with open(p, "rb") as fh:
                    out[os.path.relpath(p, path)] = fh.read()
    return out


def same(src, dest):
    try:
        return tree(dest) == tree(src) if os.path.isdir(src) else read(dest) == read(src)
    except (OSError, Unsafe):
        return False


def mine(p):
    """p is an okf install of this thing: the okf skill dir or the zsh glue."""
    try:
        if os.path.isdir(p):
            head = read(os.path.join(p, "SKILL.md")) or ""
            return re.match(r"---\r?\n(?:[^\n]*\n)*?name:[ \t]*okf[ \t]*\r?\n", head) is not None
        return (read(p) or "").startswith("#compdef okf\n")
    except (OSError, Unsafe):
        return False


def put_state(src, dest, copy):
    tail = "/".join(src.split(os.sep)[-2:])  # skills/okf or cli/_okf
    if os.path.islink(dest):
        if not copy and os.path.realpath(dest) == os.path.realpath(src):
            return "ok"
        return "stale" if os.readlink(dest).rstrip("/").endswith(tail) or mine(dest) else "foreign"
    if os.path.lexists(dest):
        if copy and same(src, dest):
            return "ok"
        return "stale" if mine(dest) else "foreign"
    return "absent"


def put(src, dest, copy):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = os.path.join(os.path.dirname(dest), ".okf-cli.tmp." + os.path.basename(dest))
    clear(tmp)
    if not copy:
        os.symlink(src, tmp)
    elif os.path.isdir(src):
        shutil.copytree(src, tmp, ignore=IGNORED)
    else:
        shutil.copy2(src, tmp)
    clear(dest)
    os.rename(tmp, dest)


def put_step(ctx, group, subject, src, dest, copy, un, note=""):
    if not un and not os.path.exists(src):
        return Step(group, subject, "blocked", "source not found: " + ctx.short(src))
    state = put_state(src, dest, copy)
    what = ("{} (copy of {})" if copy else "{} -> {}").format(ctx.short(dest), ctx.short(src))
    if note:
        what += "  [{}]".format(note)
    if un:
        if state == "absent":
            return Step(group, subject, "ok")
        if state == "foreign":
            return Step(group, subject, "skip", "{} is not okf's; left alone".format(ctx.short(dest)))
        return Step(group, subject, "remove", what, lambda: (clear(dest), prune(ctx, os.path.dirname(dest))))
    if state == "ok":
        return Step(group, subject, "ok", what)
    if state == "foreign":
        return Step(group, subject, "blocked",
                    "{} exists and is not okf's; move it away, then re-run".format(ctx.short(dest)))
    return Step(group, subject, "create" if state == "absent" else "update", what,
                lambda: put(src, dest, copy))


# --- skills ------------------------------------------------------------------


def harness_dir(ctx, h):
    e = ctx.env
    return {
        "claude": e.get("CLAUDE_CONFIG_DIR") or ctx.path(".claude"),
        "omp": e.get("PI_CODING_AGENT_DIR") or ctx.path(e.get("PI_CONFIG_DIR") or ".omp", "agent"),
        "codex": e.get("CODEX_HOME") or ctx.path(".codex"),
        "opencode": os.path.join(e.get("XDG_CONFIG_HOME") or ctx.path(".config"), "opencode"),
        "kimi": e.get("KIMI_CODE_HOME") or ctx.path(".kimi-code"),
        "openclaw": e.get("OPENCLAW_STATE_DIR") or ctx.path(".openclaw"),
        "hermes": e.get("HERMES_HOME") or ctx.path(".hermes"),
    }[h]


def skill_steps(ctx, hs, un):
    src = os.path.join(ctx.pkg_root, "skills", "okf")
    copy = not ctx.source_tree
    steps = []

    def own(subject, dest, copy, note=""):
        steps.append(put_step(ctx, "skills", subject, src, dest, copy, un, note))
    if "claude" in hs:
        own("claude", os.path.join(harness_dir(ctx, "claude"), "skills", "okf"), copy)
    if "hermes" in hs:  # follows symlinks, but logs a security warning for a skill resolving outside ~/.hermes/skills
        own("hermes", os.path.join(harness_dir(ctx, "hermes"), "skills", "okf"), True)
    custom_openclaw = "openclaw" in hs and bool(ctx.env.get("OPENCLAW_STATE_DIR"))
    if custom_openclaw:  # a custom state dir drops ~/.agents/skills from the session skill index
        own("openclaw", os.path.join(harness_dir(ctx, "openclaw"), "skills", "okf"), True)
    readers = [h for h in SHARED_READERS if h in hs and not (h == "openclaw" and custom_openclaw)]
    shared = ctx.path(".agents", "skills", "okf")
    if readers and (not un or len(hs) == len(HARNESSES)):  # a subset uninstall keeps what the others read
        own("shared", shared, copy, "read by " + ", ".join(readers))
    elif readers:
        steps.append(Step("skills", "shared", "skip", "kept: other agents still read " + ctx.short(shared)))
    if not un:
        steps += [Step("skills", h, "skip", "covered by the shared " + ctx.short(shared)) for h in readers]
    return steps


# --- MCP ---------------------------------------------------------------------


def cli_step(ctx, subject, state, add, rm, un):
    """Registration through the harness's own CLI; `state` comes from reading its config."""
    if un:
        if state in ("ok", "differs"):
            return Step("mcp", subject, "remove", "run: " + shlex.join(rm), lambda: ctx.run(rm))
        if state == "foreign":
            return Step("mcp", subject, "skip", "the okf server is not okf's own; left alone")
        return Step("mcp", subject, "ok")
    if state == "ok":
        return Step("mcp", subject, "ok", "registered")
    if state == "foreign":
        return Step("mcp", subject, "blocked",
                    "an `okf` MCP server that is not okf's own exists; remove it ({}), then re-run".format(
                        shlex.join(rm)))
    if state == "differs":
        return Step("mcp", subject, "update", "run: {} && {}".format(shlex.join(rm), shlex.join(add)),
                    lambda: (ctx.run(rm), ctx.run(add)))
    return Step("mcp", subject, "create", "run: " + shlex.join(add), lambda: ctx.run(add))


def json_state(path, container, ident):
    try:
        servers = load_json(read(os.path.realpath(path)), path).get(container)
        return entry_state(servers.get("okf") if isinstance(servers, dict) else None, ident)
    except (Unsafe, OSError):
        return "unknown"


def json_step(ctx, h, path, container, entry, ident, un, new_doc=None, mode=None):
    what = "{}.okf in {}".format(container, ctx.short(path))
    manual = "add this to {} by hand:\n{}".format(
        ctx.short(path), json.dumps({container: {"okf": entry}}, indent=2))
    return file_step(ctx, "mcp", h, path, json_edit(container, entry, ident, un, ctx.short(path), new_doc),
                     what, manual, mode=mode)


def mcp_claude(ctx, un, args):
    base = ctx.env.get("CLAUDE_CONFIG_DIR")
    cfg = os.path.join(base, ".claude.json") if base else ctx.path(".claude.json")
    ident = {"command": "uv", "args": args}
    add = ["claude", "mcp", "add", "--scope", "user", "--transport", "stdio", "okf", "--", "uv"] + args
    if not ctx.which("claude"):  # fallback: key-scoped merge (0600 on creation: credentials live there)
        return json_step(ctx, "claude", cfg, "mcpServers", {"type": "stdio", **ident, "env": {}},
                         ident, un, mode=0o600)
    return cli_step(ctx, "claude", json_state(cfg, "mcpServers", ident), add,
                    ["claude", "mcp", "remove", "okf", "--scope", "user"], un)


def mcp_codex(ctx, un, args):
    cfg = os.path.join(harness_dir(ctx, "codex"), "config.toml")
    add = ["codex", "mcp", "add", "okf", "--", "uv"] + args
    try:
        text = read(os.path.realpath(cfg)) or ""
    except (Unsafe, OSError) as e:
        return Step("mcp", "codex", "blocked", "{}: {}".format(ctx.short(cfg), e))
    if any(l.strip() == BEGIN for l in text.split("\n")) or not ctx.which("codex"):
        t, body = toml_edit(args, un)  # a block we wrote stays ours; no CLI: fall back to the block
        return file_step(ctx, "mcp", "codex", cfg, t, "[mcp_servers.okf] in " + ctx.short(cfg),
                         "add this to {} by hand:\n{}".format(ctx.short(cfg), "\n".join(body)))
    return cli_step(ctx, "codex", entry_state(toml_entry(text), {"command": "uv", "args": args}), add,
                    ["codex", "mcp", "remove", "okf"], un)


def mcp_openclaw(ctx, un, args):
    cfg = os.path.join(harness_dir(ctx, "openclaw"), "openclaw.json")  # JSON5: read the text, never write it
    add = ["openclaw", "mcp", "set", "okf", json.dumps({"command": "uv", "args": args})]
    rm = ["openclaw", "mcp", "unset", "okf"]
    try:
        text = read(os.path.realpath(cfg)) or ""
    except (Unsafe, OSError) as e:
        return Step("mcp", "openclaw", "blocked", "{}: {}".format(ctx.short(cfg), e))
    if not ctx.which("openclaw"):
        if un:
            return Step("mcp", "openclaw", "skip" if SCRIPT in text else "ok",
                        "the openclaw CLI is not on PATH; run by hand: " + shlex.join(rm))
        return Step("mcp", "openclaw", "blocked",
                    "the openclaw CLI is not on PATH; run by hand:\n" + shlex.join(add))
    state = "absent" if SCRIPT not in text else "ok" if args[-1] in text else "differs"
    return cli_step(ctx, "openclaw", state, add, rm, un)


def mcp_hermes(ctx, un, args):
    cfg = os.path.join(harness_dir(ctx, "hermes"), "config.yaml")
    t, whole = yaml_edit(args, un)
    return file_step(ctx, "mcp", "hermes", cfg, t, "mcp_servers.okf in " + ctx.short(cfg),
                     "add this to {} by hand:\n{}".format(ctx.short(cfg), "\n".join(whole[1:-1])))


def opencode_config(ctx):
    if ctx.env.get("OPENCODE_CONFIG"):  # the user named their config file
        return ctx.env["OPENCODE_CONFIG"]
    base = harness_dir(ctx, "opencode")
    for name in ("opencode.json", "opencode.jsonc"):
        if os.path.isfile(os.path.join(base, name)):
            return os.path.join(base, name)
    return os.path.join(base, "opencode.json")


def mcp_steps(ctx, hs, un):
    script = os.path.join(ctx.pkg_root, "mcp", SCRIPT)
    args = ["run", "--with", "mcp<2", script]
    ident = {"command": "uv", "args": args}
    handlers = {
        "claude": mcp_claude, "codex": mcp_codex, "openclaw": mcp_openclaw, "hermes": mcp_hermes,
        "omp": lambda c, u, a: json_step(
            c, "omp", os.path.join(harness_dir(c, "omp"), "mcp.json"), "mcpServers",
            {"type": "stdio", **ident, "env": {}}, ident, u),
        "kimi": lambda c, u, a: json_step(
            c, "kimi", os.path.join(harness_dir(c, "kimi"), "mcp.json"), "mcpServers", dict(ident), ident, u),
        "opencode": lambda c, u, a: json_step(
            c, "opencode", opencode_config(c), "mcp",
            {"type": "local", "command": ["uv"] + a, "enabled": True, "timeout": 30000},
            {"command": ["uv"] + a}, u, new_doc={"$schema": "https://opencode.ai/config.json"}),
    }
    steps = []
    for h in hs:
        if not un and not ctx.which("uv"):
            steps.append(Step("mcp", h, "blocked",
                              "uv is not on PATH; install it (https://docs.astral.sh/uv/), then re-run"))
        elif not un and not os.path.isfile(script):
            steps.append(Step("mcp", h, "blocked", "MCP server script not found: " + ctx.short(script)))
        else:
            steps.append(handlers[h](ctx, un, args))
    return steps


# --- shells: PATH wrapper, rc blocks, completion -----------------------------


def shell_paths(ctx):
    data = ctx.env.get("XDG_DATA_HOME") or ctx.path(".local", "share")
    conf = os.path.join(ctx.env.get("XDG_CONFIG_HOME") or ctx.path(".config"), "fish")
    if ctx.platform == "darwin":  # terminals start login shells, which never read .bashrc
        bash_rc = next((ctx.path(n) for n in (".bash_profile", ".bash_login", ".profile")
                        if os.path.isfile(ctx.path(n))), ctx.path(".bash_profile"))
    else:
        bash_rc = ctx.path(".bashrc")
    return {
        "zsh_rc": os.path.join(ctx.env.get("ZDOTDIR") or ctx.home, ".zshrc"),
        # uninstall looks everywhere a block may have gone, whatever platform or ZDOTDIR said then
        "zsh_rcs": list(dict.fromkeys([os.path.join(ctx.env.get("ZDOTDIR") or ctx.home, ".zshrc"),
                                       ctx.path(".zshrc")])),
        "zsh_comp": ctx.path(".zsh", "completions", "_okf"),
        "bash_rc": bash_rc,
        "bash_rcs": [ctx.path(n) for n in (".bashrc", ".bash_profile", ".bash_login", ".profile")],
        "bash_comp": os.path.join(data, "bash-completion", "completions", "okf"),
        "fish_dir": conf,
        "fish_conf": os.path.join(conf, "conf.d", "okf.fish"),
        "fish_comp": os.path.join(conf, "completions", "okf.fish"),
    }


def wrapper_step(ctx, un):
    """~/.local/bin/okf for a source tree whose okf is not on PATH yet.
    -> (step, whether ~/.local/bin must be on PATH)"""
    dest = ctx.path(".local", "bin", "okf")
    cli = os.path.join(ctx.pkg_root, "cli", "okf-cli.py")
    text = WRAPPER_HEAD + 'exec uv run --script {} "$@"\n'.format(shlex.quote(cli))
    what = "{} (runs {})".format(ctx.short(dest), ctx.short(cli))
    try:
        ours = (read(dest) or "").startswith(WRAPPER_HEAD)
    except (Unsafe, OSError):
        ours = False

    def t(cur):
        if cur is not None and not cur.startswith(WRAPPER_HEAD):
            if un:
                raise Skip("{} is not okf's; left alone".format(ctx.short(dest)))
            raise Unsafe("{} exists and is not okf's; move it away, then re-run".format(ctx.short(dest)))
        return None if un else text

    def step():
        s = file_step(ctx, "shell", "PATH", dest, t, what, backup=False, mode=0o755)
        return s, s.status != "blocked"  # a wrapper that could not be placed needs no PATH line
    if un or ours:
        return step()
    found = ctx.which("okf")
    if found:
        return Step("shell", "PATH", "skip", "okf is already on PATH: " + ctx.short(found)), False
    if not ctx.source_tree:  # pipx/uv put their own console script in a bin directory; that is not ours to touch
        return Step("shell", "PATH", "skip",
                    "okf is not on PATH; run `pipx ensurepath` (or add its bin directory to PATH)"), False
    return step()  # a foreign file in the way comes back BLOCKED


def argcomplete_code(shell):
    try:
        from argcomplete.shell_integration import shellcode
    except ImportError as e:
        raise Unsafe("argcomplete cannot be imported ({})".format(e))
    return "{}\n{}".format(MANAGED, shellcode(["okf"], shell=shell))


def owned_file(content, un, where):
    def t(old):
        if old is not None and old.strip() and not old.startswith(MANAGED + "\n"):
            if un:
                raise Skip("{} is not okf's; left alone".format(where))
            raise Unsafe("{} exists and is not okf's; move it away, then re-run".format(where))
        return None if un else content()
    return t


def completion_step(ctx, sh, p, un):
    subject = sh + " completion"
    if sh == "zsh":
        return put_step(ctx, "shell", subject, os.path.join(ctx.pkg_root, "cli", "_okf"),
                        p["zsh_comp"], not ctx.source_tree, un)
    path = p[sh + "_comp"]
    return file_step(ctx, "shell", subject, path, owned_file(lambda: argcomplete_code(sh), un, ctx.short(path)),
                     ctx.short(path), backup=False)


def home_var(ctx, path):
    return '"$HOME' + path[len(ctx.home):] + '"' if path.startswith(ctx.home + os.sep) else shlex.quote(path)


def rc_body(ctx, sh, rest, p, needs_path, comp):
    """Lines our rc block holds; `rest` is the rc without our block, so what the
    user already configures is not added twice."""
    body = []
    if needs_path and not mentions(rest, ".local/bin"):
        body.append('case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) export PATH="$HOME/.local/bin:$PATH" ;; esac')
    if comp and sh == "zsh":
        fpath = mentions(rest, ".zsh/completions")
        compinit = any(re.search(r"\bcompinit\b", l) for l in rest if not l.lstrip().startswith("#"))
        if not fpath:
            body.append('fpath=("$HOME/.zsh/completions" $fpath)')
        if not compinit:
            body.append("autoload -Uz compinit && compinit")
        elif not fpath:  # compinit may have run already: register without waiting for it
            body += ["autoload -Uz _okf", "(( $+functions[compdef] )) && compdef _okf okf"]
    elif comp:
        body.append("if [ -r {0} ]; then . {0}; fi".format(home_var(ctx, p["bash_comp"])))
    return body


def rc_step(ctx, sh, p, un, needs_path, comp, path=None):
    if sh == "fish":
        path = p["fish_conf"]
        t = owned_file(lambda: MANAGED + "\nif not contains -- $HOME/.local/bin $PATH\n"
                       "    set -gx PATH $HOME/.local/bin $PATH\nend\n",
                       un or not needs_path, ctx.short(path))
        step = file_step(ctx, "shell", "fish PATH", path, t, ctx.short(path), backup=False)
    else:
        path = path or p[sh + "_rc"]

        def t(old):
            text = old or ""
            lines = lines_of(text.replace("\r", ""))  # enough to decide whether anything is to be done
            body = [] if un else rc_body(ctx, sh, drop_block(lines), p, needs_path, comp)
            if not body and find_block(lines) is None:
                return old
            if "\r" in text:
                raise Unsafe("the file uses CRLF line endings")
            if not body:
                return join(drop_block(lines)) or None
            return join(put_block(lines, [BEGIN, MANAGED] + body + [END]))
        manual = "add to {} by hand:\n{}".format(
            ctx.short(path), "\n".join([BEGIN] + rc_body(ctx, sh, [], p, needs_path, comp) + [END]))
        step = file_step(ctx, "shell", sh + " rc", path, t, ctx.short(path) + " (managed block)", manual)
    return None if step.status == "ok" and not os.path.lexists(path) else step  # nothing wanted, nothing there


def shell_steps(ctx, ss, un):
    if not ss:
        return []
    p = shell_paths(ctx)
    wrapper, needs_path = wrapper_step(ctx, un)
    steps = [wrapper]
    for sh in ss:
        comp = completion_step(ctx, sh, p, un)
        active = comp.status in ("create", "update", "ok")
        rcs = [x for x in p[sh + "_rcs"] if os.path.lexists(x)] if un and sh != "fish" else [None]
        steps += [comp] + [rc_step(ctx, sh, p, un, needs_path, active, x) for x in rcs]
    return [s for s in steps if s]


# --- selection, plan, output -------------------------------------------------


def passwd_shell():
    import pwd  # not at module level: Windows has no pwd, and run() rejects it with a message
    try:
        return pwd.getpwuid(os.getuid()).pw_shell
    except KeyError:  # a container user without a passwd entry
        return ""


def shell_detected(ctx, sh):
    p = shell_paths(ctx)
    # SHELL is set by login(1) and by bash, not by zsh: without it (cron, env -i, sudo) the passwd entry is the login shell
    login = os.path.basename(ctx.env.get("SHELL") or passwd_shell())
    if sh == "zsh":
        return os.path.isfile(p["zsh_rc"]) or login == "zsh"
    if sh == "bash":
        return any(os.path.isfile(ctx.path(n)) for n in (".bashrc", ".bash_profile")) or login == "bash"
    return os.path.isdir(p["fish_dir"]) or login == "fish"


def select(ctx, only, un):
    """-> (harnesses, shells, skip steps). Install without --only auto-detects;
    --only names are taken as given; uninstall without --only considers all."""
    if only is not None or un:
        return ([h for h in HARNESSES if only is None or h in only],
                [s for s in SHELLS if only is None or s in only], [])
    hs, ss, notes = [], [], []
    for h in HARNESSES:
        d = harness_dir(ctx, h)
        if ctx.which(h) or os.path.isdir(d):
            hs.append(h)
        else:
            notes.append(Step("detect", h, "skip", "not detected (no `{}` on PATH, no {})".format(h, ctx.short(d))))
    for s in SHELLS:
        if shell_detected(ctx, s):
            ss.append(s)
        else:
            notes.append(Step("detect", s, "skip", "not detected (no rc file or config directory, not the login shell)"))
    return hs, ss, notes


def plan(ctx, only=None, un=False):
    hs, ss, steps = select(ctx, only, un)
    return steps + skill_steps(ctx, hs, un) + mcp_steps(ctx, hs, un) + shell_steps(ctx, ss, un)


def execute(steps):
    for s in steps:
        if s.status not in CHANGES:
            continue
        try:
            s.apply()
            s.done = True
        except Skip as e:
            s.status, s.detail = "skip", str(e)
        except Unsafe as e:
            s.status, s.detail = "blocked", str(e)
        except (OSError, Failed) as e:
            s.status, s.detail = "failed", str(e)


PLAN_VERB = {"create": "create", "update": "update", "remove": "remove", "ok": "unchanged",
             "skip": "skip", "blocked": "BLOCKED", "failed": "FAILED"}
DONE_VERB = dict(PLAN_VERB, create="created", update="updated", remove="removed")


def report(ctx, steps, apply, un):
    """The --json output: one dict like the other commands print, one entry per step."""
    return {"apply": apply, "uninstall": un, "source": ctx.pkg_root, "source_tree": ctx.source_tree,
            "steps": [{"group": s.group, "subject": s.subject, "status": s.status, "done": s.done,
                       "detail": s.detail} for s in steps]}


def render(ctx, steps, apply, un):
    print("okf install{} - {}".format(
        " --uninstall" if un else "",
        "applied" if apply else "PLAN only, nothing is changed (add --apply to perform it)"))
    print("source: {} ({})".format(ctx.short(ctx.pkg_root),
                                   "source tree, skills are linked" if ctx.source_tree
                                   else "installed package, skills are copied"))
    group = None
    width = max([len(s.subject) for s in steps] + [8]) + 2
    for s in steps:
        if un and s.status == "ok":
            continue
        if s.group != group:
            group = s.group
            print("\n" + group)
        first, *rest = s.detail.split("\n")
        print("  {:<10}{:<{w}}{}".format((DONE_VERB if s.done else PLAN_VERB)[s.status], s.subject, first,
                                         w=width).rstrip())
        for line in rest:
            print(" " * (12 + width) + line)
    planned = [s for s in steps if s.status in CHANGES or s.done]
    bad = [s for s in steps if s.status in ("blocked", "failed")]
    print()
    if bad:
        print("{} step(s) blocked or failed: read the marked lines above".format(len(bad)))
    if apply and any(s.done for s in steps):
        print("done: {} step(s) changed. Open a new shell and restart your agents to pick it up.".format(
            sum(s.done for s in steps)))
    elif planned:
        print("{} step(s) planned. Run again with --apply to perform them.".format(len(planned)))
    elif not bad:
        print("nothing to {}: already up to date".format("remove" if un else "do"))


def run(args, ctx=None):
    """Entry point of `okf install`; returns (exit code, report). Prints the text report
    unless `args.json`; a refused call raises OkfError."""
    ctx = ctx or Ctx()
    if ctx.platform == "win32":
        raise OkfError("internal", "ERROR: okf install supports macOS and Linux only")
    only = None
    if args.only is not None:
        only = [n.strip() for n in args.only.split(",") if n.strip()]
        unknown = [n for n in only if n not in HARNESSES + SHELLS]
        if unknown or not only:
            raise OkfError("invalid_input", "install: unknown --only name(s): {}; valid: {}".format(
                ", ".join(unknown) or "(none given)", ", ".join(HARNESSES + SHELLS)))
    steps = plan(ctx, only, args.uninstall)
    if args.apply:
        execute(steps)
    code = 1 if any(s.status in ("blocked", "failed") for s in steps) else 0
    if not args.json:
        render(ctx, steps, args.apply, args.uninstall)
    return code, report(ctx, steps, args.apply, args.uninstall)
