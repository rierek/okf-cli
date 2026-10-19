package install

import (
	"fmt"
	"math"
	"strconv"
	"strings"
	"unicode/utf16"

	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

// This file is json.loads and json.dumps of Python, to the byte: the parser keeps the order of
// the keys and reports an error with the same words and position as JSONDecodeError (Python
// 3.14), the writer indents like json.dumps(indent=...) and escapes like ensure_ascii on or off.
// Documents are *jobj (ordered object), []any, string, bool, nil and jnum (a number as the
// text Python would print for it).

// jnum is a number as json.dumps prints it: an int as digits, a float as repr (NaN, Infinity).
type jnum string

// jobj is a JSON object in key order; assigning an existing key keeps its position.
type jobj struct {
	keys []string
	m    map[string]any
}

func newObj() *jobj { return &jobj{m: map[string]any{}} }

// obj builds a jobj from alternating keys and values.
func obj(kv ...any) *jobj {
	o := newObj()
	for i := 0; i < len(kv); i += 2 {
		o.set(kv[i].(string), kv[i+1])
	}
	return o
}

func (o *jobj) get(k string) (any, bool) { v, ok := o.m[k]; return v, ok }

func (o *jobj) set(k string, v any) {
	if _, ok := o.m[k]; !ok {
		o.keys = append(o.keys, k)
	}
	o.m[k] = v
}

func (o *jobj) del(k string) {
	if _, ok := o.m[k]; !ok {
		return
	}
	delete(o.m, k)
	for i, key := range o.keys {
		if key == k {
			o.keys = append(o.keys[:i:i], o.keys[i+1:]...)
			break
		}
	}
}

func (o *jobj) size() int { return len(o.keys) }

// strList is a list of strings as a JSON array.
func strList(items ...string) []any {
	out := make([]any, len(items))
	for i, s := range items {
		out[i] = s
	}
	return out
}

// jsonError is json.JSONDecodeError.
type jsonError struct {
	msg string
	pos int
	doc []rune
}

func (e *jsonError) Error() string {
	line, last := 1, -1
	for i := range min(e.pos, len(e.doc)) {
		if e.doc[i] == '\n' {
			line++
			last = i
		}
	}
	return fmt.Sprintf("%s: line %d column %d (char %d)", e.msg, line, e.pos-last, e.pos)
}

// stopIteration is the scanner's "no value here" signal; the decoder turns it into "Expecting value".
type stopIteration struct{ pos int }

func (stopIteration) Error() string { return "stop" }

type scanner struct{ s []rune }

// parseJSON is json.loads(text).
func parseJSON(text string) (any, error) {
	sc := &scanner{s: []rune(text)}
	if len(sc.s) > 0 && sc.s[0] == '\ufeff' {
		return nil, sc.errAt("Unexpected UTF-8 BOM (decode using utf-8-sig)", 0)
	}
	v, end, err := sc.scanOnce(sc.skipWS(0))
	if err != nil {
		return nil, sc.fail(err)
	}
	if end = sc.skipWS(end); end != len(sc.s) {
		return nil, sc.errAt("Extra data", end)
	}
	return v, nil
}

func (sc *scanner) errAt(msg string, pos int) error { return &jsonError{msg, pos, sc.s} }

func (sc *scanner) fail(err error) error {
	if st, ok := err.(stopIteration); ok {
		return sc.errAt("Expecting value", st.pos)
	}
	return err
}

func (sc *scanner) skipWS(i int) int {
	for i < len(sc.s) && (sc.s[i] == ' ' || sc.s[i] == '\t' || sc.s[i] == '\n' || sc.s[i] == '\r') {
		i++
	}
	return i
}

func (sc *scanner) has(i int, lit string) bool {
	r := []rune(lit)
	if i+len(r) > len(sc.s) {
		return false
	}
	for k, c := range r {
		if sc.s[i+k] != c {
			return false
		}
	}
	return true
}

func (sc *scanner) scanOnce(i int) (any, int, error) {
	s := sc.s
	if i >= len(s) {
		return nil, 0, stopIteration{i}
	}
	switch s[i] {
	case '"':
		str, next, err := sc.scanString(i + 1)
		return str, next, err
	case '{':
		return sc.parseObject(i + 1)
	case '[':
		return sc.parseArray(i + 1)
	case 'n':
		if sc.has(i, "null") {
			return nil, i + 4, nil
		}
	case 't':
		if sc.has(i, "true") {
			return true, i + 4, nil
		}
	case 'f':
		if sc.has(i, "false") {
			return false, i + 5, nil
		}
	case 'N':
		if sc.has(i, "NaN") {
			return jnum("NaN"), i + 3, nil
		}
	case 'I':
		if sc.has(i, "Infinity") {
			return jnum("Infinity"), i + 8, nil
		}
	case '-':
		if sc.has(i, "-Infinity") {
			return jnum("-Infinity"), i + 9, nil
		}
	}
	return sc.matchNumber(i)
}

func isDigit(c rune) bool { return c >= '0' && c <= '9' }

// matchNumber follows _match_number_unicode of CPython's _json.c, backtracking rules included.
func (sc *scanner) matchNumber(start int) (any, int, error) {
	s := sc.s
	end := len(s) - 1
	i := start
	if s[i] == '-' {
		i++
		if i > end {
			return nil, 0, stopIteration{start}
		}
	}
	switch {
	case s[i] >= '1' && s[i] <= '9':
		i++
		for i <= end && isDigit(s[i]) {
			i++
		}
	case s[i] == '0':
		i++
	default:
		return nil, 0, stopIteration{start}
	}
	float := false
	if i < end && s[i] == '.' && isDigit(s[i+1]) {
		float = true
		i += 2
		for i <= end && isDigit(s[i]) {
			i++
		}
	}
	if i < end && (s[i] == 'e' || s[i] == 'E') {
		eStart := i
		i++
		if i < end && (s[i] == '-' || s[i] == '+') {
			i++
		}
		for i <= end && isDigit(s[i]) {
			i++
		}
		if isDigit(s[i-1]) {
			float = true
		} else {
			i = eStart
		}
	}
	text := string(s[start:i])
	if !float {
		if strings.TrimLeft(text, "-") == "0" {
			text = "0" // int("-0")
		}
		return jnum(text), i, nil
	}
	f, _ := strconv.ParseFloat(text, 64) // out of range gives ±Inf, as float() does
	return jnum(floatRepr(f)), i, nil
}

func floatRepr(f float64) string {
	switch {
	case math.IsNaN(f):
		return "NaN"
	case math.IsInf(f, 1):
		return "Infinity"
	case math.IsInf(f, -1):
		return "-Infinity"
	}
	return pytext.ReprFloat(f)
}

func (sc *scanner) parseObject(i int) (any, int, error) {
	s := sc.s
	o := newObj()
	i = sc.skipWS(i)
	if i >= len(s) || s[i] != '}' {
		for {
			if i >= len(s) || s[i] != '"' {
				return nil, 0, sc.errAt("Expecting property name enclosed in double quotes", i)
			}
			key, next, err := sc.scanString(i + 1)
			if err != nil {
				return nil, 0, err
			}
			i = sc.skipWS(next)
			if i >= len(s) || s[i] != ':' {
				return nil, 0, sc.errAt("Expecting ':' delimiter", i)
			}
			i = sc.skipWS(i + 1)
			val, next, err := sc.scanOnce(i)
			if err != nil {
				return nil, 0, err
			}
			o.set(key, val)
			i = sc.skipWS(next)
			if i < len(s) && s[i] == '}' {
				break
			}
			if i >= len(s) || s[i] != ',' {
				return nil, 0, sc.errAt("Expecting ',' delimiter", i)
			}
			comma := i
			i = sc.skipWS(i + 1)
			if i < len(s) && s[i] == '}' {
				return nil, 0, sc.errAt("Illegal trailing comma before end of object", comma)
			}
		}
	}
	return o, i + 1, nil
}

func (sc *scanner) parseArray(i int) (any, int, error) {
	s := sc.s
	list := []any{}
	i = sc.skipWS(i)
	if i >= len(s) || s[i] != ']' {
		for {
			val, next, err := sc.scanOnce(i)
			if err != nil {
				return nil, 0, err
			}
			list = append(list, val)
			i = sc.skipWS(next)
			if i < len(s) && s[i] == ']' {
				break
			}
			if i >= len(s) || s[i] != ',' {
				return nil, 0, sc.errAt("Expecting ',' delimiter", i)
			}
			comma := i
			i = sc.skipWS(i + 1)
			if i < len(s) && s[i] == ']' {
				return nil, 0, sc.errAt("Illegal trailing comma before end of array", comma)
			}
		}
	}
	return list, i + 1, nil
}

func hexVal(c rune) int {
	switch {
	case c >= '0' && c <= '9':
		return int(c - '0')
	case c >= 'a' && c <= 'f':
		return int(c-'a') + 10
	case c >= 'A' && c <= 'F':
		return int(c-'A') + 10
	}
	return -1
}

// scanString follows scanstring_unicode of CPython's _json.c (strict): end is the index after the
// opening quote; it returns the text and the index after the closing quote.
func (sc *scanner) scanString(end int) (string, int, error) {
	s := sc.s
	begin := end - 1
	var b strings.Builder
	for {
		next := end
		var c rune
		for ; next < len(s); next++ {
			c = s[next]
			if c == '"' || c == '\\' {
				break
			}
			if c <= 0x1f {
				return "", 0, sc.errAt("Invalid control character at", next)
			}
		}
		if next >= len(s) {
			return "", 0, sc.errAt("Unterminated string starting at", begin)
		}
		b.WriteString(string(s[end:next]))
		next++
		if c == '"' {
			return b.String(), next, nil
		}
		if next == len(s) {
			return "", 0, sc.errAt("Unterminated string starting at", begin)
		}
		c = s[next]
		if c != 'u' {
			end = next + 1
			switch c {
			case '"', '\\', '/':
			case 'b':
				c = '\b'
			case 'f':
				c = '\f'
			case 'n':
				c = '\n'
			case 'r':
				c = '\r'
			case 't':
				c = '\t'
			default:
				return "", 0, sc.errAt("Invalid \\escape", end-2)
			}
			b.WriteRune(c)
			continue
		}
		next++
		end = next + 4
		if end >= len(s) {
			return "", 0, sc.errAt("Invalid \\uXXXX escape", next-1)
		}
		cp := 0
		for ; next < end; next++ {
			d := hexVal(s[next])
			if d < 0 {
				return "", 0, sc.errAt("Invalid \\uXXXX escape", end-5)
			}
			cp = cp<<4 | d
		}
		r := rune(cp)
		if utf16.IsSurrogate(r) && r < 0xdc00 && end+6 < len(s) && s[next] == '\\' && s[next+1] == 'u' {
			next += 2
			end += 6
			c2 := 0
			for ; next < end; next++ {
				d := hexVal(s[next])
				if d < 0 {
					return "", 0, sc.errAt("Invalid \\uXXXX escape", end-5)
				}
				c2 = c2<<4 | d
			}
			if c2 >= 0xdc00 && c2 <= 0xdfff {
				r = utf16.DecodeRune(r, rune(c2))
			} else {
				end -= 6
			}
		}
		if utf16.IsSurrogate(r) {
			r = '\ufffd' // a lone surrogate cannot be held in a Go string
		}
		b.WriteRune(r)
	}
}

// dumps is json.dumps(v, indent=indent, ensure_ascii=ascii): indent is nil for the compact form
// (", " and ": " separators), else the string one level adds.
func dumps(v any, indent *string, ascii bool) string {
	var b strings.Builder
	dump(&b, v, indent, ascii, 0)
	return b.String()
}

func dump(b *strings.Builder, v any, indent *string, ascii bool, level int) {
	nl := func(n int) {
		b.WriteByte('\n')
		b.WriteString(strings.Repeat(*indent, n))
	}
	sep := func(first bool, n int) {
		switch {
		case indent == nil && !first:
			b.WriteString(", ")
		case indent != nil && first:
			nl(n)
		case indent != nil:
			b.WriteByte(',')
			nl(n)
		}
	}
	switch x := v.(type) {
	case nil:
		b.WriteString("null")
	case bool:
		b.WriteString(strconv.FormatBool(x))
	case string:
		dumpString(b, x, ascii)
	case jnum:
		b.WriteString(string(x))
	case *jobj:
		if x.size() == 0 {
			b.WriteString("{}")
			return
		}
		b.WriteByte('{')
		for i, k := range x.keys {
			sep(i == 0, level+1)
			dumpString(b, k, ascii)
			b.WriteString(": ")
			dump(b, x.m[k], indent, ascii, level+1)
		}
		if indent != nil {
			nl(level)
		}
		b.WriteByte('}')
	case []any:
		if len(x) == 0 {
			b.WriteString("[]")
			return
		}
		b.WriteByte('[')
		for i, e := range x {
			sep(i == 0, level+1)
			dump(b, e, indent, ascii, level+1)
		}
		if indent != nil {
			nl(level)
		}
		b.WriteByte(']')
	default:
		panic(fmt.Sprintf("install: cannot dump %T", v))
	}
}

func dumpString(b *strings.Builder, s string, ascii bool) {
	const hexDigits = "0123456789abcdef"
	b.WriteByte('"')
	for _, r := range s {
		switch {
		case r == '"':
			b.WriteString(`\"`)
		case r == '\\':
			b.WriteString(`\\`)
		case r == '\n':
			b.WriteString(`\n`)
		case r == '\r':
			b.WriteString(`\r`)
		case r == '\t':
			b.WriteString(`\t`)
		case r == '\b':
			b.WriteString(`\b`)
		case r == '\f':
			b.WriteString(`\f`)
		case r < 0x20 || ascii && (r > 0x7e):
			if r > 0xffff {
				hi, lo := utf16.EncodeRune(r)
				fmt.Fprintf(b, `\u%04x\u%04x`, hi, lo)
			} else {
				b.WriteString(`\u`)
				for shift := 12; shift >= 0; shift -= 4 {
					b.WriteByte(hexDigits[(r>>shift)&0xf])
				}
			}
		default:
			b.WriteRune(r)
		}
	}
	b.WriteByte('"')
}

// containsScript is `SCRIPT in json.dumps(v)`: the script name sits inside one string or key.
func containsScript(v any) bool {
	switch x := v.(type) {
	case string:
		return strings.Contains(x, scriptName)
	case *jobj:
		for _, k := range x.keys {
			if strings.Contains(k, scriptName) || containsScript(x.m[k]) {
				return true
			}
		}
	case []any:
		for _, e := range x {
			if containsScript(e) {
				return true
			}
		}
	}
	return false
}

// equalsWant is `value == want` for the identity values of an MCP entry: a string, or a list of
// strings.
func equalsWant(value any, want any) bool {
	switch w := want.(type) {
	case string:
		s, ok := value.(string)
		return ok && s == w
	case []string:
		list, ok := value.([]any)
		if !ok || len(list) != len(w) {
			return false
		}
		for i, e := range list {
			if s, ok := e.(string); !ok || s != w[i] {
				return false
			}
		}
		return true
	}
	return false
}
