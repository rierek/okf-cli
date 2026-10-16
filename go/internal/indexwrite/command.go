package indexwrite

import (
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/cli"
	"nas/volume1/data/git/okf-tools/go/internal/complete"
	"nas/volume1/data/git/okf-tools/go/internal/diffs"
	"nas/volume1/data/git/okf-tools/go/internal/envelope"
	"nas/volume1/data/git/okf-tools/go/internal/okferr"
	"nas/volume1/data/git/okf-tools/go/internal/stdio"
)

// Register attaches reindex with its completer.
func Register(app *cli.App) {
	app.Attach("reindex", cli.Spec{
		Args: []cli.Arg{
			{Dest: "target", Help: "<bundle> or <bundle>/<subdir>"},
			{Flags: []string{"--init"}, Action: cli.StoreTrue,
				Help: "recursively migrate marker-less flat index.md in the subtree to managed marker blocks " +
					"(bespoke multi-section indexes are skipped + flagged)"},
			{Flags: []string{"--check"}, Action: cli.StoreTrue,
				Help: "dry-run: with --init preview conversions; else report stale + uncovered. No writes"},
			{Flags: []string{"--force"}, Action: cli.StoreTrue,
				Help: "with --init, also flatten a pure multi-section listing (prose/tables still refuse)"},
			cli.JSON(),
		},
		Handler: runReindex,
	})
	complete.Attach([]string{"reindex"}, "target", complete.Scopes)
}

// runReindex is Python cmd_reindex.
func runReindex(root string, a *cli.Args) (any, error) {
	target := strings.TrimRight(a.String("target"), "/")
	tp := catalogue.Join(root, target)
	if !catalogue.RealFS.IsDir(tp) {
		return nil, okferr.Newf(okferr.NotFound, "not a directory: %s", target)
	}
	init, check, asJSON := a.Bool("init"), a.Bool("check"), a.JSON
	plan, info, err := PlanReindex(root, tp, init, a.Bool("force"), catalogue.RealFS)
	if err != nil {
		return nil, err
	}
	files := diffs.UnifiedDiffs(plan, nil)
	if !check {
		if err := diffs.WritePlan(root, plan); err != nil {
			return nil, err
		}
	}
	stale, skipped := info.Stale, info.Skipped
	changed, shownStale := []string{}, []string{}
	if !check {
		changed = stale
	}
	if check && !init {
		shownStale = stale
	}
	result := envelope.O("applied", !check, "init", nil, "updated", changed, "skipped", skipped,
		"stale", shownStale, "uncovered", []string{}, "unreadable", info.Unreadable,
		"files", diffs.JSONFiles(files))
	verb, nConv, nSkip := "", 0, 0
	if init {
		verb = "converted"
		if check {
			verb = "would convert"
		}
		converted, skippedInit := []string{}, []envelope.Obj{}
		for _, r := range info.Init {
			switch r.Status {
			case StatusConverted:
				nConv++
				converted = append(converted, r.Rel)
			case StatusAlreadyManaged:
			default:
				nSkip++
				skippedInit = append(skippedInit, envelope.O("path", r.Rel, "reason", r.Status))
			}
		}
		result.Set("init", envelope.O("converted", converted, "skipped", skippedInit))
	}
	if !asJSON {
		diffs.PrintFiles(stdio.Writer, files)
		for _, rel := range info.Unreadable {
			stdio.Printf("skipped (not valid UTF-8)  %s\n", rel)
		}
		if init {
			for _, r := range info.Init {
				switch r.Status {
				case StatusConverted:
					stdio.Printf("%-14s %s\n", verb, r.Rel)
				case StatusAlreadyManaged:
				default:
					stdio.Printf("%-14s %s  (%s)\n", "skipped", r.Rel, r.Status)
				}
			}
			stdio.Printf("init: %d %s, %d skipped\n", nConv, verb, nSkip)
		}
	}
	if check {
		if init {
			return result, nil // --init --check = final-text preview of the write run
		}
		uncovered, err := UncoveredIndexDirs(root, tp)
		if err != nil {
			return nil, err
		}
		result.Set("uncovered", uncovered)
		if !asJSON {
			for _, p := range stale {
				stdio.Printf("STALE        %s\n", p)
			}
			for _, p := range uncovered {
				stdio.Printf("UNCOVERED    %s\n", p)
			}
			stdio.Printf("reindex --check: %d stale, %d uncovered, %d without markers\n",
				len(stale), len(uncovered), len(skipped))
		}
		if len(stale) > 0 || len(uncovered) > 0 {
			return nil, okferr.WithResult(okferr.Drift, "", result)
		}
	}
	if asJSON {
		return result, nil
	}
	for _, p := range changed {
		stdio.Printf("updated       %s\n", p)
	}
	for _, p := range skipped {
		stdio.Printf("skipped (no markers)  %s\n", p)
	}
	stdio.Printf("reindex: %d updated, %d skipped\n", len(changed), len(skipped))
	return nil, nil
}
