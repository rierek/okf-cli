package pytext

import (
	"strings"
	"unicode"
	"unicode/utf8"
)

// Wrap is textwrap.wrap(text, width, initial_indent=initialIndent, subsequent_indent=subsequentIndent)
// with the default TextWrapper settings (tabs expanded, whitespace replaced, long words and
// hyphens broken, surrounding whitespace dropped). Lengths count code points like Python's len.
// A width of zero or less panics where Python raises ValueError.
func Wrap(text string, width int, initialIndent, subsequentIndent string) []string {
	if width <= 0 {
		panic("pytext: invalid width (must be > 0)")
	}
	return wrapLines(wrapSplit([]rune(wrapMunge(text))), width, initialIndent, subsequentIndent)
}

// Fill is textwrap.fill: the lines of Wrap joined with newlines.
func Fill(text string, width int, initialIndent, subsequentIndent string) string {
	return strings.Join(Wrap(text, width, initialIndent, subsequentIndent), "\n")
}

// wrapMunge expands tabs to the next multiple of eight and turns every other ASCII whitespace
// character into a space (TextWrapper._munge_whitespace).
func wrapMunge(text string) string {
	var b strings.Builder
	column := 0
	for _, r := range text {
		switch {
		case r == '\t':
			n := 8 - column%8
			b.WriteString(strings.Repeat(" ", n))
			column += n
		case r == '\n' || r == '\r':
			b.WriteByte(' ')
			column = 0
		case r == '\v' || r == '\f':
			b.WriteByte(' ')
			column++
		default:
			b.WriteRune(r)
			column++
		}
	}
	return b.String()
}

// wrapIsSpace is the whitespace textwrap knows: the six ASCII characters of string.whitespace
// (other Unicode spaces are ordinary word characters to it).
func wrapIsSpace(r rune) bool { return r == ' ' || (r >= '\t' && r <= '\r') }

// wrapIsWord is the regex class \w: letters, numbers and the underscore.
func wrapIsWord(r rune) bool { return r == '_' || unicode.IsLetter(r) || unicode.IsNumber(r) }

// wrapIsLetter is the class [^\d\W] of textwrap's word pattern: a word character that is no digit.
func wrapIsLetter(r rune) bool { return wrapIsWord(r) && !unicode.IsDigit(r) }

// wrapIsWordPunct is the class [\w!"'&.,?].
func wrapIsWordPunct(r rune) bool { return wrapIsWord(r) || strings.ContainsRune(`!"'&.,?`, r) }

// wrapSplit cuts text into the indivisible chunks of TextWrapper.wordsep_re: whitespace runs,
// em-dashes between words and words ending after a hyphen of a compound.
func wrapSplit(text []rune) [][]rune {
	var chunks [][]rune
	for p := 0; p < len(text); {
		end := wrapChunkEnd(text, p)
		chunks = append(chunks, text[p:end])
		p = end
	}
	return chunks
}

// wrapChunkEnd is the end of the chunk that starts at p. The three alternatives of the regex are
// tried in its order; the lazy word match grows one character at a time and stops at the
// first position where one of its three endings holds.
func wrapChunkEnd(t []rune, p int) int {
	if wrapIsSpace(t[p]) {
		for p < len(t) && wrapIsSpace(t[p]) {
			p++
		}
		return p
	}
	if p > 0 && wrapIsWordPunct(t[p-1]) {
		if end, ok := wrapEmDashEnd(t, p); ok {
			return end
		}
	}
	for q := p + 1; ; q++ {
		switch {
		case q < len(t) && t[q] == '-' && wrapCompoundHyphen(t, q):
			return q + 1
		case q == len(t) || wrapIsSpace(t[q]):
			return q
		case wrapIsWordPunct(t[q-1]):
			if _, ok := wrapEmDashEnd(t, q); ok {
				return q
			}
		}
	}
}

// wrapEmDashEnd reports whether a run of two or more hyphens starts at i and a word character
// follows it, and where the run ends.
func wrapEmDashEnd(t []rune, i int) (int, bool) {
	end := i
	for end < len(t) && t[end] == '-' {
		end++
	}
	return end, end-i >= 2 && end < len(t) && wrapIsWord(t[end])
}

// wrapCompoundHyphen reports whether the hyphen at q ends a chunk: two letters (or letter, hyphen,
// letter) come before it and a letter, an optional hyphen and a letter come after it.
func wrapCompoundHyphen(t []rune, q int) bool {
	behind := q >= 2 && wrapIsLetter(t[q-1]) && wrapIsLetter(t[q-2]) ||
		q >= 3 && wrapIsLetter(t[q-1]) && t[q-2] == '-' && wrapIsLetter(t[q-3])
	if !behind || q+2 >= len(t) || !wrapIsLetter(t[q+1]) {
		return false
	}
	return wrapIsLetter(t[q+2]) || t[q+2] == '-' && q+3 < len(t) && wrapIsLetter(t[q+3])
}

// wrapIsBlank is chunk.strip() == "".
func wrapIsBlank(chunk []rune) bool {
	for _, r := range chunk {
		if !IsSpace(r) {
			return false
		}
	}
	return true
}

// wrapLines is TextWrapper._wrap_chunks for the default settings. The chunks are consumed
// from the end of the slice, so the slice is reversed first.
func wrapLines(chunks [][]rune, width int, initialIndent, subsequentIndent string) []string {
	for i, j := 0, len(chunks)-1; i < j; i, j = i+1, j-1 {
		chunks[i], chunks[j] = chunks[j], chunks[i]
	}
	var lines []string
	for len(chunks) > 0 {
		var line [][]rune
		lineLen := 0
		indent := initialIndent
		if len(lines) > 0 {
			indent = subsequentIndent
		}
		room := width - utf8.RuneCountInString(indent)
		if len(lines) > 0 && wrapIsBlank(chunks[len(chunks)-1]) {
			chunks = chunks[:len(chunks)-1]
		} else if len(lines) == 0 && room < 0 && len(chunks[len(chunks)-1]) == 0 {
			// Python never leaves this state: with no line written and no room for the indent
			// the empty rest of a broken word is neither dropped nor taken, and it loops forever.
			chunks = chunks[:len(chunks)-1]
		}
		for len(chunks) > 0 && lineLen+len(chunks[len(chunks)-1]) <= room {
			line = append(line, chunks[len(chunks)-1])
			lineLen += len(chunks[len(chunks)-1])
			chunks = chunks[:len(chunks)-1]
		}
		if len(chunks) > 0 && len(chunks[len(chunks)-1]) > room {
			line = wrapBreakWord(chunks, line, lineLen, room)
		}
		if n := len(line); n > 0 && wrapIsBlank(line[n-1]) {
			line = line[:n-1]
		}
		if len(line) > 0 {
			var b strings.Builder
			b.WriteString(indent)
			for _, c := range line {
				b.WriteString(string(c))
			}
			lines = append(lines, b.String())
		}
	}
	return lines
}

// wrapBreakWord is TextWrapper._handle_long_word: the chunk on top of the stack is longer than
// any line, so as much of it as fits goes onto the current line (ending after the last hyphen
// that has a non-hyphen before it, when one lies inside the room), and the rest stays on the
// stack. A line that is already full takes nothing. It returns the extended line.
func wrapBreakWord(stack [][]rune, line [][]rune, lineLen, room int) [][]rune {
	top := len(stack) - 1
	chunk := stack[top]
	spaceLeft := 1
	if room >= 1 {
		spaceLeft = room - lineLen
	}
	if spaceLeft <= 0 {
		return line
	}
	end := min(spaceLeft, len(chunk))
	if len(chunk) > spaceLeft {
		hyphen := -1
		for i := spaceLeft - 1; i >= 0; i-- {
			if chunk[i] == '-' {
				hyphen = i
				break
			}
		}
		if hyphen > 0 && wrapHasNonHyphen(chunk[:hyphen]) {
			end = hyphen + 1
		}
	}
	stack[top] = chunk[end:]
	return append(line, chunk[:end])
}

// wrapHasNonHyphen is any(c != "-" for c in chunk).
func wrapHasNonHyphen(chunk []rune) bool {
	for _, r := range chunk {
		if r != '-' {
			return true
		}
	}
	return false
}
