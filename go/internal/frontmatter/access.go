package frontmatter

import (
	"strings"

	"go.yaml.in/yaml/v3"

	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

// Deref follows aliases to the anchored node; nil stays nil.
func Deref(n *yaml.Node) *yaml.Node {
	for n != nil && n.Kind == yaml.AliasNode {
		n = n.Alias
	}
	return n
}

// IsMap, IsSeq and IsScalar test the kind of a node (aliases followed).
func IsMap(n *yaml.Node) bool    { n = Deref(n); return n != nil && n.Kind == yaml.MappingNode }
func IsSeq(n *yaml.Node) bool    { n = Deref(n); return n != nil && n.Kind == yaml.SequenceNode }
func IsScalar(n *yaml.Node) bool { n = Deref(n); return n != nil && n.Kind == yaml.ScalarNode }

// IsFlow reports whether a mapping or sequence is written in flow style (`[a, b]`, `{a: 1}`).
func IsFlow(n *yaml.Node) bool { n = Deref(n); return n != nil && n.Style&yaml.FlowStyle != 0 }

// Tag is the resolved short tag of a scalar (`!!str`, `!!int`, `!!float`, `!!bool`, `!!null`,
// `!!timestamp`, ...), aliases followed; "" for a nil or non-scalar node. It is the type Python
// sees after loading: a quoted scalar is always `!!str`, a plain `true` is `!!bool`.
func Tag(n *yaml.Node) string {
	n = Deref(n)
	if n == nil || n.Kind != yaml.ScalarNode {
		return ""
	}
	return n.ShortTag()
}

// IsNull reports whether n is absent or a YAML null (`null`, `~` or no value).
func IsNull(n *yaml.Node) bool {
	n = Deref(n)
	return n == nil || (n.Kind == yaml.ScalarNode && n.ShortTag() == "!!null")
}

// IsString reports whether n is a scalar Python loads as str (a quoted scalar or a plain scalar
// that is no number, boolean, null or timestamp).
func IsString(n *yaml.Node) bool { return Tag(n) == "!!str" }

// Pair is one key and value of a mapping.
type Pair struct{ Key, Value *yaml.Node }

// Lookup is `data.get(key)` for a mapping node: the value node of the string key, or nil. Aliases
// are followed and keys merged with `<<` are found when the mapping itself lacks the key, own keys
// first and earlier merges before later ones, as ruamel's CommentedMap does. A nil or non-mapping
// node has no keys.
func Lookup(m *yaml.Node, key string) *yaml.Node {
	m = Deref(m)
	if m == nil || m.Kind != yaml.MappingNode {
		return nil
	}
	var merges []*yaml.Node
	for i := 0; i+1 < len(m.Content); i += 2 {
		k := m.Content[i]
		if k.Kind != yaml.ScalarNode {
			continue
		}
		if k.Value == "<<" && k.ShortTag() == "!!merge" {
			merges = append(merges, m.Content[i+1])
			continue
		}
		if k.Value == key && k.ShortTag() == "!!str" {
			return m.Content[i+1]
		}
	}
	for _, merged := range merges {
		if d := Deref(merged); d != nil && d.Kind == yaml.SequenceNode {
			for _, each := range d.Content {
				if v := Lookup(each, key); v != nil {
					return v
				}
			}
		} else if v := Lookup(merged, key); v != nil {
			return v
		}
	}
	return nil
}

// Has is `key in data`.
func Has(m *yaml.Node, key string) bool { return Lookup(m, key) != nil }

// Items is the key and value pairs of a mapping in document order, aliases followed. Keys that come
// in through a `<<` merge follow the own keys (a merged key an own key overrides is skipped), as
// ruamel inserts them; the merge key itself is not listed.
func Items(m *yaml.Node) []Pair {
	m = Deref(m)
	if m == nil || m.Kind != yaml.MappingNode {
		return nil
	}
	var out []Pair
	seen := map[string]bool{}
	var merges []*yaml.Node
	for i := 0; i+1 < len(m.Content); i += 2 {
		k, v := m.Content[i], m.Content[i+1]
		if k.Kind == yaml.ScalarNode && k.Value == "<<" && k.ShortTag() == "!!merge" {
			merges = append(merges, v)
			continue
		}
		out = append(out, Pair{k, v})
		seen[mergeID(k)] = true
	}
	for _, merged := range merges {
		sources := []*yaml.Node{merged}
		if d := Deref(merged); d != nil && d.Kind == yaml.SequenceNode {
			sources = d.Content
		}
		for _, src := range sources {
			for _, p := range Items(src) {
				if id := mergeID(p.Key); !seen[id] {
					seen[id] = true
					out = append(out, p)
				}
			}
		}
	}
	return out
}

func mergeID(k *yaml.Node) string { return k.ShortTag() + "|" + k.Value }

// Elems is the items of a sequence node (aliases followed), nil for anything else.
func Elems(n *yaml.Node) []*yaml.Node {
	n = Deref(n)
	if n == nil || n.Kind != yaml.SequenceNode {
		return nil
	}
	return n.Content
}

// ScalarText is the text of a value as Python scalar_text gives it: nothing is "", a string is its
// content without quotes, a typed scalar (boolean, number, timestamp) is in its YAML form, so
// `True` reads `true`, `+5` reads `5`, `.Inf` reads `.inf`; every other number and timestamp keeps
// the form the author wrote. Python also dumps explicitly tagged scalars with their tag and pads
// fractional seconds of a timestamp to six digits; neither is reproduced. A mapping or sequence
// gives the first line of its YAML form.
func ScalarText(n *yaml.Node) string {
	n = Deref(n)
	if n == nil {
		return ""
	}
	if n.Kind != yaml.ScalarNode {
		out, err := yaml.Marshal(n)
		if err != nil {
			return ""
		}
		first, _, _ := strings.Cut(string(out), "\n")
		return first
	}
	switch n.ShortTag() {
	case "!!null":
		return ""
	case "!!bool":
		return strings.ToLower(n.Value)
	case "!!int":
		if n.Value == "-0" {
			return "0"
		}
		return strings.TrimPrefix(n.Value, "+")
	case "!!float":
		switch strings.ToLower(n.Value) {
		case ".inf", "+.inf":
			return ".inf"
		case "-.inf":
			return "-.inf"
		case ".nan":
			return ".nan"
		}
	}
	return n.Value
}

// Text is Python fm_text: the text of data[key], def when data lacks the key. A key with no value
// gives "".
func Text(data *yaml.Node, key, def string) string {
	if v := Lookup(data, key); v != nil {
		return ScalarText(v)
	}
	return def
}

// Tags is Python tags_of: the tags of a frontmatter mapping, in order. A list gives its items; a
// lone scalar, which reads as a list as before the switch (`tags: a, b`), is split at its commas.
// Every tag is stripped; empty ones are dropped.
func Tags(data *yaml.Node) []string {
	tags := Lookup(data, "tags")
	var items []string
	if IsSeq(tags) {
		for _, item := range Elems(tags) {
			items = append(items, ScalarText(item))
		}
	} else {
		items = strings.Split(ScalarText(tags), ",")
	}
	out := []string{}
	for _, item := range items {
		if s := pytext.Strip(item); s != "" {
			out = append(out, s)
		}
	}
	return out
}

// FlowTags is Python flow_tags: the `tags` node when it is a non-empty flow-style list `[a, b]`,
// else nil.
func FlowTags(data *yaml.Node) *yaml.Node {
	tags := Deref(Lookup(data, "tags"))
	if tags != nil && tags.Kind == yaml.SequenceNode && len(tags.Content) > 0 && tags.Style&yaml.FlowStyle != 0 {
		return tags
	}
	return nil
}

// Meta is Python fm_meta: (type, title, description) of a frontmatter mapping as strings. The
// title falls back to stem, the description to "".
func Meta(data *yaml.Node, stem string) (typ, title, description string) {
	title = Text(data, "title", "")
	if title == "" {
		title = stem
	}
	return Text(data, "type", ""), title, Text(data, "description", "")
}
