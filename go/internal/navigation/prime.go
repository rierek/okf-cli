package navigation

import (
	"strconv"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/cli"
	"nas/volume1/data/git/okf-tools/go/internal/envelope"
	"nas/volume1/data/git/okf-tools/go/internal/pytext"
	"nas/volume1/data/git/okf-tools/go/internal/sqlstore"
	"nas/volume1/data/git/okf-tools/go/internal/tagvec"
)

func primeArgs() []cli.Arg {
	return []cli.Arg{
		{Flags: []string{"--full"}, Action: cli.StoreTrue, Help: "add types+tags to each bundle block"},
		{Flags: []string{"--compact"}, Action: cli.StoreTrue,
			Help: "list bundles as name+count one-liners instead of the " +
				"`index` blocks (description+directories)"},
		{Flags: []string{"--check-semantic"}, Action: cli.StoreTrue,
			Help: "run the exact content-hash semantic coverage check " +
				"(~2s on a large catalogue) instead of reporting only " +
				"whether the semantic index is present"},
		cli.JSON(),
	}
}

// semanticCoverageLine is Python _semantic_coverage_line: the onboarding statement about the
// semantic arm's reach. Without thorough it reports presence only, since the exact count costs
// seconds on a large catalogue.
func semanticCoverageLine(root string, paths []string, thorough bool) (string, error) {
	const absent = "semantic index: absent — `find` runs its lexical arm only"
	if !catalogue.RealFS.IsFile(sqlstore.TagvecPath(root)) {
		return absent, nil
	}
	if !thorough {
		return "semantic index: present — staleness not checked by default " +
			"(costs ~2s on a large catalogue); run `prime --check-semantic` " +
			"for an exact count", nil
	}
	cov, ok, err := tagvec.SemanticCoverage(root, paths)
	if err != nil {
		return "", err
	}
	switch {
	case !ok:
		return absent, nil
	case cov.Embedded >= cov.Total:
		return "semantic index: complete — all " + strconv.Itoa(cov.Total) + " concept(s) embedded", nil
	}
	return "semantic index: partial — " + strconv.Itoa(cov.Embedded) + " of " + strconv.Itoa(cov.Total) +
		" concept(s) embedded; the rest is invisible to the semantic arm (rebuild: cli/embeddings/" +
		"build_tagvec.py --target concepts)", nil
}

// renderCatalogueState is Python render_catalogue_state: the live half of the onboarding, facts
// read off this catalogue rather than asserted in prose.
func renderCatalogueState(root string, bundles []string, thorough bool) (string, error) {
	var paths []string
	for _, b := range bundles {
		for cid := range catalogue.IterConcepts(catalogue.Join(root, b), true) {
			paths = append(paths, b+"/"+cid)
		}
	}
	lines := []string{"## This catalogue", "", "root: " + root,
		"bundles: " + strconv.Itoa(len(bundles)) + " · concepts: " + strconv.Itoa(len(paths))}
	if catalogue.RealFS.IsFile(sqlstore.FTSPath(root)) {
		lines = append(lines, "fts index: present — `find` runs its lexical arm")
	} else {
		lines = append(lines, "fts index: absent — `find` degrades to a substring scan; run `build-index`")
	}
	semantic, err := semanticCoverageLine(root, paths, thorough)
	if err != nil {
		return "", err
	}
	lines = append(lines, semantic)
	registered, err := catalogue.LoadTags(root, "")
	if err != nil {
		return "", err
	}
	if registered == nil {
		lines = append(lines, "tag vocabulary: open — no TAGS.md, any tag passes")
	} else {
		lines = append(lines, "tag vocabulary: closed — "+strconv.Itoa(len(registered))+" tags in TAGS.md; "+
			"check a new one with `tags --validate`, adopt it with `tags --register`")
	}
	slugs, err := catalogue.CtxSlugs(root)
	if err != nil {
		return "", err
	}
	if len(slugs) > 0 {
		lines = append(lines, "ctx bundles: "+strconv.Itoa(len(slugs))+" — "+strings.Join(slugs, " · ")+
			" — `ctx show <slug>` lists one")
	}
	var docs []string
	for _, d := range []string{"README.md", "SPEC.md", "TYPES.md", "PROPERTIES.md", "TAGS.md"} {
		if catalogue.RealFS.IsFile(catalogue.Join(root, d)) {
			docs = append(docs, d)
		}
	}
	if len(docs) > 0 {
		lines = append(lines, "root docs: "+strings.Join(docs, " · "))
	}
	return strings.Join(lines, "\n"), nil
}

// runPrime is Python cmd_prime: guide, command directory, find reference, catalogue state and
// bundle TOC in one call. --compact is the session-start rendering.
func runPrime(app *cli.App, root string, a *cli.Args) (any, error) {
	compact, full := a.Bool("compact"), a.Bool("full")
	var guide, commands, find string
	if compact {
		guide, commands = primeIntroCompact, cli.RenderOverview(app.Directory(), 1000000, false)
		find = "## find — the entry point\n\n" + pytext.Strip(app.CommandUsage("find")) + "\n\n" +
			findScalesCompact + "\nFull flag semantics: `find --help`."
	} else {
		guide, commands = primeIntro, cli.RenderOverview(app.Directory(), 96, false)
		find = "## find — the entry point, in full\n\n" + pytext.Strip(app.CommandHelp("find"))
	}
	bundleNames, err := catalogue.ListBundles(root)
	if err != nil {
		return nil, err
	}
	state, err := renderCatalogueState(root, bundleNames, a.Bool("check_semantic"))
	if err != nil {
		return nil, err
	}
	bundles := make([]string, len(bundleNames))
	for i, b := range bundleNames {
		if compact {
			bundles[i] = renderBundleLine(root, b)
		} else if bundles[i], err = renderBundleBlock(root, b, full); err != nil {
			return nil, err
		}
	}
	if a.JSON {
		return envelope.O("guide", guide, "commands", commands, "find", find, "state", state, "bundles", bundles), nil
	}
	w := newOut()
	defer w.Flush()
	printf(w, "%s\n%s\n\n%s\n\n%s\n\n", guide, commands, find, state)
	printf(w, "## Bundles\n\n")
	printf(w, "The catalogue TOC, as `index` renders it. Each name is a path: `toc <bundle>`,\n"+
		"`index <bundle>`, `--where \"path ~ <bundle>/\"` on find and list.\n\n")
	if compact {
		for _, line := range bundles {
			printf(w, "- %s\n", line)
		}
		printf(w, "(`prime` without --compact inlines each bundle's description and directories)\n")
		return nil, nil
	}
	for _, block := range bundles {
		printf(w, "%s\n-----\n", block)
	}
	if !full {
		printf(w, "(types+tags per bundle: `prime --full`; name+count only: `prime --compact`)\n")
	}
	return nil, nil
}
