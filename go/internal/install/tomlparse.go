package install

import (
	"strconv"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

// This file ports CPython 3.14's tomllib (Lib/tomllib/_parser.py and _re.py). okf_install.py
// validates and reads the Codex config.toml with it, so what is accepted, the words of an
// error and its line and column are tomllib's, not those of a Go TOML library. The functions
// follow the Python ones (snake_case becomes camelCase); positions are indexes into the code
// points of the text, as in Python.

// tomlScalar is an integer, float, date or time. tomllib has validated it; the callers never
// look at its value, so only the kind and the literal are kept.
type tomlScalar struct {
	kind string // integer, float, local-date, local-time, local-datetime or offset-datetime
	text string // the literal as written
}

// tomlError is a failed tomllib.loads; Error() is str() of the Python exception. decode is true
// for TOMLDecodeError, the one exception okf_install.py handles, and false for the others a
// text can raise: RecursionError and the ValueError of an integer with too many digits.
type tomlError struct {
	msg    string
	decode bool
}

func (e *tomlError) Error() string { return e.msg }

const (
	tomlFrozen       = 1 << iota // Flags.FROZEN: an inline array or inline table, immutable
	tomlExplicitNest             // Flags.EXPLICIT_NEST: no longer opened with the "[table]" syntax
)

const (
	tomlMaxKeyParts = 1000 // MAX_KEY_PARTS: sys.getrecursionlimit()
	tomlMaxDigits   = 4300 // sys.get_int_max_str_digits(): longest decimal integer int() takes

	// ponytail: Python raises RecursionError by interpreter frames (limit 1000), so where it strikes
	// depends on the caller's stack and on what is parsed at the bottom. This counts the frames of
	// nested arrays and inline tables for a caller one frame deep: 497 nested arrays and 331 nested
	// inline tables parse, one more fails, as in Python for `a = [[...]]` and `a = {b = {b = 1}}`;
	// for other values it is off by a level or two. It exists so that absurd nesting fails with an
	// error instead of exhausting the Go stack.
	tomlRecursionLimit = 1000
	tomlBaseFrames     = 4 // <module>, loads, key_value_rule, parse_key_value_pair
)

// parseTOML is tomllib.loads(text): the document as map[string]any, or an error whose Error() is
// exactly str() of the Python exception, e.g. "Expected '=' after a key in a key/value pair (at
// line 1, column 6)". Tables are map[string]any, arrays []any, strings string, booleans bool;
// integers, floats, dates and times are tomlScalar. The error is a *tomlError. Text that is not
// valid UTF-8 reads as U+FFFD, where Python could not have produced the string at all.
func parseTOML(text string) (doc map[string]any, err error) {
	// The parser raises a *tomlError by panic, as the Python raises TOMLDecodeError.
	defer func() {
		if r := recover(); r != nil {
			e, ok := r.(*tomlError)
			if !ok {
				panic(r)
			}
			doc, err = nil, e
		}
	}()
	// The spec allows converting "\r\n" to "\n", even in string literals.
	p := &tomlParser{src: []rune(strings.ReplaceAll(text, "\r\n", "\n"))}
	return p.loads(), nil
}

// tomlParser reads the text as code points; every pos is an index into src.
type tomlParser struct {
	src   []rune
	depth int // Python frames of the arrays and inline tables being parsed
}

// at is src[pos], or -1 where Python raises IndexError.
func (p *tomlParser) at(pos int) rune {
	if pos < len(p.src) {
		return p.src[pos]
	}
	return -1
}

// startsWith is src.startswith(prefix, pos) for an ASCII prefix.
func (p *tomlParser) startsWith(prefix string, pos int) bool {
	for i := range len(prefix) {
		if p.at(pos+i) != rune(prefix[i]) {
			return false
		}
	}
	return true
}

// text is the slice src[from:to], clamped like Python's.
func (p *tomlParser) text(from, to int) string {
	to = min(to, len(p.src))
	if from >= to {
		return ""
	}
	return string(p.src[from:to])
}

// index is src.index(expect, from) for an ASCII text, -1 where Python raises ValueError.
func (p *tomlParser) index(expect string, from int) int {
	for i := from; i+len(expect) <= len(p.src); i++ {
		if p.startsWith(expect, i) {
			return i
		}
	}
	return -1
}

// err is TOMLDecodeError(msg, src, pos).
func (p *tomlParser) err(msg string, pos int) *tomlError {
	if pos >= len(p.src) {
		return &tomlError{msg + " (at end of document)", true}
	}
	line, last := 1, -1 // the line, and the index of the last "\n" before pos
	for i := range pos {
		if p.src[i] == '\n' {
			line, last = line+1, i
		}
	}
	col := pos + 1
	if line > 1 {
		col = pos - last
	}
	return &tomlError{msg + " (at line " + strconv.Itoa(line) + ", column " + strconv.Itoa(col) + ")", true}
}

// descend is the RecursionError check of a nested array or inline table: frames are what the
// level costs, leaf what the deepest helper call below it costs.
func (p *tomlParser) descend(frames, leaf int) {
	p.depth += frames
	if tomlBaseFrames+p.depth+leaf > tomlRecursionLimit {
		panic(&tomlError{"maximum recursion depth exceeded", false})
	}
}

func tomlIsWS(c rune) bool   { return c == ' ' || c == '\t' }
func tomlIsWSNL(c rune) bool { return c == ' ' || c == '\t' || c == '\n' }
func tomlDigit(c rune) bool  { return c >= '0' && c <= '9' }
func tomlIsBare(c rune) bool {
	return c >= 'a' && c <= 'z' || c >= 'A' && c <= 'Z' || tomlDigit(c) || c == '-' || c == '_'
}

// tomlIllegal is ILLEGAL_BASIC_STR_CHARS: ASCII_CTRL without tab. Literal strings and comments
// refuse the same characters. Multiline strings also take the newline.
func tomlIllegal(c rune) bool          { return (c >= 0 && c < 0x20 || c == 0x7f) && c != '\t' }
func tomlIllegalMultiline(c rune) bool { return tomlIllegal(c) && c != '\n' }

func tomlHexVal(c rune) int64 {
	switch {
	case tomlDigit(c):
		return int64(c - '0')
	case c >= 'a' && c <= 'f':
		return int64(c-'a') + 10
	case c >= 'A' && c <= 'F':
		return int64(c-'A') + 10
	}
	return -1
}

// loads is tomllib.loads after the newline normalisation: one statement at a time.
func (p *tomlParser) loads() map[string]any {
	out := &tomlOutput{data: map[string]any{}, flags: newTomlFlags()}
	var header []string
	pos := 0
	for {
		// 1. Skip line leading whitespace
		pos = p.skip(pos, tomlIsWS)

		// 2. Parse rules: end of line, comment, key/value pair, append dict to list (and move to its
		// namespace), create dict (and move to its namespace). Skip trailing whitespace when applicable.
		c := p.at(pos)
		if c < 0 {
			break
		}
		if c == '\n' {
			pos++
			continue
		}
		switch {
		case tomlIsBare(c) || c == '"' || c == '\'':
			pos = p.keyValueRule(pos, out, header)
			pos = p.skip(pos, tomlIsWS)
		case c == '[':
			out.flags.finalizePending()
			if p.at(pos+1) == '[' {
				pos, header = p.createListRule(pos, out)
			} else {
				pos, header = p.createDictRule(pos, out)
			}
			pos = p.skip(pos, tomlIsWS)
		case c != '#':
			panic(p.err("Invalid statement", pos))
		}

		// 3. Skip comment
		pos = p.skipComment(pos)

		// 4. Expect end of line or end of file
		c = p.at(pos)
		if c < 0 {
			break
		}
		if c != '\n' {
			panic(p.err("Expected newline or end of document after a statement", pos))
		}
		pos++
	}
	return out.data
}

// tomlFlags is Flags: what each key and namespace is marked as, apart from the data.
type tomlFlags struct {
	root    map[string]*tomlNode
	pending []tomlPending
}

type tomlNode struct {
	flags, recursive int // recursive flags hold for everything below the key as well
	nested           map[string]*tomlNode
}

type tomlPending struct {
	key  []string
	flag int
}

func newTomlFlags() *tomlFlags { return &tomlFlags{root: map[string]*tomlNode{}} }

func (f *tomlFlags) addPending(key []string, flag int) {
	f.pending = append(f.pending, tomlPending{key, flag})
}

func (f *tomlFlags) finalizePending() {
	for _, e := range f.pending {
		f.set(e.key, e.flag, false)
	}
	f.pending = nil
}

func (f *tomlFlags) unsetAll(key []string) {
	cont := f.root
	for _, k := range key[:len(key)-1] {
		n := cont[k]
		if n == nil {
			return
		}
		cont = n.nested
	}
	delete(cont, key[len(key)-1])
}

func (f *tomlFlags) set(key []string, flag int, recursive bool) {
	cont := f.root
	for i, k := range key {
		n := cont[k]
		if n == nil {
			n = &tomlNode{nested: map[string]*tomlNode{}}
			cont[k] = n
		}
		if i == len(key)-1 {
			if recursive {
				n.recursive |= flag
			} else {
				n.flags |= flag
			}
		}
		cont = n.nested
	}
}

func (f *tomlFlags) is(key []string, flag int) bool {
	if len(key) == 0 {
		return false // document root has no flags
	}
	cont := f.root
	for _, k := range key[:len(key)-1] {
		n := cont[k]
		if n == nil {
			return false
		}
		if n.recursive&flag != 0 {
			return true
		}
		cont = n.nested
	}
	n := cont[key[len(key)-1]]
	return n != nil && (n.flags|n.recursive)&flag != 0
}

// tomlNestOf is NestedDict.get_or_create_nest; false is Python's KeyError.
func tomlNestOf(root map[string]any, key []string, accessLists bool) (map[string]any, bool) {
	cont := root
	for _, k := range key {
		next, ok := cont[k]
		if !ok {
			next = map[string]any{}
			cont[k] = next
		}
		if list, isList := next.([]any); isList && accessLists {
			if len(list) == 0 {
				panic(&tomlError{"list index out of range", false}) // Python's IndexError
			}
			next = list[len(list)-1]
		}
		table, isTable := next.(map[string]any)
		if !isTable {
			return nil, false
		}
		cont = table
	}
	return cont, true
}

// tomlAppendNest is NestedDict.append_nest_to_list; false is Python's KeyError.
func tomlAppendNest(root map[string]any, key []string) bool {
	cont, ok := tomlNestOf(root, key[:len(key)-1], true)
	if !ok {
		return false
	}
	last := key[len(key)-1]
	cur, exists := cont[last]
	if !exists {
		cont[last] = []any{map[string]any{}}
		return true
	}
	list, isList := cur.([]any)
	if !isList {
		return false
	}
	cont[last] = append(list, map[string]any{})
	return true
}

// tomlOutput is Output: the document and the flags of its keys.
type tomlOutput struct {
	data  map[string]any
	flags *tomlFlags
}

func tomlContainer(v any) bool {
	switch v.(type) {
	case map[string]any, []any:
		return true
	}
	return false
}

func tomlJoinKey(a, b []string) []string {
	return append(append(make([]string, 0, len(a)+len(b)), a...), b...)
}

// tomlKeyRepr is the repr of a key tuple: ('a', 'b'), ('a',).
func tomlKeyRepr(key []string) string {
	parts := make([]string, len(key))
	for i, k := range key {
		parts[i] = pytext.ReprStr(k)
	}
	if len(parts) == 1 {
		return "(" + parts[0] + ",)"
	}
	return "(" + strings.Join(parts, ", ") + ")"
}

// skip is skip_chars: pos moved over the characters of the class.
func (p *tomlParser) skip(pos int, class func(rune) bool) int {
	for pos < len(p.src) && class(p.src[pos]) {
		pos++
	}
	return pos
}

// skipUntil is skip_until: the index of expect, after a check that no illegal character lies before it.
func (p *tomlParser) skipUntil(pos int, expect string, illegal func(rune) bool, errorOnEOF bool) int {
	end := p.index(expect, pos)
	if end < 0 {
		end = len(p.src)
		if errorOnEOF {
			panic(p.err("Expected "+pytext.ReprStr(expect), end))
		}
	}
	for i := pos; i < end; i++ {
		if illegal(p.src[i]) {
			panic(p.err("Found invalid character "+pytext.ReprStr(string(p.src[i])), i))
		}
	}
	return end
}

func (p *tomlParser) skipComment(pos int) int {
	if p.at(pos) == '#' {
		return p.skipUntil(pos+1, "\n", tomlIllegal, false)
	}
	return pos
}

func (p *tomlParser) skipCommentsAndArrayWS(pos int) int {
	for {
		before := pos
		pos = p.skip(pos, tomlIsWSNL)
		pos = p.skipComment(pos)
		if pos == before {
			return pos
		}
	}
}

func (p *tomlParser) createDictRule(pos int, out *tomlOutput) (int, []string) {
	pos++ // Skip "["
	pos = p.skip(pos, tomlIsWS)
	pos, key := p.parseKey(pos)

	if out.flags.is(key, tomlExplicitNest) || out.flags.is(key, tomlFrozen) {
		panic(p.err("Cannot declare "+tomlKeyRepr(key)+" twice", pos))
	}
	out.flags.set(key, tomlExplicitNest, false)
	if _, ok := tomlNestOf(out.data, key, true); !ok {
		panic(p.err("Cannot overwrite a value", pos))
	}

	if !p.startsWith("]", pos) {
		panic(p.err("Expected ']' at the end of a table declaration", pos))
	}
	return pos + 1, key
}

func (p *tomlParser) createListRule(pos int, out *tomlOutput) (int, []string) {
	pos += 2 // Skip "[["
	pos = p.skip(pos, tomlIsWS)
	pos, key := p.parseKey(pos)

	if out.flags.is(key, tomlFrozen) {
		panic(p.err("Cannot mutate immutable namespace "+tomlKeyRepr(key), pos))
	}
	// Free the namespace now that it points to another empty list item...
	out.flags.unsetAll(key)
	// ...but this key precisely is still prohibited from table declaration
	out.flags.set(key, tomlExplicitNest, false)
	if !tomlAppendNest(out.data, key) {
		panic(p.err("Cannot overwrite a value", pos))
	}

	if !p.startsWith("]]", pos) {
		panic(p.err("Expected ']]' at the end of an array declaration", pos))
	}
	return pos + 2, key
}

func (p *tomlParser) keyValueRule(pos int, out *tomlOutput, header []string) int {
	pos, key, value := p.parseKeyValuePair(pos)
	keyParent, keyStem := key[:len(key)-1], key[len(key)-1]
	absKeyParent := tomlJoinKey(header, keyParent)

	for i := 1; i < len(key); i++ {
		contKey := tomlJoinKey(header, key[:i])
		// Check that dotted key syntax does not redefine an existing table
		if out.flags.is(contKey, tomlExplicitNest) {
			panic(p.err("Cannot redefine namespace "+tomlKeyRepr(contKey), pos))
		}
		// Containers in the relative path can't be opened with the table syntax or dotted
		// key/value syntax in following table sections.
		out.flags.addPending(contKey, tomlExplicitNest)
	}

	if out.flags.is(absKeyParent, tomlFrozen) {
		panic(p.err("Cannot mutate immutable namespace "+tomlKeyRepr(absKeyParent), pos))
	}

	nest, ok := tomlNestOf(out.data, absKeyParent, true)
	if !ok {
		panic(p.err("Cannot overwrite a value", pos))
	}
	if _, exists := nest[keyStem]; exists {
		panic(p.err("Cannot overwrite a value", pos))
	}
	// Mark inline table and array namespaces recursively immutable
	if tomlContainer(value) {
		out.flags.set(tomlJoinKey(header, key), tomlFrozen, true)
	}
	nest[keyStem] = value
	return pos
}

func (p *tomlParser) parseKeyValuePair(pos int) (int, []string, any) {
	pos, key := p.parseKey(pos)
	if p.at(pos) != '=' {
		panic(p.err("Expected '=' after a key in a key/value pair", pos))
	}
	pos++
	pos = p.skip(pos, tomlIsWS)
	pos, value := p.parseValue(pos)
	return pos, key, value
}

func (p *tomlParser) parseKey(pos int) (int, []string) {
	pos, part := p.parseKeyPart(pos)
	key := []string{part}
	pos = p.skip(pos, tomlIsWS)
	for p.at(pos) == '.' {
		pos++
		pos = p.skip(pos, tomlIsWS)
		pos, part = p.parseKeyPart(pos)
		key = append(key, part)
		if len(key) > tomlMaxKeyParts {
			panic(&tomlError{"TOML key has more than the allowed " + strconv.Itoa(tomlMaxKeyParts) + " parts", false})
		}
		pos = p.skip(pos, tomlIsWS)
	}
	return pos, key
}

func (p *tomlParser) parseKeyPart(pos int) (int, string) {
	switch c := p.at(pos); {
	case tomlIsBare(c):
		start := pos
		pos = p.skip(pos, tomlIsBare)
		return pos, p.text(start, pos)
	case c == '\'':
		return p.parseLiteralStr(pos)
	case c == '"':
		return p.parseBasicStr(pos+1, false)
	}
	panic(p.err("Invalid initial character for a key part", pos))
}

func (p *tomlParser) parseArray(pos int) (int, []any) {
	pos++
	array := []any{}

	pos = p.skipCommentsAndArrayWS(pos)
	if p.startsWith("]", pos) {
		return pos + 1, array
	}
	for {
		var val any
		pos, val = p.parseValue(pos)
		array = append(array, val)
		pos = p.skipCommentsAndArrayWS(pos)

		c := p.at(pos)
		if c == ']' {
			return pos + 1, array
		}
		if c != ',' {
			panic(p.err("Unclosed array", pos))
		}
		pos++

		pos = p.skipCommentsAndArrayWS(pos)
		if p.startsWith("]", pos) {
			return pos + 1, array
		}
	}
}

func (p *tomlParser) parseInlineTable(pos int) (int, map[string]any) {
	pos++
	nested := map[string]any{}
	flags := newTomlFlags()

	pos = p.skip(pos, tomlIsWS)
	if p.startsWith("}", pos) {
		return pos + 1, nested
	}
	for {
		var key []string
		var value any
		pos, key, value = p.parseKeyValuePair(pos)
		keyParent, keyStem := key[:len(key)-1], key[len(key)-1]
		if flags.is(key, tomlFrozen) {
			panic(p.err("Cannot mutate immutable namespace "+tomlKeyRepr(key), pos))
		}
		nest, ok := tomlNestOf(nested, keyParent, false)
		if !ok {
			panic(p.err("Cannot overwrite a value", pos))
		}
		if _, exists := nest[keyStem]; exists {
			panic(p.err("Duplicate inline table key "+pytext.ReprStr(keyStem), pos))
		}
		nest[keyStem] = value
		pos = p.skip(pos, tomlIsWS)
		c := p.at(pos)
		if c == '}' {
			return pos + 1, nested
		}
		if c != ',' {
			panic(p.err("Unclosed inline table", pos))
		}
		if tomlContainer(value) {
			flags.set(key, tomlFrozen, true)
		}
		pos++
		pos = p.skip(pos, tomlIsWS)
	}
}

// tomlEscapes is BASIC_STR_ESCAPE_REPLACEMENTS, by the character after the backslash.
var tomlEscapes = map[rune]string{'b': "\b", 't': "\t", 'n': "\n", 'f': "\f", 'r': "\r", '"': `"`, '\\': `\`}

func (p *tomlParser) parseBasicStrEscape(pos int, multiline bool) (int, string) {
	id := p.at(pos + 1) // the character after the backslash
	pos += 2
	if multiline && (id == ' ' || id == '\t' || id == '\n') {
		// Skip whitespace until next non-whitespace character or end of the doc. Error if
		// non-whitespace is found before newline.
		if id != '\n' {
			pos = p.skip(pos, tomlIsWS)
			c := p.at(pos)
			if c < 0 {
				return pos, ""
			}
			if c != '\n' {
				panic(p.err("Unescaped '\\' in a string", pos))
			}
			pos++
		}
		pos = p.skip(pos, tomlIsWSNL)
		return pos, ""
	}
	switch id {
	case 'u':
		return p.parseHexChar(pos, 4)
	case 'U':
		return p.parseHexChar(pos, 8)
	}
	if s, ok := tomlEscapes[id]; ok {
		return pos, s
	}
	panic(p.err("Unescaped '\\' in a string", pos))
}

func (p *tomlParser) parseHexChar(pos, hexLen int) (int, string) {
	var v int64
	for i := range hexLen {
		d := tomlHexVal(p.at(pos + i))
		if d < 0 {
			panic(p.err("Invalid hex value", pos))
		}
		v = v<<4 | d
	}
	pos += hexLen
	if v > 0xD7FF && v < 0xE000 || v > 0x10FFFF { // not a Unicode scalar value
		panic(p.err("Escaped character is not a Unicode scalar value", pos))
	}
	return pos, string(rune(v))
}

func (p *tomlParser) parseLiteralStr(pos int) (int, string) {
	pos++ // Skip starting apostrophe
	start := pos
	pos = p.skipUntil(pos, "'", tomlIllegal, true)
	return pos + 1, p.text(start, pos) // Skip ending apostrophe
}

func (p *tomlParser) parseMultilineStr(pos int, literal bool) (int, string) {
	pos += 3
	if p.startsWith("\n", pos) {
		pos++
	}

	var delim, result string
	if literal {
		delim = "'"
		end := p.skipUntil(pos, "'''", tomlIllegalMultiline, true)
		result = p.text(pos, end)
		pos = end + 3
	} else {
		delim = `"`
		pos, result = p.parseBasicStr(pos, true)
	}

	// Add at maximum two extra apostrophes/quotes if the end sequence is 4 or 5 chars long
	// instead of just 3.
	if !p.startsWith(delim, pos) {
		return pos, result
	}
	pos++
	if !p.startsWith(delim, pos) {
		return pos, result + delim
	}
	pos++
	return pos, result + delim + delim
}

func (p *tomlParser) parseBasicStr(pos int, multiline bool) (int, string) {
	illegal := tomlIllegal
	if multiline {
		illegal = tomlIllegalMultiline
	}
	var result strings.Builder
	start := pos
	for {
		c := p.at(pos)
		switch {
		case c < 0:
			panic(p.err("Unterminated string", pos))
		case c == '"':
			if !multiline {
				result.WriteString(p.text(start, pos))
				return pos + 1, result.String()
			}
			if p.startsWith(`"""`, pos) {
				result.WriteString(p.text(start, pos))
				return pos + 3, result.String()
			}
			pos++
		case c == '\\':
			result.WriteString(p.text(start, pos))
			var parsed string
			pos, parsed = p.parseBasicStrEscape(pos, multiline)
			result.WriteString(parsed)
			start = pos
		case illegal(c):
			panic(p.err("Illegal character "+pytext.ReprStr(string(c)), pos))
		default:
			pos++
		}
	}
}

func (p *tomlParser) parseValue(pos int) (int, any) {
	switch p.at(pos) {
	// Basic strings
	case '"':
		var s string
		if p.startsWith(`"""`, pos) {
			pos, s = p.parseMultilineStr(pos, false)
		} else {
			pos, s = p.parseBasicStr(pos+1, false)
		}
		return pos, s

	// Literal strings
	case '\'':
		var s string
		if p.startsWith("'''", pos) {
			pos, s = p.parseMultilineStr(pos, true)
		} else {
			pos, s = p.parseLiteralStr(pos)
		}
		return pos, s

	// Booleans
	case 't':
		if p.startsWith("true", pos) {
			return pos + 4, true
		}
	case 'f':
		if p.startsWith("false", pos) {
			return pos + 5, false
		}

	// Arrays: the frames of parse_value and parse_array
	case '[':
		p.descend(2, 2)
		pos, array := p.parseArray(pos)
		p.depth -= 2
		return pos, array

	// Inline tables: the frames of parse_value, parse_inline_table and parse_key_value_pair
	case '{':
		p.descend(3, 3)
		pos, table := p.parseInlineTable(pos)
		p.depth -= 3
		return pos, table
	}

	// Dates and times
	if end, kind := p.matchDatetime(pos); end >= 0 {
		if !p.dateExists(pos) {
			panic(p.err("Invalid date or datetime", pos))
		}
		return end, tomlScalar{kind, p.text(pos, end)}
	}
	if end := p.matchTime(pos); end >= 0 {
		return end, tomlScalar{"local-time", p.text(pos, end)}
	}

	// Integers and "normal" floats. The regex will greedily match any type starting with a
	// decimal char, so needs to be located after handling of dates and times.
	if end, float := p.matchNumber(pos); end >= 0 {
		lit := p.text(pos, end)
		if float {
			return end, tomlScalar{"float", lit}
		}
		// int(lit, 0) refuses a decimal integer of more than 4300 digits (not 0x, 0o, 0b ones)
		if len(lit) > 1 && lit[0] == '0' {
			return end, tomlScalar{"integer", lit}
		}
		digits := len(strings.TrimLeft(lit, "+-")) - strings.Count(lit, "_")
		if digits > tomlMaxDigits {
			panic(&tomlError{"Exceeds the limit (" + strconv.Itoa(tomlMaxDigits) + " digits) for integer string conversion: value has " +
				strconv.Itoa(digits) + " digits; use sys.set_int_max_str_digits() to increase the limit", false})
		}
		return end, tomlScalar{"integer", lit}
	}

	// Special floats
	if s := p.text(pos, pos+3); s == "inf" || s == "nan" {
		return pos + 3, tomlScalar{"float", s}
	}
	if s := p.text(pos, pos+4); s == "-inf" || s == "+inf" || s == "-nan" || s == "+nan" {
		return pos + 4, tomlScalar{"float", s}
	}

	panic(p.err("Invalid value", pos))
}

// The matchers are _re.py's regular expressions by hand: each returns the end of the match at pos,
// or -1. Every optional part of those expressions is last in its group, so none of them backtracks.

// hour is ([01][0-9]|2[0-3]) at pos.
func (p *tomlParser) hour(pos int) bool {
	a, b := p.at(pos), p.at(pos+1)
	return (a == '0' || a == '1') && tomlDigit(b) || a == '2' && b >= '0' && b <= '3'
}

// minSec is ([0-5][0-9]) at pos.
func (p *tomlParser) minSec(pos int) bool {
	return p.at(pos) >= '0' && p.at(pos) <= '5' && tomlDigit(p.at(pos+1))
}

// matchTime is RE_LOCALTIME: hh:mm:ss with an optional fraction of any length.
func (p *tomlParser) matchTime(pos int) int {
	if !p.hour(pos) || p.at(pos+2) != ':' || !p.minSec(pos+3) || p.at(pos+5) != ':' || !p.minSec(pos+6) {
		return -1
	}
	end := pos + 8
	if p.at(end) == '.' && tomlDigit(p.at(end+1)) {
		end = p.skip(end+2, tomlDigit)
	}
	return end
}

// matchDate is the date of RE_DATETIME: yyyy-mm-dd.
func (p *tomlParser) matchDate(pos int) int {
	for i := range 4 {
		if !tomlDigit(p.at(pos + i)) {
			return -1
		}
	}
	m1, m2, d1, d2 := p.at(pos+5), p.at(pos+6), p.at(pos+8), p.at(pos+9)
	if p.at(pos+4) != '-' || !(m1 == '0' && m2 >= '1' && m2 <= '9' || m1 == '1' && m2 >= '0' && m2 <= '2') ||
		p.at(pos+7) != '-' ||
		!(d1 == '0' && d2 >= '1' && d2 <= '9' || (d1 == '1' || d1 == '2') && tomlDigit(d2) || d1 == '3' && (d2 == '0' || d2 == '1')) {
		return -1
	}
	return pos + 10
}

// matchDatetime is RE_DATETIME: a date, then optionally a time and, after it, an offset. The
// kind is that of the longest part that matched.
func (p *tomlParser) matchDatetime(pos int) (int, string) {
	end := p.matchDate(pos)
	if end < 0 {
		return -1, ""
	}
	kind := "local-date"
	if sep := p.at(end); sep == 'T' || sep == 't' || sep == ' ' {
		if t := p.matchTime(end + 1); t >= 0 {
			end, kind = t, "local-datetime"
			switch c := p.at(end); {
			case c == 'Z' || c == 'z':
				end, kind = end+1, "offset-datetime"
			case (c == '+' || c == '-') && p.hour(end+1) && p.at(end+3) == ':' && p.minSec(end+4):
				end, kind = end+6, "offset-datetime"
			}
		}
	}
	return end, kind
}

// dateExists is datetime.date(year, month, day) not raising ValueError for the date that
// matchDate matched at pos.
func (p *tomlParser) dateExists(pos int) bool {
	num := func(from, n int) int {
		v := 0
		for i := from; i < from+n; i++ {
			v = v*10 + int(p.src[i]-'0')
		}
		return v
	}
	year, month, day := num(pos, 4), num(pos+5, 2), num(pos+8, 2)
	days := [...]int{31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31}[month-1]
	if month == 2 && (year%4 == 0 && year%100 != 0 || year%400 == 0) {
		days = 29
	}
	return year > 0 && day <= days
}

// matchNumber is RE_NUMBER: a 0x, 0o or 0b integer, or a decimal one with an optional fractional
// and exponent part (float then). Digits may be separated by single underscores.
func (p *tomlParser) matchNumber(pos int) (end int, float bool) {
	if p.at(pos) == '0' {
		var digit func(rune) bool
		switch p.at(pos + 1) {
		case 'x':
			digit = func(c rune) bool { return tomlHexVal(c) >= 0 }
		case 'b':
			digit = func(c rune) bool { return c == '0' || c == '1' }
		case 'o':
			digit = func(c rune) bool { return c >= '0' && c <= '7' }
		}
		if digit != nil && digit(p.at(pos+2)) {
			return p.digits(pos+3, digit), false
		}
	}
	end = pos
	if c := p.at(end); c == '+' || c == '-' {
		end++
	}
	switch c := p.at(end); {
	case c == '0':
		end++
	case c >= '1' && c <= '9':
		end = p.digits(end+1, tomlDigit)
	default:
		return -1, false
	}
	if p.at(end) == '.' && tomlDigit(p.at(end+1)) {
		end, float = p.digits(end+2, tomlDigit), true
	}
	if c := p.at(end); c == 'e' || c == 'E' {
		exp := end + 1
		if c := p.at(exp); c == '+' || c == '-' {
			exp++
		}
		if tomlDigit(p.at(exp)) {
			end, float = p.digits(exp+1, tomlDigit), true
		}
	}
	return end, float
}

// digits is (?:_?d)* at pos: more digits, each with an underscore before it if need be.
func (p *tomlParser) digits(pos int, digit func(rune) bool) int {
	for {
		next := pos
		if p.at(next) == '_' {
			next++
		}
		if !digit(p.at(next)) {
			return pos
		}
		pos = next + 1
	}
}
