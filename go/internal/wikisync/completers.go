package wikisync

import (
	"sort"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/complete"
	"nas/volume1/data/git/okf-tools/go/internal/frontmatter"
)

// CompleteBlockIDs offers the canon block ids declared in the concept already on the line (dest
// "concept"). A concept that does not resolve offers nothing, silently. Used for the `block-id`
// argument of sync-export and sync-insert.
func CompleteBlockIDs(c complete.Context) []complete.Candidate {
	concept := c.String("concept")
	if c.Root == "" || concept == "" {
		return nil
	}
	ap, err := catalogue.ResolveConcept(c.Root, concept)
	if err != nil {
		return nil
	}
	text, err := catalogue.ReadFile(ap)
	if err != nil {
		return nil
	}
	var out []complete.Candidate
	for _, blk := range ParseCanonBlocks(frontmatter.Read(text).Body) {
		out = append(out, complete.Candidate{Value: blk.ID})
	}
	return out
}

// CompleteCanonSources offers every canon owner as `/bundle/concept.md`, sorted. Used for the
// `--source` option of sync-status and sync-update.
func CompleteCanonSources(c complete.Context) []complete.Candidate {
	idx := canonIndexOf(c)
	set := map[string]bool{}
	for k := range idx {
		set["/"+k.Rel] = true
	}
	return sortedCandidates(set)
}

// CompleteCanonBlockIDs offers every declared canon block id, sorted and narrowed to the owner
// named by `--source` (dest "source") when it is on the line. Used for the `--block` option of
// sync-status and sync-update.
func CompleteCanonBlockIDs(c complete.Context) []complete.Candidate {
	idx := canonIndexOf(c)
	source := strings.TrimLeft(c.String("source"), "/")
	set := map[string]bool{}
	for k := range idx {
		if source == "" || k.Rel == source {
			set[k.ID] = true
		}
	}
	return sortedCandidates(set)
}

func canonIndexOf(c complete.Context) CanonIndex {
	if c.Root == "" {
		return nil
	}
	idx, err := BuildCanonIndex(c.Root)
	if err != nil {
		return nil
	}
	return idx
}

func sortedCandidates(set map[string]bool) []complete.Candidate {
	values := make([]string, 0, len(set))
	for v := range set {
		values = append(values, v)
	}
	sort.Strings(values)
	out := make([]complete.Candidate, len(values))
	for i, v := range values {
		out[i] = complete.Candidate{Value: v}
	}
	return out
}
