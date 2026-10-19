package move

import (
	"bytes"
	"errors"
	"os"
	"os/exec"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

// runGit runs git with args and returns its stderr as Python's text-mode capture reads it (line
// endings translated, outer whitespace stripped). ok is false when git ran and refused; the error
// is the failure to run it at all (no git binary).
func runGit(args ...string) (stderr string, ok bool, err error) {
	var buf bytes.Buffer
	cmd := exec.Command("git", args...)
	cmd.Stderr = &buf
	runErr := cmd.Run()
	if runErr == nil {
		return "", true, nil
	}
	var exit *exec.ExitError
	if errors.As(runErr, &exit) {
		return pytext.Strip(lfNormalised(buf.String())), false, nil
	}
	return "", false, runErr
}

// gitMv is the history-preserving, staged move.
//
// It tries `git mv` at root first. When that fails because the source lies beyond a symlinked
// bundle boundary (its real path leaves root's own tree, into the foreign project repository the
// bundle links to) it resolves that real repository and retries `git mv` there; that only
// succeeds when the destination ALSO resolves into that same repository, i.e. an ordinary rename
// that stays inside the bundle. `archive`'s destination never does: `_archive/<bundle>/…` lives in
// the catalogue root, so the two repositories differ and a single `git mv` cannot span them. That
// case, and a plain untracked file where git declines for an unrelated reason, both fall back to a
// plain filesystem rename.
//
// It returns:
//
//	moved  true once a `git mv` staged the move, at root or at a resolved foreign repository.
//	repo   the real repository that received the write, whenever it differs from root; "" when it is
//	       the same, or when none could be resolved.
//	reason git's own stderr explaining why it declined, verbatim; "" when git succeeded or the git
//	       binary itself is unavailable.
//
// The error is a failed filesystem rename.
func gitMv(root, oldAbs, newAbs string) (moved bool, repo, reason string, err error) {
	stderr, ok, runErr := runGit("-C", root, "mv", "-f", oldAbs, newAbs)
	if runErr != nil {
		return false, "", "", os.Rename(oldAbs, newAbs)
	}
	if ok {
		return true, "", "", nil
	}

	reason = stderr
	realRoot := pyRealpath(root)
	realOld := pyRealpath(oldAbs)
	foreign := ""
	if !under(realOld, realRoot) {
		if top, why := catalogue.GitToplevel(pyDirname(realOld)); why == "" && pyRealpath(top) != realRoot {
			foreign = pyRealpath(top)
			realNewDir := pyRealpath(pyDirname(newAbs))
			if under(realNewDir, foreign) {
				realNew := catalogue.Join(realNewDir, pyBasename(newAbs))
				stderr2, ok2, runErr2 := runGit("-C", foreign, "mv", "-f", realOld, realNew)
				if runErr2 != nil {
					return false, "", "", runErr2
				}
				if ok2 {
					return true, foreign, "", nil
				}
				if stderr2 != "" {
					reason = stderr2
				}
			}
		}
	}
	return false, foreign, reason, os.Rename(oldAbs, newAbs)
}
