// Package indexwrite is the managed index-block writer of the okf binary and the command reindex
// (Python okf.catalogue, writer half, and okf.index: plan_reindex, convert_flat_index,
// init_indexes, uncovered_index_dirs, cmd_reindex).
//
// The renderers and the block splice (RenderBlock, RenderTree, ManagedBlockFor,
// ReplaceManagedBlock), ReindexTree, PlanReindex and CtxIndexSkeleton are what the move core and
// the ctx commands import; they need neither the command wiring nor a catalogue root outside their
// arguments. Every reader goes through a catalogue.TreeView, so PlanReindex can plan the managed
// blocks of a tree that does not exist yet (the tree after a move).
package indexwrite

import (
	"path/filepath"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/diffs"
	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

// CtxIndexSkeleton is Python _CTX_INDEX_SKELETON: the text of the `_ctx/index.md` that the first
// ctx write creates, a title, one intro line and an empty managed block under `## Contents`.
const CtxIndexSkeleton = "# Context bundles\n\n" +
	"Curated, ordered reading lists per topic — one file per ctx slug, managed by `okf ctx`.\n\n" +
	"## Contents\n\n" + catalogue.MarkStart + "\n" + catalogue.MarkEnd + "\n"

// relSlash is os.path.relpath(p, root) with `/` separators.
func relSlash(root, p string) string {
	rel, err := filepath.Rel(root, p)
	if err != nil {
		return filepath.ToSlash(p)
	}
	return filepath.ToSlash(rel)
}

// walkDirs is the in-place prune every index walk applies to the directory names: dot directories
// and `assets` are not part of the OKF tree.
func walkDirs(dirnames []string) []string {
	kept := make([]string, 0, len(dirnames))
	for _, d := range dirnames {
		if !strings.HasPrefix(d, ".") && d != "assets" {
			kept = append(kept, d)
		}
	}
	return kept
}

// RenderBlock is Python render_block: the OKF bullet list of an index, subdirectories first, then
// concept files. Links are catalogue-root-absolute (`/bundle/subdir/concept.md`) so Obsidian
// resolves them from the vault root. dirRel is the index directory's path relative to the root
// ("" or "." is the root itself). A description is whitespace-collapsed and follows ` - `.
func RenderBlock(subdirs, concepts []catalogue.IndexRow, dirRel string) string {
	if dirRel == "." {
		dirRel = ""
	}
	dirRel = strings.Trim(dirRel, "/")
	prefix := "/"
	if dirRel != "" {
		prefix = "/" + dirRel + "/"
	}
	lines := make([]string, 0, len(subdirs)+len(concepts))
	row := func(r catalogue.IndexRow, tail string) {
		line := "* [" + r.Title + "](" + prefix + r.Name + tail + ")"
		if d := catalogue.Collapse(r.Description); d != "" {
			line += " - " + d
		}
		lines = append(lines, line)
	}
	for _, r := range subdirs {
		row(r, "/index.md")
	}
	for _, r := range concepts {
		row(r, ".md")
	}
	return strings.Join(lines, "\n")
}

// RenderTree is Python render_tree: the recursive variant of RenderBlock for a managed
// `index-map.md`. It lists the whole subtree below dir as a nested bullet list, two spaces per
// level, with the same link form and the same order (subdirectories first, then concepts). Only a
// subdirectory that carries an index.md is descended into.
func RenderTree(dir, root string, depth int, view catalogue.TreeView) (string, error) {
	dirRel := relSlash(root, dir)
	pad := strings.Repeat("  ", depth)
	var lines []string
	subs, err := catalogue.ListSubdirsWithIndex(dir, view)
	if err != nil {
		return "", err
	}
	for _, s := range subs {
		lines = append(lines, pad+RenderBlock([]catalogue.IndexRow{s}, nil, dirRel))
		child, err := RenderTree(catalogue.Join(dir, s.Name), root, depth+1, view)
		if err != nil {
			return "", err
		}
		if child != "" {
			lines = append(lines, child)
		}
	}
	concepts, err := catalogue.ListDirConcepts(dir, view)
	if err != nil {
		return "", err
	}
	if body := RenderBlock(nil, concepts, dirRel); body != "" {
		for _, ln := range strings.Split(body, "\n") {
			lines = append(lines, pad+ln)
		}
	}
	return strings.Join(lines, "\n"), nil
}

// ManagedBlockFor is Python managed_block_for: the generated block of one reserved index file, the
// recursive tree for `index-map.md`, one level for every other managed index. idxName is the file
// name on disk.
func ManagedBlockFor(dir, root, idxName string, view catalogue.TreeView) (string, error) {
	if pytext.Lower(idxName) == "index-map.md" {
		return RenderTree(dir, root, 0, view)
	}
	subs, err := catalogue.ListSubdirsWithIndex(dir, view)
	if err != nil {
		return "", err
	}
	concepts, err := catalogue.ListDirConcepts(dir, view)
	if err != nil {
		return "", err
	}
	return RenderBlock(subs, concepts, relSlash(root, dir)), nil
}

// ReplaceManagedBlock is Python replace_managed_block: text with the content between the markers
// replaced by block. found is false, and text returned as it is, when a marker is missing.
func ReplaceManagedBlock(text, block string) (string, bool) {
	si := strings.Index(text, catalogue.MarkStart)
	if si < 0 {
		return text, false
	}
	ei := strings.Index(text[si:], catalogue.MarkEnd)
	if ei < 0 {
		return text, false
	}
	ei += si
	inner := "\n"
	if block != "" {
		inner = "\n" + block + "\n"
	}
	return text[:si+len(catalogue.MarkStart)] + inner + text[ei:], true
}

// ReindexTree is Python reindex_tree: it refreshes the managed block of every `index.md` and
// `index-map.md` below dir (reserved names matched case-insensitively, dot directories and
// `assets` skipped, a file without the marker left alone), writes only the files that change and
// returns their root-relative paths in walk order. The ctx commands call it with the `_ctx`
// directory. Like Python it reads and rewrites a changed file through the lossy decode, so a
// changed file ends with LF line endings.
func ReindexTree(root, dir string) ([]string, error) {
	var changed []string
	var failure error
	catalogue.SortedWalk(dir, func(dp string, dn, fn []string) []string {
		if failure != nil {
			return nil
		}
		for _, name := range []string{"index.md", "index-map.md"} {
			idxName, ok := catalogue.FindReservedName(fn, name)
			if !ok {
				continue
			}
			idx := catalogue.Join(dp, idxName)
			text, err := catalogue.ReadFile(idx)
			if err != nil {
				failure = err
				return nil
			}
			if !strings.Contains(text, catalogue.MarkStart) {
				continue
			}
			block, err := ManagedBlockFor(dp, root, idxName, catalogue.RealFS)
			if err != nil {
				failure = err
				return nil
			}
			next, _ := ReplaceManagedBlock(text, block)
			if next == text {
				continue
			}
			if err := diffs.WriteFileVerbatim(idx, next); err != nil {
				failure = err
				return nil
			}
			changed = append(changed, relSlash(root, idx))
		}
		return walkDirs(dn)
	})
	return changed, failure
}
