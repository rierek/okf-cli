package yamlpatch_test

import (
	"strings"
	"testing"

	. "nas/volume1/data/git/okf-tools/go/internal/yamlpatch"
)

// Exact-output tests: every edit of the edit set on block-style input, and on flow-style input for the
// edits that accept it. A case names the stored file text, the edits and the whole new text, so a line
// the patcher touches by mistake, a lost comment, a changed quote style or a changed line ending
// shows up as a text difference.

// f is a file text: the block between the delimiters and a short body behind the closing one.
func f(block string) string { return "---\n" + block + "---\n# Title\n" }

// crlf writes every line break of s as CRLF.
func crlf(s string) string { return strings.ReplaceAll(s, "\n", "\r\n") }

type applyCase struct {
	name  string
	in    string
	edits []Edit
	want  string
}

func runApply(t *testing.T, cases []applyCase) {
	t.Helper()
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			got, err := Apply(c.in, c.edits...)
			if err != nil {
				t.Fatalf("Apply: %v\n in:\n%s", err, c.in)
			}
			if got != c.want {
				t.Errorf("\n got %q\nwant %q", got, c.want)
			}
		})
	}
}

func TestSetValue(t *testing.T) {
	set := func(key string, v Value) []Edit { return []Edit{SetValue(key, v)} }
	runApply(t, []applyCase{
		{"plain keeps plain and the trailing comment", f("type: X\ndescription: old text  # why\ntags: [a]\n"), set("description", Str("new text")),
			f("type: X\ndescription: new text  # why\ntags: [a]\n")},
		{"double quotes stay double, comment stays", f("description: \"old: text\"  # why\nz: 1\n"), set("description", Str("new")),
			f("description: \"new\"  # why\nz: 1\n")},
		{"double quotes escape quote and backslash", f("description: \"old\"\n"), set("description", Str(`say "hi" \o/`)),
			f("description: \"say \\\"hi\\\" \\\\o/\"\n")},
		{"single quotes stay single and double their quote", f("description: 'old'\n"), set("description", Str("it's")),
			f("description: 'it''s'\n")},
		{"single quotes cannot carry a line break: double quotes", f("description: 'old'\n"), set("description", Str("a\nb")),
			f("description: \"a\\nb\"\n")},
		{"plain value that reads back as another type is quoted", f("description: old\n"), set("description", Str("true")),
			f("description: 'true'\n")},
		{"plain value with colon and space is single-quoted", f("description: old\n"), set("description", Str("a: b")),
			f("description: 'a: b'\n")},
		{"empty string is single-quoted", f("description: old\n"), set("description", Str("")), f("description: ''\n")},
		{"plain stays plain with an apostrophe inside", f("description: old\n"), set("description", Str("it's fine")),
			f("description: it's fine\n")},
		{"multi-line plain scalar becomes one line", f("description: first\n  second\nz: 1\n"), set("description", Str("new")),
			f("description: new\nz: 1\n")},
		{"multi-line plain scalar with a blank line inside", f("description: first\n\n  second\nz: 1\n"), set("description", Str("new")),
			f("description: new\nz: 1\n")},
		{"multi-line double-quoted scalar with a # line", f("description: \"a\n  # b\"\nz: 1\n"), set("description", Str("new")),
			f("description: \"new\"\nz: 1\n")},
		{"literal scalar: strip chomping, blank line behind stays", f("description: |\n  a\n  # b\n\nz: 1\n"), set("description", Str("new")),
			f("description: |-\n  new\n\nz: 1\n")},
		{"literal scalar with deeper content indentation", f("description: |\n      a\n      b\nz: 1\n"), set("description", Str("new")),
			f("description: |-\n      new\nz: 1\n")},
		{"empty literal scalar, the blank line behind stays", f("description: |\n\nz: 1\n"), set("description", Str("new")),
			f("description: |-\n  new\n\nz: 1\n")},
		{"a hash inside a plain scalar is no comment", f("description: a#b c  # why\nz: 1\n"), set("description", Str("new")),
			f("description: new  # why\nz: 1\n")},
		{"a comment line indented like a continuation line ends the scalar", f("description: first\n  # not part of it\nz: 1\n"), set("description", Str("new")),
			f("description: new\n  # not part of it\nz: 1\n")},
		{"literal scalar keeps the header comment", f("description: |  # note\n  a\nz: 1\n"), set("description", Str("new")),
			f("description: |-  # note\n  new\nz: 1\n")},
		{"keep-chomped literal scalar", f("description: |+\n  text\n\n\nz: 1\n"), set("description", Str("new")),
			f("description: |-\n  new\n\n\nz: 1\n")},
		{"folded scalar", f("description: >\n  a\n  b\nz: 1\n"), set("description", Str("new")),
			f("description: >-\n  new\nz: 1\n")},
		{"literal scalar with a text it cannot carry", f("description: |  # note\n  a\nz: 1\n"), set("description", Str("a\nb")),
			f("description: \"a\\nb\"  # note\nz: 1\n")},
		{"value on the next line", f("description:\n  \"on its own line\"\nstatus: draft\n"), set("description", Str("new")),
			f("description:\n  \"new\"\nstatus: draft\n")},
		{"empty value", f("description:\nz: 1\n"), set("description", Str("new")), f("description: new\nz: 1\n")},
		{"empty value with a comment", f("description:   # c\nz: 1\n"), set("description", Str("new")), f("description: new   # c\nz: 1\n")},
		{"tilde value", f("description: ~\n"), set("description", Str("new")), f("description: new\n")},
		{"typed plain scalar", f("at: 2026-01-01  # c\n"), set("at", Plain("2026-10-12T19:00:00Z")), f("at: 2026-10-12T19:00:00Z  # c\n")},
		{"typed plain scalar over a quoted one", f("at: '2026-01-01'\n"), set("at", Plain("2026-10-12")), f("at: 2026-10-12\n")},
		{"key in quotes", f("\"description\": old\n"), set("description", Str("new")), f("\"description\": new\n")},
		{"the string key, not the integer key of the same text", f("1: a\n'1': b\n"), set("1", Str("x")), f("1: a\n'1': x\n")},
		{"missing key goes behind the last line, comments included", f("type: X\n# end\n"), set("status", Str("draft")), f("type: X\n# end\nstatus: draft\n")},
		{"missing key with a mapping", f("type: X\n"), set("generated", Map("by", Str("human:a"), "at", Str("2026-01-29T00:00:00+00:00"))),
			f("type: X\ngenerated:\n  by: human:a\n  at: '2026-01-29T00:00:00+00:00'\n")},
		{"indented keys: the new key follows them", f("  type: X\n  description: old\n"), set("status", Str("s")), f("  type: X\n  description: old\n  status: s\n")},
		{"CRLF: the scalar is patched, its line keeps CRLF", crlf(f("description: old  # c\nz: 1\n")), set("description", Str("new")), crlf(f("description: new  # c\nz: 1\n"))},
		{"CRLF: a new key ends with CRLF", crlf(f("type: X\n")), set("status", Str("s")), crlf(f("type: X\nstatus: s\n"))},
		{"CRLF: a literal scalar", crlf(f("description: |\n  a\nz: 1\n")), set("description", Str("new")), crlf(f("description: |-\n  new\nz: 1\n"))},
		{"unicode before the scalar", f("title: éé\ndescription: 'ä ö'\n"), set("description", Str("ü")), f("title: éé\ndescription: 'ü'\n")},
		{"single quotes with a doubled quote inside", f("description: 'it''s old'  # c\nz: 1\n"), set("description", Str("x")), f("description: 'x'  # c\nz: 1\n")},
		{"plain value with a tab inside", f("description: a\tb  # c\nz: 1\n"), set("description", Str("new")), f("description: new  # c\nz: 1\n")},
		{"double quotes with an escaped quote inside", f("description: \"say \\\"hi\\\"\"  # c\nz: 1\n"), set("description", Str("x")), f("description: \"x\"  # c\nz: 1\n")},
		{"a comment inside the flow list of another key does not matter", f("tags: [a, # c\n  b]\nz: 1\n"), set("z", Str("2")), f("tags: [a, # c\n  b]\nz: '2'\n")},
	})
}

func TestNewKey(t *testing.T) {
	newKey := func(key string, v Value) []Edit { return []Edit{NewKey(key, v)} }
	sources := List(
		Map("resource", Str("https://example.org/pasta"), "title", Str("[Pasta basics](https://example.org/pasta)")),
		Map("resource", Str("~/dev/x/y.md"), "title", Str("Y")))
	runApply(t, []applyCase{
		{"string", f("type: X\n"), newKey("status", Str("draft")), f("type: X\nstatus: draft\n")},
		{"typed plain scalar", f("type: X\n"), newKey("at", Plain("2026-10-12T19:00:00Z")), f("type: X\nat: 2026-10-12T19:00:00Z\n")},
		{"mapping", f("type: X\n"), newKey("generated", Map("by", Str("human:golden"), "at", Str("2026-01-29T00:00:00+00:00"))),
			f("type: X\ngenerated:\n  by: human:golden\n  at: '2026-01-29T00:00:00+00:00'\n")},
		{"list of strings", f("type: X\n"), newKey("tags", List(Str("a"), Str("b c"))), f("type: X\ntags:\n  - a\n  - b c\n")},
		{"list of mappings as migrate writes sources", f("type: X\n"), newKey("sources", sources),
			f("type: X\nsources:\n  - resource: https://example.org/pasta\n    title: '[Pasta basics](https://example.org/pasta)'\n" +
				"  - resource: ~/dev/x/y.md\n    title: Y\n")},
		{"empty list and empty mapping", f("type: X\n"), []Edit{NewKey("a", List()), NewKey("b", Map())}, f("type: X\na: []\nb: {}\n")},
		{"mapping that holds a list", f("type: X\n"), newKey("m", Map("k", List(Str("x"), Str("y")), "j", Str("z"))),
			f("type: X\nm:\n  k:\n    - x\n    - y\n  j: z\n")},
		{"list item mapping that holds a list", f("type: X\n"), newKey("l", List(Map("k", List(Str("x")), "j", Str("z")))),
			f("type: X\nl:\n  - k:\n      - x\n    j: z\n")},
		{"string with a line break", f("type: X\n"), newKey("d", Str("a\nb")), f("type: X\nd: \"a\\nb\"\n")},
		{"a key of another type is another key", f("1: a\ntrue: b\n"), newKey("1", Str("x")), f("1: a\ntrue: b\n'1': x\n")},
		{"a string key that reads as another type is quoted", f("a: 1\n"), newKey("true", Str("x")), f("a: 1\n'true': x\n")},
		{"into an empty block", "---\n---\n# Body", newKey("type", Str("X")), "---\ntype: X\n---\n# Body"},
		{"into a comment-only block", "---\n# just a comment\n---\n# Body", newKey("type", Str("X")), "---\n# just a comment\ntype: X\n---\n# Body"},
		{"into a block of blank lines", "---\n\n---\n# Body", newKey("type", Str("X")), "---\n\ntype: X\n---\n# Body"},
		{"empty flow root turns into a block", "---\n{}\n---\n# Body", newKey("type", Str("X")), "---\ntype: X\n---\n# Body"},
		{"empty flow root with a comment line behind it", "---\n{}\n# note\n---\n# Body", newKey("type", Str("X")), "---\ntype: X\n# note\n---\n# Body"},
		{"delimiter line with spaces and a comment stay", "---   \ntype: X\n---   \n# Body", newKey("tags", Str("a")), "---   \ntype: X\ntags: a\n---   \n# Body"},
		{"file without frontmatter gets a block", "# Title\n\ntext\n", newKey("type", Str("X")), "---\ntype: X\n---\n# Title\n\ntext\n"},
		{"empty file without frontmatter", "", newKey("type", Str("X")), "---\ntype: X\n---\n"},
		{"CRLF file without frontmatter", "# Title\r\ntext\r\n", newKey("type", Str("X")), "---\r\ntype: X\r\n---\r\n# Title\r\ntext\r\n"},
		{"no final newline in the file", "---\ntype: X\n---", newKey("a", Str("b")), "---\ntype: X\na: b\n---"},
	})
}

func TestAppendItem(t *testing.T) {
	app := func(key string, v Value) []Edit { return []Edit{AppendItem(key, v)} }
	verified := Map("by", Str("human:x"), "at", Plain("2026-10-12T19:00:00Z"))
	runApply(t, []applyCase{
		{"block list, indentation of the items", f("tags:\n  - a\n  - b\nz: 1\n"), app("tags", Str("c")), f("tags:\n  - a\n  - b\n  - c\nz: 1\n")},
		{"block list, dash in the key column", f("tags:\n- a\n- b\nz: 1\n"), app("tags", Str("c")), f("tags:\n- a\n- b\n- c\nz: 1\n")},
		{"block list, four spaces", f("tags:\n    - a\nz: 1\n"), app("tags", Str("c")), f("tags:\n    - a\n    - c\nz: 1\n")},
		{"block list, several spaces behind the dash", f("tags:\n  -   a\nz: 1\n"), app("tags", Str("c")), f("tags:\n  -   a\n  -   c\nz: 1\n")},
		{"the comment of the next key stays below", f("tags:\n  - a\n# about z\nz: 1\n"), app("tags", Str("c")), f("tags:\n  - a\n  - c\n# about z\nz: 1\n")},
		{"blank lines after the list stay below", f("tags:\n  - a\n\nz: 1\n"), app("tags", Str("c")), f("tags:\n  - a\n  - c\n\nz: 1\n")},
		{"last key, a trailing comment stays below", f("z: 1\ntags:\n  - a\n# end\n"), app("tags", Str("c")), f("z: 1\ntags:\n  - a\n  - c\n# end\n")},
		{"commented-out item below the list stays below", f("tags:\n  - a\n  # - b\nz: 1\n"), app("tags", Str("c")), f("tags:\n  - a\n  - c\n  # - b\nz: 1\n")},
		{"blank line inside the list", f("tags:\n  - a\n\n  - b\nz: 1\n"), app("tags", Str("c")), f("tags:\n  - a\n\n  - b\n  - c\nz: 1\n")},
		{"item that needs quotes", f("tags:\n  - a\n"), app("tags", Str("x: y")), f("tags:\n  - a\n  - 'x: y'\n")},
		{"item with a space stays plain", f("tags:\n  - a\n"), app("tags", Str("b c")), f("tags:\n  - a\n  - b c\n")},
		{"flow list keeps the rest of the line", f("tags: [a, b]  # c\nz: 1\n"), app("tags", Str("c")), f("tags: [a, b, c]  # c\nz: 1\n")},
		{"empty flow list", f("tags: []\n"), app("tags", Str("c")), f("tags: [c]\n")},
		{"flow list over several lines with a trailing comma", f("tags: [\n  a,\n  b,\n]\nz: 1\n"), app("tags", Str("c")), f("tags: [\n  a,\n  b, c\n]\nz: 1\n")},
		{"flow list over several lines without a trailing comma", f("tags: [\n  a,\n  b\n]\nz: 1\n"), app("tags", Str("c")), f("tags: [\n  a,\n  b, c\n]\nz: 1\n")},
		{"flow list with a space before the bracket", f("tags: [a, b ]\n"), app("tags", Str("c")), f("tags: [a, b, c ]\n")},
		{"flow list with quoted items holding commas", f("tags: [\"a, b\", 'c']\n"), app("tags", Str("d")), f("tags: [\"a, b\", 'c', d]\n")},
		{"flow list item that needs quotes", f("tags: [a]\n"), app("tags", Str("x, y")), f("tags: [a, 'x, y']\n")},
		{"flow list item with a hash and no space before it", f("tags: [a#b, c]\n"), app("tags", Str("d")), f("tags: [a#b, c, d]\n")},
		{"flow list item in quotes with a hash behind a space", f("tags: [\"a # b\", c]\n"), app("tags", Str("d")), f("tags: [\"a # b\", c, d]\n")},
		{"flow list item with an apostrophe", f("tags: [it's, x]\n"), app("tags", Str("y")), f("tags: [it's, x, y]\n")},
		{"flow list with nested brackets", f("tags: [a, [b, c]]\n"), app("tags", Str("d")), f("tags: [a, [b, c], d]\n")},
		{"one block mapping becomes the first item", f("verified:\n  by: a/b\n  at: 2026-01-01\nz: 1\n"), app("verified", verified),
			f("verified:\n  - by: a/b\n    at: 2026-01-01\n  - by: human:x\n    at: 2026-10-12T19:00:00Z\nz: 1\n")},
		{"one block mapping with a comment line above its first key", f("verified:\n  # who\n  by: a/b\n  at: 2026-01-01\nz: 1\n"), app("verified", verified),
			f("verified:\n    # who\n  - by: a/b\n    at: 2026-01-01\n  - by: human:x\n    at: 2026-10-12T19:00:00Z\nz: 1\n")},
		{"one flow mapping on the key line becomes the first item", f("verified: {by: a, at: b}  # who\nz: 1\n"), app("verified", verified),
			f("verified:\n  - {by: a, at: b}  # who\n  - by: human:x\n    at: 2026-10-12T19:00:00Z\nz: 1\n")},
		{"missing key becomes a one-item list", f("type: X\n"), app("verified", verified),
			f("type: X\nverified:\n  - by: human:x\n    at: 2026-10-12T19:00:00Z\n")},
		{"missing key, scalar item", f("type: X\n"), app("tags", Str("a")), f("type: X\ntags:\n  - a\n")},
		{"list of block mappings in the key column", f("verified:\n- by: a/b\n  at: 2026-01-01\nz: 1\n"), app("verified", verified),
			f("verified:\n- by: a/b\n  at: 2026-01-01\n- by: human:x\n  at: 2026-10-12T19:00:00Z\nz: 1\n")},
		{"list of block mappings", f("verified:\n  - by: a/b\n    at: 2026-01-01\nz: 1\n"), app("verified", verified),
			f("verified:\n  - by: a/b\n    at: 2026-01-01\n  - by: human:x\n    at: 2026-10-12T19:00:00Z\nz: 1\n")},
		{"list of flow mappings: the new item is a flow mapping", f("verified:\n  - {by: a, at: b}\nz: 1\n"), app("verified", verified),
			f("verified:\n  - {by: a, at: b}\n  - {by: human:x, at: 2026-10-12T19:00:00Z}\nz: 1\n")},
		{"mapping item behind scalar items", f("tags:\n  - a\n"), app("tags", Map("k", Str("v"))), f("tags:\n  - a\n  - k: v\n")},
		{"indented root keys", f("  tags:\n    - a\n  z: 1\n"), app("tags", Str("c")), f("  tags:\n    - a\n    - c\n  z: 1\n")},
		{"indented root keys, missing key", f("  z: 1\n"), app("verified", verified), f("  z: 1\n  verified:\n    - by: human:x\n      at: 2026-10-12T19:00:00Z\n")},
		{"CRLF block list", crlf(f("tags:\n  - a\n  - b\n# c\nz: 1\n")), app("tags", Str("c")), crlf(f("tags:\n  - a\n  - b\n  - c\n# c\nz: 1\n"))},
		{"CRLF flow list", crlf(f("tags: [a, b]\nz: 1\n")), app("tags", Str("c")), crlf(f("tags: [a, b, c]\nz: 1\n"))},
		{"CRLF mapping becomes a list", crlf(f("verified:\n  by: a\n  at: b\nz: 1\n")), app("verified", verified),
			crlf(f("verified:\n  - by: a\n    at: b\n  - by: human:x\n    at: 2026-10-12T19:00:00Z\nz: 1\n"))},
		{"file without frontmatter: verify writes a new block", "# Title\n", app("verified", verified),
			"---\nverified:\n  - by: human:x\n    at: 2026-10-12T19:00:00Z\n---\n# Title\n"},
		{"empty flow root turns into a block", "---\n{}\n---\n", app("verified", verified),
			"---\nverified:\n  - by: human:x\n    at: 2026-10-12T19:00:00Z\n---\n"},
	})
}

func TestRenameItem(t *testing.T) {
	ren := func(key string, i int, s string) []Edit { return []Edit{RenameItem(key, i, s)} }
	runApply(t, []applyCase{
		{"block item keeps its trailing comment", f("tags:\n  - a  # first\n  - b\n"), ren("tags", 0, "x"), f("tags:\n  - x  # first\n  - b\n")},
		{"block item, second", f("tags:\n  - a\n  - b\n  - c\n"), ren("tags", 1, "x"), f("tags:\n  - a\n  - x\n  - c\n")},
		{"double-quoted item stays double", f("tags:\n  - \"a b\"  # c\n"), ren("tags", 0, "x"), f("tags:\n  - \"x\"  # c\n")},
		{"single-quoted item stays single", f("tags:\n  - 'a'\n"), ren("tags", 0, "x y"), f("tags:\n  - 'x y'\n")},
		{"plain item whose new text needs quotes", f("tags:\n  - a\n"), ren("tags", 0, "x: y"), f("tags:\n  - 'x: y'\n")},
		{"multi-line plain item", f("tags:\n  - first\n    second\n  - b\n"), ren("tags", 0, "x"), f("tags:\n  - x\n  - b\n")},
		{"last item followed by a comment", f("tags:\n  - a\n# c\nz: 1\n"), ren("tags", 0, "x"), f("tags:\n  - x\n# c\nz: 1\n")},
		{"dash in the key column", f("tags:\n- a\n- b\n"), ren("tags", 1, "x"), f("tags:\n- a\n- x\n")},
		{"flow item", f("tags: [a, \"b c\", d]  # c\nz: 1\n"), ren("tags", 0, "x"), f("tags: [x, \"b c\", d]  # c\nz: 1\n")},
		{"flow item, quoted", f("tags: [a, \"b c\", d]\n"), ren("tags", 1, "q"), f("tags: [a, \"q\", d]\n")},
		{"flow item, new text needs quotes", f("tags: [a, b]\n"), ren("tags", 1, "x, y"), f("tags: [a, 'x, y']\n")},
		{"flow item over several lines", f("tags: [\n  a,\n  b\n]\n"), ren("tags", 1, "x"), f("tags: [\n  a,\n  x\n]\n")},
		{"CRLF block", crlf(f("tags:\n  - a  # c\n  - b\n")), ren("tags", 0, "x"), crlf(f("tags:\n  - x  # c\n  - b\n"))},
		{"unicode items", f("tags:\n  - ä\n  - ö\n"), ren("tags", 1, "ü"), f("tags:\n  - ä\n  - ü\n")},
	})
}

func TestDeleteItem(t *testing.T) {
	del := func(key string, i int) []Edit { return []Edit{DeleteItem(key, i)} }
	list := f("tags:\n  - a\n  - b\n  - c\nz: 1\n")
	runApply(t, []applyCase{
		{"block, first", list, del("tags", 0), f("tags:\n  - b\n  - c\nz: 1\n")},
		{"block, middle", list, del("tags", 1), f("tags:\n  - a\n  - c\nz: 1\n")},
		{"block, last", list, del("tags", 2), f("tags:\n  - a\n  - b\nz: 1\n")},
		{"block: comments around stay", f("tags:\n  - a\n  # about b\n  - b\n  - c\n"), del("tags", 1), f("tags:\n  - a\n  # about b\n  - c\n")},
		{"block: comment lines before the next item stay", f("tags:\n  - a\n  # about b\n  - b\n  - c\n"), del("tags", 0), f("tags:\n  # about b\n  - b\n  - c\n")},
		{"flow: a nested list is one item", f("tags: [a, [b, c], d]\n"), del("tags", 1), f("tags: [a, d]\n")},
		{"flow: a nested list as the last item", f("tags: [a, [b, c]]\n"), del("tags", 1), f("tags: [a]\n")},
		{"flow: a nested mapping and a quoted item with a bracket", f("tags: [{a: 1, b: 2}, \"x]\", d]\n"), del("tags", 0), f("tags: [\"x]\", d]\n")},
		{"block: the lines of a mapping item go", f("sources:\n  - resource: a\n    title: A\n  - resource: b\n    title: B\n"), del("sources", 0),
			f("sources:\n  - resource: b\n    title: B\n")},
		{"block: item with a trailing comment", f("tags:\n  - a  # first\n  - b\n"), del("tags", 0), f("tags:\n  - b\n")},
		{"block: the only item leaves an empty flow list", f("tags:\n  - a\nz: 1\n"), del("tags", 0), f("tags: []\nz: 1\n")},
		{"block: the only item, key comment stays", f("tags:  # c\n  - a\n"), del("tags", 0), f("tags: []  # c\n")},
		{"block: the only item, key in quotes", f("\"tags\":\n  - a\n"), del("tags", 0), f("\"tags\": []\n")},
		{"block: the only item, a space before the colon", f("tags :\n  - a\n"), del("tags", 0), f("tags : []\n")},
		{"block: the only item, then the key", f("tags:\n  - a\nz: 1\n"), []Edit{DeleteItem("tags", 0), DeleteKey("tags")}, f("z: 1\n")},
		{"flow, first", f("tags: [a, b, c]  # c\n"), del("tags", 0), f("tags: [b, c]  # c\n")},
		{"flow, middle", f("tags: [a, b, c]\n"), del("tags", 1), f("tags: [a, c]\n")},
		{"flow, last", f("tags: [a, b, c]\n"), del("tags", 2), f("tags: [a, b]\n")},
		{"flow, the only item", f("tags: [a]  # c\n"), del("tags", 0), f("tags: []  # c\n")},
		{"flow: quoted items with commas", f("tags: [\"a, b\", 'c', d]\n"), del("tags", 1), f("tags: [\"a, b\", d]\n")},
		{"flow, last item behind a trailing comma", f("tags: [a, b,]\n"), del("tags", 1), f("tags: [a,]\n")},
		{"flow over several lines, middle", f("tags: [\n  a,\n  b,\n  c\n]\n"), del("tags", 1), f("tags: [\n  a,\n  c\n]\n")},
		{"flow over several lines, last", f("tags: [\n  a,\n  b\n]\n"), del("tags", 1), f("tags: [\n  a\n]\n")},
		{"CRLF block", crlf(list), del("tags", 1), crlf(f("tags:\n  - a\n  - c\nz: 1\n"))},
		{"CRLF flow", crlf(f("tags: [a, b]\nz: 1\n")), del("tags", 0), crlf(f("tags: [b]\nz: 1\n"))},
		{"one edit after the other: indices count in the list as it stands", list, []Edit{DeleteItem("tags", 2), DeleteItem("tags", 0)}, f("tags:\n  - b\nz: 1\n")},
		{"all items removed, then the key", f("tags: [a, b]\nz: 1\n"), []Edit{DeleteItem("tags", 1), DeleteItem("tags", 0), DeleteKey("tags")}, f("z: 1\n")},
	})
}

func TestDeleteKey(t *testing.T) {
	del := func(key string) []Edit { return []Edit{DeleteKey(key)} }
	runApply(t, []applyCase{
		{"comments above and behind stay", f("a: 1\n# about b\nb: 2\n# about c\nc: 3\n"), del("b"), f("a: 1\n# about b\n# about c\nc: 3\n")},
		{"list value", f("tags:\n  - a\n  - b\nz: 1\n"), del("tags"), f("z: 1\n")},
		{"flow list with its comment", f("tags: [a, b]  # c\nz: 1\n"), del("tags"), f("z: 1\n")},
		{"literal scalar: the blank line behind stays", f("d: |\n  x\n\ne: 1\n"), del("d"), f("\ne: 1\n")},
		{"literal scalar, then a comment in column 0", f("d: |\n  x\n# c\ne: 1\n"), del("d"), f("# c\ne: 1\n")},
		{"multi-line double-quoted value", f("d: \"a\n  # b\"\ne: 1\n"), del("d"), f("e: 1\n")},
		{"mapping value", f("m:\n  k: v\n  j: w\ne: 1\n"), del("m"), f("e: 1\n")},
		{"the last key", f("a: 1\nb: 2\n"), del("b"), f("a: 1\n")},
		{"the only key leaves an empty block", "---\nonly: 1\n---\nbody", del("only"), "---\n---\nbody"},
		{"key in quotes", f("\"a b\": 1\nc: 2\n"), del("a b"), f("c: 2\n")},
		{"CRLF", crlf(f("a: 1\nb: 2\nc: 3\n")), del("b"), crlf(f("a: 1\nc: 3\n"))},
		{"last key with a trailing comment", f("a: 1\nb: 2\n# end\n"), del("b"), f("a: 1\n# end\n")},
	})
}

func TestReplaceKey(t *testing.T) {
	gen := Map("by", Str("human:spike"), "at", Str("2026-10-12T19:00:00+00:00"))
	runApply(t, []applyCase{
		{"timestamp becomes generated, the comment above stays", f("# when\ntimestamp: 2026-10-06  # c\nz: 1\n"), []Edit{ReplaceKey("timestamp", "generated", gen)},
			f("# when\ngenerated:\n  by: human:spike\n  at: '2026-10-12T19:00:00+00:00'\nz: 1\n")},
		{"the comment behind the value stays", f("timestamp: 2026-10-06\n# about z\nz: 1\n"), []Edit{ReplaceKey("timestamp", "generated", gen)},
			f("generated:\n  by: human:spike\n  at: '2026-10-12T19:00:00+00:00'\n# about z\nz: 1\n")},
		{"same key, scalar to list", f("description: old\nz: 1\n"), []Edit{ReplaceKey("description", "description", List(Str("a"), Str("b")))},
			f("description:\n  - a\n  - b\nz: 1\n")},
		{"multi-line value is replaced as a whole", f("timestamp:\n  a: 1\n  b: 2\nz: 1\n"), []Edit{ReplaceKey("timestamp", "generated", gen)},
			f("generated:\n  by: human:spike\n  at: '2026-10-12T19:00:00+00:00'\nz: 1\n")},
		{"sources over an empty flow list, in place", f("a: 1\nsources: []\nz: 1\n"), []Edit{ReplaceKey("sources", "sources", List(Map("resource", Str("r"), "title", Str("t"))))},
			f("a: 1\nsources:\n  - resource: r\n    title: t\nz: 1\n")},
		{"CRLF", crlf(f("timestamp: 2026-10-06\nz: 1\n")), []Edit{ReplaceKey("timestamp", "generated", gen)},
			crlf(f("generated:\n  by: human:spike\n  at: '2026-10-12T19:00:00+00:00'\nz: 1\n"))},
		{"timestamp goes when generated exists", f("timestamp: 2026-10-06\ngenerated: {by: a/b}\n"), []Edit{DeleteKey("timestamp")}, f("generated: {by: a/b}\n")},
		{"a flow list is replaced as a whole, its comment goes with it", f("tags: [a, b]  # c\nz: 1\n"), []Edit{ReplaceKey("tags", "tags", List(Str("x")))},
			f("tags:\n  - x\nz: 1\n")},
		{"a flow mapping is replaced as a whole", f("timestamp: {at: x}\nz: 1\n"), []Edit{ReplaceKey("timestamp", "generated", gen)},
			f("generated:\n  by: human:spike\n  at: '2026-10-12T19:00:00+00:00'\nz: 1\n")},
	})
}

func TestFlowToBlock(t *testing.T) {
	ftb := []Edit{FlowToBlock("tags")}
	runApply(t, []applyCase{
		{"the comment keeps its column", f("tags: [glossary, ops]   # flow form on purpose\nz: 1\n"), ftb,
			f("tags:                   # flow form on purpose\n  - glossary\n  - ops\nz: 1\n")},
		{"no comment", f("tags: [food]\nz: 1\n"), ftb, f("tags:\n  - food\nz: 1\n")},
		{"item text stays as written", f("tags: [\"a b\", 'c', d]\n"), ftb, f("tags:\n  - \"a b\"\n  - 'c'\n  - d\n")},
		{"items over several lines", f("tags: [\n  a,\n  b\n]\nz: 1\n"), ftb, f("tags:\n  - a\n  - b\nz: 1\n")},
		{"comment behind a closing bracket on its own line", f("tags: [\n  a\n]  # c\n"), ftb, f("tags: # c\n  - a\n")},
		{"flow items stay flow", f("tags: [{a: 1}, [b]]\n"), ftb, f("tags:\n  - {a: 1}\n  - [b]\n")},
		{"unicode before the comment", f("tags: [ä, ö]  # ü\n"), ftb, f("tags:         # ü\n  - ä\n  - ö\n")},
		{"indented root keys", f("  tags: [a, b]\n  z: 1\n"), ftb, f("  tags:\n    - a\n    - b\n  z: 1\n")},
		{"CRLF", crlf(f("tags: [a, b]  # c\nz: 1\n")), ftb, crlf(f("tags:         # c\n  - a\n  - b\nz: 1\n"))},
	})
}

func TestSetBody(t *testing.T) {
	runApply(t, []applyCase{
		{"the head stays byte-identical", "---   \nk: v  # c\n---   \nold", []Edit{SetBody("\nnew\n")}, "---   \nk: v  # c\n---\nnew\n"},
		{"CRLF head stays", "---\r\nk: v\r\n---\r\nold", []Edit{SetBody("\nnew")}, "---\r\nk: v\r\n---\nnew"},
		{"file without frontmatter: the text is the body", "old\n", []Edit{SetBody("new\n")}, "new\n"},
		{"block first, then the body", "# Title\n", []Edit{NewKey("type", Str("Context")), SetBody("\n# slug\n")}, "---\ntype: Context\n---\n# slug\n"},
		{"the same body", f("k: v\n"), []Edit{SetBody("\n# Title\n")}, f("k: v\n")},
	})
}

func TestApplyEmptyEditListReturnsTheInput(t *testing.T) {
	for _, in := range []string{f("k: v\n"), "no frontmatter", "", "---\nk: [\n---\nbody", "---\r\nk: v\r\n---\r\n", "\xff---\n"} {
		got, err := Apply(in)
		if err != nil || got != in {
			t.Errorf("Apply(%q) = %q, %v; want the input", in, got, err)
		}
	}
}

func TestEditsRunInOrder(t *testing.T) {
	runApply(t, []applyCase{
		{"rename then append then set", f("type: X\ntags:\n  - a\n  - b\n"),
			[]Edit{RenameItem("tags", 0, "x"), AppendItem("tags", Str("c")), SetValue("type", Str("Y")), NewKey("n", Str("1"))},
			f("type: Y\ntags:\n  - x\n  - b\n  - c\nn: '1'\n")},
		{"flow to block, then append", f("tags: [a, b]  # c\n"), []Edit{FlowToBlock("tags"), AppendItem("tags", Str("c"))},
			f("tags:         # c\n  - a\n  - b\n  - c\n")},
		{"verified: a mapping, then another entry", f("verified:\n  by: a\n  at: b\n"), []Edit{
			AppendItem("verified", Map("by", Str("x"), "at", Plain("2026-01-01"))),
			AppendItem("verified", Map("by", Str("y"), "at", Plain("2026-01-02")))},
			f("verified:\n  - by: a\n    at: b\n  - by: x\n    at: 2026-01-01\n  - by: y\n    at: 2026-01-02\n")},
	})
}
