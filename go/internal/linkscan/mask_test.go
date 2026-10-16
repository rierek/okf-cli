package linkscan

import (
	"reflect"
	"strings"
	"testing"
)

// syncBlock is a materialised canon block as `okf sync` writes it. Its payload holds a wikilink
// and a markdown link that the owner's copy, not this one, must report and rewrite.
const syncBlock = "<!-- okf:sync id=rule source=/kc/owner.md hash=0123456789ab -->\n" +
	"> [!quote] Synchronised from `/kc/owner.md`, do not edit here.\n" +
	"<!-- okf:sync-body -->\n" +
	"payload [[w]] and [p](t.md)\n" +
	"<!-- /okf:sync -->"

// show renders a mask with every blanked byte as `#`, so a case reads as the text it masks. No
// input below holds a `#` of its own.
func show(mask string) string { return strings.ReplaceAll(mask, "\x00", "#") }

// hashes is s with every byte but a newline replaced by `#`: the mask of a fully masked span.
func hashes(s string) string {
	b := []byte(s)
	for i, c := range b {
		if c != '\n' {
			b[i] = '#'
		}
	}
	return string(b)
}

var maskCases = []struct {
	name string
	text string
	yaml bool
	want string
}{
	// fenced code
	{"backtick fence", "a\n```\n[[x]]\n```\nb [[y]]\n", false, "a\n###\n#####\n###\nb [[y]]\n"},
	{"tilde fence", "~~~\n[[x]]\n~~~\n[[y]]\n", false, "###\n#####\n###\n[[y]]\n"},
	{"four backtick fence holds a three backtick line",
		"````\n```\n[[x]]\n```\n````\n[[y]]\n", false, "####\n###\n#####\n###\n####\n[[y]]\n"},
	{"prose fence mention does not shift the pairing",
		"Use ``` to open.\n\n````\n[[x]]\n````\n[[y]]\n", false, "Use ``` to open.\n\n####\n#####\n####\n[[y]]\n"},
	{"narrower run does not close a wider fence",
		"````\n```\nx\n````\ny\n", false, "####\n###\n#\n####\ny\n"},
	{"tilde run does not close a backtick fence",
		"```\nx\n~~~\ny\n```\nz\n", false, "###\n#\n###\n#\n###\nz\n"},
	{"closer with an info string does not close",
		"```\n``` end\nx\n```\ny\n", false, "###\n#######\n#\n###\ny\n"},
	{"unclosed fence runs to the end", "a\n```\nb\nc\n", false, "a\n###\n#\n#\n"},
	{"fence indented by three spaces", "   ```\n   [[a]]\n   ```\n", false, "######\n########\n######\n"},
	{"an info string with a backtick opens no fence", "```a`b\n[[x]]\n", false, "``###b\n[[x]]\n"},

	// sync spans, masked before the comment stage
	{"sync span payload is masked",
		"before\n" + syncBlock + "\nafter [[live]]\n", false,
		"before\n" + hashes(syncBlock) + "\nafter [[live]]\n"},
	{"sync spans keep the text between them live",
		syncBlock + "\nbetween [[x]]\n" + syncBlock + "\n", false,
		hashes(syncBlock) + "\nbetween [[x]]\n" + hashes(syncBlock) + "\n"},
	{"sync marker without its closer is an ordinary comment",
		"<!-- okf:sync id=a -->\nx [[w]]\n", false, hashes("<!-- okf:sync id=a -->") + "\nx [[w]]\n"},
	{"sync span in the frontmatter region",
		"note: x\n" + syncBlock + "\nlive [[a]]\n", true,
		"note: x\n" + hashes(syncBlock) + "\nlive [[a]]\n"},

	// comments
	{"percent and html comments",
		"<!-- TODO [[a]] -->\n%% draft [[b]] %%\nlive [[c]]\n", false,
		hashes("<!-- TODO [[a]] -->\n%% draft [[b]] %%\n") + "live [[c]]\n"},
	{"a comment ends at its own closer",
		"%% one %%\nlive [[a]]\n%% two %%\n<!-- three -->\nlive [[b]]\n<!-- four -->\n", false,
		hashes("%% one %%") + "\nlive [[a]]\n" + hashes("%% two %%\n<!-- three -->") + "\nlive [[b]]\n" +
			hashes("<!-- four -->") + "\n"},
	{"a multi-line comment keeps its newlines",
		"a <!-- one\ntwo --> b %%x\ny%% c\n", false,
		"a " + hashes("<!-- one\ntwo -->") + " b " + hashes("%%x\ny%%") + " c\n"},

	// inline code
	{"inline code",
		"a `x` b ``y`` c `` [[z]] `` d\n", false,
		"a ### b ##### c " + hashes("`` [[z]] ``") + " d\n"},
	{"two backticks without content are no code", "a `` b\n", false, "a `` b\n"},
	{"inline code does not span lines", "`a\nb` [[x]]\n", false, "`a\nb` [[x]]\n"},
	{"inline code in the frontmatter region", "note: \"see `[[X]]` here\"\n", true,
		"note: \"see " + hashes("`[[X]]`") + " here\"\n"},

	// indented code
	{"indented code after a blank line",
		"Example:\n\n    Use [[a]] here.\n\nEnd.\n", false,
		"Example:\n\n" + hashes("    Use [[a]] here.") + "\n\nEnd.\n"},
	{"tab indented code", "intro\n\n\tcode [[a]]\n", false, "intro\n\n" + hashes("\tcode [[a]]") + "\n"},
	{"indented code ends at its last indented line",
		"p\n\n    one\n\n    two\n    \nq\n", false,
		"p\n\n" + hashes("    one\n\n    two") + "\n    \nq\n"},
	{"list continuation is not code", "- bullet\n\n    continues [[a]]\n", false, "- bullet\n\n    continues [[a]]\n"},
	{"nested list continuation is not code", "- a\n  - b\n\n      deep [[x]]\n", false,
		"- a\n  - b\n\n      deep [[x]]\n"},
	{"second indented paragraph after a list is not code",
		"- item\n\n    cont\n\n    more [[x]]\n", false, "- item\n\n    cont\n\n    more [[x]]\n"},
	{"indentation without a blank line before is not code",
		"Some prose\n    continued [[a]]\n", false, "Some prose\n    continued [[a]]\n"},
	{"an indented first line is not code", "    [[a]] first\nprose\n\n", false, "    [[a]] first\nprose\n\n"},
	{"frontmatter indentation is structure",
		"type: x\nrelated:\n\n    - \"[[b]]\"\n", true, "type: x\nrelated:\n\n    - \"[[b]]\"\n"},
	{"the same lines in the body are code",
		"type: x\nrelated:\n\n    - \"[[b]]\"\n", false,
		"type: x\nrelated:\n\n" + hashes("    - \"[[b]]\"") + "\n"},

	// every stage runs over the output of the previous one
	{"a fence masks the closer of an earlier comment",
		"%% x\n```\n%%\n[[a]]\n```\n", false, "%% x\n###\n##\n#####\n###\n"},
	{"a backtick in a comment opens no inline code",
		"<!-- ` --> `y` [[a]] `z`\n", false, hashes("<!-- ` -->") + " ### [[a]] ###\n"},

	// bytes, not characters
	{"multi-byte characters", "é `é` 日本 %% 😀 %%\n", false, "é #### 日本 ##########\n"},
	{"multi-byte characters in a fence", "```\n日本\n```\n", false, "###\n######\n###\n"},
	{"verbatim CRLF text", "```\r\nx\r\n```\r\n[[a]]\r\n", false, "####\n##\n####\n[[a]]\r\n"},
}

func TestDeadZoneMask(t *testing.T) {
	for _, tc := range maskCases {
		t.Run(tc.name, func(t *testing.T) {
			got := DeadZoneMask(tc.text, tc.yaml)
			if len(got) != len(tc.text) {
				t.Fatalf("the mask changed the byte length: %d to %d", len(tc.text), len(got))
			}
			if show(got) != tc.want {
				t.Errorf("mask of %q\n got %q\nwant %q", tc.text, show(got), tc.want)
			}
		})
	}
}

func TestInlineCodeSpans(t *testing.T) {
	tests := []struct {
		text string
		want [][]int
	}{
		{"`a`", [][]int{{0, 3}}},
		{"``a``", [][]int{{0, 5}}},
		{"` `", [][]int{{0, 3}}},
		{"`a``b`", [][]int{{0, 3}, {3, 6}}}, // a longer run closes with its first backticks
		{"``", nil},
		{"`a\nb`", nil},
		{"```a``", [][]int{{0, 6}}}, // the whole run finds no closer, so the opener shrinks
		{"a ``` b ``` c", [][]int{{2, 11}}},
		{"`` a ` b ``", [][]int{{0, 11}}},
		{"é `é`", [][]int{{3, 7}}}, // byte offsets
	}
	for _, tc := range tests {
		if got := InlineCodeSpans(tc.text); !reflect.DeepEqual(got, tc.want) {
			t.Errorf("InlineCodeSpans(%q) = %v, want %v", tc.text, got, tc.want)
		}
	}
}

func TestListItemRE(t *testing.T) {
	for _, line := range []string{"- a", "* a", "+ a", "1. a", "12) a", "  - a", "\t- a", "٣. a", "- "} {
		if !ListItemRE.MatchString(line) {
			t.Errorf("%q is a list item", line)
		}
	}
	for _, line := range []string{"-a", "1.a", "-", "-\n", "text", "1 a", "a. b", "    code"} {
		if ListItemRE.MatchString(line) {
			t.Errorf("%q is no list item", line)
		}
	}
}
