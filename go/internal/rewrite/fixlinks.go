package rewrite

import (
	"fmt"
	"path"
	"path/filepath"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/check"
	"nas/volume1/data/git/okf-tools/go/internal/cli"
	"nas/volume1/data/git/okf-tools/go/internal/complete"
	"nas/volume1/data/git/okf-tools/go/internal/diffs"
	"nas/volume1/data/git/okf-tools/go/internal/envelope"
	"nas/volume1/data/git/okf-tools/go/internal/frontmatter"
	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

// resolveCrosslinkTarget is Python resolve_crosslink_target: the catalogue-root-absolute form
// (`/bundle/subdir/concept.md`) of the file the link target tgt, found in bundle/cdir, points at.
// Interpretations are tried in order: a leading `/` as legacy bundle-root, as catalogue-root,
// else relative to cdir, then (mis-depthed `../`) the `../`-stripped tail from the root. It
// answers only for a file that exists.
func resolveCrosslinkTarget(root, bundle, cdir, tgt string) (string, bool) {
	isFile := catalogue.RealFS.IsFile
	var dest string
	if strings.HasPrefix(tgt, "/") {
		p := strings.TrimLeft(tgt, "/")
		dest = catalogue.Join(catalogue.Join(root, bundle), p)
		if !isFile(dest) {
			dest = catalogue.Join(root, p)
		}
	} else {
		dest = path.Clean(catalogue.Join(catalogue.Join(catalogue.Join(root, bundle), cdir), tgt))
		if !isFile(dest) {
			tail := tgt
			for {
				if strings.HasPrefix(tail, "../") {
					tail = tail[3:]
				} else if strings.HasPrefix(tail, "./") {
					tail = tail[2:]
				} else {
					break
				}
			}
			if cand := catalogue.Join(root, tail); isFile(cand) {
				dest = cand
			}
		}
	}
	if !isFile(dest) {
		return "", false
	}
	absDest, err := catalogue.Abspath(dest)
	if err != nil {
		return "", false
	}
	absRoot, err := catalogue.Abspath(root)
	if err != nil {
		return "", false
	}
	rel, err := filepath.Rel(absRoot, absDest)
	if err != nil {
		return "", false
	}
	return "/" + filepath.ToSlash(rel), true
}

// rewriteCrosslinksInBody is Python rewrite_crosslinks_in_body: every resolvable markdown link of
// body in canonical catalogue-root-absolute form, links in code spans and fences untouched. It
// returns the new body, the number of links changed and the targets that did not resolve.
func rewriteCrosslinksInBody(root, bundle, cdir, body string) (string, int, []string) {
	masked, tokens := check.MaskCodeSpans(body)
	var out strings.Builder
	var unresolved []string
	changed, last := 0, 0
	for _, m := range catalogue.CrosslinkRE.FindAllStringSubmatchIndex(masked, -1) {
		label, target := masked[m[2]:m[3]], masked[m[4]:m[5]]
		rawTgt, anchor, _ := strings.Cut(target, "#")
		rawTgt = pytext.Strip(rawTgt)
		if !strings.HasSuffix(rawTgt, ".md") || strings.HasPrefix(rawTgt, "http://") ||
			strings.HasPrefix(rawTgt, "https://") || strings.HasPrefix(rawTgt, "mailto:") {
			continue
		}
		resolved, ok := resolveCrosslinkTarget(root, bundle, cdir, rawTgt)
		if !ok {
			unresolved = append(unresolved, rawTgt)
			continue
		}
		newTarget := resolved
		if anchor != "" {
			newTarget += "#" + anchor
		}
		if newTarget == target {
			continue // already canonical
		}
		changed++
		out.WriteString(masked[last:m[0]])
		out.WriteString("[" + label + "](" + newTarget + ")")
		last = m[1]
	}
	out.WriteString(masked[last:])
	return check.Unmask(out.String(), tokens), changed, unresolved
}

// unresolvedLink is one link target fix-crosslinks could not resolve: the file and the target.
type unresolvedLink struct{ rel, target string }

// planFixCrosslinks is Python fix_crosslinks: the links of every .md under target rewritten to
// catalogue-root-absolute form. Reserved files are left alone unless includeReserved, which
// narrows them to the text outside the managed index block. It writes nothing and returns the
// number of files touched, the unresolved links, the plan and the files that are not valid UTF-8.
func planFixCrosslinks(root, target string, includeReserved bool) (touched int, unresolved []unresolvedLink, plan []diffs.PlanEntry, skipped []string, err error) {
	skipped = []string{}
	scopes, err := catalogue.ResolveScopes(root, target, false, false)
	if err != nil {
		return
	}
	for _, sc := range scopes {
		for ap := range catalogue.IterAllMd(sc.Path, false) {
			reserved := catalogue.IsReserved(filepath.Base(ap))
			if reserved && !includeReserved {
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
			inBundle, rerr := filepath.Rel(sc.Path, ap)
			if rerr != nil {
				err = rerr
				return
			}
			cdir := filepath.ToSlash(filepath.Dir(inBundle))
			if cdir == "." {
				cdir = ""
			}
			var newBody string
			var changed int
			var unres []string
			if reserved {
				before, block, after := catalogue.SplitManagedBlock(doc.Body)
				nb, cb, ub := rewriteCrosslinksInBody(root, sc.Bundle, cdir, before)
				na, ca, ua := rewriteCrosslinksInBody(root, sc.Bundle, cdir, after)
				newBody, changed, unres = nb+block+na, cb+ca, append(ub, ua...)
			} else {
				newBody, changed, unres = rewriteCrosslinksInBody(root, sc.Bundle, cdir, doc.Body)
			}
			for _, u := range unres {
				unresolved = append(unresolved, unresolvedLink{rel, u})
			}
			if changed > 0 {
				newText := doc.Head + newBody
				touched++
				plan = append(plan, diffs.PlanEntry{Path: rel, Old: &text, New: &newText})
			}
		}
	}
	return
}

// runFixCrosslinks is Python cmd_fix_crosslinks.
func runFixCrosslinks(root string, a *cli.Args) (any, error) {
	target := a.String("target")
	if err := scanTarget(root, target); err != nil {
		return nil, err
	}
	touched, unresolved, plan, skipped, err := planFixCrosslinks(root, target, a.Bool("include_reserved"))
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
		rows := make([]envelope.Obj, len(unresolved))
		for i, u := range unresolved {
			rows[i] = envelope.O("path", u.rel, "target", u.target)
		}
		return envelope.O("applied", !dry, "files", diffs.JSONFiles(files), "skipped", skipped, "unresolved", rows), nil
	}
	verb := "rewrote"
	if dry {
		verb = "would rewrite"
	}
	var tail strings.Builder
	for _, u := range unresolved {
		fmt.Fprintf(&tail, "unresolved     %s  -> %s\n", u.rel, u.target)
	}
	fmt.Fprintf(&tail, "fix-crosslinks: %d file(s) %s, %d unresolved link(s)\n", touched, verb, len(unresolved))
	printFixReport(files, skipped, tail.String())
	return nil, nil
}

// registerFixCrosslinks attaches fix-crosslinks and its completer.
func registerFixCrosslinks(app *cli.App) {
	app.Attach("fix-crosslinks", cli.Spec{
		Args: []cli.Arg{
			{Dest: "target", Nargs: cli.Optional, Help: "<bundle> or <bundle>/<subdir> (default: whole catalogue)"},
			{Flags: []string{"--check"}, Action: cli.StoreTrue, Help: "dry-run: report without writing"},
			{Flags: []string{"--include-reserved"}, Dest: "include_reserved", Action: cli.StoreTrue,
				Help: "also rewrite RESERVED files (index.md, log.md, " +
					"readme.md, index-map.md), narrowed to the text " +
					"outside the managed <!-- okf:index --> block, " +
					"which stays byte-identical (D-fxcr-01, off by " +
					"default)"},
			cli.JSON(),
		},
		Handler: runFixCrosslinks,
	})
	complete.Attach([]string{"fix-crosslinks"}, "target", complete.Scopes)
}
