package spec

import (
	"time"

	"go.yaml.in/yaml/v3"

	"nas/volume1/data/git/okf-tools/go/internal/frontmatter"
	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

// Filled is Python filled: a value that says something, that is not absent or null, not blank
// text, not an empty list or mapping. Every other scalar is filled.
func Filled(n *yaml.Node) bool {
	switch {
	case frontmatter.IsNull(n):
		return false
	case isStr(n):
		return pytext.Strip(frontmatter.ScalarText(n)) != ""
	case frontmatter.IsSeq(n):
		return len(frontmatter.Elems(n)) > 0
	case frontmatter.IsMap(n):
		return len(frontmatter.Items(n)) > 0
	}
	return true
}

// VerifiedEntries is Python verified_entries: the `verified` entries of a frontmatter, a bare
// mapping counting as one entry (OKF §5.2, §11). ok is false when `verified` is absent or neither
// a mapping nor a list; an empty list gives no entries and ok true. The items of a list come back
// as written, so a caller checks them with frontmatter.IsMap. The slice is shared with the tree.
func VerifiedEntries(fm *yaml.Node) (entries []*yaml.Node, ok bool) {
	value := frontmatter.Lookup(fm, "verified")
	switch {
	case frontmatter.IsMap(value):
		return []*yaml.Node{frontmatter.Deref(value)}, true
	case frontmatter.IsSeq(value):
		return frontmatter.Elems(value), true
	}
	return nil, false
}

// VerifiedIsWellFormed is Python verified_is_well_formed: `verified` is a mapping or a list of
// mappings (OKF §5.2); an absent key is not.
func VerifiedIsWellFormed(fm *yaml.Node) bool {
	entries, ok := VerifiedEntries(fm)
	if !ok {
		return false
	}
	for _, entry := range entries {
		if !frontmatter.IsMap(entry) {
			return false
		}
	}
	return true
}

// TrustTier is Python trust_tier (OKF §5.3), from `verified` alone: "unverified" without an entry
// that names a `by`, "human-reviewed" when one such actor is `human:<id>`, else
// "machine-confirmed" (an actor outside the convention is no human).
func TrustTier(fm *yaml.Node) string {
	entries, _ := VerifiedEntries(fm)
	named := false
	for _, entry := range entries {
		if !frontmatter.IsMap(entry) {
			continue
		}
		by := frontmatter.Lookup(entry, "by")
		if !Filled(by) {
			continue
		}
		named = true
		if kind, _, ok := ParseActor(by); ok && kind == "human" {
			return "human-reviewed"
		}
	}
	if named {
		return "machine-confirmed"
	}
	return "unverified"
}

// IsStale is Python is_stale (OKF §5.5): `stale_after`, the one source, parses and now has reached
// it. An absent or unparseable `stale_after` is not stale.
func IsStale(fm *yaml.Node, now time.Time) bool {
	at, ok := ParseOkfDatetime(frontmatter.Lookup(fm, "stale_after"))
	return ok && !now.Before(at)
}

// TrustFields is Python trust_fields: the `tier` and `stale` values every concept record of
// `--json` output carries, in that order.
func TrustFields(fm *yaml.Node, now time.Time) (tier string, stale bool) {
	return TrustTier(fm), IsStale(fm, now)
}
