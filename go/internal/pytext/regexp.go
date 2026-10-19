package pytext

import (
	"regexp"
	"strings"
)

// Python's \s, \d and \w match Unicode characters for a str pattern; Go's match ASCII only. Regexp
// compiles a Python pattern after rewriting those three classes (outside and inside brackets), so
// a scan of Unicode text finds what the Python scan found. `[\s\S]` becomes `(?s:.)`.
//
// Two differences stay with the caller: Python's `$` also matches before a final newline (Go's
// does not; strip the newline or write `\n?\z`), and `\S`, `\D` and `\W` inside a bracket keep
// their ASCII meaning.
const (
	spaceRanges = `\t\n\v\f\r \x{1c}-\x{1f}\x{85}\x{a0}\x{1680}\x{2000}-\x{200a}\x{2028}\x{2029}\x{202f}\x{205f}\x{3000}`
	digitRanges = `\p{Nd}`
	wordRanges  = `\p{L}\p{N}_`
)

// Regexp is regexp.MustCompile of the Python pattern with its Unicode classes; it panics on a
// pattern Go cannot compile, like MustCompile.
func Regexp(pattern string) *regexp.Regexp {
	return regexp.MustCompile(translate(pattern))
}

func translate(p string) string {
	p = strings.ReplaceAll(p, `[\s\S]`, `(?s:.)`)
	var b strings.Builder
	inClass := false
	for i := 0; i < len(p); i++ {
		c := p[i]
		switch {
		case c == '\\' && i+1 < len(p):
			i++
			b.WriteString(expandEscape(p[i], inClass))
		case c == '[' && !inClass:
			inClass = true
			b.WriteByte(c)
			// a leading ^ and a leading ] belong to the class
			if i+1 < len(p) && p[i+1] == '^' {
				i++
				b.WriteByte('^')
			}
			if i+1 < len(p) && p[i+1] == ']' {
				i++
				b.WriteString(`\]`)
			}
		case c == ']' && inClass:
			inClass = false
			b.WriteByte(c)
		default:
			b.WriteByte(c)
		}
	}
	return b.String()
}

// expandEscape writes the escape `\<e>`, widening \s \d \w (and, outside a bracket, \S \D \W).
func expandEscape(e byte, inClass bool) string {
	ranges := map[byte]string{'s': spaceRanges, 'd': digitRanges, 'w': wordRanges}
	if r, ok := ranges[e]; ok {
		if inClass {
			return r
		}
		return "[" + r + "]"
	}
	if !inClass {
		if r, ok := ranges[e+'a'-'A']; ok && e >= 'A' && e <= 'Z' {
			return "[^" + r + "]"
		}
	}
	return `\` + string(e)
}
