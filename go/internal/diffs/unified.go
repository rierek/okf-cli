// Package diffs renders the dry-run view of a write plan and writes the plan to disk (Python
// okf.diffs and catalogue.write_file_verbatim). The unified diff is a port of difflib.unified_diff
// with its SequenceMatcher, so the output is byte for byte what the Python tool printed.
package diffs

import (
	"slices"
	"strconv"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

// PlanEntry is one file of a write plan: the text it has now and the text the write run gives it.
// A nil Old is a file the run creates; a nil New is a file the run deletes.
type PlanEntry struct {
	Path     string
	Old, New *string
}

// FileDiff is one entry of the dry-run listing: the file, the path it moved from (nil unless it
// moved) and the unified diff text.
type FileDiff struct {
	Path    string  `json:"path"`
	OldPath *string `json:"old_path"`
	Diff    string  `json:"diff"`
}

// noNewline is what _lines appends to a last line that has no line break.
const noNewline = "\n\\ No newline at end of file\n"

// lines is Python _lines: the text split like str.splitlines(keepends=True), a last line without
// a final "\n" (a lone "\r" or form feed counts as missing) marked as git marks it.
func lines(text string) []string {
	ls := pytext.SplitLines(text, true)
	if n := len(ls); n > 0 && !strings.HasSuffix(ls[n-1], "\n") {
		ls[n-1] += noNewline
	}
	return ls
}

// formatRange is difflib._format_range_unified: the "ed" form of the line range [start, stop).
func formatRange(start, stop int) string {
	beginning, length := start+1, stop-start
	if length == 1 {
		return strconv.Itoa(beginning)
	}
	if length == 0 {
		beginning--
	}
	return strconv.Itoa(beginning) + "," + strconv.Itoa(length)
}

// unifiedDiff is difflib.unified_diff(a, b, fromfile, tofile) with three lines of context, no file
// dates and "\n" as line terminator, joined to one string: empty when a and b are equal.
func unifiedDiff(a, b []string, fromfile, tofile string) string {
	var sb strings.Builder
	for gi, group := range groupedOpcodes(newMatcher(a, b).opcodes(), 3) {
		if gi == 0 {
			sb.WriteString("--- " + fromfile + "\n+++ " + tofile + "\n")
		}
		first, last := group[0], group[len(group)-1]
		sb.WriteString("@@ -" + formatRange(first.i1, last.i2) + " +" + formatRange(first.j1, last.j2) + " @@\n")
		for _, c := range group {
			if c.tag == tagEqual {
				writePrefixed(&sb, ' ', a[c.i1:c.i2])
				continue
			}
			if c.tag == tagReplace || c.tag == tagDelete {
				writePrefixed(&sb, '-', a[c.i1:c.i2])
			}
			if c.tag == tagReplace || c.tag == tagInsert {
				writePrefixed(&sb, '+', b[c.j1:c.j2])
			}
		}
	}
	return sb.String()
}

func writePrefixed(sb *strings.Builder, prefix byte, ls []string) {
	for _, line := range ls {
		sb.WriteByte(prefix)
		sb.WriteString(line)
	}
}

// sameText is Python `old == new` for a text or None.
func sameText(x, y *string) bool {
	if x == nil || y == nil {
		return x == y
	}
	return *x == *y
}

// textOrEmpty is Python `text or ""` for a text or None.
func textOrEmpty(p *string) string {
	if p == nil {
		return ""
	}
	return *p
}

// UnifiedDiffs is Python unified_diffs: one entry per changed file of the plan, ordered by path,
// headed `a/<path>` and `b/<path>`; entries whose old and new text are equal are omitted. A nil
// Old is a file the write run creates, headed `/dev/null` and `b/<path>` as git prints it; a nil
// New is a file the run deletes, headed `a/<path>` and `/dev/null`. moves maps the path of a moved
// file to the path it came from: that entry's Old is the text at the old path, its diff starts
// with git's `rename from` / `rename to` lines and is kept even when the text is unchanged, its
// `a/` header names the old path and OldPath carries it. Other entries have a nil OldPath.
func UnifiedDiffs(plan []PlanEntry, moves map[string]string) []FileDiff {
	sorted := slices.Clone(plan)
	slices.SortStableFunc(sorted, func(x, y PlanEntry) int { return strings.Compare(x.Path, y.Path) })
	out := make([]FileDiff, 0, len(sorted))
	for _, e := range sorted {
		src, moved := moves[e.Path]
		same := sameText(e.Old, e.New)
		if same && !moved {
			continue
		}
		d := FileDiff{Path: e.Path}
		if moved {
			d.OldPath = &src
		}
		// Python tests the old path for truth, not for None: an empty one is no move in the head
		// and the header, but still the entry's old_path.
		if src != "" {
			d.Diff = "rename from " + src + "\nrename to " + e.Path + "\n"
		}
		if !same {
			from, to := "/dev/null", "/dev/null"
			if e.Old != nil {
				from = "a/" + e.Path
				if src != "" {
					from = "a/" + src
				}
			}
			if e.New != nil {
				to = "b/" + e.Path
			}
			d.Diff += unifiedDiff(lines(textOrEmpty(e.Old)), lines(textOrEmpty(e.New)), from, to)
		}
		out = append(out, d)
	}
	return out
}
