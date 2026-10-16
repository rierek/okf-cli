package yamlpatch_test

import (
	"strings"
	"testing"

	"go.yaml.in/yaml/v3"

	"nas/volume1/data/git/okf-tools/go/internal/frontmatter"
	. "nas/volume1/data/git/okf-tools/go/internal/yamlpatch"
)

// The quoting rule for a new string scalar: plain when the plain form reads back as the same string,
// single-quoted for any other value, double-quoted only for a line break or a character that single
// quotes cannot carry.

func TestQuotingRuleExactText(t *testing.T) {
	for _, c := range []struct{ in, want string }{
		// plain
		{"a", "a"}, {"a b", "a b"}, {"it's fine", "it's fine"}, {"-a", "-a"}, {"a#b", "a#b"}, {"a:b", "a:b"},
		{"https://example.org/pasta", "https://example.org/pasta"}, {"human:golden", "human:golden"},
		{"é", "é"}, {"日本語 😀", "日本語 😀"}, {"yes", "yes"}, {"12:30", "12:30"}, {"a, b", "a, b"},
		{"a ---", "a ---"}, {"a\\b", "a\\b"}, {"a\"b", "a\"b"}, {":a", ":a"}, {"---", "---"}, {"--- a", "--- a"}, {"...", "..."},
		// a tab is double-quoted: yaml.v3 reads it inside a plain scalar, ruamel (the Python CLI) cannot
		{"a\tb", "\"a\\tb\""}, {"\ta", "\"\\ta\""}, {"a\t", "\"a\\t\""}, {"\t", "\"\\t\""}, {"a \tb", "\"a \\tb\""},
		{"tab\tinside [A](https://a.org)", "\"tab\\tinside [A](https://a.org)\""}, {"it's\ta", "\"it's\\ta\""}, {"a\t: b", "\"a\\t: b\""},
		// ruamel (the Python CLI) gives these plain strings another type, or fails on them, where yaml.v3 reads a string
		{"=", "'='"}, {"2026-02-30", "'2026-02-30'"}, {"2026-13-45", "'2026-13-45'"}, {"1e400", "'1e400'"}, {"+_", "'+_'"}, {"-_", "'-_'"}, {"._", "'._'"},
		{"2026-01-01T12:00:00", "'2026-01-01T12:00:00'"}, {"2026-01-01t12:00:00", "'2026-01-01t12:00:00'"}, {"2026-01-01T12:00:00+01", "'2026-01-01T12:00:00+01'"},
		{"2026-01-01T12:00:00.123", "'2026-01-01T12:00:00.123'"}, {"2026-01-01T12:00:00.Z", "'2026-01-01T12:00:00.Z'"}, {"2026-01-01T1:00:00", "'2026-01-01T1:00:00'"},
		{"0_", "'0_'"}, {"1_0", "'1_0'"}, {"0b101", "'0b101'"}, {"017", "'017'"}, {"-.INF", "'-.INF'"}, {"5.", "'5.'"}, {"1e-3", "'1e-3'"}, {"!", "'!'"}, {"&", "'&'"}, {"*", "'*'"},
		// ... and these look like a number or a date to a human but are strings to both readers
		{"_", "_"}, {"__", "__"}, {"inf", "inf"}, {"NaN", "NaN"}, {"0b2", "0b2"}, {"1e", "1e"}, {"0x", "0x"}, {"1.2.3", "1.2.3"}, {"2026-01-01 junk", "2026-01-01 junk"},
		// yaml.v3 reads these as timestamps, ruamel as strings: they are quoted all the same
		{"2026-1-1", "'2026-1-1'"}, {"2026-01-1", "'2026-01-1'"}, {"2026-1-01", "'2026-1-01'"},
		// single quotes: the plain form reads back as something else, or not at all
		{"", "''"}, {" ", "' '"}, {" a", "' a'"}, {"a ", "'a '"}, {"a: b", "'a: b'"}, {"a:", "'a:'"},
		{"- a", "'- a'"}, {"-", "'-'"}, {"?", "'?'"}, {"? a", "'? a'"}, {"a #b", "'a #b'"}, {"#a", "'#a'"}, {"&a", "'&a'"}, {"*a", "'*a'"},
		{"!a", "'!a'"}, {"|", "'|'"}, {">", "'>'"}, {"'a'", "'''a'''"}, {"\"a\"", "'\"a\"'"}, {"'", "''''"}, {"\"", "'\"'"},
		{"%a", "'%a'"}, {"@a", "'@a'"}, {"`a", "'`a'"}, {"[a]", "'[a]'"}, {"{a}", "'{a}'"}, {"[", "'['"}, {"{", "'{'"},
		{"true", "'true'"}, {"False", "'False'"}, {"null", "'null'"}, {"~", "'~'"}, {"1", "'1'"}, {"-1", "'-1'"}, {"+1", "'+1'"},
		{"1.5", "'1.5'"}, {".5", "'.5'"}, {"1e3", "'1e3'"}, {"0x1F", "'0x1F'"}, {"0o17", "'0o17'"}, {"1_000", "'1_000'"},
		{"2026-01-01", "'2026-01-01'"}, {"2026-01-29T00:00:00+00:00", "'2026-01-29T00:00:00+00:00'"}, {"<<", "'<<'"},
		{"[Pasta basics](https://example.org/pasta)", "'[Pasta basics](https://example.org/pasta)'"}, {"it's: x", "'it''s: x'"},
		{"---:", "'---:'"},
		// double quotes: a line break or a character single quotes cannot carry
		{"a\nb", "\"a\\nb\""}, {"a\r\nb", "\"a\\r\\nb\""}, {"\n", "\"\\n\""}, {"a\x01b", "\"a\\x01b\""}, {"\x7f", "\"\\x7F\""},
		{"a\u0085b", "\"a\\Nb\""}, {"a\u2028b", "\"a\\Lb\""}, {"a\u2029b", "\"a\\Pb\""}, {"\ufeffa", "\"\\uFEFFa\""},
		{"a\x00b", "\"a\\x00b\""}, {"\"a\nb\\", "\"\\\"a\\nb\\\\\""},
	} {
		got, err := Apply(f("type: X\n"), NewKey("k", Str(c.in)))
		if err != nil {
			t.Errorf("%q: %v", c.in, err)
			continue
		}
		if want := f("type: X\nk: " + c.want + "\n"); got != want {
			t.Errorf("%q written as\n got %q\nwant %q", c.in, got, want)
		}
	}
}

// Whatever the string, the written text reads back as that string, in every place a string is written.
func TestQuotingRoundTrip(t *testing.T) {
	values := []string{"", " ", "a", "a b", " a", "a ", "a: b", "a:", "a #b", "a#b", "#a", "- a", "-a", "?", "&a", "*a", "!a", "|", ">", "'", "\"", "'a'",
		"%a", "@a", "`a", "[a]", "[", "]", "{a}", "}", "a, b", "a,b", "true", "yes", "no", "on", "y", "null", "~", "0", "-1", "1.5", ".inf", ".nan", "0x1F",
		"2026-01-01", "2026-10-12T19:00:00Z", "12:30", "<<", "=", "é", "日本語", "😀", "a\tb", "\t", "a\nb", "\n", "a\r\nb", "\r", "a\x00b", "a\x01b",
		"\x7f", "a\u0085b", "a\u2028b", "a\u2029b", "\ufeffa", "a\\b", "a\"b", "it's", "---", "--- a", "...", "a ---", "key: value # c", "a\\nb",
		"=", "2026-02-30", "1e400", "+_", "._", "2026-01-01T12:00:00", "tab\tinside [A](https://a.org)",
		strings.Repeat("long text ", 300), "a" + strings.Repeat(" b", 500)}
	check := func(t *testing.T, what, v string, n *yaml.Node) {
		t.Helper()
		if n == nil || n.Kind != yaml.ScalarNode || n.ShortTag() != "!!str" || n.Value != v {
			t.Errorf("%s of %q reads back as %v", what, v, n)
		}
	}
	for _, v := range values {
		in := f("type: X\nflow: []\nblock:\n  - first\nname: old\n")
		out, err := Apply(in, NewKey("k", Str(v)), AppendItem("flow", Str(v)), AppendItem("block", Str(v)), SetValue("name", Str(v)),
			NewKey("m", Map("x", Str(v))), NewKey("l", List(Str(v), Map("y", Str(v)))))
		if err != nil {
			t.Errorf("%q: %v", v, err)
			continue
		}
		doc := frontmatter.Read(out)
		if doc.Err != "" {
			t.Errorf("%q: the output does not read: %s", v, doc.Err)
			continue
		}
		lookup := func(key string) *yaml.Node { return frontmatter.Lookup(doc.Root, key) }
		check(t, "a new value", v, lookup("k"))
		check(t, "a set value", v, lookup("name"))
		check(t, "a flow list item", v, lookup("flow").Content[0])
		check(t, "a block list item", v, lookup("block").Content[1])
		check(t, "a mapping value", v, lookup("m").Content[1])
		check(t, "a list item", v, lookup("l").Content[0])
		check(t, "a mapping value in a list item", v, lookup("l").Content[1].Content[1])
		if rename, err := Apply(in, RenameItem("block", 0, v)); err != nil {
			t.Errorf("rename to %q: %v", v, err)
		} else {
			check(t, "a renamed item", v, frontmatter.Lookup(frontmatter.Read(rename).Root, "block").Content[0])
		}
	}
	// the same strings as the keys of a new mapping
	for _, v := range values {
		if v == "" {
			continue
		}
		out, err := Apply(f("a: 1\n"), NewKey("m", Map(v, Str("x"))))
		if len(v) > 1024 { // a key of a block mapping holds at most 1024 characters: refused, never written
			if err == nil {
				t.Errorf("a key of %d characters was written", len(v))
			}
			continue
		}
		if err != nil {
			t.Errorf("key %q: %v", v, err)
			continue
		}
		doc := frontmatter.Read(out)
		if doc.Err != "" {
			t.Errorf("key %q: the output does not read: %s", v, doc.Err)
			continue
		}
		if k := frontmatter.Lookup(doc.Root, "m").Content[0]; k.Value != v || k.ShortTag() != "!!str" {
			t.Errorf("key %q reads back as %q (%s)", v, k.Value, k.ShortTag())
		}
	}
}

// A typed plain scalar is written as given and keeps its type.
func TestPlainKeepsItsType(t *testing.T) {
	out, err := Apply(f("a: 1\n"), NewKey("at", Plain("2026-10-12T19:00:00Z")), NewKey("n", Plain("42")), NewKey("b", Plain("true")))
	if err != nil {
		t.Fatal(err)
	}
	if want := f("a: 1\nat: 2026-10-12T19:00:00Z\nn: 42\nb: true\n"); out != want {
		t.Errorf("got %q want %q", out, want)
	}
	doc := frontmatter.Read(out)
	for key, tag := range map[string]string{"at": "!!timestamp", "n": "!!int", "b": "!!bool"} {
		if got := frontmatter.Tag(frontmatter.Lookup(doc.Root, key)); got != tag {
			t.Errorf("%s has the type %s, want %s", key, got, tag)
		}
	}
}
