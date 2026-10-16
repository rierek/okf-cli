package linkscan

import "strings"

// InlineCodeSpans is Python INLINE_CODE_RE.finditer: the [start, end) byte offsets of every inline
// code span of s, in the shape of regexp.FindAllStringIndex(s, -1). The Python pattern is
//
//	(`+)(?:(?!\1).)+?\1
//
// a run of backticks, one or more characters that are no newline and do not start a run of the
// same length, then a run of the same length. RE2 has neither the backreference nor the
// lookahead, so the match is written out with the same preferences: from a backtick the whole run
// that starts there opens first and, when that finds no closer, one backtick fewer at a time; the
// closer is the first run of the opener's length after at least one character, and a longer run
// closes with its first backticks. No span crosses a newline.
func InlineCodeSpans(s string) [][]int {
	var spans [][]int
	for p := 0; p < len(s); {
		if s[p] == '`' {
			if end := inlineCodeEnd(s, p); end >= 0 {
				spans = append(spans, []int{p, end})
				p = end
				continue
			}
		}
		p++
	}
	return spans
}

// inlineCodeEnd is the end of the span that opens at the backtick p, or -1.
func inlineCodeEnd(s string, p int) int {
	run := 0
	for p+run < len(s) && s[p+run] == '`' {
		run++
	}
	for n := run; n > 0; n-- {
		if end := inlineCodeClose(s, p+n, s[p:p+n]); end >= 0 {
			return end
		}
	}
	return -1
}

// inlineCodeClose is the end of the closing fence for an opener that ends at from, or -1. The
// first content character may not be a newline or the start of a fence; after it, the first
// fence ends the span and a newline or the end of s fails it.
func inlineCodeClose(s string, from int, fence string) int {
	if from >= len(s) || s[from] == '\n' || strings.HasPrefix(s[from:], fence) {
		return -1
	}
	for i := from + 1; i < len(s); i++ {
		if strings.HasPrefix(s[i:], fence) {
			return i + len(fence)
		}
		if s[i] == '\n' {
			return -1
		}
	}
	return -1
}
