// Package linkscan decides which spans of a markdown file count as links and finds them: the
// dead-zone mask, the files a rename or reference scan visits, where a markdown link points, the
// outbound links of a file and the reference matrix of a target (Python okf.linkscan).
//
// Offsets are BYTE offsets into the UTF-8 text, where Python counted code points. Every offset
// this package returns or accepts (WikilinkRegions, WikilinkScanTextAt, InlineCodeSpans, and the
// spans a regexp reports over a mask) addresses bytes, so text[start:end] cuts the original. A
// caller that prints a column or an offset converts it itself.
//
// The mask keeps the BYTE length of its input. Python blanked one NUL per masked character;
// here every byte of a masked character becomes one NUL (a three-byte character gives three), so
// an offset in the mask is the same offset in the original text. Only `\n` survives inside a
// masked span: a regexp over the mask that must not cross a line still cannot, and the line
// rules of the indented-code stage see the same lines. The blank is NUL and not a space on
// purpose: the indented-code stage treats a whitespace-only line as blank, and a fully masked
// line (a fence, a comment) must stay non-blank.
package linkscan

import (
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

// The spans Obsidian does not index as links and the list items the indented-code stage and
// `migrate` look for. Fences are found line-based, not by regexp (catalogue.FenceLineSpans): a
// regexp pairs backtick runs left to right with no notion of line start or fence length, so one
// prose ``` mention or a 4-backtick fence shifts every later pairing by one and leaves a real
// code block exposed to the rewriter.
var (
	// CommentRE matches an Obsidian `%%` comment or an HTML comment, each up to its first closer.
	CommentRE = pytext.Regexp(`%%[\s\S]*?%%|<!--[\s\S]*?-->`)
	// ListItemRE matches the start of a markdown list item: indentation, a `-`, `*` or `+` or a
	// number followed by `.` or `)`, then a space or a tab. It is anchored at the start of the
	// text, so ReplaceAllString(line, "") strips that prefix once, as Python's sub("", line,
	// count=1) does.
	ListItemRE = pytext.Regexp(`^[ \t]*(?:[-*+]|\d+[.)])[ \t]`)
)

// DeadZoneMask blanks every span Obsidian does not index, in stages: fenced code, sync spans,
// comments, inline code and, unless yaml is set, indented code. Each stage runs over the output of
// the previous one, so a construct inside an already masked span cannot open a new one: no
// nesting, no pairing drift. The result has the byte length of text, the same newlines and NUL
// for every other masked byte.
//
// yaml skips only the indented-code stage, because YAML indentation is structure: a block list
// under a blank line is not a code block. Inline code is masked in both regions: exempting it in
// frontmatter cost more than it bought, since a `---` thematic rule whose first line happens to
// read like `key: value` lands in the frontmatter region and its prose backticks would then be
// rewritable, while a genuine link property wrapped in backticks has zero occurrences
// catalogue-wide and would only be under-reported, never corrupted.
//
// The sync stage sits between the fence stage and the comment stage, and the order is
// load-bearing: CommentRE would blank the `<!-- okf:sync … -->` markers first and leave the
// payload between them live, so a [[wikilink]] in a materialised canon block would still be
// reported and, worse, rewritten by `rename`. Masked here, the owner's copy stays the only one
// reported and rewritten, which is where the link belongs.
func DeadZoneMask(text string, yaml bool) string {
	masked := blank(text, fencedSpans(text))
	masked = blank(masked, catalogue.SyncSpanRE.FindAllStringIndex(masked, -1))
	masked = blank(masked, CommentRE.FindAllStringIndex(masked, -1))
	masked = blank(masked, InlineCodeSpans(masked))
	if yaml {
		return masked
	}
	return blank(masked, indentedSpans(masked))
}

// blank is text with every byte of every [start, end) span replaced by NUL, newlines kept and the
// length preserved. Length preservation is the point: offsets in the masked copy address the same
// bytes in the original, so a scan can report and rewrite against the real text without a
// stash-and-restore round trip.
func blank(text string, spans [][]int) string {
	if len(spans) == 0 {
		return text
	}
	out := []byte(text)
	for _, s := range spans {
		for i := s[0]; i < s[1]; i++ {
			if out[i] != '\n' {
				out[i] = 0
			}
		}
	}
	return string(out)
}

// lineOffsets is the byte offset of every line start, plus the length of all lines at the end, so
// offs[len(lines)] is a valid span end.
func lineOffsets(lines []string) []int {
	offs := make([]int, 0, len(lines)+1)
	pos := 0
	for _, ln := range lines {
		offs = append(offs, pos)
		pos += len(ln)
	}
	return append(offs, pos)
}

// fencedSpans is catalogue.FenceLineSpans as byte-offset spans over the lines of text.
func fencedSpans(text string) [][]int {
	lines := pytext.SplitLines(text, true)
	offs := lineOffsets(lines)
	var spans [][]int
	for _, s := range catalogue.FenceLineSpans(lines) {
		spans = append(spans, []int{offs[s.First], offs[s.End]})
	}
	return spans
}

func isBlank(line string) bool { return pytext.Strip(line) == "" }

func isIndented(line string) bool {
	return strings.HasPrefix(line, "    ") || strings.HasPrefix(line, "\t")
}

// indentedSpans finds the 4-space and tab indented code blocks of text.
//
// Indentation alone does not make one: the same shape is markdown's list-continuation form,
// which Obsidian renders as prose and does index. A run of indented lines opens a code block
// only when it follows a blank line whose own predecessor is neither a list item nor itself
// indented.
func indentedSpans(text string) [][]int {
	lines := pytext.SplitLines(text, true)
	offs := lineOffsets(lines)
	var spans [][]int
	for i, n := 0, len(lines); i < n; {
		if isBlank(lines[i]) || !isIndented(lines[i]) || !opensCodeBlock(lines, i) {
			i++
			continue
		}
		start := i
		i++ // guaranteed progress
		for i < n && (isBlank(lines[i]) || isIndented(lines[i])) {
			i++
		}
		end := i
		for end > start && isBlank(lines[end-1]) {
			end--
		}
		spans = append(spans, []int{offs[start], offs[end]})
	}
	return spans
}

// opensCodeBlock reports whether the indented line i opens a code block: a blank line sits right
// before it (line 0 has none) and the last non-blank line before that blank is no list item and
// not indented.
func opensCodeBlock(lines []string, i int) bool {
	if i == 0 || !isBlank(lines[i-1]) {
		return false
	}
	for j := i - 2; j >= 0; j-- {
		if !isBlank(lines[j]) {
			return !ListItemRE.MatchString(lines[j]) && !isIndented(lines[j])
		}
	}
	return true
}
