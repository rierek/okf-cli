package frontmatter

import (
	"strings"

	"go.yaml.in/yaml/v3"
)

// yaml.v3 reads YAML 1.1, where NEL (U+0085), LS (U+2028) and PS (U+2029) are line breaks; ruamel
// reads YAML 1.2, where they are ordinary characters. A plain scalar, a comment or a flow list that
// holds one therefore reads in Python and fails here, and a quoted scalar folds it away. The three
// are swapped for private-use characters for the parse, which keeps every line and column, and
// swapped back in the texts of the node tree. A block that already holds the private-use
// characters is parsed as it is.
const placeholders = "\ue000\ue001\ue002"

var (
	breakSwap    = strings.NewReplacer("\u0085", "\ue000", "\u2028", "\ue001", "\u2029", "\ue002")
	breakRestore = strings.NewReplacer("\ue000", "\u0085", "\ue001", "\u2028", "\ue002", "\u2029")
)

// swapBreaks returns block with NEL, LS and PS replaced, and whether it replaced any.
func swapBreaks(block string) (string, bool) {
	if !strings.ContainsAny(block, "\u0085\u2028\u2029") || strings.ContainsAny(block, placeholders) {
		return block, false
	}
	return breakSwap.Replace(block), true
}

// restoreBreaks puts NEL, LS and PS back into the texts of a node tree.
func restoreBreaks(n *yaml.Node) {
	if n == nil {
		return
	}
	n.Value = breakRestore.Replace(n.Value)
	n.HeadComment = breakRestore.Replace(n.HeadComment)
	n.LineComment = breakRestore.Replace(n.LineComment)
	n.FootComment = breakRestore.Replace(n.FootComment)
	for _, c := range n.Content {
		restoreBreaks(c)
	}
}
