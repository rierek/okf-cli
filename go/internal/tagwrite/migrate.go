package tagwrite

import (
	"fmt"
	"maps"
	"slices"
	"strings"

	"go.yaml.in/yaml/v3"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/cli"
	"nas/volume1/data/git/okf-tools/go/internal/complete"
	"nas/volume1/data/git/okf-tools/go/internal/diffs"
	"nas/volume1/data/git/okf-tools/go/internal/envelope"
	"nas/volume1/data/git/okf-tools/go/internal/frontmatter"
	"nas/volume1/data/git/okf-tools/go/internal/history"
	"nas/volume1/data/git/okf-tools/go/internal/okferr"
	"nas/volume1/data/git/okf-tools/go/internal/pytext"
	"nas/volume1/data/git/okf-tools/go/internal/spec"
	"nas/volume1/data/git/okf-tools/go/internal/yamlpatch"
)

// migrateStatus is the binding, complete per-value `status` decision (Python STATUS_MAP, D37).
var migrateStatus = map[string]string{
	"obsolete": "deprecated", "deleted": "deprecated", "archived": "deprecated",
	"accepted": "stable", "active": "stable", "passive": "stable", "stable": "stable",
	"todo": "draft", "planned": "draft", "in-bearbeitung": "draft", "experimental": "draft",
	"draft": "draft", "deprecated": "deprecated",
}

// registerMigrate attaches `migrate` (Python add_migrate_parser) and the scope completer of its target.
func registerMigrate(app *cli.App) {
	app.Attach("migrate", cli.Spec{
		Args: []cli.Arg{
			{Dest: "target", Nargs: cli.Optional, Help: "<bundle> or <bundle>/<subdir> (default: whole catalogue)"},
			{Flags: []string{"--apply"}, Action: cli.StoreTrue,
				Help: "write the previewed changes (default: dry-run preview only)"},
			cli.JSON(),
		},
		Handler: runMigrate,
	})
	complete.Attach([]string{"migrate"}, "target", complete.Scopes)
}

// migrateIssue is one unresolved point of a concept: {path, field, reason}.
type migrateIssue struct{ path, field, reason string }

// migrateRun is the plan of one `migrate` run (Python _plan): the new texts, what stays unresolved
// and how many concepts hold each old status value.
type migrateRun struct {
	root    string
	authors map[string]string
	hist    *history.History
	plan    []diffs.PlanEntry
	issues  []migrateIssue
	counts  map[string]int
}

// migrateAuthors is Python _author_table: the `git_authors` table of `.okf.toml` ({email: actor}).
// A table that is none, or a value that follows no actor convention, is invalid_input before any
// file is planned.
func migrateAuthors(root string) (map[string]string, error) {
	config, err := catalogue.LoadConfig(root)
	if err != nil {
		return nil, err
	}
	raw, present := config["git_authors"]
	if !present {
		return map[string]string{}, nil
	}
	table, ok := raw.(map[string]any)
	if !ok {
		return nil, okferr.New(okferr.InvalidInput, "git_authors in .okf.toml is not a table of email = actor")
	}
	authors := make(map[string]string, len(table))
	// ponytail: the first offender in key order is named, Python names the first in file order;
	// the TOML metadata of a second decode would give that order if it ever matters.
	for _, email := range slices.Sorted(maps.Keys(table)) {
		actor, _ := table[email].(string)
		if _, _, ok := spec.ParseActorText(actor); !ok {
			return nil, okferr.Newf(okferr.InvalidInput, "git_authors[%s] in .okf.toml is not an actor "+
				"(human:<id>, process:<id> or <producer>/<version>): %s", email, pytext.Repr(table[email]))
		}
		authors[email] = actor
	}
	return authors, nil
}

// planMigrate is Python _plan: every concept under the target, its edits applied to the stored text
// in memory. A concept whose edits the writer refuses ends the run before anything is written.
func planMigrate(root, target string) (*migrateRun, error) {
	authors, err := migrateAuthors(root)
	if err != nil {
		return nil, err
	}
	m := &migrateRun{root: root, authors: authors, hist: history.New(root), counts: map[string]int{}}
	defer m.hist.Close()
	scopes, err := catalogue.ResolveScopes(root, target, false, false)
	if err != nil {
		return nil, err
	}
	for _, scope := range scopes {
		for _, ap := range catalogue.IterConcepts(scope.Path, true) {
			if err := m.concept(ap); err != nil {
				return nil, err
			}
		}
	}
	for _, note := range m.hist.Notes() {
		envelope.Note(note)
	}
	return m, nil
}

// concept plans one file: status, then `timestamp` to `generated`, then the citation sections to
// `sources`, all in one Apply. A file that is not UTF-8 or has no readable frontmatter is skipped.
func (m *migrateRun) concept(ap string) error {
	text, ok, err := catalogue.ReadFileVerbatim(ap)
	if err != nil || !ok {
		return err
	}
	doc := frontmatter.Read(text)
	if doc.Head == "" || doc.Err != "" {
		return nil
	}
	path := relPath(m.root, ap)
	edits := m.status(doc.Root, path)
	stamp, err := m.generated(doc.Root, ap, path)
	if err != nil {
		return err
	}
	edits = append(edits, stamp...)
	edits = append(edits, m.sources(doc.Root, path, doc.Body)...)
	if len(edits) == 0 {
		return nil
	}
	migrated, err := yamlpatch.Apply(text, edits...)
	if err != nil {
		return patchError(path, err)
	}
	m.plan = append(m.plan, planEntry(path, text, migrated))
	return nil
}

func (m *migrateRun) issue(path, field, reason string) {
	m.issues = append(m.issues, migrateIssue{path, field, reason})
}

// status counts the status value and sets it to its D37 decision; a value with none is unresolved.
// A value that is no str (Python isinstance) is counted and reported under its repr.
func (m *migrateRun) status(data *yaml.Node, path string) []yamlpatch.Edit {
	n := frontmatter.Lookup(data, "status")
	if n == nil {
		return nil
	}
	key, shown, decision, decided := "", "", "", false
	if migrateIsStr(n) {
		key = frontmatter.Deref(n).Value
		shown = pytext.ReprStr(key)
		decision, decided = migrateStatus[key]
	} else {
		key = migrateRepr(n)
		shown = key
	}
	m.counts[key]++
	switch {
	case !decided:
		m.issue(path, "status", "no recorded decision for status value "+shown)
	case decision != key:
		return []yamlpatch.Edit{yamlpatch.SetValue("status", yamlpatch.Str(decision))}
	}
	return nil
}

// generated replaces `timestamp` by `generated {by, at}` from the last body-changing commit (OKF
// D18), or deletes it when `generated` exists; without a usable commit the field is unresolved.
func (m *migrateRun) generated(data *yaml.Node, ap, path string) ([]yamlpatch.Edit, error) {
	switch {
	case !frontmatter.Has(data, "timestamp"):
		return nil, nil
	case frontmatter.Has(data, "generated"):
		return []yamlpatch.Edit{yamlpatch.DeleteKey("timestamp")}, nil
	}
	commit, err := m.hist.LastBodyCommit(ap, false)
	if err != nil {
		return nil, err
	}
	if commit == nil {
		m.issue(path, "generated", "no body-changing commit found in git history")
		return nil, nil
	}
	by := m.authors[commit.Email]
	if by == "" {
		local, _, _ := strings.Cut(commit.Email, "@")
		by = "human:" + local
	}
	if _, _, ok := spec.ParseActorText(by); !ok {
		m.issue(path, "generated.by", "author email "+pytext.ReprStr(commit.Email)+
			" maps to no actor; add it to git_authors")
		return nil, nil
	}
	at := yamlpatch.Str(spec.Isoformat(commit.Time))
	return []yamlpatch.Edit{yamlpatch.ReplaceKey("timestamp", "generated",
		yamlpatch.Map("by", yamlpatch.Str(by), "at", at))}, nil
}

// sources moves the citation sections of the body into `sources` (D24). A `sources` that is
// there but falsy is replaced in place, as Python's assignment does; a truthy one is unresolved.
func (m *migrateRun) sources(data *yaml.Node, path, body string) []yamlpatch.Edit {
	newBody, entries, reason := citationSources(body)
	switch {
	case reason != "":
		m.issue(path, "sources", reason)
	case len(entries) == 0:
	case migrateTruthy(frontmatter.Lookup(data, "sources")):
		m.issue(path, "sources", "concept already carries sources; rework the citation section by hand")
	default:
		put := yamlpatch.NewKey("sources", yamlpatch.List(entries...))
		if frontmatter.Has(data, "sources") {
			put = yamlpatch.ReplaceKey("sources", "sources", yamlpatch.List(entries...))
		}
		return []yamlpatch.Edit{put, yamlpatch.SetBody(newBody)}
	}
	return nil
}

// runMigrate is Python cmd_migrate: the dry-run preview, or with --apply the writing of exactly
// that plan.
func runMigrate(root string, a *cli.Args) (any, error) {
	target := a.String("target")
	if target != "" {
		if err := catalogue.RequireBundleDir(root, target); err != nil {
			return nil, err
		}
	}
	m, err := planMigrate(root, target)
	if err != nil {
		return nil, err
	}
	files := diffs.UnifiedDiffs(m.plan, nil)
	apply := a.Bool("apply")
	if apply {
		if err := diffs.WritePlan(root, m.plan); err != nil {
			return nil, err
		}
	}
	olds := slices.Sorted(maps.Keys(m.counts))
	mapping := make([]envelope.Obj, len(olds))
	for i, old := range olds {
		var decision any
		if d, ok := migrateStatus[old]; ok {
			decision = d
		}
		mapping[i] = envelope.O("old", old, "new", decision, "count", m.counts[old])
	}
	if a.JSON {
		unresolved := make([]envelope.Obj, len(m.issues))
		for i, u := range m.issues {
			unresolved[i] = envelope.O("path", u.path, "field", u.field, "reason", u.reason)
		}
		return envelope.O("applied", apply, "files", diffData(files), "unresolved", unresolved,
			"status_mapping", mapping), nil
	}
	w := newOut()
	defer w.Flush()
	if len(mapping) > 0 {
		fmt.Fprintln(w, "status mapping:")
		for _, old := range olds {
			decision := "(no decision)"
			if d, ok := migrateStatus[old]; ok {
				decision = d
			}
			fmt.Fprintf(w, "  %s -> %s (%d concept(s))\n", old, decision, m.counts[old])
		}
	}
	printDiffs(w, files)
	for _, u := range m.issues {
		fmt.Fprintf(w, "unresolved %s: %s\n", u.path, u.reason)
	}
	verb, tail := "would migrate", "; dry-run: re-run with --apply"
	if apply {
		verb, tail = "migrated", ""
	}
	fmt.Fprintf(w, "migrate: %s %d file(s), %d unresolved%s\n", verb, len(files), len(m.issues), tail)
	return nil, nil
}
