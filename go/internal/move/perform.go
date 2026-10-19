package move

import (
	"fmt"
	"os"
	"sort"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/check"
	"nas/volume1/data/git/okf-tools/go/internal/ctxfile"
	"nas/volume1/data/git/okf-tools/go/internal/diffs"
	"nas/volume1/data/git/okf-tools/go/internal/envelope"
	"nas/volume1/data/git/okf-tools/go/internal/linkscan"
	"nas/volume1/data/git/okf-tools/go/internal/okferr"
	"nas/volume1/data/git/okf-tools/go/internal/pytext"
	"nas/volume1/data/git/okf-tools/go/internal/stdio"
)

// Record is the JSON object a move answers with: Python's keys in Python's order. Callers append
// their own keys (`archive` adds `restore` and `active_inbound_concepts`).
type Record = envelope.Obj

// wikilinkRow is the JSON row of a wikilink the move reports without rewriting it.
func wikilinkRow(r WikilinkRecord) envelope.Obj {
	return envelope.O("source", r.Source, "region", r.Region, "raw", r.Raw, "candidates", r.Candidates)
}

// PerformRename is the validation, planning and application core shared by `rename`, `archive`
// and `ctx rename`. The callers pass already resolved absolute paths; verb only steers the prefix
// of error messages ("rename: " vs "archive: "), every other line of output is unchanged.
//
// plan is an already computed PlanRename result, so a caller that built one for its own reporting
// (archive's inbound count) does not pay for a second scan; nil computes it here. quiet suppresses
// every stdout line (JSON mode); notes still go through envelope.Note. Without apply nothing is
// written. Every refusal is raised before the first write: the git move runs first, the text
// writes after.
func PerformRename(root, oldAbs, newAbs string, apply, force bool, verb string, plan *RenamePlan, quiet bool) (Record, error) {
	die := func(kind okferr.Kind, msg string) error { return okferr.New(kind, verb+": "+msg) }

	if !strings.HasSuffix(oldAbs, ".md") || !strings.HasSuffix(newAbs, ".md") {
		return nil, die(okferr.InvalidInput, "both paths must be .md concept files")
	}
	if !catalogue.RealFS.IsFile(oldAbs) {
		return nil, die(okferr.NotFound, "source not found: "+oldAbs)
	}
	if catalogue.IsReserved(pyBasename(oldAbs)) {
		return nil, die(okferr.InvalidInput, "refusing to move a reserved file ("+pyBasename(oldAbs)+")")
	}
	if catalogue.IsReserved(pyBasename(newAbs)) {
		// A reserved name is not a concept, so nothing can resolve to it: every inbound wikilink
		// would be rewritten to an address that is dead on arrival, and the report would still
		// say it succeeded.
		return nil, die(okferr.InvalidInput, "refusing to rename onto a reserved name ("+pyBasename(newAbs)+
			") — no wikilink can resolve to it")
	}
	newBaseRaw := dropMd(pyBasename(newAbs))
	if pytext.Strip(newBaseRaw) == "" {
		return nil, die(okferr.InvalidInput, "destination has an empty basename — `[[…]]` would become `[[]]`, "+
			"which no scan can find again")
	}
	if newBaseRaw != pytext.Strip(newBaseRaw) {
		// The scanner strips the page part, the index does not strip filenames, so the two keys
		// could never meet: the rewritten link would resolve to nothing while the run reported
		// success.
		return nil, die(okferr.InvalidInput, "destination basename has leading or trailing whitespace — the "+
			"rewritten `[["+newBaseRaw+"]]` would resolve to nothing")
	}
	if strings.IndexFunc(newBaseRaw, func(r rune) bool { return r < 32 }) != -1 {
		return nil, die(okferr.InvalidInput, "destination basename contains a control character — the rewritten "+
			"link would be unmatchable by any later scan")
	}
	if oldAbs == newAbs {
		return nil, die(okferr.InvalidInput, "source and destination are identical")
	}
	if pyCommonpath(oldAbs, root) != root || pyCommonpath(newAbs, root) != root {
		return nil, die(okferr.InvalidInput, "both paths must live under the catalogue root")
	}
	for _, p := range []string{oldAbs, newAbs} {
		if strings.Count(pyRelpath(p, root), "/") < 1 {
			return nil, die(okferr.InvalidInput, "path must be inside a bundle (<bundle>/<concept>.md)")
		}
	}
	if bad := check.ForbiddenFilenameChars(pyBasename(newAbs)); bad != "" {
		return nil, die(okferr.InvalidInput, "forbidden char(s) in new filename: "+bad)
	}
	// samefile: on a case-insensitive filesystem a case-only rename has a destination that
	// "exists" because it IS the source. Refusing that would make `Foo.md` -> `foo.md` impossible
	// without --force overwriting itself.
	if pyExists(newAbs) && apply && !force {
		same, err := pySamefile(oldAbs, newAbs)
		if err != nil {
			return nil, err
		}
		if !same {
			return nil, die(okferr.InvalidInput, "destination exists (use --force to overwrite): "+newAbs)
		}
	}

	// From here on the source is addressed exactly as the filesystem spells it, so the two halves
	// of the rename and the self-reference check all compare the same string. The destination
	// keeps the caller's spelling of its own basename (that is the rename), but its directory part
	// is canonicalised for the same reason.
	oldAbs = canonicalCasePath(root, oldAbs)
	newAbs = catalogue.Join(canonicalCasePath(root, pyDirname(newAbs)), pyBasename(newAbs))

	if plan == nil {
		var err error
		if plan, err = PlanRename(root, oldAbs, newAbs); err != nil {
			return nil, err
		}
	}
	say := func(format string, args ...any) {
		if !quiet {
			stdio.Printf(format+"\n", args...)
		}
	}
	oldRel, newRel := pyRelpath(oldAbs, root), pyRelpath(newAbs, root)
	ctxHits, err := ctxfile.CtxMemberships(root, oldRel)
	if err != nil {
		return nil, err
	}
	var ctxWhere []string
	for _, h := range ctxHits {
		pos := "reference"
		if h.Entry.Pos != nil {
			pos = fmt.Sprintf("pos %d", *h.Entry.Pos)
		}
		ctxWhere = append(ctxWhere, h.Slug+" ("+pos+")")
	}

	var wlRewrite, wlSkipped, wlAmbiguous []WikilinkRecord
	for _, r := range plan.Wikilinks {
		switch r.Status {
		case StatusRewrite:
			wlRewrite = append(wlRewrite, r)
		case StatusSkippedAmbiguous:
			wlSkipped = append(wlSkipped, r)
		}
		// Every occurrence the plan says loses its unique target, whether or not a byte of it
		// changes. Derived from resolving each one against the catalogue before AND after the
		// move, so the tie-break is honoured on both sides: counting rewrites blindly refused
		// renames that broke nothing, and looking only at rewrites missed the ones that break
		// without being rewritten.
		if r.TurnsAmbiguous {
			wlAmbiguous = append(wlAmbiguous, r)
		}
	}
	collisions := plan.WikilinkCollisions

	printSkipped := func() {
		for _, r := range wlSkipped {
			say("  skipped-ambiguous  %s [%s]  %s  candidates: %s", r.Source, r.Region, r.Raw,
				strings.Join(r.Candidates, ", "))
		}
		for _, c := range collisions {
			say("  wikilink-collision  new basename already taken by %s", c)
		}
		for _, r := range wlAmbiguous {
			say("  turns-ambiguous  %s [%s]  %s  candidates after the move: %s", r.Source, r.Region, r.Raw,
				strings.Join(r.Candidates, ", "))
		}
	}

	if apply && len(wlAmbiguous) > 0 && !force {
		set := map[string]bool{}
		var sources []string
		for _, r := range wlAmbiguous {
			if !set[r.Source] {
				set[r.Source] = true
				sources = append(sources, r.Source)
			}
		}
		sort.Strings(sources)
		return nil, die(okferr.InvalidInput, fmt.Sprintf("this move leaves %d inbound wikilink(s) ambiguous: %s — the "+
			"same corruption `skipped-ambiguous` declines to commit, so it may not happen by accident either "+
			"(use --force to proceed)", len(wlAmbiguous), strings.Join(sources, ", ")))
	}

	inbound := make([]envelope.Obj, 0, len(plan.Inbound))
	for _, in := range plan.Inbound {
		inbound = append(inbound, envelope.O("source", in.Source, "old", in.Old, "new", in.New))
	}
	outbound := make([]envelope.Obj, 0, len(plan.Outbound))
	for _, o := range plan.Outbound {
		outbound = append(outbound, envelope.O("old", o.Old, "new", o.New))
	}
	wikilinks := make([]envelope.Obj, 0, len(wlRewrite))
	for _, r := range wlRewrite {
		wikilinks = append(wikilinks, envelope.O("source", r.Source, "region", r.Region, "raw", r.Raw, "new_raw", r.NewRaw))
	}
	syncSources := make([]envelope.Obj, 0, len(plan.SyncSources))
	for _, s := range plan.SyncSources {
		syncSources = append(syncSources, envelope.O("consumer", s.Consumer, "blocks", s.Blocks))
	}
	skipped := make([]envelope.Obj, 0, len(wlSkipped))
	for _, r := range wlSkipped {
		skipped = append(skipped, wikilinkRow(r))
	}
	turns := make([]envelope.Obj, 0, len(wlAmbiguous))
	for _, r := range wlAmbiguous {
		turns = append(turns, wikilinkRow(r))
	}
	result := envelope.O(
		"applied", apply, "old", oldRel, "new", newRel,
		"inbound", inbound, "outbound", outbound, "wikilinks", wikilinks,
		"sync_sources", syncSources, "ctx", ctxWhere,
		"skipped_ambiguous", skipped, "wikilink_collisions", collisions,
		"turns_ambiguous", turns, "reindex_bundles", plan.Bundles,
	)

	entries, moves, info, err := planMoveTexts(root, oldAbs, newAbs, plan, wlRewrite, ctxHits)
	if err != nil {
		return nil, err
	}
	files := diffs.UnifiedDiffs(entries, moves)
	result.Set("files", diffs.JSONFiles(files))

	if !apply {
		if !quiet {
			diffs.PrintFiles(stdio.Writer, files)
		}
		say("would move   %s  ->  %s", oldRel, newRel)
		for _, in := range plan.Inbound {
			say("  inbound    %s   %s  ->  %s", in.Source, in.Old, in.New)
		}
		for _, o := range plan.Outbound {
			say("  outbound   %s  ->  %s", o.Old, o.New)
		}
		for _, r := range wlRewrite {
			say("  wikilink   %s [%s]   %s  ->  %s", r.Source, r.Region, r.Raw, r.NewRaw)
		}
		for _, s := range plan.SyncSources {
			say("  sync-source  %s   %d block(s)", s.Consumer, s.Blocks)
		}
		for _, w := range ctxWhere {
			say("  ctx        %s", w)
		}
		printSkipped()
		say("  reindex    %s", strings.Join(plan.Bundles, ", "))
		say("rename (dry-run): %d inbound, %d outbound link(s), %d wikilink(s) (%d skipped-ambiguous), "+
			"%d bundle(s), %d sync source(s). Re-run with --apply.", len(plan.Inbound), len(plan.Outbound),
			len(wlRewrite), len(wlSkipped), len(plan.Bundles), len(plan.SyncSources))
		return result, nil
	}

	if pyExists(newAbs) {
		same, err := pySamefile(oldAbs, newAbs)
		if err != nil {
			return nil, err
		}
		if !same {
			// --force got us here. Say what it costs: the destination's content is gone and every
			// reference to it now addresses different content.
			clobbered, err := linkscan.BuildRefMatrix(root, newAbs)
			if err != nil {
				return nil, err
			}
			result.Set("overwrote_inbound", len(clobbered))
			say("overwrote      %s  (%d inbound markdown reference(s) now point at different content)",
				newRel, len(clobbered))
		}
	}
	if err := os.MkdirAll(pyDirname(newAbs), 0o777); err != nil {
		return nil, err
	}
	moved, gitRepo, gitReason, err := gitMv(root, oldAbs, newAbs)
	if err != nil {
		return nil, err
	}
	if err := diffs.WritePlan(root, entries); err != nil {
		return nil, err
	}
	how := "fs"
	if moved {
		how = "git mv"
	}
	say("moved (%s)  %s  ->  %s", how, oldRel, newRel)
	reason := gitReason
	if reason == "" {
		reason = "git binary unavailable"
	}
	if moved {
		if gitRepo != "" {
			say("  tracked in %s (repository differs from --root)", gitRepo)
		}
	} else {
		// Never say this looks tracked, whichever of the two causes git declined for: a
		// symlinked-bundle boundary or a plain untracked file. Always name git's own reason and,
		// only when a different repository actually received part of the write, name it.
		say("  untracked — git declined: %s", reason)
		if gitRepo != "" {
			say("  the untracked change also touches %s (repository differs from --root)", gitRepo)
		}
	}
	say("rewrote %d inbound link(s) in %d file(s), %d outbound link(s)", len(plan.Inbound), info.inboundFiles,
		len(plan.Outbound))
	say("rewrote %d wikilink(s) in %d file(s)", len(wlRewrite), info.wikilinkFiles)
	say("rewrote %d sync source(s) in %d file(s)", info.syncBlocks, len(plan.SyncSources))
	if len(ctxWhere) > 0 {
		say("listed in %d ctx bundle(s): %s", len(ctxWhere), strings.Join(ctxWhere, ", "))
		for _, n := range info.ctxNotes {
			say("  ctx        %s: not refreshed, %d parse problem(s) — run okf ctx check", n.Slug, n.Problems)
		}
	}
	printSkipped()
	say("reindexed %d index file(s) across: %s", info.reindexed, strings.Join(plan.Bundles, ", "))
	say("staged for commit — run `okf check` before committing.")

	notRefreshed := make([]envelope.Obj, 0, len(info.ctxNotes))
	for _, n := range info.ctxNotes {
		notRefreshed = append(notRefreshed, envelope.O("slug", n.Slug, "problems", n.Problems))
	}
	var trackedIn, untrackedReason any
	if gitRepo != "" {
		trackedIn = gitRepo
	}
	if !moved {
		untrackedReason = reason
	}
	movedWith := "fs"
	if moved {
		movedWith = "git mv"
	}
	result.Set("moved_with", movedWith)
	result.Set("tracked_in", trackedIn)
	result.Set("untracked_reason", untrackedReason)
	result.Set("rewritten", envelope.O(
		"inbound_links", len(plan.Inbound), "inbound_files", info.inboundFiles,
		"outbound_links", len(plan.Outbound), "wikilinks", len(wlRewrite),
		"wikilink_files", info.wikilinkFiles, "sync_sources", info.syncBlocks,
		"sync_files", len(plan.SyncSources)))
	result.Set("ctx_not_refreshed", notRefreshed)
	result.Set("reindexed", info.reindexed)
	return result, nil
}
