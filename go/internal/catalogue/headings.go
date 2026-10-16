package catalogue

import (
	"os/exec"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

var (
	fenceLineRE = pytext.Regexp("^ {0,3}(`{3,}|~{3,})[ \\t]*(.*)$")
	headingRE   = pytext.Regexp(`^(#{1,6})\s+(.+?)\s*#*$`)
)

// Span is a range of line indexes, End exclusive.
type Span struct{ First, End int }

// FenceLineSpans is Python fence_line_spans: CommonMark fenced blocks as line-index spans. An
// opener is up to three spaces of indent then three or more backticks or tildes; it closes on a
// line of at least as many of the same character carrying nothing else. An unclosed fence runs to
// the last line, which is how Obsidian renders it too. Lines may carry a trailing newline.
func FenceLineSpans(lines []string) []Span {
	var spans []Span
	n := len(lines)
	for i := 0; i < n; {
		m := fenceLineRE.FindStringSubmatch(strings.TrimRight(lines[i], "\n"))
		if m == nil {
			i++
			continue
		}
		marker, rest := m[1], m[2]
		if marker[0] == '`' && strings.Contains(rest, "`") {
			i++ // the info string may not contain a backtick
			continue
		}
		start, char, width := i, marker[0], len(marker)
		i++
		for i < n {
			cm := fenceLineRE.FindStringSubmatch(strings.TrimRight(lines[i], "\n"))
			if cm != nil && cm[1][0] == char && len(cm[1]) >= width && pytext.Strip(cm[2]) == "" {
				i++
				break
			}
			i++
		}
		spans = append(spans, Span{start, i})
	}
	return spans
}

// Heading is one ATX heading: its level (1-6), its text and the 0-based index of its line in
// body.splitlines().
type Heading struct {
	Level int
	Text  string
	Line  int
}

// IterHeadings is Python iter_headings: the ATX headings of body outside fenced code, in order.
func IterHeadings(body string) []Heading {
	lines := pytext.SplitLines(body, false)
	fenced := map[int]bool{}
	for _, s := range FenceLineSpans(lines) {
		for i := s.First; i < s.End; i++ {
			fenced[i] = true
		}
	}
	var out []Heading
	for i, line := range lines {
		if fenced[i] {
			continue
		}
		if m := headingRE.FindStringSubmatch(line); m != nil {
			out = append(out, Heading{len(m[1]), pytext.Strip(m[2]), i})
		}
	}
	return out
}

// GitToplevel is Python _git_toplevel: the repository root of a path, or the reason there is none
// ("no-git" when the git binary is missing, "no-repo" when the path is outside a repository).
// `git rev-parse` answers correctly for worktrees, submodules, `.git` files and an inherited
// GIT_DIR, and `git -C <symlink>` resolves a symlinked bundle to the foreign repository that holds
// its history.
func GitToplevel(path string) (top, reason string) {
	git, err := exec.LookPath("git")
	if err != nil {
		return "", "no-git"
	}
	out, err := exec.Command(git, "-C", path, "rev-parse", "--show-toplevel").Output()
	if err != nil {
		if _, isExit := err.(*exec.ExitError); isExit {
			return "", "no-repo"
		}
		return "", "no-git"
	}
	return pytext.Strip(string(out)), ""
}
