package ctx

import (
	"errors"
	"fmt"
	"os"
	"os/exec"
	"strings"
	"syscall"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/check"
	"nas/volume1/data/git/okf-tools/go/internal/cli"
	"nas/volume1/data/git/okf-tools/go/internal/ctxfile"
	"nas/volume1/data/git/okf-tools/go/internal/envelope"
	"nas/volume1/data/git/okf-tools/go/internal/indexwrite"
	"nas/volume1/data/git/okf-tools/go/internal/linkscan"
	"nas/volume1/data/git/okf-tools/go/internal/move"
	"nas/volume1/data/git/okf-tools/go/internal/okferr"
)

// report is Python _ctx_report: the findings of the given bundles through the finding report.
func report(root string, slugs []string, stale, asJSON bool) (any, error) {
	var findings []check.Finding
	for _, s := range slugs {
		found, err := ctxfile.CtxFindings(root, catalogue.Join(catalogue.Join(root, catalogue.CtxDir), s+".md"), stale)
		if err != nil {
			return nil, err
		}
		for _, f := range found {
			findings = append(findings, check.FindingOf(f.Rule, ctxRel(s), f.Message))
		}
	}
	return check.ReportFindings(findings, false, asJSON)
}

// runCheck is Python cmd_ctx_check: the findings of one bundle, or of all.
func runCheck(root string, a *cli.Args) (any, error) {
	slug := a.String("slug")
	slugs := []string{slug}
	if slug != "" {
		if _, err := ctxfile.LoadCtx(root, slug); err != nil {
			return nil, err
		}
	} else {
		var err error
		if slugs, err = catalogue.CtxSlugs(root); err != nil {
			return nil, err
		}
	}
	return report(root, slugs, a.Bool("stale"), a.JSON)
}

// runEdit is Python cmd_ctx_edit: the bundle in $VISUAL, else $EDITOR, else vi; afterwards the
// `_ctx` index is refreshed and the bundle checked.
func runEdit(root string, a *cli.Args) (any, error) {
	slug := a.String("slug")
	if _, err := ctxfile.LoadCtx(root, slug); err != nil {
		return nil, err
	}
	editor := os.Getenv("VISUAL")
	if editor == "" {
		editor = os.Getenv("EDITOR")
	}
	if editor == "" {
		editor = "vi"
	}
	argv, err := shlexSplit(editor)
	if err != nil {
		return nil, err
	}
	dir := catalogue.Join(root, catalogue.CtxDir)
	argv = append(argv, catalogue.Join(dir, slug+".md"))
	// no shell, and the terminal of the caller
	cmd := exec.Command(argv[0], argv[1:]...)
	if errors.Is(cmd.Err, exec.ErrDot) {
		cmd.Err = nil // execvp runs a program that a `.` or empty entry of PATH finds in the working directory
	}
	cmd.Stdin, cmd.Stdout, cmd.Stderr = os.Stdin, os.Stdout, os.Stderr
	if err := cmd.Run(); err != nil {
		var exit *exec.ExitError
		if !errors.As(err, &exit) {
			return nil, err
		}
		code := exit.ExitCode()
		if status, ok := exit.Sys().(syscall.WaitStatus); ok && status.Signaled() {
			code = -int(status.Signal()) // Python's subprocess.call reports the signal as a negative code
		}
		return nil, die(okferr.InvalidInput, "editor exited %d", code)
	}
	if _, err := indexwrite.ReindexTree(root, dir); err != nil {
		return nil, err
	}
	return report(root, []string{slug}, false, a.JSON)
}

// runRename is Python cmd_ctx_rename: the move core moves the bundle and rewrites the links to it;
// a bundle whose rows all parse is then saved once more, which refreshes its H1.
func runRename(root string, a *cli.Args) (any, error) {
	oldSlug, newSlug := a.String("old"), a.String("new")
	c, err := ctxfile.LoadCtx(root, oldSlug)
	if err != nil {
		return nil, err
	}
	if problem := ctxfile.CtxSlugProblem(newSlug); problem != "" {
		return nil, die(okferr.InvalidInput, `invalid slug "%s": %s`, newSlug, problem)
	}
	dir := catalogue.Join(root, catalogue.CtxDir)
	oldFile, newFile := catalogue.Join(dir, oldSlug+".md"), catalogue.Join(dir, newSlug+".md")
	if exists(newFile) {
		return nil, die(okferr.InvalidInput, "%s already exists", newSlug)
	}
	if len(c.Problems) == 0 {
		// The refresh after the move cannot be refused once the file has moved: the writer's
		// verdict on the frontmatter is taken now.
		text, err := catalogue.ReadFile(oldFile)
		if err != nil {
			return nil, err
		}
		if _, err := ctxfile.CtxText(ctxfile.Ctx{Slug: newSlug, Description: c.Description, Entries: c.Entries}, &text); err != nil {
			return nil, err
		}
	}
	result, err := move.PerformRename(root, oldFile, newFile, true, false, "rename", nil, a.JSON)
	if err != nil {
		return nil, err
	}
	if len(c.Problems) == 0 {
		moved, err := ctxfile.LoadCtx(root, newSlug)
		if err != nil {
			return nil, err
		}
		if err := save(root, ctxfile.Ctx{Slug: newSlug, Description: moved.Description, Entries: moved.Entries}); err != nil {
			return nil, err
		}
	}
	result.Set("old_slug", oldSlug)
	result.Set("new_slug", newSlug)
	if a.JSON {
		return result, nil
	}
	return nil, nil
}

// runRemove is Python cmd_ctx_remove: the bundle is deleted and the files that still link to it
// are listed.
func runRemove(root string, a *cli.Args) (any, error) {
	slug := a.String("slug")
	c, err := ctxfile.LoadCtx(root, slug)
	if err != nil {
		return nil, err
	}
	dir := catalogue.Join(root, catalogue.CtxDir)
	file := catalogue.Join(dir, slug+".md")
	// one reference row per link: de-duplicated by source file, in the order first seen
	refs, err := linkscan.BuildRefMatrix(root, file)
	if err != nil {
		return nil, err
	}
	sources := []string{}
	seen := map[string]bool{}
	for _, r := range refs {
		if r.Source != catalogue.CtxDir+"/index.md" && !seen[r.Source] {
			seen[r.Source] = true
			sources = append(sources, r.Source)
		}
	}
	if err := os.Remove(file); err != nil {
		return nil, err
	}
	if _, err := indexwrite.ReindexTree(root, dir); err != nil {
		return nil, err
	}
	if a.JSON {
		return envelope.O("applied", true, "slug", slug, "path", ctxRel(slug),
			"entries", len(c.Entries), "linked_from", sources), nil
	}
	var sb strings.Builder
	fmt.Fprintf(&sb, "removed %s (%d entries)\n", ctxRel(slug), len(c.Entries))
	if len(sources) > 0 {
		fmt.Fprintf(&sb, "warning: %d file(s) still link to %s:\n", len(sources), ctxRel(slug))
		for _, s := range sources {
			sb.WriteString("  " + s + "\n")
		}
	}
	fmt.Print(sb.String())
	return nil, nil
}
