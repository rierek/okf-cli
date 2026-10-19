package catalogue

import (
	"sort"

	"nas/volume1/data/git/okf-tools/go/internal/frontmatter"
	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

// RegistryRanks are the values of the rank cell of a registry entry, "—" (an em dash) being the
// unranked one. RegistryFormats (root.go) lists the two entry forms.
var RegistryRanks = []string{"1", "2", "3", "—"}

var (
	tableEntryRE      = pytext.Regexp("^\\|\\s*`([^`]+)`")
	blockEntryRE      = pytext.Regexp("^###\\s+`([^`]+)`\\s*$")
	registryHeadingRE = pytext.Regexp(`^#{1,6}(?:\s|$)`)
	fenceOpenRE       = pytext.Regexp("^ {0,3}(`{3,}|~{3,})")
	fenceCloseRE      = pytext.Regexp("^ {0,3}(`{3,}|~{3,})\\s*$")
)

// RegistryEntry is one registered value of a TAGS.md or TYPES.md. Kind is "table" (a row whose
// first cell is the backticked value; the span is that one line) or "block" (a ### `value`
// heading; the span runs to the next heading or the end of the file). Start and End are line
// indexes, End exclusive.
type RegistryEntry struct {
	Value      string
	Kind       string
	Start, End int
}

// RegistryScan is the result of ScanRegistry: the entries in file order, the line indexes of the
// headings outside code fences (ascending) and the set of line indexes inside code fences (the
// fence lines themselves included).
type RegistryScan struct {
	Entries  []RegistryEntry
	Headings []int
	Fenced   map[int]bool
}

// ScanRegistry is Python scan_registry: the registry entries of a TAGS.md or TYPES.md in both
// forms. lines is the text split with pytext.SplitLines(text, true). A table entry is a row whose
// first cell is a backticked value; a block entry is a ### `value` heading and spans to the next
// heading. Both forms are always recognised, so switching the form never turns `check` red. Lines
// inside a code fence (``` or ~~~) count in neither form, since an example in a code block is
// documentation, not an entry. A table row outside fences counts anywhere in the file. Setext
// headings are not recognised.
func ScanRegistry(lines []string) RegistryScan {
	scan := RegistryScan{Fenced: map[int]bool{}}
	var fenceChar byte
	fenceWidth := 0 // the width of the opening fence while inside one, else 0
	for i, line := range lines {
		if fenceWidth > 0 {
			scan.Fenced[i] = true
			if m := fenceCloseRE.FindStringSubmatch(line); m != nil && m[1][0] == fenceChar && len(m[1]) >= fenceWidth {
				fenceWidth = 0
			}
			continue
		}
		if m := fenceOpenRE.FindStringSubmatch(line); m != nil {
			fenceChar, fenceWidth = m[1][0], len(m[1])
			scan.Fenced[i] = true
			continue
		}
		if registryHeadingRE.MatchString(line) {
			scan.Headings = append(scan.Headings, i)
		}
		if m := blockEntryRE.FindStringSubmatch(line); m != nil {
			scan.Entries = append(scan.Entries, RegistryEntry{m[1], "block", i, len(lines)})
			continue
		}
		if m := tableEntryRE.FindStringSubmatch(line); m != nil {
			scan.Entries = append(scan.Entries, RegistryEntry{m[1], "table", i, i + 1})
		}
	}
	for k := range scan.Entries {
		if e := &scan.Entries[k]; e.Kind == "block" {
			if j := sort.SearchInts(scan.Headings, e.Start+1); j < len(scan.Headings) {
				e.End = scan.Headings[j]
			}
		}
	}
	return scan
}

// loadRegistry is Python _load_registry: the set of registered values of the registry file p, nil
// (Python None) when the file is missing.
func loadRegistry(p string) (map[string]bool, error) {
	if !isFile(p) {
		return nil, nil
	}
	text, err := ReadFile(p)
	if err != nil {
		return nil, err
	}
	scan := ScanRegistry(pytext.SplitLines(text, true))
	set := make(map[string]bool, len(scan.Entries))
	for _, e := range scan.Entries {
		set[e.Value] = true
	}
	return set, nil
}

// LoadTypes is Python load_types: the set of registered `type` values, or a nil map (Python
// None) when the source is missing. typesSource overrides the default <root>/TYPES.md so a repo
// bundle can point at the central catalogue's TYPES.md; "" means the default. Table and block
// entries both count. An existing registry without entries gives an empty, non-nil set.
func LoadTypes(root, typesSource string) (map[string]bool, error) {
	if typesSource == "" {
		typesSource = Join(root, "TYPES.md")
	}
	return loadRegistry(typesSource)
}

// LoadTags is Python load_tags: the set of registered tag values from tagsSource (default
// <root>/TAGS.md when ""), or a nil map (Python None) when the file is missing, in which case the
// closed-vocabulary check is a no-op. Table and block entries both count. An existing registry
// without entries gives an empty, non-nil set.
func LoadTags(root, tagsSource string) (map[string]bool, error) {
	if tagsSource == "" {
		tagsSource = Join(root, "TAGS.md")
	}
	return loadRegistry(tagsSource)
}

// TagCount is a tag and its usage count.
type TagCount struct {
	Tag   string
	Count int
}

// TagCounts is the Python Counter of AllTags: the usage count of every tag, 0 for a tag that
// does not occur. The Counter's first-seen iteration order is not kept; every caller sorts, with
// Sorted or Ranked.
type TagCounts map[string]int

// Sorted is sorted(counts): the tags in code point order.
func (c TagCounts) Sorted() []string {
	tags := make([]string, 0, len(c))
	for tag := range c {
		tags = append(tags, tag)
	}
	sort.Strings(tags)
	return tags
}

// Ranked is sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])): the tags by usage count,
// highest first, equal counts in code point order of the tag.
func (c TagCounts) Ranked() []TagCount {
	rows := make([]TagCount, 0, len(c))
	for tag, n := range c {
		rows = append(rows, TagCount{tag, n})
	}
	sort.Slice(rows, func(i, j int) bool {
		if rows[i].Count != rows[j].Count {
			return rows[i].Count > rows[j].Count
		}
		return rows[i].Tag < rows[j].Tag
	})
	return rows
}

// AllTags is Python all_tags: the usage count of every tag across every concept of every bundle
// under root (staging directories pruned, as every read path does). A tag listed twice in one
// concept counts twice. Each concept is read and parsed once.
func AllTags(root string) (TagCounts, error) {
	bundles, err := ListBundles(root)
	if err != nil {
		return nil, err
	}
	counts := TagCounts{}
	for _, b := range bundles {
		for _, ap := range IterConcepts(Join(root, b), true) {
			text, err := ReadFile(ap)
			if err != nil {
				return nil, err
			}
			for _, tag := range frontmatter.Tags(frontmatter.Read(text).Data()) {
				counts[tag]++
			}
		}
	}
	return counts, nil
}
