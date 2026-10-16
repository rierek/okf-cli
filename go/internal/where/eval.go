package where

import (
	"cmp"
	"fmt"
	"slices"
	"strconv"
	"strings"
	"time"
	"unicode"

	"go.yaml.in/yaml/v3"

	"nas/volume1/data/git/okf-tools/go/internal/frontmatter"
	"nas/volume1/data/git/okf-tools/go/internal/spec"
)

// isInstantField names the timestamp-valued OKF v0.2 keys. They compare as instants, never as text.
func isInstantField(field string) bool {
	switch field {
	case "generated.at", "verified.at", "stale_after", "usage_window.from", "usage_window.to",
		"sources.last_modified", "sources.usage_window.from", "sources.usage_window.to":
		return true
	}
	return false
}

// leaves is what a dotted key reaches in the frontmatter: a mapping is entered by key, a list
// through each of its elements, so `verified.by` reads a bare mapping and a list alike. A list at
// the end of the path gives its items, a mapping there nothing.
func leaves(root *yaml.Node, field string) []*yaml.Node {
	var out []*yaml.Node
	walk(root, strings.Split(field, "."), &out)
	return out
}

func walk(value *yaml.Node, parts []string, out *[]*yaml.Node) {
	value = frontmatter.Deref(value)
	switch {
	case frontmatter.IsSeq(value):
		for _, item := range frontmatter.Elems(value) {
			walk(item, parts, out)
		}
	case len(parts) == 0:
		if !frontmatter.IsMap(value) {
			*out = append(*out, value)
		}
	case frontmatter.IsMap(value):
		if next := frontmatter.Lookup(value, parts[0]); next != nil {
			walk(next, parts[1:], out)
		}
	}
}

func scalarTexts(nodes []*yaml.Node) []string {
	texts := make([]string, len(nodes))
	for i, n := range nodes {
		texts[i] = frontmatter.ScalarText(n)
	}
	return texts
}

func boolText(b bool) string {
	if b {
		return "true"
	}
	return "false"
}

// fieldValues is the list of values a concept holds for a field. load returns the frontmatter
// mapping (nil without one) and reads the file only when called; now is the one instant of the
// call. A name that is no registered field is a frontmatter key, dotted for nested mappings and
// through lists of mappings.
func fieldValues(field, path string, load func() *yaml.Node, now time.Time) []string {
	switch field {
	case "path":
		return []string{path}
	case "archived":
		return []string{boolText(strings.HasPrefix(path, archivePrefix))}
	case "tag":
		return frontmatter.Tags(load())
	case "tier":
		return []string{spec.TrustTier(load())}
	case "stale":
		return []string{boolText(spec.IsStale(load(), now))}
	case "status":
		if texts := scalarTexts(leaves(load(), "status")); len(texts) > 0 {
			return texts
		}
		return []string{"stable"}
	}
	return scalarTexts(leaves(load(), field))
}

// decimalDigit is the value of a character of category Nd (what Python's \d matches and float()
// accepts): every Nd range of the Unicode tables is a run of whole sets of ten digits from zero.
func decimalDigit(r rune) (int, bool) {
	if r >= '0' && r <= '9' {
		return int(r - '0'), true
	}
	if r < 0x80 {
		return 0, false
	}
	for _, rg := range unicode.Nd.R16 {
		if r >= rune(rg.Lo) && r <= rune(rg.Hi) {
			return int(r-rune(rg.Lo)) % 10, true
		}
	}
	for _, rg := range unicode.Nd.R32 {
		if r >= rune(rg.Lo) && r <= rune(rg.Hi) {
			return int(r-rune(rg.Lo)) % 10, true
		}
	}
	return 0, false
}

// number is float(s) for a string that matches Python `-?\d+(\.\d+)?$`: no exponent, no leading
// `+`, a final newline allowed (`$` matches before it). Such values order numerically, any other
// value orders as text.
func number(s string) (float64, bool) {
	s = strings.TrimSuffix(s, "\n")
	var ascii strings.Builder
	before, after, dot := 0, 0, false
	for i, r := range s {
		d, isDigit := decimalDigit(r)
		switch {
		case isDigit:
			ascii.WriteByte(byte('0' + d))
			if dot {
				after++
			} else {
				before++
			}
		case r == '-' && i == 0:
			ascii.WriteByte('-')
		case r == '.' && !dot && before > 0:
			dot = true
			ascii.WriteByte('.')
		default:
			return 0, false
		}
	}
	if before == 0 || (dot && after == 0) {
		return 0, false
	}
	f, _ := strconv.ParseFloat(ascii.String(), 64) // out of range gives ±Inf, as float() does
	return f, true
}

// holds applies a comparison operator to the three-way comparison result c of value and wanted.
func holds(op string, c int) bool {
	switch op {
	case "=":
		return c == 0
	case "<":
		return c < 0
	case "<=":
		return c <= 0
	case ">":
		return c > 0
	case ">=":
		return c >= 0
	}
	panic("where: no ordering for operator " + op)
}

// compareText is the comparison of one text value with the wanted text: `=` exact, `~` contains,
// ordering numeric when both sides are numbers and by character order otherwise.
func compareText(op, value, wanted string) bool {
	switch op {
	case "=":
		return value == wanted
	case "~":
		return strings.Contains(value, wanted)
	}
	if a, ok := number(value); ok {
		if b, ok := number(wanted); ok {
			return holds(op, cmp.Compare(a, b))
		}
	}
	return holds(op, strings.Compare(value, wanted))
}

// holdsInstants is the comparison of a timestamp field: the stored values that read as instants
// against the literals, which compile_where has checked to be instants. A stored value that is no
// instant holds nothing.
func holdsInstants(field, op string, literals []string, member bool, load func() *yaml.Node) bool {
	var values []time.Time
	for _, leaf := range leaves(load(), field) {
		if t, ok := spec.ParseOkfDatetime(leaf); ok {
			values = append(values, t)
		}
	}
	wanted := make([]time.Time, len(literals))
	for i, literal := range literals {
		wanted[i], _ = spec.ParseOkfDatetimeText(literal)
	}
	switch {
	case member:
		return slices.ContainsFunc(values, func(v time.Time) bool { return slices.ContainsFunc(wanted, v.Equal) })
	case op == "!=":
		return !slices.ContainsFunc(values, wanted[0].Equal) // an absent key satisfies !=
	}
	return slices.ContainsFunc(values, func(v time.Time) bool { return holds(op, v.Compare(wanted[0])) })
}

// holdsLeaf is the predicate of one comparison (`member` for `in`, whose op is not used).
func holdsLeaf(field, op string, literals []string, member bool, path string, load func() *yaml.Node, now time.Time) bool {
	if isInstantField(field) {
		return holdsInstants(field, op, literals, member, load)
	}
	values := fieldValues(field, path, load, now)
	switch {
	case member:
		return slices.ContainsFunc(values, func(v string) bool { return slices.Contains(literals, v) })
	case op == "!=":
		return !slices.Contains(values, literals[0]) // an absent key satisfies !=
	}
	return slices.ContainsFunc(values, func(v string) bool { return compareText(op, v, literals[0]) })
}

// evaluate is the predicate of an expression for one concept. Operands of and/or are evaluated
// left to right and only as far as the result needs, so a concept file is read only when a field
// beyond the path is reached.
func evaluate(n node, path string, load func() *yaml.Node, now time.Time) bool {
	switch n := n.(type) {
	case andNode:
		return evaluate(n.left, path, load, now) && evaluate(n.right, path, load, now)
	case orNode:
		return evaluate(n.left, path, load, now) || evaluate(n.right, path, load, now)
	case notNode:
		return !evaluate(n.operand, path, load, now)
	case compareNode:
		return holdsLeaf(n.field, n.op, []string{n.value}, false, path, load, now)
	case inNode:
		return holdsLeaf(n.field, "in", n.values, true, path, load, now)
	}
	panic(fmt.Sprintf("where: unknown expression node %T", n))
}
