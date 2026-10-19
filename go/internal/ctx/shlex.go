package ctx

import "errors"

// shlexSplit is Python shlex.split(s) (POSIX mode, no comments): the words of s under the quoting
// rules of a POSIX shell. A single quote keeps every character, a double quote keeps every
// character but lets a backslash escape `"` and `\`, a backslash outside quotes escapes the next
// character, and a pair of quotes alone makes an empty word. A quote or a backslash that is not
// closed is an error. Only ASCII characters have a meaning, so s is read byte by byte.
func shlexSplit(s string) ([]string, error) {
	const (
		between = iota // outside a word
		inWord
		inSingle
		inDouble
		escaped         // after a backslash outside quotes
		escapedInDouble // after a backslash inside double quotes
	)
	var words []string
	var word []byte
	started := false // the word has begun, an empty quoted word included
	state := between
	for i := range len(s) {
		c := s[i]
		switch state {
		case between, inWord:
			switch c {
			case ' ', '\t', '\r', '\n':
				if started {
					words = append(words, string(word))
					word, started = nil, false
				}
				state = between
			case '\\':
				state, started = escaped, true
			case '\'':
				state, started = inSingle, true
			case '"':
				state, started = inDouble, true
			default:
				word, started, state = append(word, c), true, inWord
			}
		case inSingle:
			if c == '\'' {
				state = inWord
			} else {
				word = append(word, c)
			}
		case inDouble:
			switch c {
			case '"':
				state = inWord
			case '\\':
				state = escapedInDouble
			default:
				word = append(word, c)
			}
		case escaped:
			word, state = append(word, c), inWord
		case escapedInDouble:
			if c != '"' && c != '\\' {
				word = append(word, '\\') // only the quote and the backslash can be escaped here
			}
			word, state = append(word, c), inDouble
		}
	}
	switch state {
	case inSingle, inDouble:
		return nil, errors.New("No closing quotation")
	case escaped, escapedInDouble:
		return nil, errors.New("No escaped character")
	}
	if started {
		words = append(words, string(word))
	}
	return words, nil
}
