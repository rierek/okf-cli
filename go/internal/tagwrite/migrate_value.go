package tagwrite

import (
	"math/big"
	"regexp"
	"strconv"
	"strings"

	"go.yaml.in/yaml/v3"

	"nas/volume1/data/git/okf-tools/go/internal/frontmatter"
	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

// migrateWholeNumber is the text of an integer that go-yaml reads as a float for its size.
var migrateWholeNumber = regexp.MustCompile(`^[-+]?[0-9][0-9_]*$`)

// migrateIsStr is Python isinstance(value, str) for the value of a node: a scalar the loader reads
// as a string. A scalar with an explicit tag is no str there (ruamel keeps a TaggedScalar).
func migrateIsStr(n *yaml.Node) bool {
	n = frontmatter.Deref(n)
	return frontmatter.IsString(n) && n.Style&yaml.TaggedStyle == 0
}

// migrateRepr is Python repr() of the value a node loads as: None, True, False, int, float, str,
// list and dict print as in Python. Any other scalar (a timestamp, binary data, an explicit tag)
// is printed as the repr of its text, not as the Python object.
func migrateRepr(n *yaml.Node) string {
	n = frontmatter.Deref(n)
	switch n.Kind {
	case yaml.SequenceNode:
		var parts []string
		for _, item := range frontmatter.Elems(n) {
			parts = append(parts, migrateRepr(item))
		}
		return "[" + strings.Join(parts, ", ") + "]"
	case yaml.MappingNode:
		var parts []string
		for _, p := range frontmatter.Items(n) {
			parts = append(parts, migrateRepr(p.Key)+": "+migrateRepr(p.Value))
		}
		return "{" + strings.Join(parts, ", ") + "}"
	}
	if n.Style&yaml.TaggedStyle == 0 {
		switch frontmatter.Tag(n) {
		case "!!null":
			return "None"
		case "!!bool":
			if strings.EqualFold(n.Value, "true") {
				return "True"
			}
			return "False"
		case "!!int":
			return migrateInt(n.Value)
		case "!!float":
			if migrateWholeNumber.MatchString(n.Value) {
				return migrateInt(n.Value)
			}
			return migrateFloat(n.Value)
		}
	}
	return pytext.ReprStr(n.Value)
}

// migrateInt is Python repr() of an int written as YAML 1.2 writes it: decimal, 0x, 0o or 0b, with
// an optional sign and underscores.
func migrateInt(s string) string {
	digits := strings.ReplaceAll(s, "_", "")
	negative := strings.HasPrefix(digits, "-")
	digits = strings.TrimLeft(digits, "+-")
	base := 10
	if len(digits) > 2 && digits[0] == '0' {
		switch digits[1] {
		case 'b':
			base = 2
		case 'o':
			base = 8
		case 'x':
			base = 16
		}
		if base != 10 {
			digits = digits[2:]
		}
	}
	n, ok := new(big.Int).SetString(digits, base)
	if !ok {
		return pytext.ReprStr(s)
	}
	if negative {
		n.Neg(n)
	}
	return n.String()
}

// migrateFloat is Python repr() of a float written as YAML writes it, `.inf` and `.nan` included.
func migrateFloat(s string) string {
	text := strings.ReplaceAll(s, "_", "")
	switch strings.ToLower(strings.TrimLeft(text, "+-")) {
	case ".inf":
		if strings.HasPrefix(text, "-") {
			return "-inf"
		}
		return "inf"
	case ".nan":
		return "nan"
	}
	f, _ := strconv.ParseFloat(text, 64) // out of range gives the infinity Python reads
	return pytext.ReprFloat(f)
}

// migrateTruthy is Python bool() of the value a node loads as; an absent node (None) is false.
func migrateTruthy(n *yaml.Node) bool {
	n = frontmatter.Deref(n)
	switch {
	case n == nil:
		return false
	case n.Kind != yaml.ScalarNode:
		return len(n.Content) > 0
	case n.Style&yaml.TaggedStyle != 0:
		return true
	}
	switch frontmatter.Tag(n) {
	case "!!null":
		return false
	case "!!bool":
		return strings.EqualFold(n.Value, "true")
	case "!!int", "!!float":
		return !migrateZero(n.Value)
	case "!!str", "!!binary":
		return n.Value != ""
	}
	return true
}

// migrateZero reports whether the text of a YAML int or float is zero; `.inf` and `.nan` are not.
func migrateZero(s string) bool {
	s = strings.ToLower(strings.TrimLeft(strings.ReplaceAll(s, "_", ""), "+-"))
	switch {
	case strings.HasPrefix(s, ".inf"), strings.HasPrefix(s, ".nan"):
		return false
	case strings.HasPrefix(s, "0x"), strings.HasPrefix(s, "0o"), strings.HasPrefix(s, "0b"):
		s = s[2:]
	default:
		s, _, _ = strings.Cut(s, "e")
	}
	return strings.Trim(s, "0.") == ""
}
