package ctx

import (
	"os"
	"slices"
	"strconv"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/cli"
	"nas/volume1/data/git/okf-tools/go/internal/ctxfile"
	"nas/volume1/data/git/okf-tools/go/internal/diffs"
	"nas/volume1/data/git/okf-tools/go/internal/envelope"
	"nas/volume1/data/git/okf-tools/go/internal/indexwrite"
	"nas/volume1/data/git/okf-tools/go/internal/okferr"
	"nas/volume1/data/git/okf-tools/go/internal/pytext"
	"nas/volume1/data/git/okf-tools/go/internal/stdio"
)

// exists is Python os.path.exists: the path names something, symbolic links followed.
func exists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}

// save is Python save_ctx: it writes `_ctx/<slug>.md`, creates the `_ctx` index from its skeleton
// when it is missing and refreshes the managed index blocks under `_ctx`. The new text is made
// over the text the file has now (none for a new file), so the frontmatter of an existing bundle
// changes only through the line-patch writer, and the writer's rejection is raised before the
// first change on disk.
func save(root string, c ctxfile.Ctx) error {
	dir := catalogue.Join(root, catalogue.CtxDir)
	path := catalogue.Join(dir, c.Slug+".md")
	var existing *string
	if catalogue.RealFS.IsFile(path) {
		text, err := catalogue.ReadFile(path)
		if err != nil {
			return err
		}
		existing = &text
	}
	text, err := ctxfile.CtxText(c, existing)
	if err != nil {
		return err
	}
	if err := os.MkdirAll(dir, 0o777); err != nil {
		return err
	}
	if err := diffs.WriteFileVerbatim(path, text); err != nil {
		return err
	}
	if idx := catalogue.Join(dir, "index.md"); !exists(idx) {
		if err := diffs.WriteFileVerbatim(idx, indexwrite.CtxIndexSkeleton); err != nil {
			return err
		}
	}
	_, err = indexwrite.ReindexTree(root, dir)
	return err
}

// runCreate is Python cmd_ctx_create: a new bundle from the paths and the lines of an import file.
func runCreate(root string, a *cli.Args) (any, error) {
	slug := a.String("slug")
	if problem := ctxfile.CtxSlugProblem(slug); problem != "" {
		return nil, die(okferr.InvalidInput, `invalid slug "%s": %s`, slug, problem)
	}
	if exists(catalogue.Join(catalogue.Join(root, catalogue.CtxDir), slug+".md")) {
		return nil, die(okferr.InvalidInput, "%s already exists", slug)
	}
	type raw struct{ path, comment string }
	var paths []raw
	for _, p := range a.Strings("paths") {
		paths = append(paths, raw{p, ""})
	}
	if file := a.String("import_file"); file != "" {
		if !catalogue.RealFS.IsFile(file) {
			return nil, die(okferr.NotFound, "import file not found: %s", file)
		}
		text, err := catalogue.ReadFile(file)
		if err != nil {
			return nil, err
		}
		for _, line := range pytext.SplitLines(text, false) {
			if pytext.Strip(line) == "" || strings.HasPrefix(pytext.Lstrip(line), "#") {
				continue
			}
			p, comment, _ := strings.Cut(line, "\t")
			paths = append(paths, raw{p, pytext.Strip(comment)})
		}
	}
	if len(paths) == 0 {
		return nil, die(okferr.InvalidInput, "create needs at least one path")
	}
	seen := map[string]bool{}
	var entries []ctxfile.CtxEntry
	var missing []string
	for _, p := range paths {
		norm, ok := ctxfile.CtxNormalizePath(root, p.path, true)
		switch {
		case !ok:
			missing = append(missing, p.path)
		case !seen[norm]:
			seen[norm] = true
			entries = append(entries, ctxfile.CtxEntry{Mode: "pflicht", Path: norm, Comment: p.comment})
		}
	}
	if len(missing) > 0 {
		lines := make([]string, len(missing))
		for i, p := range missing {
			lines[i] = "ctx: not found: " + p
		}
		return nil, okferr.New(okferr.NotFound, strings.Join(lines, "\n"))
	}
	slices.SortStableFunc(entries, func(x, y ctxfile.CtxEntry) int {
		return strings.Compare(pytext.Casefold(x.Path), pytext.Casefold(y.Path))
	})
	if err := save(root, ctxfile.Ctx{Slug: slug, Description: a.String("description"), Entries: entries}); err != nil {
		return nil, err
	}
	if a.JSON {
		return envelope.O("applied", true, "slug", slug, "path", ctxRel(slug), "entries", len(entries)), nil
	}
	stdio.Printf("created %s (%d entries)\n", ctxRel(slug), len(entries))
	return nil, nil
}

// editable is Python _ctx_editable: the ctx for a row edit, refused when rows do not parse (a save
// would drop them), with its required entries in position order and its other entries. The
// entries are pointers into the ctx so that an entry keeps its identity while it moves.
func editable(root, slug string) (c ctxfile.LoadedCtx, required, rest []*ctxfile.CtxEntry, err error) {
	if c, err = ctxfile.LoadCtx(root, slug); err != nil {
		return c, nil, nil, err
	}
	if len(c.Problems) > 0 {
		return c, nil, nil, die(okferr.InvalidInput,
			"%s has %d parse problem(s) — fix with okf ctx edit, see okf ctx check", slug, len(c.Problems))
	}
	for i := range c.Entries {
		if e := &c.Entries[i]; e.Mode == "pflicht" {
			required = append(required, e)
		} else {
			rest = append(rest, e)
		}
	}
	required, err = byPos(slug, required, func(e *ctxfile.CtxEntry) *int { return e.Pos })
	return c, required, rest, err
}

// sameEntry is Python's == on two entries.
func sameEntry(a, b ctxfile.CtxEntry) bool {
	if (a.Pos == nil) != (b.Pos == nil) || (a.Pos != nil && *a.Pos != *b.Pos) {
		return false
	}
	return a.Mode == b.Mode && a.Path == b.Path && a.Comment == b.Comment
}

// where is Python _ctx_where: `pos N` for a required entry, `reference` for any other.
func where(required []*ctxfile.CtxEntry, e *ctxfile.CtxEntry) string {
	for i, x := range required {
		if sameEntry(*x, *e) {
			return "pos " + strconv.Itoa(i+1)
		}
	}
	return "reference"
}

// find is Python _ctx_find: the normalised path and the first entry that has it.
func find(root string, c ctxfile.LoadedCtx, rawPath string) (string, *ctxfile.CtxEntry) {
	norm, _ := ctxfile.CtxNormalizePath(root, rawPath, false)
	for i := range c.Entries {
		if c.Entries[i].Path == norm {
			return norm, &c.Entries[i]
		}
	}
	return norm, nil
}

// entriesOf is the values behind pointers.
func entriesOf(es []*ctxfile.CtxEntry) []ctxfile.CtxEntry {
	out := make([]ctxfile.CtxEntry, len(es))
	for i, e := range es {
		out[i] = *e
	}
	return out
}

// put is Python _ctx_put: e (in neither list) becomes an entry of mode at required position pos
// (clamped to 1..n+1; the end when none), the ctx is saved and the new place reported.
func put(root string, c ctxfile.LoadedCtx, required, rest []*ctxfile.CtxEntry, e *ctxfile.CtxEntry,
	mode string, pos *int) (string, error) {
	e.Mode = mode
	if mode == "pflicht" {
		at := len(required)
		if pos != nil {
			at = max(1, min(*pos, len(required)+1)) - 1
		}
		required = slices.Insert(required, at, e)
	} else {
		rest = append(rest, e)
	}
	err := save(root, ctxfile.Ctx{Slug: c.Slug, Description: c.Description,
		Entries: entriesOf(append(slices.Clone(required), rest...))})
	return where(required, e), err
}

// optInt is the value of an optional integer option, nil when it is absent.
func optInt(a *cli.Args, dest string) *int {
	if !a.Has(dest) {
		return nil
	}
	v := a.Int(dest)
	return &v
}

// runAdd is Python cmd_ctx_add: one new entry, required (at a position) or reference.
func runAdd(root string, a *cli.Args) (any, error) {
	slug, mode, pos := a.String("slug"), a.String("mode"), optInt(a, "pos")
	c, required, rest, err := editable(root, slug)
	if err != nil {
		return nil, err
	}
	if pos != nil && mode != "pflicht" {
		return nil, die(okferr.InvalidInput, "--pos applies only to mode pflicht")
	}
	norm, ok := ctxfile.CtxNormalizePath(root, a.String("path"), true)
	if !ok {
		return nil, die(okferr.NotFound, "not found: %s", a.String("path"))
	}
	for i := range c.Entries {
		if c.Entries[i].Path == norm {
			return nil, die(okferr.InvalidInput, "%s is already in %s (%s)", norm, slug, where(required, &c.Entries[i]))
		}
	}
	at, err := put(root, c, required, rest, &ctxfile.CtxEntry{Path: norm, Comment: a.String("comment")}, mode, pos)
	if err != nil {
		return nil, err
	}
	if a.JSON {
		return envelope.O("applied", true, "slug", slug, "path", norm, "where", at), nil
	}
	stdio.Printf("added %s to %s (%s)\n", norm, slug, at)
	return nil, nil
}

// runDrop is Python cmd_ctx_drop: one entry removed, also when its file is gone.
func runDrop(root string, a *cli.Args) (any, error) {
	slug := a.String("slug")
	c, required, rest, err := editable(root, slug)
	if err != nil {
		return nil, err
	}
	norm, e := find(root, c, a.String("path"))
	if e == nil {
		return nil, die(okferr.NotFound, "%s is not in %s", norm, slug)
	}
	keep := slices.DeleteFunc(append(slices.Clone(required), rest...), func(x *ctxfile.CtxEntry) bool { return x == e })
	if err := save(root, ctxfile.Ctx{Slug: slug, Description: c.Description, Entries: entriesOf(keep)}); err != nil {
		return nil, err
	}
	if a.JSON {
		return envelope.O("applied", true, "slug", slug, "path", norm), nil
	}
	stdio.Printf("dropped %s from %s\n", norm, slug)
	return nil, nil
}

// runMove is Python cmd_ctx_move: an entry to another required position and/or another mode.
func runMove(root string, a *cli.Args) (any, error) {
	slug, pos := a.String("slug"), optInt(a, "pos")
	c, required, rest, err := editable(root, slug)
	if err != nil {
		return nil, err
	}
	if pos == nil && !a.Has("mode") {
		return nil, die(okferr.InvalidInput, "move needs --pos or --mode")
	}
	norm, e := find(root, c, a.String("path"))
	if e == nil {
		return nil, die(okferr.NotFound, "%s is not in %s", norm, slug)
	}
	mode := e.Mode
	if a.Has("mode") {
		mode = a.String("mode")
	}
	if pos != nil && mode != "pflicht" {
		return nil, die(okferr.InvalidInput, "--pos applies only to mode pflicht")
	}
	isNot := func(x *ctxfile.CtxEntry) bool { return x == e }
	required = slices.DeleteFunc(required, isNot)
	rest = slices.DeleteFunc(rest, isNot)
	at, err := put(root, c, required, rest, e, mode, pos)
	if err != nil {
		return nil, err
	}
	if a.JSON {
		return envelope.O("applied", true, "slug", slug, "path", norm, "where", at), nil
	}
	stdio.Printf("moved %s in %s to %s\n", norm, slug, at)
	return nil, nil
}
