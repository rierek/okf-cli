#!/usr/bin/env python3
"""Tests for `okf install` (okf_install.py) — unittest.

Every test runs in a tmp HOME with a PATH that holds only stub binaries: nothing
touches the real home, the real PATH or a real harness. Stub CLIs (claude,
codex, openclaw) behave like the real ones for the one thing install reads
back — the config file their `mcp add/set` writes.

Run: just test tests.test_okf_install -v
"""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
import types
import unittest
from unittest import mock

_HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "cli")
if _HERE not in sys.path:  # cli/ holds the okf package
    sys.path.insert(0, _HERE)

from okf import errors as okf_errors
from okf import install as okf_install_cmd
from okf import parser as okf_parser
from okf import parser_support as okf_parser_support
from tests.okf_testkit import uv_start_log


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_HERE, filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


inst = _load("okf_install", "okf_install.py")

_STUB_HEAD = ('#!%s\nimport json, os, re, sys, time\n'
              'open(os.environ["OKF_STUB_LOG"], "a").write('
              'json.dumps([os.path.basename(sys.argv[0])] + sys.argv[1:]) + "\\n")\n'
              # install must never let a harness CLI prompt: stdin has to be /dev/null
              'if os.fstat(0).st_rdev != os.stat(os.devnull).st_rdev:\n'
              '    sys.exit("stdin is not /dev/null: a prompt could hang")\n'
              'time.sleep(float(os.environ.get("OKF_STUB_SLEEP", "0")))\n' % sys.executable)
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
cfg = os.path.join(os.path.expanduser("~"), ".codex", "config.toml")
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


def snap(root):
    """Every file and symlink under root: what a plan must not change."""
    out = {}
    for d, dirs, files in os.walk(root):
        for n in files + [x for x in dirs if os.path.islink(os.path.join(d, x))]:
            p = os.path.join(d, n)
            rel = os.path.relpath(p, root)
            if os.path.islink(p):
                out[rel] = ("link", os.readlink(p))
            else:
                with open(p, "rb") as f:
                    out[rel] = ("file", f.read(), os.stat(p).st_mode)
    return out


class Machine(unittest.TestCase):
    """A tmp machine: home, a PATH of stubs, and an installed-package layout."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = self.mk("home")
        self.bin = self.mk("bin")
        self.log = os.path.join(self.tmp, "calls.log")
        self.pkg = self.make_pkg(os.path.join(self.tmp, "pkg"))
        self.env = {"HOME": self.home, "PATH": self.bin, "SHELL": "/bin/zsh", "OKF_STUB_LOG": self.log}
        self.stub("uv")

    # -- fixtures
    def mk(self, *parts):
        p = os.path.join(self.tmp, *parts)
        os.makedirs(p, exist_ok=True)
        return p

    def put(self, path, text, mode=None):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        if mode:
            os.chmod(path, mode)
        return path

    def get(self, path):
        with open(path, encoding="utf-8", newline="") as f:
            return f.read()

    def make_pkg(self, root):
        """The layout of the wheel; use_source_tree() turns it into a checkout."""
        self.put(os.path.join(root, "skills", "okf", "SKILL.md"),
                 "---\nname: okf\ndescription: test skill\n---\nbody\n")
        self.put(os.path.join(root, "skills", "okf", "references", "a.md"), "ref\n")
        os.makedirs(os.path.join(root, "cli"), exist_ok=True)
        shutil.copy(os.path.join(_HERE, "_okf"), os.path.join(root, "cli", "_okf"))
        self.put(os.path.join(root, "cli", "okf-cli.py"), "import sys\nprint(sys.argv[1:])\n")
        self.put(os.path.join(root, "mcp", "okf_mcp.py"), "# stub\n")
        return root

    def use_source_tree(self):
        self.put(os.path.join(self.pkg, "pyproject.toml"), "")

    def stub(self, name):
        path = self.put(os.path.join(self.bin, name), _STUB_HEAD + STUBS[name])
        os.chmod(path, 0o755)

    def harness_dirs(self, *names):
        for n in names:
            self.mk("home", *{"claude": [".claude"], "omp": [".omp", "agent"], "codex": [".codex"],
                              "opencode": [".config", "opencode"], "kimi": [".kimi-code"],
                              "openclaw": [".openclaw"], "hermes": [".hermes"]}[n])

    # -- running
    def ctx(self, env=None, **kw):
        kw.setdefault("platform", "linux")
        return inst.Ctx(env=env or self.env, home=self.home, pkg_root=kw.pop("pkg", self.pkg), **kw)

    def install(self, only=None, un=False, apply=False, as_json=False, **kw):
        args = types.SimpleNamespace(apply=apply, uninstall=un, only=only, json=as_json)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code, _report = inst.run(args, self.ctx(**kw))
        return code, out.getvalue()

    def apply(self, **kw):
        return self.install(apply=True, **kw)

    def calls(self):
        if not os.path.exists(self.log):
            return []
        return [json.loads(l) for l in self.get(self.log).splitlines()]

    @property
    def script(self):
        return os.path.join(self.pkg, "mcp", "okf_mcp.py")

    @property
    def args(self):
        return ["run", "--with", "mcp<2", self.script]

    def h(self, *parts):
        return os.path.join(self.home, *parts)


class PlanOnly(Machine):
    def test_plan_changes_nothing_and_runs_no_subprocess(self):
        self.harness_dirs("claude", "codex", "omp", "hermes", "kimi")
        self.put(self.h(".zshrc"), "export A=1\n")
        self.stub("claude")
        self.stub("codex")
        before = snap(self.tmp)
        code, out = self.install()
        self.assertEqual((code, snap(self.tmp)), (0, before))
        self.assertIn("PLAN only", out)
        self.assertIn("Run again with --apply", out)
        self.assertEqual(self.calls(), [])

    def test_plan_names_every_file_and_reason(self):
        self.harness_dirs("omp", "hermes")
        code, out = self.install()
        self.assertIn("~/.omp/agent/mcp.json", out)
        self.assertIn("~/.hermes/config.yaml", out)
        self.assertIn("~/.agents/skills/okf", out)
        self.assertRegex(out, r"skip\s+claude\s+not detected \(no `claude` on PATH, no ~/.claude\)")


class ApplyAndIdempotence(Machine):
    def everything(self):
        self.harness_dirs("claude", "omp", "codex", "opencode", "kimi", "openclaw", "hermes")
        self.stub("openclaw")

    def test_apply_installs_skills_and_mcp_for_every_detected_harness(self):
        self.everything()
        code, out = self.apply()
        self.assertEqual(code, 0, out)
        for d in (".agents/skills/okf", ".claude/skills/okf", ".hermes/skills/okf"):
            self.assertEqual(self.get(self.h(d, "SKILL.md")), self.get(os.path.join(self.pkg, "skills/okf/SKILL.md")))
            self.assertTrue(os.path.isfile(self.h(d, "references", "a.md")))
            self.assertFalse(os.path.islink(self.h(d)), "a wheel install copies")
        for d in (".omp/agent/skills", ".codex/skills", ".config/opencode/skills", ".kimi-code/skills",
                  ".openclaw/skills"):
            self.assertFalse(os.path.exists(self.h(d)), d + ": the shared skill already covers it")
        stdio = {"type": "stdio", "command": "uv", "args": self.args, "env": {}}
        self.assertEqual(json.loads(self.get(self.h(".omp/agent/mcp.json"))), {"mcpServers": {"okf": stdio}})
        self.assertEqual(json.loads(self.get(self.h(".kimi-code/mcp.json"))),
                         {"mcpServers": {"okf": {"command": "uv", "args": self.args}}})
        self.assertEqual(json.loads(self.get(self.h(".config/opencode/opencode.json"))), {
            "$schema": "https://opencode.ai/config.json",
            "mcp": {"okf": {"type": "local", "command": ["uv"] + self.args, "enabled": True, "timeout": 30000}}})
        # no `claude` / `codex` CLI on PATH: the fallbacks write the config themselves
        self.assertEqual(json.loads(self.get(self.h(".claude.json"))), {"mcpServers": {"okf": stdio}})
        self.assertEqual(os.stat(self.h(".claude.json")).st_mode & 0o777, 0o600)
        okf_table = tomllib.loads(self.get(self.h(".codex/config.toml")))["mcp_servers"]["okf"]
        self.assertEqual(okf_table, {"command": "uv", "args": self.args, "startup_timeout_sec": 30})
        yaml = self.get(self.h(".hermes/config.yaml"))
        self.assertIn('mcp_servers:\n  okf:\n    command: "uv"\n    args: ["run", "--with", "mcp<2", "%s"]' % self.script,
                      yaml)
        self.assertEqual(self.calls(), [["openclaw", "mcp", "set", "okf",
                                         json.dumps({"command": "uv", "args": self.args})]])

    def test_second_apply_is_a_noop(self):
        self.everything()
        self.put(self.h(".config/opencode/opencode.json"), '{"theme": "x"}\n')
        self.assertEqual(self.apply()[0], 0)
        first, calls = snap(self.tmp), self.calls()
        code, out = self.apply()
        self.assertEqual(code, 0)
        self.assertIn("already up to date", out)
        self.assertEqual((snap(self.tmp), self.calls()), (first, calls))

    def test_cli_route_calls_the_harness_cli_once_and_then_nothing(self):
        self.harness_dirs("claude", "codex")
        for n in ("claude", "codex"):
            self.stub(n)
        self.assertEqual(self.apply()[0], 0)
        self.assertEqual(self.calls(), [
            ["claude", "mcp", "add", "--scope", "user", "--transport", "stdio", "okf", "--", "uv"] + self.args,
            ["codex", "mcp", "add", "okf", "--", "uv"] + self.args])
        self.assertEqual(self.apply()[0], 0)
        self.assertEqual(len(self.calls()), 2)

    def test_a_hanging_harness_cli_times_out_and_the_other_steps_carry_on(self):
        self.harness_dirs("claude", "omp")
        self.stub("claude")
        code, out = self.apply(env=dict(self.env, OKF_STUB_SLEEP="5"), timeout=1)
        self.assertEqual(code, 1)
        self.assertRegex(out, r"FAILED\s+claude\s+.*timed out")
        self.assertIn("okf", json.loads(self.get(self.h(".omp/agent/mcp.json")))["mcpServers"])

    def test_moved_install_updates_every_registration(self):
        self.harness_dirs("claude", "omp", "hermes")
        self.stub("claude")
        self.apply()
        moved = self.make_pkg(os.path.join(self.tmp, "moved"))
        moved_script = os.path.join(moved, "mcp", "okf_mcp.py")
        code, out = self.apply(pkg=moved)
        self.assertEqual(code, 0, out)
        moved_args = ["run", "--with", "mcp<2", moved_script]
        self.assertEqual(json.loads(self.get(self.h(".omp/agent/mcp.json")))["mcpServers"]["okf"]["args"], moved_args)
        self.assertEqual(json.loads(self.get(self.h(".claude.json")))["mcpServers"]["okf"]["args"], moved_args)
        self.assertEqual([c[:3] for c in self.calls()], [["claude", "mcp", "add"], ["claude", "mcp", "remove"],
                                                         ["claude", "mcp", "add"]])
        self.assertEqual(self.get(self.h(".hermes/config.yaml")).count("okf_mcp.py"), 1)
        self.assertIn(moved_script, self.get(self.h(".hermes/config.yaml")))

    def test_source_tree_links_skills_and_copy_dirs_stay_copies(self):
        self.use_source_tree()
        self.harness_dirs("claude", "hermes", "codex")
        self.apply()
        src = os.path.join(self.pkg, "skills", "okf")
        for d in (".claude/skills/okf", ".agents/skills/okf"):
            self.assertTrue(os.path.islink(self.h(d)))
            self.assertEqual(os.path.realpath(self.h(d)), os.path.realpath(src))
        self.assertFalse(os.path.islink(self.h(".hermes/skills/okf")), "hermes warns about symlinked skills outside its dir")
        self.assertTrue(os.path.isfile(self.h(".hermes/skills/okf/SKILL.md")))
        self.assertTrue(os.path.islink(self.h(".zsh/completions/_okf")), "a clone links the zsh glue too")

    def test_stale_copy_of_the_skill_is_replaced_and_foreign_dir_refused(self):
        self.harness_dirs("claude", "hermes")
        self.put(self.h(".claude/skills/okf/SKILL.md"), "---\nname: okf\ndescription: old\n---\nold\n")
        self.put(self.h(".hermes/skills/okf/SKILL.md"), "---\nname: mine\n---\nuser's own\n")
        before = self.get(self.h(".hermes/skills/okf/SKILL.md"))
        code, out = self.apply()
        self.assertEqual(code, 1)
        self.assertIn("BLOCKED", out)
        self.assertIn("body", self.get(self.h(".claude/skills/okf/SKILL.md")))
        self.assertEqual(self.get(self.h(".hermes/skills/okf/SKILL.md")), before)


class ForeignContentSurvives(Machine):
    def roundtrip(self, path, original, only):
        self.put(path, original)
        self.assertEqual(self.apply(only=only)[0], 0)
        installed = self.get(path)
        self.assertNotEqual(installed, original)
        self.assertEqual(self.apply(only=only)[1].count("already up to date"), 1)
        self.assertEqual(self.install(only=only, un=True, apply=True)[0], 0)
        self.assertEqual(self.get(path), original, "uninstall restores the file byte for byte")
        return installed

    def test_json_keeps_other_servers_keys_and_indentation(self):
        original = json.dumps({"theme": "dark", "mcpServers": {"other": {"command": "x", "args": []}}}, indent=4) + "\n"
        installed = self.roundtrip(self.h(".omp/agent/mcp.json"), original, "omp")
        self.assertIn('\n    "mcpServers": {\n        "other"', installed)
        doc = json.loads(installed)
        self.assertEqual(doc["mcpServers"]["other"], {"command": "x", "args": []})
        self.assertEqual(doc["theme"], "dark")

    def test_toml_keeps_comments_and_tables(self):
        original = ('# my codex config\nmodel = "gpt"  # inline\n\n[mcp_servers.other]\ncommand = "npx"\n'
                    'args = ["-y", "x"]\n\n# trailing comment\n')
        installed = self.roundtrip(self.h(".codex/config.toml"), original, "codex")
        self.assertTrue(installed.startswith(original))
        self.assertEqual(tomllib.loads(installed)["mcp_servers"]["other"]["command"], "npx")

    def test_yaml_child_goes_under_an_existing_mcp_servers_key(self):
        original = ('# hermes\nmodel: x\n\nmcp_servers:\n  # my servers\n  other:\n    command: "npx"\n'
                    '    args: ["-y", "x"]\n\ntools:\n  a: 1\n')
        installed = self.roundtrip(self.h(".hermes/config.yaml"), original, "hermes")
        lines = installed.split("\n")
        k = lines.index("  " + inst.BEGIN)
        self.assertEqual(lines[k - 1], "mcp_servers:", "directly under the key")
        self.assertEqual(lines[k + 4], "  " + inst.END)
        self.assertEqual("\n".join(lines[:k] + lines[k + 5:]), original, "the block is the only addition")

    def test_yaml_without_mcp_servers_gets_a_whole_block_at_the_end(self):
        original = "model: x\nagent:\n  name: a\n"
        installed = self.roundtrip(self.h(".hermes/config.yaml"), original, "hermes")
        self.assertTrue(installed.startswith(original + "\n" + inst.BEGIN + "\nmcp_servers:\n  okf:\n"))

    def test_yaml_siblings_of_ours_stay_untouched(self):
        original = "mcp_servers:\n  other:\n    command: x\n"
        self.put(self.h(".hermes/config.yaml"), original)
        self.apply(only="hermes")
        self.assertIn("  other:\n    command: x\n", self.get(self.h(".hermes/config.yaml")))

    def test_rc_block_goes_through_a_dotfile_symlink(self):
        self.use_source_tree()
        original = "export A=1\nalias ll='ls -l'\n"
        target = self.put(os.path.join(self.tmp, "dotfiles", "zshrc"), original)
        os.symlink(target, self.h(".zshrc"))
        self.assertEqual(self.apply(only="zsh")[0], 0)
        self.assertTrue(os.path.islink(self.h(".zshrc")), "the symlink is written through, not replaced")
        self.assertTrue(self.get(target).startswith(original + "\n" + inst.BEGIN))
        self.assertEqual(self.install(only="zsh", un=True, apply=True)[0], 0)
        self.assertEqual(self.get(target), original)
        self.assertTrue(os.path.islink(self.h(".zshrc")))

    def test_first_edit_keeps_one_backup_of_the_original(self):
        original = '{"mcpServers": {"other": {"command": "x"}}}\n'
        path = self.put(self.h(".omp/agent/mcp.json"), original)
        self.apply(only="omp")
        bak = path + ".okf-cli.bak"
        self.assertEqual(self.get(bak), original)
        self.install(only="omp", un=True, apply=True)
        self.assertEqual(self.get(bak), original, "later edits never overwrite it")

    def test_an_edited_file_keeps_its_permissions(self):
        path = self.put(self.h(".omp/agent/mcp.json"), '{"mcpServers": {"other": {"command": "x"}}}\n', 0o600)
        self.apply(only="omp")
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
        self.install(only="omp", un=True, apply=True)
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)

    def test_harness_clis_never_inherit_stdin(self):
        """A prompt must not be able to hang an apply: whatever stdin the caller has, the
        stub (which refuses anything but /dev/null) is started with /dev/null."""
        self.harness_dirs("claude")
        self.stub("claude")
        reader, writer = os.pipe()
        saved = os.dup(0)
        os.dup2(reader, 0)
        try:
            code, out = self.apply()
        finally:
            os.dup2(saved, 0)
            for fd in (saved, reader, writer):
                os.close(fd)
        self.assertEqual(code, 0, out)
        self.assertEqual(len(self.calls()), 1)


class Refusals(Machine):
    def refused(self, path, text, only, expect, **kw):
        self.put(path, text)
        code, out = self.apply(only=only, **kw)
        self.assertEqual(code, 1, out)
        self.assertIn("BLOCKED", out)
        self.assertIn(expect, out)
        self.assertEqual(self.get(path), text, "a refused edit leaves the file byte for byte")
        self.assertFalse(os.path.exists(path + ".okf-cli.bak"))
        return out

    def test_jsonc_with_comments_is_refused_with_the_manual_edit(self):
        out = self.refused(self.h(".config/opencode/opencode.jsonc"), '{\n  // my config\n  "theme": "x"\n}\n',
                           "opencode", "not plain JSON")
        self.assertIn('"okf"', out)
        self.assertIn('"command"', out)

    def test_json_that_is_not_an_object_is_refused(self):
        self.refused(self.h(".kimi-code/mcp.json"), "[1, 2]\n", "kimi", "does not hold a JSON object")

    def test_foreign_okf_entry_is_refused_and_survives_uninstall(self):
        path = self.h(".omp/agent/mcp.json")
        text = json.dumps({"mcpServers": {"okf": {"command": "mine", "args": ["x"]}}}) + "\n"
        self.refused(path, text, "omp", "not okf's own")
        code, out = self.install(only="omp", un=True, apply=True)
        self.assertEqual(code, 0)
        self.assertIn("left alone", out)
        self.assertEqual(self.get(path), text)

    def test_readme_style_python_entry_for_our_script_is_updated(self):
        path = self.h(".omp/agent/mcp.json")
        self.put(path, json.dumps({"mcpServers": {"okf": {
            "command": "python3", "args": ["/old/place/mcp/okf_mcp.py"], "note": "keep"}}}))
        self.assertEqual(self.apply(only="omp")[0], 0)
        entry = json.loads(self.get(path))["mcpServers"]["okf"]
        self.assertEqual((entry["command"], entry["args"], entry["note"]), ("uv", self.args, "keep"))

    def test_unusual_yaml_is_refused(self):
        for text, why in (("mcp_servers: {}\n", "not a plain block mapping"),
                          ("mcp_servers:\n  a: &x\n    command: c\n  b: *x\n", "anchors"),
                          ("mcp_servers:\n- a\n- b\n", "is a list"),
                          ('"mcp_servers":\n  a: 1\n', "not a plain block mapping"),
                          ("mcp_servers:\n  a: 1\nmcp_servers:\n  b: 2\n", "more than one"),
                          ("mcp_servers:\n  okf:\n    command: mine\n", "not okf's own")):
            with self.subTest(text=text):
                self.refused(self.h(".hermes/config.yaml"), text, "hermes", why)

    def test_toml_that_already_defines_okf_is_refused_without_the_cli(self):
        text = '[mcp_servers.okf]\ncommand = "mine"\n'
        self.refused(self.h(".codex/config.toml"), text, "codex", "not up to date or not okf's own")
        out = self.refused(self.h(".codex/config.toml"), "mcp_servers = {}\n[x\n", "codex", "valid TOML")
        self.assertIn("[mcp_servers.okf]", out)

    def test_crlf_and_unbalanced_markers_are_refused(self):
        self.use_source_tree()  # a checkout needs the PATH block, so there is something to write
        self.refused(self.h(".zshrc"), "export A=1\r\n", "zsh", "CRLF")
        self.refused(self.h(".zshrc"), "# >>> okf-cli >>>\nexport A=1\n", "zsh", "unbalanced")

    def test_foreign_files_are_never_overwritten_or_removed(self):
        self.use_source_tree()
        self.harness_dirs("claude")
        self.mk("home", ".config", "fish")
        foreign = {".claude/skills/okf/SKILL.md": "someone else's\n",
                   ".local/bin/okf": "#!/bin/sh\necho mine\n",
                   ".zsh/completions/_okf": "#compdef other\n",
                   ".config/fish/completions/okf.fish": "complete -c okf\n"}
        for rel, text in foreign.items():
            self.put(self.h(rel), text, 0o755)
        code, out = self.apply()
        self.assertEqual(code, 1)
        self.assertEqual(out.count("BLOCKED"), 4, out)
        self.assertEqual({rel: self.get(self.h(rel)) for rel in foreign}, foreign)
        self.assertEqual(self.install(un=True, apply=True)[0], 0)
        self.assertEqual({rel: self.get(self.h(rel)) for rel in foreign}, foreign)


class Uninstall(Machine):
    def test_uninstall_removes_exactly_what_install_created(self):
        self.use_source_tree()
        for h in ("claude", "omp", "codex", "opencode", "kimi", "openclaw", "hermes"):
            self.harness_dirs(h)
        self.stub("openclaw")
        self.stub("claude")
        self.stub("codex")
        self.put(self.h(".zshrc"), "export A=1\n")
        self.put(self.h(".config/opencode/opencode.json"), '{\n  "theme": "x"\n}\n')
        self.put(self.h(".codex/config.toml"), "# mine\n")
        before = snap(self.home)
        self.assertEqual(self.apply()[0], 0)
        self.assertNotEqual(snap(self.home), before)
        code, out = self.install(un=True, apply=True)
        self.assertEqual(code, 0, out)
        left = {k: v for k, v in snap(self.home).items() if not k.endswith(".okf-cli.bak")}
        # the CLI stubs leave a rewritten (empty-server) JSON behind, like the real CLIs
        for name in (".claude.json", ".openclaw/openclaw.json"):
            left.pop(name, None)
            before.pop(name, None)
        self.assertEqual(left, before)
        self.assertIn("remove", out)

    def test_uninstall_is_a_dry_run_without_apply(self):
        self.harness_dirs("omp")
        self.apply(only="omp")
        before = snap(self.tmp)
        code, out = self.install(un=True)
        self.assertEqual((code, snap(self.tmp)), (0, before))
        self.assertRegex(out, r"remove\s+omp")
        self.assertIn("PLAN only", out)

    def test_uninstall_when_nothing_is_installed_says_so(self):
        code, out = self.install(un=True, apply=True)
        self.assertEqual(code, 0)
        self.assertIn("nothing to remove: already up to date", out)

    def test_a_subset_uninstall_keeps_the_shared_skill_other_agents_read(self):
        self.harness_dirs("codex", "omp")
        self.apply()
        code, out = self.install(only="codex", un=True, apply=True)
        self.assertEqual(code, 0)
        self.assertTrue(os.path.isdir(self.h(".agents/skills/okf")))
        self.assertIn("kept: other agents still read", out)
        self.install(un=True, apply=True)
        self.assertFalse(os.path.exists(self.h(".agents/skills/okf")))

    def test_uninstall_through_the_cli_route(self):
        self.harness_dirs("claude", "codex")
        self.stub("claude")
        self.stub("codex")
        self.apply()
        self.install(un=True, apply=True)
        self.assertEqual([c[:3] for c in self.calls()[2:]], [["claude", "mcp", "remove"], ["codex", "mcp", "remove"]])
        self.assertEqual(self.calls()[2], ["claude", "mcp", "remove", "okf", "--scope", "user"])
        self.assertNotIn("okf", json.loads(self.get(self.h(".claude.json")))["mcpServers"])
        self.assertNotIn("okf", tomllib.loads(self.get(self.h(".codex/config.toml"))).get("mcp_servers", {}))

    def test_unmanaged_codex_table_without_the_cli_is_reported_not_edited(self):
        text = '[mcp_servers.okf]\ncommand = "uv"\nargs = ["run", "--with", "mcp<2", "%s"]\n' % self.script
        self.put(self.h(".codex/config.toml"), text)
        code, out = self.install(only="codex", un=True, apply=True)
        self.assertEqual(code, 0)
        self.assertIn("codex mcp remove okf", out)
        self.assertEqual(self.get(self.h(".codex/config.toml")), text)

    def test_uninstall_leaves_no_empty_directories_it_created(self):
        self.use_source_tree()
        self.harness_dirs("claude", "hermes", "codex")
        self.apply(only="claude,hermes,codex")
        self.install(un=True, apply=True)
        for rel in (".agents", ".claude/skills", ".hermes/skills", ".local"):
            self.assertFalse(os.path.exists(self.h(rel)), rel)
        self.assertTrue(os.path.isdir(self.h(".claude")))  # a harness dir is never pruned

    def test_hermes_rewriting_config_yaml_drops_our_markers_but_uninstall_still_finds_the_entry(self):
        # what `hermes config set` writes back: the entry survives, comments and markers do not
        self.put(self.h(".hermes/config.yaml"),
                 "model:\n  default: x\nmcp_servers:\n  time:\n    command: uvx\n  okf:\n    command: uv\n"
                 "    args:\n      - run\n      - --with\n      - mcp<2\n      - %s\ndisplay:\n  compact: true\n"
                 % self.script)
        code, out = self.install(only="hermes", un=True, apply=True)
        self.assertEqual(code, 0, out)
        self.assertEqual(self.get(self.h(".hermes/config.yaml")),
                         "model:\n  default: x\nmcp_servers:\n  time:\n    command: uvx\ndisplay:\n  compact: true\n")

    def test_a_foreign_okf_entry_in_config_yaml_survives_uninstall(self):
        text = "mcp_servers:\n  okf:\n    command: other\n"
        self.put(self.h(".hermes/config.yaml"), text)
        self.install(only="hermes", un=True, apply=True)
        self.assertEqual(self.get(self.h(".hermes/config.yaml")), text)


class EnvOverrides(Machine):
    def test_every_override_relocates_its_harness(self):
        dirs = {k: self.mk("elsewhere", k) for k in
                ("hermes", "kimi", "openclaw", "codex", "omp", "xdg_config", "zdot", "claude")}
        env = dict(self.env, HERMES_HOME=dirs["hermes"], KIMI_CODE_HOME=dirs["kimi"],
                   OPENCLAW_STATE_DIR=dirs["openclaw"], CODEX_HOME=dirs["codex"], PI_CODING_AGENT_DIR=dirs["omp"],
                   XDG_CONFIG_HOME=dirs["xdg_config"], ZDOTDIR=dirs["zdot"],
                   CLAUDE_CONFIG_DIR=dirs["claude"])
        self.use_source_tree()
        self.stub("openclaw")
        code, out = self.apply(only="claude,omp,codex,opencode,kimi,openclaw,hermes,zsh", env=env)
        self.assertEqual(code, 0, out)
        for rel in ("hermes/skills/okf/SKILL.md", "hermes/config.yaml", "kimi/mcp.json", "openclaw/skills/okf/SKILL.md",
                    "codex/config.toml", "omp/mcp.json", "xdg_config/opencode/opencode.json",
                    "claude/skills/okf/SKILL.md", "claude/.claude.json", "zdot/.zshrc"):
            self.assertTrue(os.path.lexists(os.path.join(self.tmp, "elsewhere", rel)), rel)
        # only the shared skill, the PATH wrapper and the zsh completion stay under HOME
        left = sorted(snap(self.home))
        self.assertTrue(all(p.startswith((".agents", ".local", ".zsh")) for p in left), left)

    def test_a_custom_openclaw_state_dir_still_lets_a_full_uninstall_remove_the_shared_skill(self):
        env = dict(self.env, OPENCLAW_STATE_DIR=self.mk("elsewhere", "claw"))
        self.harness_dirs("codex")
        self.stub("openclaw")
        self.apply(env=env)
        self.assertTrue(os.path.isdir(self.h(".agents/skills/okf")))
        self.assertEqual(self.install(un=True, apply=True, env=env)[0], 0)
        self.assertFalse(os.path.exists(self.h(".agents/skills/okf")))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "elsewhere", "claw", "skills", "okf")))

    def test_pi_config_dir_renames_the_omp_directory(self):
        env = dict(self.env, PI_CONFIG_DIR=".pi")
        self.apply(only="omp", env=env)
        self.assertTrue(os.path.isfile(self.h(".pi/agent/mcp.json")))
        self.assertFalse(os.path.exists(self.h(".omp")))

    def test_opencode_config_names_the_file_to_edit(self):
        mine = self.put(os.path.join(self.tmp, "elsewhere", "my-opencode.json"), '{"theme": "x"}\n')
        self.apply(only="opencode", env=dict(self.env, OPENCODE_CONFIG=mine))
        doc = json.loads(self.get(mine))
        self.assertEqual((doc["theme"], doc["mcp"]["okf"]["command"][0]), ("x", "uv"))
        self.assertFalse(os.path.exists(self.h(".config/opencode")))

    def test_openclaw_default_state_relies_on_the_shared_skill(self):
        self.stub("openclaw")
        self.apply(only="openclaw")
        self.assertFalse(os.path.exists(self.h(".openclaw/skills")))
        self.assertTrue(os.path.isfile(self.h(".agents/skills/okf/SKILL.md")))


class Detection(Machine):
    def test_only_detected_harnesses_are_installed_and_skips_say_why(self):
        self.harness_dirs("codex")
        self.stub("claude")
        code, out = self.apply()
        self.assertEqual(code, 0, out)
        self.assertTrue(os.path.exists(self.h(".claude.json")), "detected by its binary alone")
        self.assertTrue(os.path.isfile(self.h(".codex/config.toml")))
        for absent in (".hermes", ".kimi-code", ".openclaw", ".config/opencode", ".omp"):
            self.assertFalse(os.path.exists(self.h(absent)), absent)
        self.assertIn("not detected (no `hermes` on PATH, no ~/.hermes)", out)

    def test_only_overrides_detection(self):
        code, out = self.apply(only="hermes")
        self.assertEqual(code, 0, out)
        self.assertTrue(os.path.isfile(self.h(".hermes/config.yaml")))
        self.assertFalse(os.path.exists(self.h(".claude")), "not named, not touched")

    def test_unknown_only_name_is_a_usage_error(self):
        with self.assertRaises(okf_errors.OkfError) as cm:
            self.install(only="claude,nope")
        self.assertEqual((cm.exception.kind, cm.exception.code), ("invalid_input", 2))
        self.assertIn("nope", cm.exception.message)
        self.assertIn("hermes", cm.exception.message)

    def test_shells_are_detected_by_rc_file_config_dir_or_login_shell(self):
        self.put(self.h(".bashrc"), "")
        self.mk("home", ".config", "fish")
        code, out = self.install(env=dict(self.env, SHELL="/bin/dash"))
        self.assertRegex(out, r"skip\s+zsh\s+not detected")
        self.assertNotRegex(out, r"skip\s+bash\s+not detected")
        self.assertNotRegex(out, r"skip\s+fish\s+not detected")
        self.assertNotRegex(self.install()[1], r"skip\s+zsh\s+not detected", "SHELL=zsh makes zsh the login shell")

    def test_login_shell_falls_back_to_the_passwd_entry_when_SHELL_is_unset(self):
        env = {k: v for k, v in self.env.items() if k != "SHELL"}  # zsh does not set SHELL itself
        with mock.patch.object(inst, "passwd_shell", return_value="/bin/zsh"):
            self.assertNotRegex(self.install(env=env)[1], r"skip\s+zsh\s+not detected")
        with mock.patch.object(inst, "passwd_shell", return_value=""):
            self.assertRegex(self.install(env=env)[1], r"skip\s+zsh\s+not detected")

    def test_windows_is_refused(self):
        with self.assertRaises(okf_errors.OkfError) as cm:
            self.install(platform="win32")
        self.assertEqual(cm.exception.kind, "internal")
        self.assertIn("macOS and Linux", cm.exception.message)


class Uv(Machine):
    def test_missing_uv_blocks_mcp_only(self):
        os.remove(os.path.join(self.bin, "uv"))
        self.harness_dirs("omp", "claude")
        code, out = self.apply()
        self.assertEqual(code, 1)
        self.assertRegex(out, r"BLOCKED\s+omp\s+uv is not on PATH")
        self.assertFalse(os.path.exists(self.h(".omp/agent/mcp.json")))
        self.assertTrue(os.path.isfile(self.h(".agents/skills/okf/SKILL.md")), "skills proceed")
        self.assertTrue(os.path.isfile(self.h(".claude/skills/okf/SKILL.md")))

    def test_bash_and_fish_completion_are_argcomplete_shellcode(self):
        from argcomplete.shell_integration import shellcode
        self.use_source_tree()
        self.put(self.h(".bashrc"), "")
        self.mk("home", ".config", "fish")
        code, out = self.apply()
        self.assertEqual(code, 0, out)
        for sh, rel in (("bash", ".local/share/bash-completion/completions/okf"),
                        ("fish", ".config/fish/completions/okf.fish")):
            text = self.get(self.h(rel))
            self.assertTrue(text.startswith(inst.MANAGED + "\n"))
            self.assertEqual(text.split("\n", 1)[1], shellcode(["okf"], shell=sh))
        self.assertIn('if [ -r "$HOME/.local/share/bash-completion/completions/okf" ]', self.get(self.h(".bashrc")))


class ShellBlocks(Machine):
    def setUp(self):
        super().setUp()
        self.use_source_tree()

    def zsh(self, rc):
        self.put(self.h(".zshrc"), rc)
        self.assertEqual(self.apply(only="zsh")[0], 0)
        return self.get(self.h(".zshrc"))[len(rc):]

    def test_zsh_without_compinit_gets_fpath_and_compinit(self):
        block = self.zsh("export A=1\n")
        self.assertIn('fpath=("$HOME/.zsh/completions" $fpath)', block)
        self.assertIn("autoload -Uz compinit && compinit", block)
        self.assertIn('export PATH="$HOME/.local/bin:$PATH"', block)

    def test_zsh_with_compinit_elsewhere_registers_without_a_second_compinit(self):
        block = self.zsh("autoload -Uz compinit\ncompinit\n")
        self.assertNotIn("compinit", block.replace("autoload -Uz _okf", ""))
        self.assertIn("compdef _okf okf", block)
        self.assertIn('fpath=("$HOME/.zsh/completions" $fpath)', block)

    def test_zsh_that_already_does_everything_gets_only_what_is_missing(self):
        block = self.zsh('fpath=(~/.zsh/completions $fpath)\nautoload -Uz compinit && compinit\n'
                         'export PATH="$HOME/.local/bin:$PATH"\n')
        self.assertEqual(block, "", "nothing missing, nothing added")

    def test_commented_out_lines_do_not_count_as_configured(self):
        block = self.zsh("# fpath=(~/.zsh/completions $fpath)\n# compinit\n# PATH=$HOME/.local/bin:$PATH\n")
        self.assertIn("fpath=", block)
        self.assertIn("compinit", block)
        self.assertIn(".local/bin", block)

    def test_path_is_left_alone_when_okf_cli_is_already_on_it(self):
        self.stub("okf")
        code, out = self.apply(only="zsh")
        self.assertIn("okf is already on PATH", out)
        self.assertFalse(os.path.exists(self.h(".local/bin/okf")))
        self.assertNotIn(".local/bin", self.get(self.h(".zshrc")))

    def test_wrapper_starts_the_checkout_through_uv_run_script_and_passes_arguments(self):
        self.apply(only="zsh")
        wrapper = self.h(".local/bin/okf")
        self.assertTrue(os.access(wrapper, os.X_OK))
        calls = uv_start_log(self)
        done = subprocess.run([wrapper, "a", "b c"], capture_output=True, text=True)
        self.assertEqual(done.stdout.strip(), "['a', 'b c']")
        self.assertEqual(calls(), ["run --script {} a b c".format(os.path.join(self.pkg, "cli", "okf-cli.py"))])

    def test_an_installed_wheel_gets_no_wrapper_but_a_hint(self):
        os.remove(os.path.join(self.pkg, "pyproject.toml"))
        code, out = self.apply(only="zsh")
        self.assertIn("pipx ensurepath", out)
        self.assertFalse(os.path.exists(self.h(".local/bin/okf")))
        glue = self.h(".zsh/completions/_okf")
        self.assertTrue(os.path.isfile(glue) and not os.path.islink(glue), "an installed package copies the glue")

    def test_bash_rc_file_follows_the_platform(self):
        self.put(self.h(".profile"), "")
        self.apply(only="bash", platform="darwin")
        self.assertIn(".local/bin", self.get(self.h(".profile")))
        self.assertFalse(os.path.exists(self.h(".bash_profile")), "an existing .profile is bash's login file")
        self.apply(only="bash", platform="linux")
        self.assertIn(".local/bin", self.get(self.h(".bashrc")))

    def test_uninstall_finds_the_block_wherever_another_platform_put_it(self):
        self.put(self.h(".bashrc"), "alias ll='ls -l'\n")
        self.apply(only="bash", platform="linux")
        self.assertIn(inst.BEGIN, self.get(self.h(".bashrc")))
        self.install(only="bash", un=True, apply=True, platform="darwin")
        self.assertEqual(self.get(self.h(".bashrc")), "alias ll='ls -l'\n")

    def test_a_moved_checkout_retargets_wrapper_and_skill_links(self):
        self.harness_dirs("claude")
        self.apply(only="claude,zsh")
        moved = self.make_pkg(os.path.join(self.tmp, "moved"))
        self.put(os.path.join(moved, "pyproject.toml"), "")
        code, out = self.apply(only="claude,zsh", pkg=moved)
        self.assertEqual(code, 0, out)
        self.assertIn(os.path.join(moved, "cli", "okf-cli.py"), self.get(self.h(".local/bin/okf")))
        self.assertEqual(os.path.realpath(self.h(".claude/skills/okf")),
                         os.path.realpath(os.path.join(moved, "skills", "okf")))

    def test_a_broken_install_without_its_skill_is_blocked_not_a_traceback(self):
        shutil.rmtree(os.path.join(self.pkg, "skills"))
        self.harness_dirs("claude")
        code, out = self.apply(only="claude")
        self.assertEqual(code, 1)
        self.assertRegex(out, r"BLOCKED\s+claude\s+source not found")

    def test_fish_path_file_is_ours_and_removed_again(self):
        self.mk("home", ".config", "fish")
        self.apply(only="fish")
        conf = self.h(".config/fish/conf.d/okf.fish")
        self.assertIn("set -gx PATH $HOME/.local/bin $PATH", self.get(conf))
        self.install(only="fish", un=True, apply=True)
        self.assertFalse(os.path.exists(conf))

    def test_block_helpers_roundtrip_odd_files(self):
        block = [inst.BEGIN, "x", inst.END]
        for text in ("", "a", "a\n", "a\n\n", "\n\n", "a\nb\n", "a\n\n\nb\n"):
            with self.subTest(text=text):
                lines = inst.lines_of(text)
                again = inst.join(inst.drop_block(inst.put_block(lines, block)))
                self.assertEqual(again, text if text.endswith("\n") or not text else text + "\n")

    @unittest.skipUnless(shutil.which("bash"), "no bash")
    def test_generated_bash_block_is_valid_and_adds_path_once(self):
        self.put(self.h(".bashrc"), "")
        self.apply(only="bash")
        probe = ". ~/.bashrc; . ~/.bashrc; echo \"$PATH\""
        done = subprocess.run(["bash", "--norc", "--noprofile", "-c", probe], capture_output=True, text=True,
                              env={"HOME": self.home, "PATH": "/usr/bin:/bin"})
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.strip().split(":").count(self.h(".local/bin")), 1)

    @unittest.skipUnless(shutil.which("zsh"), "no zsh")
    def test_generated_zsh_block_registers_the_completion_in_a_real_zsh(self):
        self.put(self.h(".zshrc"), "")
        self.apply(only="zsh")
        done = subprocess.run(["zsh", "-f", "-c", "source ~/.zshrc; print -r -- ${_comps[okf]}"],
                              capture_output=True, text=True, env={"HOME": self.home, "PATH": "/usr/bin:/bin"})
        self.assertEqual(done.stdout.strip(), "_okf", done.stderr)

    @unittest.skipUnless(shutil.which("fish"), "no fish")
    def test_generated_fish_path_file_is_valid_fish(self):
        self.mk("home", ".config", "fish")
        self.apply(only="fish")
        done = subprocess.run(["fish", "--no-config", "-c", "source ~/.config/fish/conf.d/okf.fish; echo $PATH"],
                              capture_output=True, text=True, env={"HOME": self.home, "PATH": "/usr/bin:/bin"})
        self.assertIn(self.h(".local/bin"), done.stdout, done.stderr)


class Packaging(unittest.TestCase):
    """pyproject.toml maps the repo into the wheel with the SAME relative layout:
    okf-cli.py, okf_install.py, okf_mcp.py and cli/embeddings find each other by
    relative path, so one mismatch there breaks every pipx and uv install."""

    def setUp(self):
        path = os.path.join(_HERE, os.pardir, "pyproject.toml")
        if not os.path.isfile(path):
            self.skipTest("no pyproject.toml next to this checkout")
        with open(path, "rb") as f:
            self.cfg = tomllib.load(f)
        self.wheel = self.cfg["tool"]["hatch"]["build"]["targets"]["wheel"]

    def test_every_mapped_file_lands_at_the_same_relative_path_under_the_package(self):
        force = self.wheel["force-include"]
        self.assertEqual(self.wheel["packages"], ["okf_cli"])
        for src, dst in force.items():
            self.assertEqual(dst, "okf_cli/" + src)
            self.assertTrue(os.path.exists(os.path.join(_HERE, os.pardir, src)), src + " is mapped but missing")

    def test_everything_the_code_looks_up_relative_to_itself_ships(self):
        shipped = set(self.wheel["force-include"])
        for needed in ("cli/okf-cli.py", "cli/okf_install.py", "cli/_okf", "cli/embeddings",
                       "mcp/okf_mcp.py", "skills/okf"):
            self.assertIn(needed, shipped)

    def test_the_console_script_runs_the_hyphenated_cli_and_extras_exist(self):
        module, func = self.cfg["project"]["scripts"]["okf"].split(":")
        spec = importlib.util.spec_from_file_location(module, os.path.join(_HERE, os.pardir, module, "__init__.py"))
        entry = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(entry)
        self.assertTrue(callable(getattr(entry, func)))
        self.assertEqual(sorted(self.cfg["project"]["optional-dependencies"]), ["mcp"])

    def test_a_tree_laid_out_as_the_wheel_runs_cli_install_and_finds_its_siblings(self):
        """pyproject's mapping applied by plain copies (hatch itself is covered by the
        packaging smoke): console entry, install, MCP script and embeddings lookups."""
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        site = os.path.join(tmp, "site-packages")
        repo = os.path.join(_HERE, os.pardir)
        skip = shutil.ignore_patterns("__pycache__")
        shutil.copytree(os.path.join(repo, "okf_cli"), os.path.join(site, "okf_cli"), ignore=skip)
        for src, dst in self.wheel["force-include"].items():
            if os.path.isdir(os.path.join(repo, src)):
                shutil.copytree(os.path.join(repo, src), os.path.join(site, dst), ignore=skip)
            else:
                os.makedirs(os.path.dirname(os.path.join(site, dst)), exist_ok=True)
                shutil.copy(os.path.join(repo, src), os.path.join(site, dst))
        cat = os.path.join(tmp, "cat")
        os.makedirs(os.path.join(cat, "b"))
        for name, text in ((".okf.toml", ""), ("b/a.md", "---\ntype: Concept\ntitle: A\n---\nbody\n")):
            with open(os.path.join(cat, name), "w") as f:
                f.write(text)
        bin_dir = os.path.join(tmp, "bin")
        os.makedirs(bin_dir)
        for name in ("uv", "claude"):  # plan mode never runs them; their presence selects the CLI route
            with open(os.path.join(bin_dir, name), "w") as f:
                f.write("#!/bin/sh\nexit 0\n")
            os.chmod(os.path.join(bin_dir, name), 0o755)
        env = {"PYTHONPATH": site, "HOME": os.path.join(tmp, "home"), "PATH": bin_dir, "SHELL": "/bin/zsh"}

        def entry(*argv):  # what the pip-generated console script does: sys.exit(main())
            # cwd outside the checkout: `-c` puts it first on sys.path, so a repo-root run would import the
            # checkout's okf_cli instead of the copy under site-packages
            return subprocess.run([sys.executable, "-c", "import sys, okf_cli; sys.exit(okf_cli.main())"] + list(argv),
                                  capture_output=True, text=True, env=env, timeout=60, cwd=tmp)
        self.assertEqual(entry("--help").returncode, 0)
        prime = entry("--root", cat, "prime")
        self.assertEqual(prime.returncode, 0, prime.stderr)
        self.assertIn("agent onboarding", prime.stdout)
        plan = entry("install", "--only", "claude")
        self.assertIn("installed package, skills are copied", plan.stdout)
        self.assertIn(os.path.join(os.path.realpath(site), "okf_cli", "mcp", "okf_mcp.py"), plan.stdout)
        self.assertEqual(entry("install", "--only", "nope").returncode, 2, "exit codes pass through the entry")
        with mock.patch.dict(os.environ):
            os.environ.pop("OKF_CLI", None)
            mcp = _load("okf_mcp_wheel", os.path.join(site, "okf_cli", "mcp", "okf_mcp.py"))
        self.assertTrue(os.path.isfile(mcp.OKF_CLI), mcp.OKF_CLI)
        self.assertTrue(os.path.isfile(os.path.join(site, "okf_cli", "cli", "embeddings", "build_tagvec.py")))


class BrewPath(unittest.TestCase):
    def test_a_cellar_path_becomes_the_opt_symlink_that_survives_an_upgrade(self):
        with tempfile.TemporaryDirectory() as prefix:
            prefix = os.path.realpath(prefix)
            os.makedirs(os.path.join(prefix, "Cellar", "okf-cli", "0.1.0", "libexec", "okf_cli"))
            os.makedirs(os.path.join(prefix, "opt"))
            deep = os.path.join(prefix, "Cellar", "okf-cli", "0.1.0", "libexec", "okf_cli")
            self.assertEqual(inst.brew_opt_path(deep), deep, "no opt symlink yet: unchanged")
            os.symlink(os.path.join(prefix, "Cellar", "okf-cli", "0.1.0"), os.path.join(prefix, "opt", "okf-cli"))
            self.assertEqual(inst.brew_opt_path(deep), os.path.join(prefix, "opt", "okf-cli", "libexec", "okf_cli"))
            os.makedirs(os.path.join(prefix, "Cellar", "other", "1", "x"))
            os.symlink(os.path.join(prefix, "Cellar", "okf-cli", "0.1.0"), os.path.join(prefix, "opt", "other"))
            self.assertEqual(inst.brew_opt_path(os.path.join(prefix, "Cellar", "other", "1", "x")),
                             os.path.join(prefix, "Cellar", "other", "1", "x"), "opt points elsewhere: unchanged")


class CommandLine(unittest.TestCase):
    """The real okf-cli.py, as a user runs it: no catalogue anywhere."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = os.path.join(self.tmp, "home")
        os.makedirs(self.home)
        self.bin = os.path.join(self.tmp, "bin")
        os.makedirs(self.bin)
        with open(os.path.join(self.bin, "uv"), "w") as f:
            f.write("#!/bin/sh\nexit 0\n")
        os.chmod(os.path.join(self.bin, "uv"), 0o755)
        self.env = {"HOME": self.home, "PATH": self.bin, "SHELL": "/bin/zsh"}

    def cli(self, *argv):
        return subprocess.run([sys.executable, os.path.join(_HERE, "okf-cli.py")] + list(argv), cwd=self.tmp,
                              capture_output=True, text=True, env=self.env, timeout=60)

    def test_install_is_registered_exempt_from_the_catalogue_and_dispatchable(self):
        self.assertIn("install", okf_install_cmd.CATALOGUE_FREE)
        self.assertLessEqual(okf_install_cmd.CATALOGUE_FREE, set(okf_parser.COMMAND_DISPATCH))
        okf_parser.build_parser()  # registration fills COMMAND_GROUPS
        self.assertEqual(okf_parser_support.COMMAND_GROUPS["install"], "maintenance")

    def test_plan_runs_with_no_catalogue_and_no_root(self):
        before = snap(self.tmp)
        done = self.cli("install")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("PLAN only", done.stdout)
        self.assertEqual(snap(self.tmp), before)
        self.assertEqual(self.cli("--root", "/nonexistent/anywhere", "install").returncode, 0)

    def test_apply_from_the_checkout_links_the_real_skill_and_uninstall_undoes_it(self):
        done = self.cli("install", "--apply", "--only", "claude,zsh")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        link = os.path.join(self.home, ".claude", "skills", "okf")
        self.assertEqual(os.path.realpath(link), os.path.realpath(os.path.join(_HERE, os.pardir, "skills", "okf")))
        self.assertTrue(os.path.isfile(os.path.join(link, "SKILL.md")))
        self.assertIn("already up to date", self.cli("install", "--apply", "--only", "claude,zsh").stdout)
        self.assertEqual(self.cli("install", "--uninstall", "--apply").returncode, 0)
        self.assertFalse(os.path.lexists(link))

    def test_usage_error_exits_2(self):
        self.assertEqual(self.cli("install", "--only", "nope").returncode, 2)

    def test_json_output_is_one_parseable_dict_and_keeps_the_exit_code(self):
        plan = self.cli("install", "--json", "--only", "claude")
        env = json.loads(plan.stdout)
        self.assertEqual((env["command"], env["ok"], env["error"], plan.returncode), ("install", True, None, 0))
        doc = env["data"]
        self.assertEqual((doc["apply"], doc["uninstall"], doc["source_tree"]), (False, False, True))
        self.assertEqual([(s["group"], s["subject"], s["status"], s["done"]) for s in doc["steps"]
                          if s["group"] == "skills"], [("skills", "claude", "create", False)])
        self.assertFalse(os.path.lexists(os.path.join(self.home, ".claude")), "a plan changes nothing")
        applied = json.loads(self.cli("install", "--json", "--apply", "--only", "claude").stdout)["data"]
        self.assertTrue(all(s["done"] for s in applied["steps"] if s["status"] in ("create", "update")))
        os.makedirs(os.path.join(self.home, ".agents", "skills", "okf"))  # not ours: a blocked step
        os.makedirs(os.path.join(self.home, ".codex"))
        blocked = self.cli("install", "--json", "--only", "codex")
        self.assertEqual(blocked.returncode, 1)
        env = json.loads(blocked.stdout)
        self.assertEqual((env["ok"], env["error"]["kind"], env["error"]["code"]), (False, "internal", 1))
        self.assertIn("blocked", [s["status"] for s in env["data"]["steps"]])

    def test_okf_cli_py_copied_out_of_its_clone_says_what_is_missing(self):
        alone = os.path.join(self.tmp, "alone")
        os.makedirs(alone)
        shutil.copy(os.path.join(_HERE, "okf-cli.py"), alone)
        shutil.copytree(os.path.join(_HERE, "okf"), os.path.join(alone, "okf"),
                        ignore=shutil.ignore_patterns("__pycache__"))  # the package travels with the entry
        done = subprocess.run([sys.executable, os.path.join(alone, "okf-cli.py"), "install"], capture_output=True,
                              text=True, env=self.env, timeout=60)
        self.assertEqual(done.returncode, 1)
        self.assertIn("okf_install.py next to okf-cli.py", done.stderr)
        self.assertNotIn("Traceback", done.stderr)


if __name__ == "__main__":
    unittest.main()
