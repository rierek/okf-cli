package rewrite

import (
	"fmt"
	"path/filepath"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/check"
	"nas/volume1/data/git/okf-tools/go/internal/cli"
	"nas/volume1/data/git/okf-tools/go/internal/complete"
	"nas/volume1/data/git/okf-tools/go/internal/diffs"
	"nas/volume1/data/git/okf-tools/go/internal/envelope"
	"nas/volume1/data/git/okf-tools/go/internal/frontmatter"
	"nas/volume1/data/git/okf-tools/go/internal/okferr"
)

// scanTarget is the target gate of cmd_fix_xml_tags and cmd_fix_crosslinks: a target that is not a
// directory below the root is not_found (a typo would otherwise scan nothing and exit 0).
func scanTarget(root, target string) error {
	if target != "" && !catalogue.RealFS.IsDir(catalogue.Join(root, trimSlashes(target))) {
		return okferr.Newf(okferr.NotFound, "not a directory: %s", target)
	}
	return nil
}

// trimSlashes is target.rstrip("/").
func trimSlashes(s string) string {
	for len(s) > 0 && s[len(s)-1] == '/' {
		s = s[:len(s)-1]
	}
	return s
}

// relSlash is os.path.relpath(ap, root) with `/` separators.
func relSlash(root, ap string) (string, error) {
	rel, err := filepath.Rel(root, ap)
	return filepath.ToSlash(rel), err
}

// planFixXMLTags is Python fix_xml_like_tags: the angle-bracket placeholder chains wrapped in
// inline code across every non-reserved .md under target. It writes nothing and returns the
// number of files touched, the chains wrapped, the plan and the files that are not valid UTF-8.
func planFixXMLTags(root, target string) (touched, chains int, plan []diffs.PlanEntry, skipped []string, err error) {
	skipped = []string{}
	scopes, err := catalogue.ResolveScopes(root, target, false, false)
	if err != nil {
		return
	}
	for _, sc := range scopes {
		for ap := range catalogue.IterAllMd(sc.Path, false) {
			if catalogue.IsReserved(filepath.Base(ap)) {
				continue
			}
			var rel, text string
			var ok bool
			if rel, err = relSlash(root, ap); err != nil {
				return
			}
			if text, ok, err = catalogue.ReadFileVerbatim(ap); err != nil {
				return
			}
			if !ok {
				skipped = append(skipped, rel)
				continue
			}
			doc := frontmatter.Read(text)
			masked, tokens := check.MaskCodeSpans(doc.Body)
			count := 0
			newMasked := check.XMLTagChainRE.ReplaceAllStringFunc(masked, func(chain string) string {
				if check.IsIgnorableChain(chain) {
					return chain
				}
				count++
				return "`" + chain + "`"
			})
			if count > 0 {
				newText := doc.Head + check.Unmask(newMasked, tokens)
				touched++
				chains += count
				plan = append(plan, diffs.PlanEntry{Path: rel, Old: &text, New: &newText})
			}
		}
	}
	return
}

// runFixXMLTags is Python cmd_fix_xml_tags.
func runFixXMLTags(root string, a *cli.Args) (any, error) {
	target := a.String("target")
	if err := scanTarget(root, target); err != nil {
		return nil, err
	}
	touched, chains, plan, skipped, err := planFixXMLTags(root, target)
	if err != nil {
		return nil, err
	}
	files := diffs.UnifiedDiffs(plan, nil)
	dry := a.Bool("check")
	if !dry {
		if err := diffs.WritePlan(root, plan); err != nil {
			return nil, err
		}
	}
	if a.JSON {
		return envelope.O("applied", !dry, "files", diffs.JSONFiles(files), "skipped", skipped), nil
	}
	verb := "wrapped"
	if dry {
		verb = "would wrap"
	}
	return nil, printFixReport(files, skipped,
		fmt.Sprintf("fix-xml-tags: %d file(s) %s, %d chain(s) total\n", touched, verb, chains))
}

// registerFixXMLTags attaches fix-xml-tags and its completer.
func registerFixXMLTags(app *cli.App) {
	app.Attach("fix-xml-tags", cli.Spec{
		Args: []cli.Arg{
			{Dest: "target", Nargs: cli.Optional, Help: "<bundle> or <bundle>/<subdir> (default: whole catalogue)"},
			{Flags: []string{"--check"}, Action: cli.StoreTrue, Help: "dry-run: report without writing"},
			cli.JSON(),
		},
		Handler: runFixXMLTags,
	})
	complete.Attach([]string{"fix-xml-tags"}, "target", complete.Scopes)
}
