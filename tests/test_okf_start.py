"""How okf-cli is started (R-11): the executable entry file and the repo justfile recipes resolve the
PEP 723 header of cli/okf-cli.py through `uv run --script`, never through a bare `python3`.

Run: just test tests.test_okf_start -v
"""
import os
import shutil
import subprocess
import tempfile
import unittest

from tests.okf_testkit import uv_start_log

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
ENTRY = os.path.join(REPO, "cli", "okf-cli.py")


class EntryFileRunsDirectly(unittest.TestCase):
    def test_the_entry_file_run_directly_resolves_its_header_on_a_path_without_the_test_environment(self):
        uv = shutil.which("uv")
        assert uv, "uv is not on PATH"
        env = {k: v for k, v in os.environ.items() if k not in ("VIRTUAL_ENV", "PYTHONPATH")}
        # uv, then the system tools: whatever Python /usr/bin holds has no ruamel.yaml.
        env["PATH"] = os.pathsep.join([os.path.dirname(uv), "/usr/bin", "/bin"])
        done = subprocess.run([ENTRY, "--help"], capture_output=True, text=True, env=env)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue(done.stdout.startswith("usage: okf-cli"), done.stdout[:200])


class JustRecipesStartThroughUv(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        # Asked before the shim is in place, so the shim logs only how the recipes start okf-cli.
        self.uv_env = {"UV_CACHE_DIR": _uv_dir("cache"), "UV_PYTHON_INSTALL_DIR": _uv_dir("python")}
        self.calls = uv_start_log(self)

    def _just(self, *args):
        # HOME is the empty tmp dir, so `setup` (a plan without --apply) and `check` never see a vault.
        env = dict(os.environ, HOME=self.tmp, **self.uv_env)
        subprocess.run(["just", "--justfile", os.path.join(REPO, "justfile"), *args],
                       capture_output=True, text=True, env=env)

    def test_check_and_prime_start_the_cli_with_uv_run_script(self):
        self._just("check", self.tmp)
        self._just("prime", self.tmp)
        self.assertEqual(self.calls(), ["run --script cli/okf-cli.py --root {} check".format(self.tmp),
                                        "run --script cli/okf-cli.py --root {} prime".format(self.tmp)])

    def test_setup_starts_the_installer_with_uv_run_script(self):
        self._just("setup")
        self.assertEqual(self.calls(), ["run --script cli/okf-cli.py install"])


def _uv_dir(kind):
    """The uv cache or managed-Python directory of the real home, kept when a test swaps HOME."""
    return subprocess.run(["uv", kind, "dir"], capture_output=True, text=True, check=True).stdout.strip()


if __name__ == "__main__":
    unittest.main()
