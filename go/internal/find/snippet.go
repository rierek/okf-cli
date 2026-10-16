package find

import (
	"strings"
	"unicode/utf8"

	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

// snippetWidth is the width of the body excerpt in characters.
const snippetWidth = 140

// makeSnippet is Python make_snippet: about snippetWidth characters of body around the earliest
// term occurrence, whitespace collapsed, `…` marking a cut start and always the end. Positions
// are code points, not bytes, and are found in the lower-cased body but applied to the original,
// as Python does (a lower-casing that changes the length shifts the window, and so must the port).
func makeSnippet(body string, terms []string) string {
	low := pytext.Lower(body)
	pos := -1
	for _, t := range terms {
		if i := strings.Index(low, t); i != -1 {
			if at := utf8.RuneCountInString(low[:i]); pos == -1 || at < pos {
				pos = at
			}
		}
	}
	if pos == -1 {
		pos = 0
	}
	start := max(0, pos-snippetWidth/3)
	runes := []rune(body)
	frag := ""
	if start < len(runes) {
		frag = pytext.Collapse(string(runes[start:min(len(runes), start+snippetWidth)]))
	}
	prefix := ""
	if start > 0 {
		prefix = "…"
	}
	return prefix + frag + "…"
}
