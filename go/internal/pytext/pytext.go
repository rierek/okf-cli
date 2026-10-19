// Package pytext holds the few string semantics of Python's str that the okf core reproduces:
// whitespace as str.isspace and str.split see it, str.splitlines, str.strip and str.casefold.
// Go's own unicode.IsSpace, strings.Fields and strings.ToLower differ from them for a few
// characters; every sorted listing and every scan that Python did with these methods uses this
// package so the byte output matches.
package pytext

import (
	"strings"
	"unicode"
	"unicode/utf8"

	"golang.org/x/text/cases"
	"golang.org/x/text/language"
)

// IsSpace is str.isspace for one character: Unicode White_Space plus U+001C..U+001F.
func IsSpace(r rune) bool {
	return unicode.IsSpace(r) || (r >= 0x1c && r <= 0x1f)
}

// Fields is str.split() without arguments: the runs of non-space characters, no empty items.
func Fields(s string) []string { return strings.FieldsFunc(s, IsSpace) }

// Strip is str.strip() without arguments.
func Strip(s string) string { return strings.TrimFunc(s, IsSpace) }

// Lstrip is str.lstrip() without arguments.
func Lstrip(s string) string { return strings.TrimLeftFunc(s, IsSpace) }

// Rstrip is str.rstrip() without arguments.
func Rstrip(s string) string { return strings.TrimRightFunc(s, IsSpace) }

// Collapse is " ".join(s.split()): every whitespace run becomes one space, the ends are trimmed.
func Collapse(s string) string { return strings.Join(Fields(s), " ") }

// Casefold is str.casefold (full Unicode case folding: "ß" becomes "ss").
func Casefold(s string) string { return cases.Fold().String(s) }

// Lower is str.lower(): full Unicode lower-casing (U+0130 becomes "i" and U+0307, a final sigma
// becomes ς), where strings.ToLower maps characters one by one.
func Lower(s string) string {
	for i := range len(s) {
		if s[i] >= utf8.RuneSelf {
			return cases.Lower(language.Und).String(s)
		}
	}
	return strings.ToLower(s)
}

// SplitLines is str.splitlines(keepends): line boundaries are \n, \r, \r\n, \v, \f, \x1c, \x1d,
// \x1e, \x85, U+2028 and U+2029. A trailing boundary does not start another empty line; the empty
// string has no lines.
func SplitLines(s string, keepEnds bool) []string {
	var lines []string
	start, i := 0, 0
	for i < len(s) {
		r, size := utf8.DecodeRuneInString(s[i:])
		if !isLineBreak(r) {
			i += size
			continue
		}
		end := i
		i += size
		if r == '\r' && i < len(s) && s[i] == '\n' {
			i++
		}
		if keepEnds {
			end = i
		}
		lines = append(lines, s[start:end])
		start = i
	}
	if start < len(s) {
		lines = append(lines, s[start:])
	}
	return lines
}

func isLineBreak(r rune) bool {
	switch r {
	case '\n', '\r', '\v', '\f', 0x1c, 0x1d, 0x1e, 0x85, 0x2028, 0x2029:
		return true
	}
	return false
}
