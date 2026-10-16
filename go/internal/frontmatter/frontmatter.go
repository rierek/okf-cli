// Package frontmatter is the one reader of a concept file's frontmatter block. It splits a file
// text at the block exactly as Python read_frontmatter does and parses the block once into a
// go.yaml.in/yaml/v3 node tree whose Line, Column and Style fields every writer (the line-patch
// writer of work package C) relies on; there is no second parser.
//
// Positions: the block text starts with the newline after the opening `---`, so a node's Line
// is 1-based in FILE coordinates (the opening delimiter is line 1, the first YAML line is 2) and
// its Column is 1-based within its line.
package frontmatter

import (
	"errors"
	"fmt"
	"io"
	"strings"

	"go.yaml.in/yaml/v3"

	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

// Delim is the frontmatter delimiter line.
const Delim = "---"

// Doc is a file text cut at its frontmatter block: Head + Body is the text.
//
// Head runs from the opening `---` through the `---` of the first later newline-`---`; it is empty
// when the text has no such block (then Block and Root are empty too). Block is the text between
// the delimiters, starting with the newline after the opening `---` and ending with the newline
// before the closing one. For a non-empty Head exactly one of Root and Err is set.
type Doc struct {
	Head  string
	Block string
	Body  string
	// Document is the yaml.DocumentNode of the block, nil when the block holds no document
	// (empty or comment-only block) or failed to parse. Root is its root mapping, kept with Line,
	// Column and Style; a null or empty block reads as an empty block-style mapping.
	Document *yaml.Node
	Root     *yaml.Node
	// Err is the one-line reason the block does not read: `<problem> (line L, column C)` or
	// `block is not a mapping`. Empty when the block read or when there is no block.
	Err string
}

// Read splits text at its frontmatter block and parses the block once.
func Read(text string) Doc {
	end := -1
	if strings.HasPrefix(text, Delim) {
		if i := strings.Index(text[len(Delim):], "\n"+Delim); i >= 0 {
			end = len(Delim) + i
		}
	}
	if end == -1 {
		return Doc{Body: text}
	}
	cut := end + len(Delim) + 1
	doc := Doc{Head: text[:cut], Block: text[len(Delim) : end+1], Body: text[cut:]}
	doc.Document, doc.Root, doc.Err = parseBlock(doc.Block)
	return doc
}

// Data is the root mapping, nil when there is no block or it does not read. It is the `data` of
// the Python Frontmatter tuple; every accessor of this package accepts nil.
func (d Doc) Data() *yaml.Node { return d.Root }

// errNotMapping is the reason of a block whose root is not a mapping.
const errNotMapping = "block is not a mapping"

// parseBlock parses a block text once. It reproduces the strict parse of the spike
// (docs/topics/okf-go-port/spike/strat_yamlv3.go v3ParseStrict): an empty or comment-only block,
// or a block of one null, is an empty block-style mapping; a root that is not a mapping, a second
// document and a mapping that holds a key twice are refused.
func parseBlock(block string) (doc, root *yaml.Node, reason string) {
	dec := yaml.NewDecoder(strings.NewReader(block))
	var n yaml.Node
	if err := dec.Decode(&n); err != nil {
		if errors.Is(err, io.EOF) {
			return nil, emptyMapping(), ""
		}
		return nil, nil, syntaxReason(block, err)
	}
	var second yaml.Node
	if err := dec.Decode(&second); !errors.Is(err, io.EOF) {
		if err != nil {
			return nil, nil, syntaxReason(block, err)
		}
		return nil, nil, "expected a single document in the stream" + position(second.Line, second.Column)
	}
	if n.Kind != yaml.DocumentNode || len(n.Content) != 1 {
		return nil, nil, errNotMapping
	}
	switch c := n.Content[0]; {
	case c.Kind == yaml.MappingNode:
		if key := duplicateKey(c); key != nil {
			return nil, nil, pytext.Collapse(fmt.Sprintf("found duplicate key %q%s", key.Value, position(key.Line, key.Column)))
		}
		return &n, c, ""
	case c.Kind == yaml.ScalarNode && c.ShortTag() == "!!null":
		return nil, emptyMapping(), ""
	}
	return nil, nil, errNotMapping
}

// emptyMapping is the root of an empty block: a block-style mapping without content.
func emptyMapping() *yaml.Node { return &yaml.Node{Kind: yaml.MappingNode, Tag: "!!map"} }

func position(line, column int) string { return fmt.Sprintf(" (line %d, column %d)", line, column) }

// duplicateKey returns the second occurrence of a key in any mapping below n (the merge key
// `<<` may repeat), or nil.
func duplicateKey(n *yaml.Node) *yaml.Node {
	if n.Kind == yaml.AliasNode {
		return nil // the anchored node is checked where it is defined
	}
	if n.Kind == yaml.MappingNode {
		seen := map[string]bool{}
		for i := 0; i+1 < len(n.Content); i += 2 {
			k := n.Content[i]
			if k.Kind != yaml.ScalarNode || k.Value == "<<" {
				continue
			}
			id := k.ShortTag() + "|" + k.Value
			if seen[id] {
				return k
			}
			seen[id] = true
		}
	}
	for _, c := range n.Content {
		if k := duplicateKey(c); k != nil {
			return k
		}
	}
	return nil
}
