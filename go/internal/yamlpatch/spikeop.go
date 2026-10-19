package yamlpatch

import (
	"errors"

	"go.yaml.in/yaml/v3"

	"nas/volume1/data/git/okf-tools/go/internal/frontmatter"
)

// The five write ops of the YAML round-trip spike (docs/topics/okf-go-port/spike): the same constants as
// spike/common.go and spike/ref.py. They are the corpus method of R-03 and of work package K, not an okf
// command, and SpikeOp builds each of them only from the edit set of the writer.
const (
	spikeTag    = "spike-tag"
	spikeDesc   = "spike description"
	spikeKey    = "spike_key"
	spikeVal    = "spike value"
	spikeBy     = "human:spike"
	spikeAt     = "2026-10-12T19:00:00Z"
	spikeGenBy  = "human:spike"
	spikeGenAt  = "2026-10-12T19:00:00+00:00" // a str that resolves to a timestamp: written single-quoted
	opNoChange  = "op0"
	opAppendTag = "op1"
	opSetDesc   = "op2a"
	opNewKey    = "op2b"
	opVerified  = "op3"
	opTimestamp = "op4"
)

// SpikeOps lists the spike ops in the order of the spike.
var SpikeOps = []string{opNoChange, opAppendTag, opSetDesc, opNewKey, opVerified, opTimestamp}

// ErrNotApplicable is the result of a spike op whose precondition does not hold for the file (no `tags`
// list, no `timestamp`, ...).
var ErrNotApplicable = errors.New("not applicable")

// SpikeOp applies one spike op to a file text through the production edit set and returns the new
// text, ErrNotApplicable, or a rejection (*ParseError when the frontmatter does not read, *Rejection
// when the writer refuses the file).
func SpikeOp(op, text string) (string, error) {
	doc := frontmatter.Read(text)
	if doc.Head != "" && doc.Err != "" {
		return "", &ParseError{Reason: doc.Err}
	}
	value := func(key string) *yaml.Node { return direct(doc.Root, key) }
	switch op {
	case opNoChange:
		return text, nil
	case opAppendTag:
		if v := value("tags"); v == nil || v.Kind != yaml.SequenceNode {
			return "", ErrNotApplicable
		}
		return Apply(text, AppendItem("tags", Str(spikeTag)))
	case opSetDesc:
		if v := value("description"); v == nil || v.Kind != yaml.ScalarNode || v.ShortTag() != "!!str" {
			return "", ErrNotApplicable
		}
		return Apply(text, SetValue("description", Str(spikeDesc)))
	case opNewKey:
		return Apply(text, NewKey(spikeKey, Str(spikeVal)))
	case opVerified:
		if v := value("verified"); v != nil && !verifiedShape(v) {
			return "", ErrNotApplicable
		}
		return Apply(text, AppendItem("verified", Map("by", Str(spikeBy), "at", Plain(spikeAt))))
	case opTimestamp:
		if value("timestamp") == nil {
			return "", ErrNotApplicable
		}
		if value("generated") != nil {
			return Apply(text, DeleteKey("timestamp"))
		}
		return Apply(text, ReplaceKey("timestamp", "generated", Map("by", Str(spikeGenBy), "at", Str(spikeGenAt))))
	}
	return "", reject("unknown spike op %q", op)
}

// direct is the value of a top-level key of the root mapping, no aliases or merges followed.
func direct(root *yaml.Node, key string) *yaml.Node {
	if root == nil {
		return nil
	}
	for i := 0; i+1 < len(root.Content); i += 2 {
		if k := root.Content[i]; k.Kind == yaml.ScalarNode && k.ShortTag() == "!!str" && k.Value == key {
			return root.Content[i+1]
		}
	}
	return nil
}

// verifiedShape reports whether `verified` is a mapping or a list of mappings, what `verify` accepts.
func verifiedShape(v *yaml.Node) bool {
	switch v.Kind {
	case yaml.MappingNode:
		return true
	case yaml.SequenceNode:
		for _, it := range v.Content {
			if it.Kind != yaml.MappingNode {
				return false
			}
		}
		return true
	}
	return false
}
