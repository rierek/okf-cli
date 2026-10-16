// Package history is the last body-changing commit of a concept (Python okf.history, OKF D18), read
// from git history.
//
// "Body" is what frontmatter.Read returns after the frontmatter, for every historic version of the
// file alike, so a commit that only touches frontmatter never counts. One `git log` per scope (the
// catalogue root, or the folder of a file that lives outside it) lists every commit with its raw
// changes and blob ids, renames detected; one `git cat-file --batch` per such log serves the
// versions the walk of a concept asks for, newest first and no older than it needs. The number of
// git processes therefore grows with the scopes, not with the concepts or the commits.
package history

import (
	"errors"
	"os/exec"
	"path/filepath"
	"slices"
	"strings"
	"time"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
)

// Commit is the committer instant (with the offset git recorded) and the author email of a commit,
// Python Commit(time, email). Compare Time as an instant; write it with spec.Isoformat, which gives
// the `+00:00` Python writes where time.RFC3339 would write `Z`.
type Commit struct {
	Time  time.Time
	Email string
}

const (
	noGit  = "git binary not found"
	noRepo = "not inside a git repository"
)

// logArgs is the `git log` of one scope, after `-C <top>` and before `-- <path>`. The -c options
// keep a user's log configuration out of the machine-read stream; --format opens each commit with
// \x01.
var logArgs = []string{"-c", "log.showSignature=false", "-c", "i18n.logOutputEncoding=UTF-8", "log", "-M", "-z", "--raw",
	"--no-abbrev", "--no-color", "--format=%x01%cI%x1f%ae"}

// History is the per-run lookup of body-changing commits under a catalogue root.
type History struct {
	root  string
	logs  map[string]*scopeLog // scope directory -> its log, nil when it has no usable git
	notes []string
}

// New is Python History(root): a lookup for the catalogue at root. Nothing is read until
// LastBodyCommit asks.
func New(root string) *History {
	return &History{root: realpath(root), logs: map[string]*scopeLog{}}
}

// LastBodyCommit is Python last_body_commit: the last commit that changed the body of the file at
// the absolute path ap, nil for an untracked file, a file outside any repository or a file without
// such a commit. keepGenerated skips the commits that changed `generated.at` along with the body,
// which are regenerations: the last commit that edited the body of a concept whose
// `generated.at` it left alone. A problem with git itself (a process that cannot start, output
// that is no log) is an error.
func (h *History) LastBodyCommit(ap string, keepGenerated bool) (*Commit, error) {
	file := realpath(ap)
	scope := h.root
	if !strings.HasPrefix(file, h.root+"/") {
		scope = filepath.Dir(file)
	}
	l, err := h.log(scope)
	if err != nil || l == nil {
		return nil, err
	}
	for ev := range l.follow(relpath(l.top, file)) {
		body, generated, err := l.changes(ev)
		if err != nil {
			return nil, err
		}
		if body && !(keepGenerated && generated) {
			commit := l.commits[ev.idx]
			return &commit, nil
		}
	}
	return nil, nil
}

func (h *History) log(scope string) (*scopeLog, error) {
	if l, ok := h.logs[scope]; ok {
		return l, nil
	}
	l, err := h.open(scope)
	if err != nil {
		return nil, err
	}
	h.logs[scope] = l
	return l, nil
}

func (h *History) open(scope string) (*scopeLog, error) {
	top, reason := catalogue.GitToplevel(scope)
	if reason != "" {
		if reason == "no-git" {
			h.note(noGit)
		} else {
			where := "the catalogue root"
			if scope != h.root {
				where = relpath(h.root, scope)
			}
			h.note(where + " is " + noRepo)
		}
		return nil, nil
	}
	top = realpath(top)
	args := append(append([]string{"-C", top}, logArgs...), "--", relpath(top, scope))
	out, err := exec.Command("git", args...).Output()
	var exit *exec.ExitError
	if errors.As(err, &exit) {
		out = nil // no commits yet: no history
	} else if err != nil {
		return nil, err
	}
	return parseLog(top, out)
}

func (h *History) note(message string) {
	if !slices.Contains(h.notes, message) {
		h.notes = append(h.notes, message)
	}
}

// Notes is what kept a lookup from running, once each, for the caller to announce: the git binary
// is missing, or a scope is not inside a git repository.
func (h *History) Notes() []string { return slices.Clone(h.notes) }

// Close ends the git processes the lookups started.
func (h *History) Close() error {
	var err error
	for _, l := range h.logs {
		if l != nil {
			err = errors.Join(err, l.close())
		}
	}
	return err
}

// relpath is Python os.path.relpath of two absolute paths.
func relpath(base, target string) string {
	rel, err := filepath.Rel(base, target)
	if err != nil {
		return target
	}
	return rel
}
