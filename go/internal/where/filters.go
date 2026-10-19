package where

import (
	"errors"
	"io/fs"
	"slices"
	"strings"
	"time"

	"go.yaml.in/yaml/v3"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/frontmatter"
	"nas/volume1/data/git/okf-tools/go/internal/spec"
)

// archivePrefix is the directory of archived concepts.
const archivePrefix = "_archive/"

// FindFilters is the `--where` expression as ONE value, with the predicate defined once. Build it
// with CompileWhere. The filters describe the ANSWER, not one arm of it: whichever arm ends up
// owning the ranking, the same predicate holds.
//
// Two rules sit beside the expression, not in it:
//
//	archive  a path under `_archive/` is no match unless the expression names `archived` (R-08);
//	         the expression then decides alone and IncludeArchive is true, so every traversal
//	         reaches the archive
//	corpus   with corpus bundles set, a path outside those bundles is no match; an archived path
//	         compares without its `_archive/` prefix (R-09)
//
// IncludeTopics only tells the lexical arms which corpus to read.
//
// Arms consume the value one of two ways, and both hand back what they did NOT cover so that
// skipping a conjunct is visible instead of silent: SQLWhere for arms that filter in the
// database, Matches and MatchesLoaded for arms that walk the file tree.
type FindFilters struct {
	tree           node // the syntax tree of --where, nil without one
	includeArchive bool
	includeTopics  bool
	corpusBundles  []string
	now            time.Time // the one instant of the call, for `stale` and the records
}

func newFindFilters(tree node, includeTopics bool, corpusBundles []string, now time.Time) *FindFilters {
	return &FindFilters{
		tree:           tree,
		includeArchive: mentions(tree, "archived"),
		includeTopics:  includeTopics,
		corpusBundles:  slices.Clone(corpusBundles),
		now:            now,
	}
}

// mentions is true when the expression tree references field; a nil tree is the empty expression.
func mentions(n node, field string) bool {
	switch n := n.(type) {
	case andNode:
		return mentions(n.left, field) || mentions(n.right, field)
	case orNode:
		return mentions(n.left, field) || mentions(n.right, field)
	case notNode:
		return mentions(n.operand, field)
	case compareNode:
		return n.field == field
	case inNode:
		return n.field == field
	}
	return false
}

// CompileWhere is Python compile_where: the filter value of one `--where` expression, or of none
// (text nil: only the archive default and the corpus rule apply). It returns invalid_input for a
// syntax error and for semantic misuse of a field. The instant of the call is taken here.
func CompileWhere(text *string, includeTopics bool, corpusBundles []string) (*FindFilters, error) {
	var tree node
	if text != nil {
		var err error
		if tree, err = parseWhere(*text); err != nil {
			return nil, err
		}
		if err = validate(tree); err != nil {
			return nil, err
		}
	}
	return newFindFilters(tree, includeTopics, corpusBundles, spec.Utcnow()), nil
}

// Now is the one instant of the call, the clock of `stale` and of the records.
func (f *FindFilters) Now() time.Time { return f.now }

// IncludeArchive is true when the expression names `archived`, so every traversal reaches the
// archive.
func (f *FindFilters) IncludeArchive() bool { return f.includeArchive }

// IncludeTopics tells the lexical arms to read the topic corpus too.
func (f *FindFilters) IncludeTopics() bool { return f.includeTopics }

// HasExpression is Python's truthiness of the value: whether an expression restricts the result.
// Neither the archive default nor the corpus rule count; PathVisible enforces those.
func (f *FindFilters) HasExpression() bool { return f.tree != nil }

// PathVisible holds R-08 and R-09, next to the expression because they are the same predicate: a
// path under `_archive/` is invisible unless the expression names `archived`, and with a corpus a
// path outside it is invisible. Any caller that walks paths in Go (not SQL) gets both rules by
// calling this, not by re-deriving them.
func (f *FindFilters) PathVisible(path string) bool {
	archived := strings.HasPrefix(path, archivePrefix)
	if archived && !f.includeArchive {
		return false
	}
	if len(f.corpusBundles) == 0 {
		return true
	}
	compared := path
	if archived {
		compared = path[len(archivePrefix):]
	}
	return slices.ContainsFunc(f.corpusBundles, func(b string) bool {
		return compared == b || strings.HasPrefix(compared, b+"/")
	})
}

// MatchesLoaded is the full predicate for a concept whose frontmatter the caller already read: fm
// is the root mapping, nil for a concept without a readable frontmatter block.
func (f *FindFilters) MatchesLoaded(path string, fm *yaml.Node) bool {
	return f.PathVisible(path) && (f.tree == nil ||
		evaluate(f.tree, path, func() *yaml.Node { return fm }, f.now))
}

// Matches is the same predicate, reading the concept file `<root>/<path>.md` only when the
// expression needs a field beyond the path, and then once. It checks the path rules first so a
// filtered-out path costs no disk read. A path that no longer resolves fails; any other read error
// is returned.
//
// There is no shortcut for an empty value: the archive default is itself a restriction, so even a
// value without an expression runs PathVisible.
func (f *FindFilters) Matches(root, path string) (bool, error) {
	if !f.PathVisible(path) {
		return false, nil
	}
	if f.tree == nil {
		return true, nil
	}
	var (
		fm      *yaml.Node
		loaded  bool
		loadErr error
	)
	load := func() *yaml.Node {
		if !loaded {
			loaded = true
			text, err := catalogue.ReadFile(catalogue.Join(root, path+".md"))
			if err != nil {
				loadErr = err
			} else {
				fm = frontmatter.Read(text).Data()
			}
		}
		return fm
	}
	matched := evaluate(f.tree, path, load, f.now)
	switch {
	case errors.Is(loadErr, fs.ErrNotExist):
		return false, nil
	case loadErr != nil:
		return false, loadErr
	}
	return matched, nil
}
