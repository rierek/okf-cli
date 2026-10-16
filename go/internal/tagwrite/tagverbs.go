package tagwrite

import (
	"fmt"
	"io"
	"slices"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/cli"
	"nas/volume1/data/git/okf-tools/go/internal/complete"
	"nas/volume1/data/git/okf-tools/go/internal/diffs"
	"nas/volume1/data/git/okf-tools/go/internal/envelope"
	"nas/volume1/data/git/okf-tools/go/internal/frontmatter"
	"nas/volume1/data/git/okf-tools/go/internal/where"
	"nas/volume1/data/git/okf-tools/go/internal/yamlpatch"
)

// notAList is the reason of a file whose `tags` is no YAML list (`tags: a, b`).
const notAList = "tags field not in inline/block form"

func registerTagVerbs(app *cli.App) {
	apply := cli.Arg{Flags: []string{"--apply"}, Action: cli.StoreTrue, Help: "write changes (default: dry-run preview only)"}
	app.Attach("merge-tags", cli.Spec{
		Args: []cli.Arg{
			{Dest: "tags", Nargs: cli.OneOrMore, Help: "source tag(s) to merge, e.g. workflow workflows"},
			{Flags: []string{"--into"}, Required: true, Metavar: []string{"TAG"}, Help: "destination tag name"},
			cli.WhereArg(), apply, cli.JSON(),
		},
		Handler: runMergeTags,
	})
	app.Attach("normalize-tags", cli.Spec{
		Args:    []cli.Arg{cli.WhereArg(), apply, cli.JSON()},
		Handler: runNormalizeTags,
	})
	app.Attach("remove-tags", cli.Spec{
		Args: []cli.Arg{
			{Dest: "tags", Nargs: cli.OneOrMore, Help: "tag(s) to remove, e.g. stale draft"},
			cli.WhereArg(), apply, cli.JSON(),
		},
		Handler: runRemoveTags,
	})
	complete.Attach([]string{"merge-tags"}, "tags", complete.Tags)
	complete.Attach([]string{"merge-tags"}, "into", complete.Tags)
	complete.Attach([]string{"remove-tags"}, "tags", complete.Tags)
}

// concept is one concept file a tag verb looks at: its catalogue-relative path, its frontmatter as
// read for matching (undecodable bytes replaced) and its text as stored (ok false: not valid UTF-8,
// so a rewrite would corrupt it).
type concept struct {
	rel    string
	doc    frontmatter.Doc
	stored string
	ok     bool
}

// selectedConcepts is Python _selected_concepts: every concept the --where expression selects, every
// concept without one. Staging directories are not pruned: the write verbs must reach staging
// content too, or a tag change silently leaves the old tag behind there.
func selectedConcepts(root string, a *cli.Args) ([]concept, error) {
	var text *string
	if a.Has("where") {
		expr := a.String("where")
		text = &expr
	}
	filters, err := where.CompileWhere(text, false, nil)
	if err != nil {
		return nil, err
	}
	scopes, err := catalogue.ResolveScopes(root, "", filters.IncludeArchive(), false)
	if err != nil {
		return nil, err
	}
	var out []concept
	for _, scope := range scopes {
		for _, ap := range catalogue.IterConcepts(scope.Path, false) {
			decoded, err := catalogue.ReadFile(ap)
			if err != nil {
				return nil, err
			}
			stored, ok, err := catalogue.ReadFileVerbatim(ap)
			if err != nil {
				return nil, err
			}
			c := concept{rel: relPath(root, ap), doc: frontmatter.Read(decoded), stored: stored, ok: ok}
			if filters.HasExpression() && !filters.MatchesLoaded(strings.TrimSuffix(c.rel, ".md"), c.doc.Data()) {
				continue
			}
			out = append(out, c)
		}
	}
	return out, nil
}

// unparseableReason is Python _unparseable_reason: why a write verb leaves the file alone when its
// frontmatter does not parse or the file is not valid UTF-8, else "".
func (c concept) unparseableReason() string {
	switch {
	case !c.ok:
		return "file is not valid UTF-8"
	case c.doc.Head != "" && c.doc.Data() == nil:
		return "frontmatter does not parse: " + c.doc.Err
	}
	return ""
}

// skipped is one file a tag verb leaves alone, with the reason.
type skipped struct{ rel, reason string }

func relsOf(files []skipped) []string {
	rels := make([]string, len(files))
	for i, f := range files {
		rels[i] = f.rel
	}
	return rels
}

// tagItems is the item nodes of the `tags` list of a concept, or ok false when `tags` is no YAML
// list (Python _retag's None).
func tagItems(c concept) (items []string, ok bool) {
	node := frontmatter.Lookup(c.doc.Data(), "tags")
	if !frontmatter.IsSeq(node) {
		return nil, false
	}
	for _, item := range frontmatter.Elems(node) {
		items = append(items, frontmatter.ScalarText(item))
	}
	return items, true
}

// hasAny reports whether tags (Python tags_of) holds one of the wanted tags.
func hasAny(tags []string, wanted map[string]bool) bool {
	return slices.ContainsFunc(tags, func(t string) bool { return wanted[t] })
}

// writeResult is Python _write_result: the unified diffs of the plan, the new texts written on
// --apply and, in text mode, the diffs and the skipped files. The plan holds only finished texts, so
// a refusal of the frontmatter writer has ended the run before this writes anything.
func writeResult(w io.Writer, root string, a *cli.Args, plan []diffs.PlanEntry, unparseable []skipped) ([]diffs.FileDiff, error) {
	files := diffs.UnifiedDiffs(plan, nil)
	if a.Bool("apply") {
		if err := diffs.WritePlan(root, plan); err != nil {
			return nil, err
		}
	}
	if !a.JSON {
		printDiffs(w, files)
		for _, u := range unparseable {
			fmt.Fprintf(w, "unparseable    %s  (%s \u2014 skipped)\n", u.rel, u.reason)
		}
	}
	return files, nil
}

// verbOf is the verb of the summary line: what the run did or would do.
func verbOf(a *cli.Args) string {
	if a.Bool("apply") {
		return "rewrote"
	}
	return "would rewrite"
}

// runMergeTags is Python cmd_merge_tags: the source tags renamed to --into in place, one list item
// at a time so the comment and quoting of every other item stay; a later item that would repeat a
// tag already kept is dropped.
func runMergeTags(root string, a *cli.Args) (any, error) {
	sources := map[string]bool{}
	for _, t := range a.Strings("tags") {
		sources[t] = true
	}
	into := a.String("into")
	concepts, err := selectedConcepts(root, a)
	if err != nil {
		return nil, err
	}
	var plan []diffs.PlanEntry
	var unparseable []skipped
	for _, c := range concepts {
		if reason := c.unparseableReason(); reason != "" {
			unparseable = append(unparseable, skipped{c.rel, reason})
			continue
		}
		if !hasAny(frontmatter.Tags(c.doc.Data()), sources) {
			continue
		}
		items, ok := tagItems(c)
		if !ok {
			unparseable = append(unparseable, skipped{c.rel, notAList})
			continue
		}
		seen := map[string]bool{}
		var edits []yamlpatch.Edit
		for i, old := range items {
			renamed := old
			if sources[old] {
				renamed = into
			}
			switch {
			case seen[renamed]:
				edits = append(edits, yamlpatch.DeleteItem("tags", i))
			case renamed != old:
				edits = append(edits, yamlpatch.RenameItem("tags", i, renamed))
			}
			seen[renamed] = true
		}
		// The edits run from the last item to the first, so an index still counts in the list as it
		// stands when its edit runs.
		slices.Reverse(edits)
		text, err := patch(c, edits)
		if err != nil {
			return nil, err
		}
		plan = append(plan, planEntry(c.rel, c.stored, text))
	}
	w := newOut()
	defer w.Flush()
	files, err := writeResult(w, root, a, plan, unparseable)
	if err != nil {
		return nil, err
	}
	if a.JSON {
		return envelope.O("applied", a.Bool("apply"), "unparseable", relsOf(unparseable),
			"from", sortedKeys(sources), "into", into, "files", diffData(files)), nil
	}
	fmt.Fprintf(w, "merge-tags: %d file(s) %s, %d unparseable \u2014 %s -> %s\n",
		len(files), verbOf(a), len(unparseable), strings.Join(sortedKeys(sources), ", "), into)
	return nil, nil
}

// runRemoveTags is Python cmd_remove_tags: the tags removed from every selected concept. Emptying
// the tag list strips the whole `tags:` key (no dangling key).
func runRemoveTags(root string, a *cli.Args) (any, error) {
	targets := map[string]bool{}
	for _, t := range a.Strings("tags") {
		targets[t] = true
	}
	concepts, err := selectedConcepts(root, a)
	if err != nil {
		return nil, err
	}
	var plan []diffs.PlanEntry
	var unparseable []skipped
	emptied := []string{}
	for _, c := range concepts {
		if reason := c.unparseableReason(); reason != "" {
			unparseable = append(unparseable, skipped{c.rel, reason})
			continue
		}
		if !hasAny(frontmatter.Tags(c.doc.Data()), targets) {
			continue
		}
		items, ok := tagItems(c)
		if !ok {
			unparseable = append(unparseable, skipped{c.rel, notAList})
			continue
		}
		var edits []yamlpatch.Edit
		for i := len(items) - 1; i >= 0; i-- {
			if targets[items[i]] {
				edits = append(edits, yamlpatch.DeleteItem("tags", i))
			}
		}
		if len(edits) == len(items) {
			edits = append(edits, yamlpatch.DeleteKey("tags"))
			emptied = append(emptied, c.rel)
		}
		text, err := patch(c, edits)
		if err != nil {
			return nil, err
		}
		plan = append(plan, planEntry(c.rel, c.stored, text))
	}
	w := newOut()
	defer w.Flush()
	files, err := writeResult(w, root, a, plan, unparseable)
	if err != nil {
		return nil, err
	}
	if a.JSON {
		return envelope.O("applied", a.Bool("apply"), "emptied", emptied, "unparseable", relsOf(unparseable),
			"removed", sortedKeys(targets), "files", diffData(files)), nil
	}
	fmt.Fprintf(w, "remove-tags: %d file(s) %s, %d emptied, %d unparseable \u2014 removed %s\n",
		len(files), verbOf(a), len(emptied), len(unparseable), strings.Join(sortedKeys(targets), ", "))
	return nil, nil
}

// runNormalizeTags is Python cmd_normalize_tags: every non-empty flow-style `tags: [a, b]` list
// turned into a block list. A local convention of this catalogue, not an OKF requirement: both
// forms stay valid. A file whose frontmatter does not parse is never written.
func runNormalizeTags(root string, a *cli.Args) (any, error) {
	concepts, err := selectedConcepts(root, a)
	if err != nil {
		return nil, err
	}
	var plan []diffs.PlanEntry
	var unparseable []skipped
	for _, c := range concepts {
		if reason := c.unparseableReason(); reason != "" {
			unparseable = append(unparseable, skipped{c.rel, reason})
			continue
		}
		if frontmatter.FlowTags(c.doc.Data()) == nil {
			continue
		}
		text, err := patch(c, []yamlpatch.Edit{yamlpatch.FlowToBlock("tags")})
		if err != nil {
			return nil, err
		}
		plan = append(plan, planEntry(c.rel, c.stored, text))
	}
	w := newOut()
	defer w.Flush()
	files, err := writeResult(w, root, a, plan, unparseable)
	if err != nil {
		return nil, err
	}
	if a.JSON {
		return envelope.O("applied", a.Bool("apply"), "unparseable", relsOf(unparseable), "files", diffData(files)), nil
	}
	fmt.Fprintf(w, "normalize-tags: %d file(s) %s, %d unparseable\n", len(files), verbOf(a), len(unparseable))
	return nil, nil
}

// patch is the new text of a concept after the edits; a refusal of the frontmatter writer names the
// file and ends the run (R-04).
func patch(c concept, edits []yamlpatch.Edit) (string, error) {
	text, err := yamlpatch.Apply(c.stored, edits...)
	if err != nil {
		return "", patchError(c.rel, err)
	}
	return text, nil
}

// sortedKeys is sorted(set): the members in code point order.
func sortedKeys(set map[string]bool) []string {
	keys := make([]string, 0, len(set))
	for k := range set {
		keys = append(keys, k)
	}
	slices.Sort(keys)
	return keys
}
