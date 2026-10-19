package yamlpatch

import (
	"fmt"
	"strings"

	"go.yaml.in/yaml/v3"

	"nas/volume1/data/git/okf-tools/go/internal/frontmatter"
)

// scalarCtx is where a new scalar is written; plain scalars read differently in each.
type scalarCtx int

const (
	ctxValue scalarCtx = iota // the value of a block mapping key: `k: s`
	ctxItem                   // an item of a block list: `  - s`
	ctxFlow                   // an item of a flow list: `[s]`
	ctxKey                    // a mapping key: `s: x`
)

// The quoting rule for a new string scalar (one rule for every edit). Two readers must read the written text
// back as exactly this string: yaml.v3 (the self-check) and ruamel (the Python CLI), which do not agree on
// every plain scalar. A parser decides for yaml.v3, ruamel's own resolver table (ruamel.go) for ruamel:
//
//  1. plain, when the plain form reads back as exactly this string through yaml.v3 (`true`, `2026-01-29`,
//     `[x]`, `a: b`, `a #b`, the empty string and the like fail), ruamel's table gives it no other type
//     (`=`, `2026-02-30`, `1e400`, `+_`, a time without a zone and the like fail), and it holds no tab,
//     which ruamel cannot read inside a plain scalar;
//  2. else single-quoted, as ruamel writes it (`'it''s'`);
//  3. else double-quoted, only for a string with a line break, a tab (ruamel writes it so) or a character
//     that single quotes cannot carry (a control character, NEL, LS, PS, ...).

// quoteScalar writes s by the quoting rule for the context.
func quoteScalar(s string, ctx scalarCtx) string {
	switch {
	case plainOK(s, ctx):
		return s
	case singleOK(s):
		return "'" + strings.ReplaceAll(s, "'", "''") + "'"
	}
	return dquote(s)
}

// plainOK reports whether s, written plain in the context, reads back as the same plain string through
// yaml.v3 and as a string through ruamel.
func plainOK(s string, ctx scalarCtx) bool {
	if s == "" || !singleOK(s) || s != trimSpaces(s) || resolvesToOtherType(s) {
		return false
	}
	probe := map[scalarCtx]string{
		ctxValue: "k: " + s,
		ctxItem:  "k:\n  - " + s,
		ctxFlow:  "k: [" + s + "]",
		ctxKey:   s + ": x",
	}[ctx]
	doc := frontmatter.Read("---\n" + probe + "\n---\n")
	if doc.Err != "" || doc.Root == nil || len(doc.Root.Content) != 2 {
		return false
	}
	key, val := doc.Root.Content[0], doc.Root.Content[1]
	var scalar *yaml.Node
	switch ctx {
	case ctxKey:
		scalar = key
	case ctxValue:
		scalar = val
	default:
		if val.Kind != yaml.SequenceNode || len(val.Content) != 1 {
			return false
		}
		scalar = val.Content[0]
	}
	return scalar.Kind == yaml.ScalarNode && scalar.Anchor == "" &&
		scalar.ShortTag() == "!!str" && scalar.Value == s
}

// singleOK reports whether single quotes, and a plain scalar, can carry s: every character printable, none
// a line break, no tab. The tab is the one printable character kept out: yaml.v3 reads it inside a plain
// scalar, but PyYAML-family readers (ruamel, the Python CLI) end the scalar at it and fail with "found
// character '\t' that cannot start any token". Their own writer puts such a string in double quotes, and so
// does this one.
func singleOK(s string) bool {
	for _, r := range s {
		if !printableRune(r) {
			return false
		}
	}
	return true
}

// printableLine reports whether s is one line of printable characters.
func printableLine(s string) bool { return singleOK(s) }

// printableRune is YAML's printable set minus the tab (see singleOK), minus NEL, LS and PS, which YAML 1.1
// readers (yaml.v3) take for line breaks, and minus the byte order mark.
func printableRune(r rune) bool {
	switch {
	case r >= 0x20 && r <= 0x7e:
		return true
	case r >= 0xa0 && r <= 0xd7ff:
		return r != 0x2028 && r != 0x2029
	case r >= 0xe000 && r <= 0xfffd:
		return r != 0xfeff
	case r >= 0x10000 && r <= 0x10ffff:
		return true
	}
	return false
}

func trimSpaces(s string) string { return strings.Trim(s, " \t") }

// dquote writes s double-quoted, escaping what a double-quoted scalar must not carry raw.
func dquote(s string) string {
	var b strings.Builder
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
		case r == 0x85:
			b.WriteString(`\N`)
		case r == 0x2028:
			b.WriteString(`\L`)
		case r == 0x2029:
			b.WriteString(`\P`)
		case printableRune(r):
			b.WriteRune(r)
		case r <= 0xff:
			fmt.Fprintf(&b, `\x%02X`, r)
		default:
			fmt.Fprintf(&b, `\u%04X`, r)
		}
	}
	b.WriteByte('"')
	return b.String()
}
