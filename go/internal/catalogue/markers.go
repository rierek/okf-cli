package catalogue

import (
	"regexp"

	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

// The marker literals and patterns of the catalogue layer. B owns them; every consumer imports
// them and never redefines one.
const (
	// MarkStart and MarkEnd bound the managed index block of an index file.
	MarkStart = "<!-- okf:index -->"
	MarkEnd   = "<!-- /okf:index -->"
	// Exempt in an index file opts the directory out of index generation.
	Exempt = "<!-- okf:index-exempt -->"

	// Canon block synchronisation notation. The owner declares an addressable block with
	// `okf:canon id=…`; a consumer carries a materialised copy inside an `okf:sync` marker set that
	// records where it came from and the hash of the payload at copy time. The generated
	// attribution callout sits outside the hashed payload.
	CanonEnd    = "<!-- /okf:canon -->"
	SyncBody    = "<!-- okf:sync-body -->"
	SyncEnd     = "<!-- /okf:sync -->"
	SyncOpenLit = "<!-- okf:sync "

	// CtxDir is the directory of the ctx bundles under the catalogue root. It counts as a bundle
	// directory although it starts with `_`; the ctx file model itself belongs to work package C.
	CtxDir = "_ctx"
)

// reserved is Python RESERVED: the file names that are not concepts, compared in lower case.
var reserved = map[string]bool{"index.md": true, "log.md": true, "readme.md": true, "index-map.md": true}

// IsReserved reports whether a file name is one of the reserved names (index.md, log.md,
// readme.md, index-map.md), case-insensitively.
func IsReserved(name string) bool { return reserved[pytext.Lower(name)] }

// ReservedNames is the reserved file names in lower case, sorted.
func ReservedNames() []string {
	return []string{"index-map.md", "index.md", "log.md", "readme.md"}
}

// FindReservedName is Python _find_reserved_name: the case-insensitive lookup of a reserved file
// name in a directory listing. It returns the actual on-disk name, preserving its case.
func FindReservedName(filenames []string, name string) (string, bool) {
	low := pytext.Lower(name)
	for _, f := range filenames {
		if pytext.Lower(f) == low {
			return f, true
		}
	}
	return "", false
}

var (
	// CanonOpenRE matches an `okf:canon` opening marker; group 1 is the block id.
	CanonOpenRE = pytext.Regexp(`<!--\s*okf:canon\s+id=([A-Za-z0-9._-]+)\s*-->`)
	// SyncOpenRE matches a generated `okf:sync` opening marker with the groups id, source and hash.
	// Attribute order is fixed because every marker is generated; a reordered marker is a hand
	// edit, and `malformed` is the correct report for one.
	SyncOpenRE = pytext.Regexp(`<!--\s*okf:sync\s+id=(?P<id>[A-Za-z0-9._-]+)` +
		`\s+source=(?P<source>\S+)` +
		`\s+hash=(?P<hash>[0-9a-f]{12})\s*-->`)
	// SyncSpanRE matches a materialised sync span from its opening `<!-- okf:sync ` through the
	// first `<!-- /okf:sync -->`.
	SyncSpanRE = pytext.Regexp(`<!--\s*okf:sync\s[\s\S]*?` + regexp.QuoteMeta(SyncEnd))
	// CrosslinkRE matches a markdown link `[text](target)`; group 1 is the text, group 2 the target.
	CrosslinkRE = regexp.MustCompile(`\[([^\]]+)\]\(([^)]+)\)`)
)
