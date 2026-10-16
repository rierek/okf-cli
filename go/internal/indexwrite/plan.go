package indexwrite

import (
	"path/filepath"
	"slices"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/diffs"
	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

// The statuses of ConvertFlatIndex. "unreadable" is added by InitIndexes for a file that is not
// valid UTF-8.
const (
	StatusConverted        = "converted"
	StatusAlreadyManaged   = "already-managed"
	StatusSkipMultiSection = "skip-multi-section"
	StatusSkipTrailing     = "skip-trailing-content"
	StatusSkipNoList       = "skip-no-list"
	StatusUnreadable       = "unreadable"
)

var bulletRE = pytext.Regexp(`^[*\-+]\s`)

// ConvertFlatIndex is Python convert_flat_index: the migration of a marker-less, hand-curated
// index.md to a managed marker block. It returns the new text and the status. A single-section
// listing (one `## ` section whose tail is only a bullet list) always converts; a multi-section
// listing converts only with force, and only when every section body is headings and bullets;
// prose or a table is real content and refuses; a missing list is flagged.
func ConvertFlatIndex(text string, force bool) (string, string) {
	if strings.Contains(text, catalogue.MarkStart) {
		return text, StatusAlreadyManaged
	}
	lines := pytext.SplitLines(text, false)
	var h2 []int
	for _, h := range catalogue.IterHeadings(text) {
		if h.Level == 2 {
			h2 = append(h2, h.Line)
		}
	}
	if len(h2) == 0 {
		return text, StatusSkipNoList
	}
	multi := len(h2) >= 2
	if multi && !force {
		return text, StatusSkipMultiSection
	}
	first := h2[0]
	sawBullet, sawProse := false, false
	for i := first + 1; i < len(lines); i++ {
		s := pytext.Strip(lines[i])
		if s == "" || slices.Contains(h2, i) {
			continue // blank or sub-section heading: allowed
		}
		if bulletRE.MatchString(s) {
			sawBullet = true
		} else {
			sawProse = true // prose or a table is real content
		}
	}
	if !sawBullet {
		return text, StatusSkipNoList
	}
	if sawProse {
		return text, StatusSkipTrailing
	}
	head := pytext.Rstrip(strings.Join(lines[:first], "\n"))
	section := "## Contents"
	if !multi {
		section = pytext.Rstrip(lines[first])
	}
	return head + "\n\n" + section + "\n\n" + catalogue.MarkStart + "\n" + catalogue.MarkEnd + "\n", StatusConverted
}

// IndexStub is Python index_stub: the text of the index.md that `reindex --init` creates in dir
// when it has none, a title (the directory name) and an empty marker block.
func IndexStub(dir string) string {
	abs, err := catalogue.Abspath(dir)
	title := ""
	if err == nil && abs != "/" {
		title = filepath.Base(abs)
	}
	return "# " + title + "\n\n## Contents\n\n" + catalogue.MarkStart + "\n" + catalogue.MarkEnd + "\n"
}

// InitResult is one (root-relative path, status) result of InitIndexes.
type InitResult struct{ Rel, Status string }

// InitIndexes is Python init_indexes: it walks the target subtree on disk and converts each
// marker-less flat index.md with ConvertFlatIndex. It writes nothing. results are sorted by path;
// plan holds the (stored, converted) text of the converted files.
func InitIndexes(root, target string, force bool) (results []InitResult, plan []diffs.PlanEntry, err error) {
	catalogue.SortedWalk(target, func(dp string, dn, fn []string) []string {
		if err != nil {
			return nil
		}
		if idxName, ok := catalogue.FindReservedName(fn, "index.md"); ok {
			idx := catalogue.Join(dp, idxName)
			rel := relSlash(root, idx)
			text, readable, rerr := catalogue.ReadFileVerbatim(idx)
			switch {
			case rerr != nil:
				err = rerr
				return nil
			case !readable:
				results = append(results, InitResult{rel, StatusUnreadable})
			default:
				next, status := ConvertFlatIndex(text, force)
				if status == StatusConverted {
					plan = append(plan, diffs.PlanEntry{Path: rel, Old: &text, New: &next})
				}
				results = append(results, InitResult{rel, status})
			}
		}
		return walkDirs(dn)
	})
	slices.SortFunc(results, func(a, b InitResult) int {
		if c := strings.Compare(a.Rel, b.Rel); c != 0 {
			return c
		}
		return strings.Compare(a.Status, b.Status)
	})
	return results, plan, err
}

// ReindexInfo is what PlanReindex reports beside the plan: Init holds the results of InitIndexes
// (nil without init), Stale the paths whose managed block is out of date, Skipped the index files
// without markers and Unreadable those that are not valid UTF-8.
type ReindexInfo struct {
	Init                       []InitResult
	Stale, Skipped, Unreadable []string
}

// PlanReindex is Python plan_reindex: the final text of every index file the `reindex` write run
// changes or creates. With init that is the stub of a missing index.md in dir, then the flat-index
// conversions, then the refreshed managed blocks: one (rel, stored text, new text) entry per file
// (a nil Old is a created file), in the order the files first entered the plan. It writes nothing.
// dir is absolute; the tree is read through view, so the move core plans the blocks of the tree
// after a move; init and the real-disk walk of its conversions always read the disk.
func PlanReindex(root, dir string, init, force bool, view catalogue.TreeView) ([]diffs.PlanEntry, ReindexInfo, error) {
	stored := map[string]*string{}
	final := map[string]string{}
	var order []string
	put := func(rel string, old *string, text string) {
		if _, seen := final[rel]; !seen {
			order = append(order, rel)
		}
		if _, seen := stored[rel]; !seen {
			stored[rel] = old
		}
		final[rel] = text
	}
	info := ReindexInfo{Stale: []string{}, Skipped: []string{}, Unreadable: []string{}}
	created := ""
	if init {
		idx := catalogue.Join(dir, "index.md")
		if !catalogue.RealFS.IsFile(idx) {
			created = relSlash(root, idx)
			put(created, nil, IndexStub(dir))
		}
		results, conv, err := InitIndexes(root, dir, force)
		if err != nil {
			return nil, info, err
		}
		info.Init = results
		for _, c := range conv {
			put(c.Path, c.Old, *c.New)
		}
	}
	type indexFile struct{ dir, name string }
	var files []indexFile
	view.Walk(dir, func(dp string, dn, fn []string) []string {
		if created != "" && dp == dir && !slices.Contains(fn, "index.md") {
			fn = append(slices.Clone(fn), "index.md") // the write run walks the file it created
		}
		for _, name := range []string{"index.md", "index-map.md"} {
			if idxName, ok := catalogue.FindReservedName(fn, name); ok {
				files = append(files, indexFile{dp, idxName})
			}
		}
		return walkDirs(dn)
	})
	slices.SortFunc(files, func(a, b indexFile) int {
		if c := strings.Compare(a.dir, b.dir); c != 0 {
			return c
		}
		return strings.Compare(a.name, b.name)
	})
	for _, f := range files {
		idx := catalogue.Join(f.dir, f.name)
		rel := relSlash(root, idx)
		var text string
		if t, ok := final[rel]; ok {
			text = t
		} else {
			t, readable, err := view.ReadVerbatim(idx)
			if err != nil {
				return nil, info, err
			}
			if !readable {
				info.Unreadable = append(info.Unreadable, rel)
				continue
			}
			text = t
		}
		if !strings.Contains(text, catalogue.MarkStart) {
			info.Skipped = append(info.Skipped, rel)
			continue
		}
		block, err := ManagedBlockFor(f.dir, root, f.name, view)
		if err != nil {
			return nil, info, err
		}
		next, _ := ReplaceManagedBlock(text, block)
		if next == text {
			continue
		}
		info.Stale = append(info.Stale, rel)
		put(rel, &text, next)
	}
	plan := make([]diffs.PlanEntry, len(order))
	for i, rel := range order {
		next := final[rel]
		plan[i] = diffs.PlanEntry{Path: rel, Old: stored[rel], New: &next}
	}
	return plan, info, nil
}

// UncoveredIndexDirs is Python uncovered_index_dirs: the sorted root-relative paths of the
// marker-less index files whose directory holds concept files, which no coverage net proves
// listed. An index with the managed marker or the exempt marker is not reported. target is the
// directory to walk, absolute or relative to root.
func UncoveredIndexDirs(root, target string) ([]string, error) {
	out := []string{}
	var failure error
	catalogue.SortedWalk(catalogue.Join(root, target), func(dp string, dn, fn []string) []string {
		if failure != nil {
			return nil
		}
		if idxName, ok := catalogue.FindReservedName(fn, "index.md"); ok {
			idx := catalogue.Join(dp, idxName)
			text, err := catalogue.ReadFile(idx)
			if err != nil {
				failure = err
				return nil
			}
			if !strings.Contains(text, catalogue.MarkStart) && !strings.Contains(text, catalogue.Exempt) {
				concepts, err := catalogue.ListDirConcepts(dp, catalogue.RealFS)
				if err != nil {
					failure = err
					return nil
				}
				if len(concepts) > 0 {
					out = append(out, relSlash(root, idx))
				}
			}
		}
		return walkDirs(dn)
	})
	slices.Sort(out)
	return out, failure
}
