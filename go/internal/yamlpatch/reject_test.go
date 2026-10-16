package yamlpatch_test

import (
	"errors"
	"strings"
	"testing"

	"nas/volume1/data/git/okf-tools/go/internal/frontmatter"
	"nas/volume1/data/git/okf-tools/go/internal/okferr"
	. "nas/volume1/data/git/okf-tools/go/internal/yamlpatch"
)

// Rejection tests (R-04): a shape the writer cannot patch safely gives a one-line reason and no text.

func TestRejections(t *testing.T) {
	multiFlow := f("tags: [a, # inner comment\n  b]\nz: 1\n")
	anchored := f("description: &d \"anchored\"\nalso: *d\n")
	cases := []struct {
		name   string
		in     string
		edits  []Edit
		reason string // a part of the one-line reason
	}{
		{"not valid UTF-8", "---\nk: \xff\n---\n", []Edit{SetValue("k", Str("x"))}, "not valid UTF-8"},
		{"a bare carriage return in the frontmatter", "---\na: 1\rb: 2\n---\n", []Edit{NewKey("c", Str("x"))}, "carriage return"},
		{"a key on the opening delimiter line", "--- a: 1\n b: 2\n---\n", []Edit{NewKey("c", Str("x"))}, "opening delimiter"},
		{"a root that is a non-empty flow mapping", f("{type: X, tags: [a]}\n"), []Edit{NewKey("c", Str("x"))}, "flow mapping"},
		{"an empty flow root with a comment on its line", f("{}  # c\n"), []Edit{NewKey("c", Str("x"))}, "flow mapping"},
		{"a flow root on the opening delimiter line", "--- {}\n---\n", []Edit{NewKey("c", Str("x"))}, "flow mapping"},

		{"comment inside a flow list: append", multiFlow, []Edit{AppendItem("tags", Str("c"))}, "comment"},
		{"comment inside a flow list: rename", multiFlow, []Edit{RenameItem("tags", 0, "c")}, "comment"},
		{"comment inside a flow list: delete an item", multiFlow, []Edit{DeleteItem("tags", 0)}, "comment"},
		{"comment inside a flow list: flow to block", multiFlow, []Edit{FlowToBlock("tags")}, "comment"},

		{"set-value on a list", f("tags:\n  - a\n"), []Edit{SetValue("tags", Str("x"))}, "list or a mapping"},
		{"set-value on a flow list", f("tags: [a]\n"), []Edit{SetValue("tags", Str("x"))}, "list or a mapping"},
		{"set-value on a mapping", f("m:\n  k: v\n"), []Edit{SetValue("m", Str("x"))}, "list or a mapping"},
		{"set-value of a mapping over a scalar", f("description: x\n"), []Edit{SetValue("description", Map("a", Str("b")))}, "string or a typed scalar"},
		{"set-value of a list over a scalar", f("description: x\n"), []Edit{SetValue("description", List(Str("a")))}, "string or a typed scalar"},

		{"anchor on the targeted value", anchored, []Edit{SetValue("description", Str("x"))}, "anchor"},
		{"alias value", f("base: &b {a: 1}\ncopy: *b\n"), []Edit{SetValue("copy", Str("x"))}, "alias"},
		{"explicit tag", f("description: !!str x\n"), []Edit{SetValue("description", Str("y"))}, "explicit tag"},
		{"anchor inside the value: delete the key", f("m:\n  a: &x 1\n  b: *x\n"), []Edit{DeleteKey("m")}, "anchor"},
		{"anchored list: append", f("tags: &t [a, b]\nother: *t\n"), []Edit{AppendItem("tags", Str("c"))}, "anchor"},
		{"alias item: rename", f("x: &a v\ntags:\n  - *a\n"), []Edit{RenameItem("tags", 0, "c")}, "alias"},
		{"anchored key", f("&k key: v\n"), []Edit{DeleteKey("key")}, "anchor"},

		{"rename: key missing", f("a: 1\n"), []Edit{RenameItem("tags", 0, "x")}, "not in the frontmatter"},
		{"delete item: key missing", f("a: 1\n"), []Edit{DeleteItem("tags", 0)}, "not in the frontmatter"},
		{"delete key: key missing", f("a: 1\n"), []Edit{DeleteKey("tags")}, "not in the frontmatter"},
		{"replace key: key missing", f("a: 1\n"), []Edit{ReplaceKey("tags", "x", Str("y"))}, "not in the frontmatter"},
		{"flow to block: key missing", f("a: 1\n"), []Edit{FlowToBlock("tags")}, "not in the frontmatter"},
		{"delete key on a file without frontmatter", "text\n", []Edit{DeleteKey("a")}, "not in the frontmatter"},
		{"new key that exists", f("a: 1\n"), []Edit{NewKey("a", Str("2"))}, "already in the frontmatter"},
		{"replace key by another existing key", f("a: 1\nb: 2\n"), []Edit{ReplaceKey("a", "b", Str("x"))}, "already in the frontmatter"},
		{"rename: index past the end", f("tags:\n  - a\n"), []Edit{RenameItem("tags", 1, "x")}, "no item 1"},
		{"delete item: negative index", f("tags:\n  - a\n"), []Edit{DeleteItem("tags", -1)}, "no item -1"},
		{"rename: not a list", f("tags: a\n"), []Edit{RenameItem("tags", 0, "x")}, "not a list"},
		{"rename: a mapping item", f("tags:\n  - a: 1\n"), []Edit{RenameItem("tags", 0, "x")}, "not a plain or quoted scalar"},
		{"rename: a block scalar item", f("tags:\n  - |\n    text\n"), []Edit{RenameItem("tags", 0, "x")}, "not a plain or quoted scalar"},

		{"append: a scalar value", f("tags: a, b\n"), []Edit{AppendItem("tags", Str("c"))}, "not a list"},
		{"append: an empty value", f("tags:\nz: 1\n"), []Edit{AppendItem("tags", Str("c"))}, "not a list"},
		{"append: a scalar to a mapping", f("verified:\n  by: a\n"), []Edit{AppendItem("verified", Str("c"))}, "scalar cannot be appended"},
		{"append: a flow mapping over several lines", f("verified: {by: a,\n  at: b}\n"), []Edit{AppendItem("verified", Map("by", Str("x")))}, "several lines"},
		{"append: a list as item", f("tags: [a]\n"), []Edit{AppendItem("tags", List(Str("c")))}, "list item"},
		{"append: a mapping with a list to a flow list", f("tags: [a]\n"), []Edit{AppendItem("tags", Map("k", List(Str("c"))))}, "flow list cannot carry"},
		{"flow to block: a block list", f("tags:\n  - a\n"), []Edit{FlowToBlock("tags")}, "not a flow list"},
		{"flow to block: an empty list", f("tags: []\n"), []Edit{FlowToBlock("tags")}, "empty"},
		{"flow to block: the list on the next line", f("tags:\n  [a, b]\n"), []Edit{FlowToBlock("tags")}, "key line"},
		{"flow to block: an item over several lines", f("tags: [\"a\n  b\", c]\n"), []Edit{FlowToBlock("tags")}, "several lines"},

		{"a typed scalar with a line break", f("a: 1\n"), []Edit{NewKey("k", Plain("a\nb"))}, "not a writable plain scalar"},
		{"an empty typed scalar", f("a: 1\n"), []Edit{NewKey("k", Plain(""))}, "not a writable plain scalar"},
		{"a typed scalar with leading space", f("a: 1\n"), []Edit{NewKey("k", Plain(" x"))}, "not a writable plain scalar"},
		{"a mapping with a key twice", f("a: 1\n"), []Edit{NewKey("k", Map("a", Str("x"), "a", Str("y")))}, "twice"},
		{"a list inside a list", f("a: 1\n"), []Edit{NewKey("k", List(List(Str("x"))))}, "list inside a list"},
		{"a string that is not UTF-8", f("a: 1\n"), []Edit{NewKey("k", Str("\xff"))}, "not valid UTF-8"},
		{"a body that is not UTF-8", f("a: 1\n"), []Edit{SetBody("\xff")}, "not valid UTF-8"},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			got, err := Apply(c.in, c.edits...)
			if err == nil {
				t.Fatalf("Apply succeeded with %q; want a rejection containing %q", got, c.reason)
			}
			if got != "" {
				t.Errorf("a rejection returned the text %q", got)
			}
			var rej *Rejection
			if !errors.As(err, &rej) {
				t.Fatalf("error %T %v is no *Rejection", err, err)
			}
			if !strings.Contains(rej.Reason, c.reason) || strings.ContainsAny(rej.Reason, "\r\n") {
				t.Errorf("reason %q: want one line containing %q", rej.Reason, c.reason)
			}
			if failure := okferr.As(err); failure.Kind != okferr.InvalidInput || failure.Code() != 2 || failure.Message != rej.Reason {
				t.Errorf("classified as %v/%d %q, want invalid_input/2 with the reason", failure.Kind, failure.Code(), failure.Message)
			}
		})
	}
}

func TestMapPanicsOnMisuse(t *testing.T) {
	for name, args := range map[string][]any{"odd": {"a"}, "key": {1, Str("x")}, "value": {"a", "x"}} {
		func() {
			defer func() {
				if recover() == nil {
					t.Errorf("Map with %s arguments did not panic", name)
				}
			}()
			Map(args...)
		}()
	}
}

// A file whose frontmatter does not read gives B's reason unchanged, as a *ParseError.
func TestParseErrorsPassThrough(t *testing.T) {
	for name, in := range map[string]string{
		"unclosed flow list": f("tags: [a\nz: 1\n"),
		"block is a list":    f("- a\n- b\n"),
		"duplicate key":      f("a: 1\na: 2\n"),
		"tab indentation":    f("tags:\n\t- a\n"),
		"unclosed quote":     f("description: \"abc\n"),
	} {
		t.Run(name, func(t *testing.T) {
			want := frontmatter.Read(in).Err
			if want == "" {
				t.Fatal("the reader accepts the text")
			}
			got, err := Apply(in, SetValue("a", Str("x")))
			var pe *ParseError
			if !errors.As(err, &pe) || got != "" {
				t.Fatalf("Apply = %q, %v; want a *ParseError and no text", got, err)
			}
			if pe.Reason != want {
				t.Errorf("reason %q, want the reader's %q", pe.Reason, want)
			}
			if failure := okferr.As(err); failure.Kind != okferr.InvalidInput || failure.Message != want {
				t.Errorf("classified as %v %q", failure.Kind, failure.Message)
			}
		})
	}
}

func TestOneRejectionDoesNotLeakEarlierEdits(t *testing.T) {
	in := f("tags:\n  - a\n")
	got, err := Apply(in, AppendItem("tags", Str("b")), DeleteKey("missing"))
	if err == nil || got != "" {
		t.Fatalf("Apply = %q, %v; want only the rejection", got, err)
	}
}
