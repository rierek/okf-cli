package complete

import "strings"

// This file is argcomplete's lexers.split_line over its copy of shlex (posix mode, whitespace
// split), which also records where the last COMP_WORDBREAKS character sits in the current word.
// Positions are characters, as in Python.

const (
	lexWhitespace = " \t\r\n"
	lexQuotes     = `'"`
	lexEscape     = `\`
	lexWordchars  = "abcdfeghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"
	stateNone     = rune(-1)
)

// lexer is one shlex instance; state is a space, 'a' (in a word), a quote or the escape
// character, or stateNone at the end of the input.
type lexer struct {
	in         []rune
	pos        int // StringIO.tell()
	state      rune
	token      []rune
	wordbreaks string
	lastBreak  int // last_wordbreak_pos, -1 for None
}

func (l *lexer) read() (rune, bool) {
	if l.pos >= len(l.in) {
		return 0, false
	}
	r := l.in[l.pos]
	l.pos++
	return r, true
}

// readline skips to the end of the line (instream.readline()).
func (l *lexer) readline() {
	for {
		r, ok := l.read()
		if !ok || r == '\n' {
			return
		}
	}
}

func (l *lexer) isBreak(r rune) bool { return strings.ContainsRune(l.wordbreaks, r) }

// next is get_token: the next word, ok false at the end of the input. A word cut off inside a
// quote or after an escape gives errOpen; l.token then holds what was read of it.
func (l *lexer) next() (word string, ok bool, errOpen bool) {
	quoted := false
	escaped := ' '
	for {
		r, has := l.read()
		switch {
		case l.state == stateNone:
			l.token = nil
		case l.state == ' ':
			switch {
			case !has:
				l.state = stateNone
			case strings.ContainsRune(lexWhitespace, r):
				if len(l.token) > 0 || quoted {
					goto done
				}
				continue
			case r == '#':
				l.readline()
				continue
			case strings.ContainsRune(lexEscape, r):
				escaped, l.state = 'a', r
				continue
			case strings.ContainsRune(lexWordchars, r):
				l.token, l.state = []rune{r}, 'a'
				continue
			case strings.ContainsRune(lexQuotes, r):
				l.state = r
				continue
			default: // whitespace_split
				l.token, l.state = []rune{r}, 'a'
				if l.isBreak(r) {
					l.lastBreak = len(l.token) - 1
				}
				continue
			}
		case strings.ContainsRune(lexQuotes, l.state):
			quoted = true
			switch {
			case !has:
				return "", false, true
			case r == l.state:
				l.state = 'a'
			case strings.ContainsRune(lexEscape, r) && l.state == '"':
				escaped, l.state = l.state, r
			default:
				l.token = append(l.token, r)
			}
			continue
		case strings.ContainsRune(lexEscape, l.state):
			if !has {
				return "", false, true
			}
			if strings.ContainsRune(lexQuotes, escaped) && r != l.state && r != escaped {
				l.token = append(l.token, l.state)
			}
			l.token = append(l.token, r)
			l.state = escaped
			continue
		default: // 'a'
			switch {
			case !has:
				l.state = stateNone
			case strings.ContainsRune(lexWhitespace, r):
				l.state = ' '
				if len(l.token) > 0 || quoted {
					goto done
				}
				continue
			case r == '#':
				l.readline()
				l.state = ' '
				if len(l.token) > 0 || quoted {
					goto done
				}
				continue
			case strings.ContainsRune(lexQuotes, r):
				l.state = r
				continue
			case strings.ContainsRune(lexEscape, r):
				escaped, l.state = 'a', r
				continue
			default:
				l.token = append(l.token, r)
				if l.isBreak(r) {
					l.lastBreak = len(l.token) - 1
				}
				continue
			}
		}
		break // the end of the input
	}
done:
	word = string(l.token)
	isNone := len(l.token) == 0 && !quoted
	l.token = nil
	if l.state == ' ' {
		l.lastBreak = -1
	}
	return word, !isNone, false
}

// splitLine is split_line: the quote that opens the word under the cursor, its prefix and suffix
// at point, the words before it and the position of the last wordbreak in it (-1 for none).
func splitLine(line string, point int, wordbreaks string) (prequote, prefix, suffix string, words []string, lastBreak int) {
	in := []rune(line)
	if point < len(in) {
		in = in[:point]
	}
	l := &lexer{in: in, state: ' ', wordbreaks: wordbreaks, lastBreak: -1}
	split := func(word []rune) (string, string, string, []string, int) {
		p := len(word) + point - l.pos
		if l.state == ' ' {
			p++
		}
		if p > len(word) {
			words = append(words, string(word))
			word = nil
			p = 0
		}
		cut := p
		if cut < 0 { // Python slicing from the end
			cut = max(len(word)+cut, 0)
		}
		quote := ""
		if l.state != stateNone && strings.ContainsRune(lexQuotes, l.state) {
			quote = string(l.state)
		}
		return quote, string(word[:cut]), string(word[cut:]), words, l.lastBreak
	}
	for {
		word, ok, open := l.next()
		if open {
			if l.pos >= point {
				return split(l.token)
			}
			return "", "", "", words, -1 // argcomplete raises here; nothing to complete
		}
		if !ok {
			return "", "", "", words, -1
		}
		if l.pos >= point {
			return split([]rune(word))
		}
		words = append(words, word)
	}
}
