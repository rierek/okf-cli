"""The last body-changing commit of a concept (OKF D18), read from git history.

"Body" is what `read_frontmatter` returns after the frontmatter, for every historic version of the
file alike, so a commit that only touches frontmatter never counts. One `git log` per scope (the
catalogue root, or a mounted bundle's own folder) lists every commit with its raw changes and
blob IDs, renames detected; one `git cat-file --batch` per repository serves the versions the
walk of a concept asks for, newest first and no older than it needs. The number of git processes
therefore grows with the scopes, not with the concepts or the commits."""

import os
import subprocess
from collections import namedtuple
from collections.abc import Mapping

from okf.catalogue import _git_toplevel, read_frontmatter
from okf.spec import parse_okf_datetime

Commit = namedtuple("Commit", "time email")  # commit instant (aware), author email
_Event = namedtuple("_Event", "idx status old_path old_sha new_sha")
_ZEROS = "0" * 40
_NO_GIT = "git binary not found"
_NO_REPO = "not inside a git repository"
# -c keeps a user's log config out of the machine-read stream; --format opens each commit with \x01
_LOG = ["-c", "log.showSignature=false", "-c", "i18n.logOutputEncoding=UTF-8", "log", "-M", "-z", "--raw",
        "--no-abbrev", "--no-color", "--format=%x01%cI%x1f%ae"]


class _Blobs:
    """`git cat-file --batch` of one repository: one process, versions read on request."""

    def __init__(self, top):
        process = subprocess.Popen(["git", "-C", top, "cat-file", "--batch"], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        assert process.stdin is not None and process.stdout is not None  # both are PIPE
        self._process, self._in, self._out = process, process.stdin, process.stdout

    def text(self, sha):
        """The blob as text, as `read_file` decodes a file; None when the repository lacks it."""
        self._in.write(sha.encode() + b"\n")
        self._in.flush()
        header = self._out.readline().split()
        if len(header) != 3:
            return None
        data = self._out.read(int(header[2]))
        self._out.readline()  # the LF after the content
        return data.decode("utf-8", errors="replace")

    def close(self):
        self._in.close()
        self._out.close()
        self._process.wait()


class _Log:
    """The commits and per-path changes of one scope."""

    def __init__(self, top, raw):
        self.top = top
        self.commits, self.by_path = [], {}  # by_path: path -> its events, newest commit first
        for chunk in raw.split(b"\x01")[1:]:
            head, _, rest = chunk.partition(b"\0")
            when, _, email = head.decode("utf-8", errors="replace").partition("\x1f")
            self.commits.append(Commit(parse_okf_datetime(when), email))
            fields = rest.decode("utf-8", errors="replace").split("\0")
            i = 0
            while i < len(fields):
                if not fields[i].lstrip("\n").startswith(":"):
                    i += 1
                    continue
                _, _, old_sha, new_sha, status = fields[i].lstrip("\n")[1:].split(" ")
                width = 2 if status[0] in "RC" else 1
                paths = fields[i + 1:i + 1 + width]
                event = _Event(len(self.commits) - 1, status, paths[0], old_sha, new_sha)
                self.by_path.setdefault(paths[-1], []).append(event)
                i += 1 + width
        self._blobs, self._docs = None, {}

    def follow(self, path):
        """The events of `path`, newest first, through its renames."""
        floor = -1
        while True:
            for event in self.by_path.get(path, ()):
                if event.idx > floor:
                    yield event
                    if event.status[0] == "R":
                        path, floor = event.old_path, event.idx
                        break
            else:
                return

    def _doc(self, sha):
        if sha not in self._docs:
            if self._blobs is None:
                self._blobs = _Blobs(self.top)
            text = None if sha == _ZEROS else self._blobs.text(sha)
            self._docs[sha] = read_frontmatter(text or "")
        return self._docs[sha]

    def changes(self, event):
        """(body changed, generated.at changed) by this event; `generated.at` compares as an instant."""
        if event.status[0] == "D":
            return False, False
        new = self._doc(event.new_sha)
        if event.status[0] == "A":
            return True, _generated_at(new) is not None
        old = self._doc(event.old_sha)
        return old.body != new.body, _generated_at(old) != _generated_at(new)

    def close(self):
        if self._blobs is not None:
            self._blobs.close()


def _generated_at(doc):
    generated = doc.data.get("generated") if doc.data is not None else None
    return parse_okf_datetime(generated.get("at")) if isinstance(generated, Mapping) else None


class History:
    """Per-run lookups of body-changing commits under the catalogue root `root`."""

    def __init__(self, root):
        self._root = os.path.realpath(root)
        self._logs = {}  # scope directory -> _Log, or None when it has no usable git
        self._notes = []

    def last_body_commit(self, ap, keep_generated=False):
        """The Commit (instant, author email) of the last commit that changed the body of `ap`; None
        for an untracked file, a file outside any repository or a file without such a commit.
        `keep_generated` skips the commits that changed `generated.at` along with the body, which
        are regenerations: the last commit that edited the body of a concept whose `generated.at`
        it left alone."""
        real = os.path.realpath(ap)
        scope = self._root if real.startswith(self._root + os.sep) else os.path.dirname(real)
        log = self._log(scope)
        if log is None:
            return None
        for event in log.follow(os.path.relpath(real, log.top).replace(os.sep, "/")):
            body, generated = log.changes(event)
            if body and not (keep_generated and generated):
                return log.commits[event.idx]
        return None

    def _log(self, scope):
        if scope not in self._logs:
            self._logs[scope] = self._open(scope)
        return self._logs[scope]

    def _open(self, scope):
        top, reason = _git_toplevel(scope)
        if top is None:
            where = "the catalogue root" if scope == self._root else os.path.relpath(scope, self._root)
            self._note(_NO_GIT if reason == "no-git" else "{} is {}".format(where, _NO_REPO))
            return None
        top = os.path.realpath(top)
        prefix = os.path.relpath(scope, top).replace(os.sep, "/")
        res = subprocess.run(["git", "-C", top, *_LOG, "--", prefix], capture_output=True)
        return _Log(top, res.stdout if res.returncode == 0 else b"")  # no commits yet: no history

    def _note(self, message):
        if message not in self._notes:
            self._notes.append(message)

    def notes(self):
        """What kept a lookup from running, once each, for the caller to announce."""
        return list(self._notes)

    def close(self):
        for log in self._logs.values():
            if log is not None:
                log.close()
