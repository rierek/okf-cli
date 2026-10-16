package wikisync

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/cli"
	"nas/volume1/data/git/okf-tools/go/internal/complete"
	"nas/volume1/data/git/okf-tools/go/internal/envelope"
	"nas/volume1/data/git/okf-tools/go/internal/okferr"
)

const scopeHelp = "<bundle> or <bundle>/<subdir> (default: whole catalogue)"

// Register attaches `wikilinks`, `sync-export` and `sync-status` with their completers.
func Register(app *cli.App) {
	app.Attach("wikilinks", cli.Spec{
		Args: []cli.Arg{
			{Dest: "target", Nargs: cli.Optional, Help: scopeHelp},
			{Flags: []string{"--unresolved"}, Action: cli.StoreTrue,
				Help: "list only unresolved and ambiguous occurrences (summary stays complete)"},
			cli.JSON(),
		},
		Handler: runWikilinks,
	})
	complete.Attach([]string{"wikilinks"}, "target", complete.Scopes)

	app.Attach("sync-export", cli.Spec{
		Args: []cli.Arg{
			{Dest: "concept", Help: "canonical concept (<bundle>/<concept-id>)"},
			{Dest: "block_id", Metavar: []string{"block-id"}, Help: "canon block id declared in that concept"},
			cli.JSON(),
		},
		Handler: runSyncExport,
	})
	complete.Attach([]string{"sync-export"}, "concept", complete.Concepts)
	complete.Attach([]string{"sync-export"}, "block_id", CompleteBlockIDs)

	app.Attach("sync-status", cli.Spec{
		Args: []cli.Arg{
			{Dest: "target", Nargs: cli.Optional, Help: scopeHelp},
			{Flags: []string{"--source"}, Help: "only blocks whose canonical source is this path (/bundle/concept.md)"},
			{Flags: []string{"--block"}, Metavar: []string{"BLOCK_ID"}, Help: "only blocks with this id"},
			cli.JSON(),
		},
		Handler: runSyncStatus,
	})
	complete.Attach([]string{"sync-status"}, "target", complete.Scopes)
	complete.Attach([]string{"sync-status"}, "source", CompleteCanonSources)
	complete.Attach([]string{"sync-status"}, "block", CompleteCanonBlockIDs)
}

// optional is the value of an option as a pointer: nil when the option is absent, so an empty
// value still filters.
func optional(a *cli.Args, dest string) *string {
	if !a.Has(dest) {
		return nil
	}
	s := a.String(dest)
	return &s
}

// requireDir is the not_found gate of a scoped scan: a typo'd bundle scanned nothing and exited 0.
func requireDir(root, target string) error {
	if target != "" && !catalogue.RealFS.IsDir(catalogue.Join(root, filepath.Clean(target))) {
		return okferr.Newf(okferr.NotFound, "not a directory: %s", target)
	}
	return nil
}

// strOrNil is s as a JSON value: null when the marker did not parse.
func strOrNil(s string, parsed bool) any {
	if !parsed {
		return nil
	}
	return s
}

func runSyncExport(root string, a *cli.Args) (any, error) {
	_, _, payload, err := CanonPayload(root, a.String("concept"), a.String("block_id"))
	if err != nil {
		return nil, err
	}
	payload = strings.Trim(payload, "\n")
	if a.JSON {
		return envelope.O("payload", payload), nil
	}
	// Payload only, nothing else, so the output pipes.
	_, err = os.Stdout.WriteString(payload + "\n")
	return nil, err
}

func runSyncStatus(root string, a *cli.Args) (any, error) {
	target := a.String("target")
	if err := requireDir(root, target); err != nil {
		return nil, err
	}
	_, found, err := ScanSyncBlocks(root, target, optional(a, "source"), optional(a, "block"))
	if err != nil {
		return nil, err
	}
	totals := map[string]int{}
	rows := make([]envelope.Obj, 0, len(found))
	drift := false
	for _, h := range found {
		totals[h.Status]++
		drift = drift || h.Status != "synced"
		rows = append(rows, envelope.O("consumer", h.Rel,
			"id", strOrNil(h.Block.ID, h.Block.MarkerParsed),
			"source", strOrNil(h.Block.Source, h.Block.MarkerParsed),
			"status", h.Status))
	}
	if a.JSON {
		totalsObj := envelope.Obj{}
		for _, s := range Statuses {
			totalsObj.Set(s, totals[s])
		}
		result := envelope.O("blocks", rows, "totals", totalsObj)
		if drift {
			return nil, okferr.WithResult(okferr.Drift, "", result)
		}
		return result, nil
	}
	var sb strings.Builder
	for _, h := range found {
		fmt.Fprintf(&sb, "%-18s %-32s %s#%s\n", h.Status, h.Rel, orQuestion(h.Block.Source), orQuestion(h.Block.ID))
	}
	parts := make([]string, len(Statuses))
	for i, s := range Statuses {
		parts[i] = fmt.Sprintf("%d %s", totals[s], s)
	}
	sb.WriteString("sync-status: " + strings.Join(parts, ", ") + "\n")
	fmt.Print(sb.String())
	if drift {
		return nil, okferr.New(okferr.Drift, "")
	}
	return nil, nil
}

func orQuestion(s string) string {
	if s == "" {
		return "?"
	}
	return s
}

func runWikilinks(root string, a *cli.Args) (any, error) {
	target := a.String("target")
	if target != "" {
		norm := strings.Trim(filepath.ToSlash(filepath.Clean(target)), "/")
		if !catalogue.RealFS.IsDir(catalogue.Join(root, norm)) {
			return nil, okferr.Newf(okferr.NotFound, "not a directory: %s", target)
		}
		// The target must name a bundle, or a subdirectory of one the walk would traverse.
		// Without this `wikilinks ..` walks out of the catalogue and `wikilinks <bundle>/_plan`
		// scans staging that the reporting surface excludes.
		var segments []string
		excluded := false
		for _, s := range strings.Split(norm, "/") {
			if s == "." || s == "" {
				continue
			}
			segments = append(segments, s)
			excluded = excluded || strings.HasPrefix(s, ".") || strings.HasPrefix(s, "_") || s == "assets"
		}
		bundles, err := catalogue.ListBundles(root)
		if err != nil {
			return nil, err
		}
		isBundle := len(segments) > 0
		if isBundle {
			isBundle = false
			for _, b := range bundles {
				if b == segments[0] {
					isBundle = true
					break
				}
			}
		}
		if !isBundle || excluded {
			return nil, okferr.Newf(okferr.InvalidInput, "not a scannable bundle path: %s", target)
		}
	}
	links, err := ScanWikilinks(root, target, nil)
	if err != nil {
		return nil, err
	}
	totals := map[string]int{}
	for _, l := range links {
		totals[l.Status]++
	}
	shown := links
	if a.Bool("unresolved") {
		shown = nil
		for _, l := range links {
			if l.Status != "resolved" {
				shown = append(shown, l)
			}
		}
	}
	if a.JSON {
		return wikilinksData(shown, totals, a.Bool("unresolved")), nil
	}
	var sb strings.Builder
	for _, l := range shown {
		fmt.Fprintf(&sb, "%-10s %-11s %s  %s", l.Status, l.Region, l.Source, l.Raw)
		if l.Embed {
			sb.WriteString("  (embed)")
		}
		if l.Status == "ambiguous" {
			sb.WriteString("  candidates: " + strings.Join(l.Candidates, ", "))
		}
		sb.WriteByte('\n')
	}
	fmt.Fprintf(&sb, "wikilinks: %d link(s), %d resolved, %d ambiguous, %d unresolved\n",
		len(links), totals["resolved"], totals["ambiguous"], totals["unresolved"])
	fmt.Print(sb.String())
	return nil, nil
}

// wikilinksData is the envelope data of `wikilinks --json`. by_bundle counts what `links` carries,
// so the two never contradict each other; totals is always the unfiltered census and filtered says
// which of the two a consumer looks at.
func wikilinksData(shown []Wikilink, totals map[string]int, filtered bool) envelope.Obj {
	statuses := []string{"resolved", "ambiguous", "unresolved"}
	counts := func(m map[string]int) envelope.Obj {
		o := envelope.Obj{}
		for _, s := range statuses {
			o.Set(s, m[s])
		}
		return o
	}
	links := make([]envelope.Obj, len(shown))
	perBundle := map[string]map[string]int{}
	var order []string
	for i, l := range shown {
		links[i] = envelope.O("source", l.Source, "region", l.Region, "raw", l.Raw, "page", l.Page,
			"alias", l.Alias, "suffix", l.Suffix, "embed", l.Embed,
			"span", []int{l.SpanStart, l.SpanEnd}, "status", l.Status, "candidates", l.Candidates)
		b, _, _ := strings.Cut(l.Source, "/")
		if perBundle[b] == nil {
			perBundle[b] = map[string]int{}
			order = append(order, b)
		}
		perBundle[b][l.Status]++
	}
	byBundle := envelope.Obj{}
	for _, b := range order {
		byBundle.Set(b, counts(perBundle[b]))
	}
	return envelope.O("links", links, "by_bundle", byBundle, "totals", counts(totals), "filtered", filtered)
}
