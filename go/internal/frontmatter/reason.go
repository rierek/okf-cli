package frontmatter

import (
	"strings"
	"unicode/utf8"

	"go.yaml.in/yaml/v3"

	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

// syntaxReason words a yaml.v3 syntax error as `<problem> (line L, column C)`, whitespace
// collapsed, 1-based in file coordinates.
//
// yaml.v3 reports a problem and a line only, and that line is the start of the failing construct
// (0-based for parser errors, 1-based for scanner errors). The column is therefore found by
// probing: the position is the end of the shortest prefix of the block that makes the parser fail
// with the same message, found line by line and then character by character. For a character
// the scanner rejects (a tab, a stray colon) that is the character itself; for an unfinished
// construct (an unclosed flow list) it is the point where the construct can no longer be
// completed. When no prefix fails alike the position is the end of the block.
func syntaxReason(block string, err error) string {
	msg := err.Error()
	line, column := failurePosition(block, msg)
	problem := strings.TrimPrefix(msg, "yaml: ")
	if rest, ok := strings.CutPrefix(problem, "line "); ok {
		if _, after, found := strings.Cut(rest, ": "); found {
			problem = after
		}
	}
	return pytext.Collapse(problem + position(line, column))
}

// failurePosition returns the 1-based (line, column) of the last character of the shortest prefix
// of block whose decoding fails with message msg.
func failurePosition(block, msg string) (line, column int) {
	fails := func(k int) bool {
		var n yaml.Node
		err := yaml.NewDecoder(strings.NewReader(block[:k])).Decode(&n)
		return err != nil && err.Error() == msg
	}
	lineStart, lineNo, prevStart := 0, 1, 0
	for lineStart < len(block) {
		lineEnd := len(block)
		if i := strings.IndexByte(block[lineStart:], '\n'); i >= 0 {
			lineEnd = lineStart + i + 1
		}
		if fails(lineEnd) {
			k := lineEnd
			for j := lineStart; j < lineEnd; {
				_, size := utf8.DecodeRuneInString(block[j:])
				j += size
				if j < lineEnd && fails(j) {
					k = j
					break
				}
			}
			return lineNo, utf8.RuneCountInString(block[lineStart:k])
		}
		prevStart, lineStart, lineNo = lineStart, lineEnd, lineNo+1
	}
	// no prefix fails alike: the end of the block
	return max(lineNo-1, 1), utf8.RuneCountInString(block[prevStart:])
}
