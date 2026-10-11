"""Shared real-git check for the `--check` previews (OKFT-d6an, R-21): the preview of a verb and the
`git diff` after its write run agree per file on the `---`/`+++` headers and every hunk (git's
`diff --git`, `index` and mode lines carry hashes, and the heading text git appends to a hunk
header is a git-only hint; all are excluded)."""
import json
import os
import re
import shutil
import subprocess

from tests.okf_testkit import _cli

HAS_GIT = shutil.which("git") is not None


class GitPreviewMixin:
    """For a TestCase whose `self.tmp` is a temp directory that is removed afterwards."""

    def _git(self, repo, *argv):
        env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null",
                   HOME=repo, GIT_TERMINAL_PROMPT="0")
        res = subprocess.run(["git", "-C", repo, "-c", "init.defaultBranch=main", "-c", "user.name=t",
                              "-c", "user.email=t@e", "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false"]
                             + list(argv), capture_output=True, env=env)
        self.assertEqual(res.returncode, 0, res.stderr)
        return res.stdout.decode()  # bytes first: text mode would fold the CRLF the diff must show

    def commit_files(self, repo, files):
        """Write `files` ({rel: bytes}) under `repo` and commit them as the base."""
        for rel, data in files.items():
            ap = os.path.join(repo, rel)
            os.makedirs(os.path.dirname(ap), exist_ok=True)
            with open(ap, "wb") as f:
                f.write(data)
        self._git(repo, "init", "-q")
        self._git(repo, "add", "-A")
        self._git(repo, "commit", "-qm", "base")

    def json_files(self, root, *argv, ok_codes=(0,)):
        """`data["files"]` of the real CLI run `okf-cli --root <root> <argv> --json`."""
        res = _cli(root, *argv, "--json")
        self.assertIn(res.returncode, ok_codes, res.stderr)
        return json.loads(res.stdout)["data"]["files"]

    def assert_preview_equals_git_diff(self, repo, check, write):
        """`check()` and `write()` return the `files` list of the verb's --check and write run. The
        check run leaves the tree clean; after the write run each preview diff equals the file's
        `git diff` (created files via intent-to-add) and the preview names exactly the changed files."""
        preview = check()
        self.assertTrue(preview)
        self.assertEqual(self._git(repo, "status", "--porcelain"), "")
        write()
        self._git(repo, "add", "-A", "-N")
        changed = sorted(self._git(repo, "diff", "--name-only").split())
        self.assertEqual(changed, [f["path"] for f in preview])
        for f in preview:
            out = self._git(repo, "diff", "--no-color", "--no-ext-diff", "--", f["path"])
            out = re.sub(r"(?m)^(@@ [^@]*@@).*$", r"\1", out)  # git adds the nearest line as a hunk heading
            self.assertEqual(f["diff"], out[out.index("--- "):], f["path"])
        return preview

    def assert_preview_equals_staged_diff(self, repo, check, write):
        """Like `assert_preview_equals_git_diff` for a write run that also moves files and stages
        them (`git mv`): after the write run `git add -A` and `git diff --cached -M` give one block
        per file, and each preview diff equals its block, `rename from`/`rename to` lines included
        (`similarity index` is git's own number and is excluded with the other git-only lines)."""
        preview = check()
        self.assertTrue(preview)
        self.assertEqual(self._git(repo, "status", "--porcelain"), "")
        write()
        self._git(repo, "add", "-A")
        out = self._git(repo, "diff", "--cached", "--no-color", "--no-ext-diff", "-M")
        blocks = {}
        for block in re.split(r"(?m)^(?=diff --git )", out):
            if not block:
                continue
            lines, in_header = [], True
            for ln in block.splitlines(keepends=True)[1:]:
                in_header = in_header and not ln.startswith(("--- ", "@@"))
                if not (in_header and re.match(r"(index |similarity index |(new|deleted) file mode|(old|new) mode)", ln)):
                    lines.append(ln)
            path = re.match(r"diff --git a/.* b/(.*)\n", block).group(1)
            blocks[path] = re.sub(r"(?m)^(@@ [^@]*@@).*$", r"\1", "".join(lines))
        self.assertEqual(sorted(blocks), [f["path"] for f in preview])
        for f in preview:
            self.assertEqual(f["diff"], blocks[f["path"]], f["path"])
        return preview
