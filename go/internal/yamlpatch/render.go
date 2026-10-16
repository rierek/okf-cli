package yamlpatch

import (
	"strings"
)

// New values are written in block style as the Python CLI writes them (ruamel with mapping indent 2,
// sequence indent 4, offset 2): two spaces per mapping level and list items as `  - ` under their key.

func pad(n int) string { return strings.Repeat(" ", n) }

// scalarText is the text of a scalar value in the context.
func scalarText(v Value, ctx scalarCtx) string {
	if x, ok := v.(plainValue); ok {
		return x.s
	}
	return quoteScalar(v.(strValue).s, ctx)
}

// pairLines renders `key: value` at the indentation as lines without line endings.
func pairLines(indent int, key string, v Value) []string {
	k := pad(indent) + quoteScalar(key, ctxKey)
	switch x := v.(type) {
	case mapValue:
		if len(x.keys) == 0 {
			return []string{k + ": {}"}
		}
		out := []string{k + ":"}
		for i, ck := range x.keys {
			out = append(out, pairLines(indent+2, ck, x.vals[i])...)
		}
		return out
	case listValue:
		if len(x.items) == 0 {
			return []string{k + ": []"}
		}
		out := []string{k + ":"}
		for _, item := range x.items {
			out = append(out, itemLines(indent+2, item)...)
		}
		return out
	}
	return []string{k + ": " + scalarText(v, ctxValue)}
}

// itemLines renders one list item whose dash stands at the column `indent`.
func itemLines(indent int, v Value) []string {
	body := itemBodyLines(v)
	out := make([]string, len(body))
	for i, l := range body {
		if i == 0 {
			out[i] = pad(indent) + "- " + l
		} else {
			out[i] = pad(indent+2) + l
		}
	}
	return out
}

// itemBodyLines is what follows the dash of a block list item: one line for a scalar, the pairs of a
// mapping with the later ones relative to the first.
func itemBodyLines(v Value) []string {
	m, ok := v.(mapValue)
	if !ok {
		return []string{scalarText(v, ctxItem)}
	}
	if len(m.keys) == 0 {
		return []string{"{}"}
	}
	var out []string
	for i, k := range m.keys {
		out = append(out, pairLines(0, k, m.vals[i])...)
	}
	return out
}

// flowItemText is a list item written inside the brackets of a flow list: a scalar, or a mapping
// of scalars as `{k: v, ...}`.
func flowItemText(v Value) (string, bool) {
	m, ok := v.(mapValue)
	if !ok {
		return scalarText(v, ctxFlow), true
	}
	parts := make([]string, len(m.keys))
	for i, k := range m.keys {
		switch m.vals[i].(type) {
		case strValue, plainValue:
		default:
			return "", false
		}
		parts[i] = quoteScalar(k, ctxKey) + ": " + scalarText(m.vals[i], ctxFlow)
	}
	return "{" + strings.Join(parts, ", ") + "}", true
}
