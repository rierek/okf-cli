package tagwrite

import (
	"fmt"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/cli"
	"nas/volume1/data/git/okf-tools/go/internal/complete"
	"nas/volume1/data/git/okf-tools/go/internal/diffs"
	"nas/volume1/data/git/okf-tools/go/internal/envelope"
	"nas/volume1/data/git/okf-tools/go/internal/frontmatter"
	"nas/volume1/data/git/okf-tools/go/internal/okferr"
	"nas/volume1/data/git/okf-tools/go/internal/wikisync"
)

const syncScopeHelp = "<bundle> or <bundle>/<subdir> (default: whole catalogue)"

// registerSync attaches `sync-insert` and `sync-update` with their completers (Python
// add_sync_insert_parser and add_sync_update_parser).
func registerSync(app *cli.App) {
	app.Attach("sync-insert", cli.Spec{
		Args: []cli.Arg{
			{Dest: "consumer", Help: "consumer concept to insert into (<bundle>/<concept-id>)"},
			{Dest: "concept", Help: "canonical owner concept (<bundle>/<concept-id>)"},
			{Dest: "block_id", Metavar: []string{"block-id"}, Help: "canon block id to materialise"},
			{Flags: []string{"--apply"}, Action: cli.StoreTrue, Help: "write the block (default: dry-run preview only)"},
			cli.JSON(),
		},
		Handler: runSyncInsert,
	})
	complete.Attach([]string{"sync-insert"}, "consumer", complete.Concepts)
	complete.Attach([]string{"sync-insert"}, "concept", complete.Concepts)
	complete.Attach([]string{"sync-insert"}, "block_id", wikisync.CompleteBlockIDs)

	app.Attach("sync-update", cli.Spec{
		Args: []cli.Arg{
			{Dest: "target", Nargs: cli.Optional, Help: syncScopeHelp},
			{Flags: []string{"--source"}, Help: "only blocks whose canonical source is this path (/bundle/concept.md)"},
			{Flags: []string{"--block"}, Metavar: []string{"BLOCK_ID"}, Help: "only blocks with this id"},
			{Flags: []string{"--apply"}, Action: cli.StoreTrue, Help: "write changes (default: dry-run preview only)"},
			{Flags: []string{"--force"}, Action: cli.StoreTrue,
				Help: "also overwrite a consumer copy that was modified locally (discards it)"},
			cli.JSON(),
		},
		Handler: runSyncUpdate,
	})
	complete.Attach([]string{"sync-update"}, "target", complete.Scopes)
	complete.Attach([]string{"sync-update"}, "source", wikisync.CompleteCanonSources)
	complete.Attach([]string{"sync-update"}, "block", wikisync.CompleteCanonBlockIDs)
}

// renderSyncBlock is Python render_sync_block, the one place the sync notation is authored. The
// visible callout sits between the opening marker and the body marker, so the hash covers the
// payload alone.
func renderSyncBlock(blockID, source, payload string) string {
	return catalogue.SyncOpenLit + "id=" + blockID + " source=" + source + " hash=" + wikisync.SyncHash(payload) + " -->\n" +
		"> [!quote] Synchronisiert aus `" + source + "` — Canon-Owner, hier nicht bearbeiten.\n" +
		catalogue.SyncBody + "\n" + strings.Trim(payload, "\n") + "\n" + catalogue.SyncEnd
}

// syncOrQuestion is Python `s or "?"`: the part of a block address a malformed marker lacks.
func syncOrQuestion(s string) string {
	if s == "" {
		return "?"
	}
	return s
}

// syncAddr is Python _sync_addr: `/bundle/owner.md#block-id`, still printable for a malformed marker.
func syncAddr(b wikisync.SyncBlock) string {
	return syncOrQuestion(b.Source) + "#" + syncOrQuestion(b.ID)
}

// syncRow is Python _block_row, plus the status of an unresolvable block. A marker that did not
// parse has neither source nor id (null).
func syncRow(h wikisync.SyncHit, withStatus bool) envelope.Obj {
	var source, id any
	if h.Block.MarkerParsed {
		source, id = h.Block.Source, h.Block.ID
	}
	row := envelope.O("consumer", h.Rel, "source", source, "id", id)
	if withStatus {
		row.Set("status", h.Status)
	}
	return row
}

func syncRows(hits []wikisync.SyncHit, withStatus bool) []envelope.Obj {
	rows := make([]envelope.Obj, len(hits))
	for i, h := range hits {
		rows[i] = syncRow(h, withStatus)
	}
	return rows
}

// syncFilter is the value of an option as a pointer: nil when the option is absent, so an empty
// value still filters (Python `is not None`).
func syncFilter(a *cli.Args, dest string) *string {
	if !a.Has(dest) {
		return nil
	}
	s := a.String(dest)
	return &s
}

// runSyncInsert is Python cmd_sync_insert: append the canon block `block-id` of the owner to the
// consumer. The frontmatter is not touched; the text is cut at it only to find the body.
func runSyncInsert(root string, a *cli.Args) (any, error) {
	blockID, apply := a.String("block_id"), a.Bool("apply")
	ownerPath, ownerRel, payload, err := wikisync.CanonPayload(root, a.String("concept"), blockID)
	if err != nil {
		return nil, err
	}
	source := "/" + ownerRel
	consumerPath, err := catalogue.ResolveConcept(root, a.String("consumer"))
	if err != nil {
		return nil, err
	}
	consumerRel := relPath(root, consumerPath)
	if consumerPath == ownerPath {
		return nil, okferr.Newf(okferr.InvalidInput, "%s owns `%s` — a canon owner does not consume its own block",
			consumerRel, blockID)
	}
	stored, ok, err := catalogue.ReadFileVerbatim(consumerPath)
	if err != nil {
		return nil, err
	}
	if !ok {
		return nil, okferr.Newf(okferr.NonConformant, "not valid UTF-8: %s", consumerRel)
	}
	doc := frontmatter.Read(stored)
	for _, b := range wikisync.ParseSyncBlocks(doc.Body) {
		if b.ID != blockID {
			continue
		}
		if b.Source == source {
			return nil, okferr.Newf(okferr.InvalidInput, "%s already carries `%s` from %s — use sync-update to refresh it",
				consumerRel, blockID, source)
		}
		// Two blocks with one id read as one block to a human, and `sync-status --block` could not
		// tell them apart either.
		return nil, okferr.Newf(okferr.InvalidInput,
			"%s already carries a block `%s` from %s — the id would be ambiguous in this concept",
			consumerRel, blockID, syncOrQuestion(b.Source))
	}
	next := doc.Head + strings.TrimRight(doc.Body, "\n") + "\n\n" + renderSyncBlock(blockID, source, payload) + "\n"
	files := diffs.UnifiedDiffs([]diffs.PlanEntry{planEntry(consumerRel, stored, next)}, nil)

	w := newOut()
	defer w.Flush()
	if !a.JSON {
		printDiffs(w, files)
	}
	if apply {
		if err := diffs.WriteFileVerbatim(consumerPath, next); err != nil {
			return nil, err
		}
	}
	if a.JSON {
		return envelope.O("applied", apply, "consumer", consumerRel, "source", source, "id", blockID,
			"files", diffData(files)), nil
	}
	if apply {
		fmt.Fprintf(w, "inserted        %s   %s#%s\n", consumerRel, source, blockID)
	} else {
		fmt.Fprintf(w, "would insert    %s   %s#%s\n", consumerRel, source, blockID)
		fmt.Fprintln(w, "sync-insert (dry-run): re-run with --apply.")
	}
	return nil, nil
}

// runSyncUpdate is Python cmd_sync_update: re-render every outdated block from its canon owner.
// Blocks whose owner is gone or whose markers are broken are never written and always reported; a
// block edited in the consumer is reported and left alone unless --force discards the edit. The
// blocks that can be updated are written even when others are reported.
func runSyncUpdate(root string, a *cli.Args) (any, error) {
	target := a.String("target")
	if target != "" {
		if err := catalogue.RequireBundleDir(root, target); err != nil {
			return nil, err
		}
	}
	canon, found, err := wikisync.ScanSyncBlocks(root, target, syncFilter(a, "source"), syncFilter(a, "block"))
	if err != nil {
		return nil, err
	}
	apply, force := a.Bool("apply"), a.Bool("force")
	verb := "would update"
	if apply {
		verb = "updated"
	}

	var consumers []string // absolute paths in order of first block
	byConsumer := map[string][]wikisync.SyncHit{}
	var refused, unresolvable []wikisync.SyncHit
	for _, h := range found {
		switch {
		case h.Status == "synced":
		case h.Status == "source-missing" || h.Status == "malformed":
			// Repairing or deleting a block whose owner is gone, or whose markers a human broke,
			// is a human decision, not a rewrite.
			unresolvable = append(unresolvable, h)
		case (h.Status == "consumer-modified" || h.Status == "both-changed") && !force:
			refused = append(refused, h)
		default:
			if _, seen := byConsumer[h.Path]; !seen {
				consumers = append(consumers, h.Path)
			}
			byConsumer[h.Path] = append(byConsumer[h.Path], h)
		}
	}

	var updated []wikisync.SyncHit
	var plan []diffs.PlanEntry
	for _, ap := range consumers {
		hits := byConsumer[ap]
		stored, ok, err := catalogue.ReadFileVerbatim(ap)
		if err != nil {
			return nil, err
		}
		if !ok {
			envelope.Note("skipping " + ap + " — not valid UTF-8")
			continue
		}
		next, ok := spliceSyncBlocks(stored, hits, canon)
		if !ok {
			envelope.Note("skipping " + ap + " — its sync blocks differ between the scan and the stored bytes")
			continue
		}
		updated = append(updated, hits...)
		plan = append(plan, planEntry(hits[0].Rel, stored, next))
	}
	files := diffs.UnifiedDiffs(plan, nil)
	if apply {
		if err := diffs.WritePlan(root, plan); err != nil {
			return nil, err
		}
	}
	result := envelope.O("applied", apply, "files", diffData(files), "updated", syncRows(updated, false),
		"refused", syncRows(refused, false), "unresolvable", syncRows(unresolvable, true))

	if !a.JSON {
		w := newOut()
		defer w.Flush()
		printDiffs(w, files)
		for _, h := range updated {
			fmt.Fprintf(w, "%-14s %s   %s\n", verb, h.Rel, syncAddr(h.Block))
		}
		for _, h := range refused {
			fmt.Fprintf(w, "refused        %s   %s  (consumer copy modified — reconcile into the canon owner first, or --force to discard)\n",
				h.Rel, syncAddr(h.Block))
		}
		for _, h := range unresolvable {
			fmt.Fprintf(w, "%-14s %s   %s\n", h.Status, h.Rel, syncAddr(h.Block))
		}
		rerun := ""
		if !apply {
			rerun = " Re-run with --apply."
		}
		fmt.Fprintf(w, "sync-update: %d %s, %d refused, %d unresolvable.%s\n", len(updated), verb, len(refused), len(unresolvable), rerun)
	}
	if len(refused) > 0 || len(unresolvable) > 0 {
		return nil, okferr.WithResult(okferr.Drift, "", result)
	}
	if a.JSON {
		return result, nil
	}
	return nil, nil
}

// spliceSyncBlocks is stored with the blocks of hits re-rendered from the canon index, false when
// the stored bytes do not carry the blocks the scan saw.
//
// Python cuts the spans from the scan, which reads through universal newlines, and splices them
// into the verbatim text: in a CRLF file every offset behind the first line ending is off and the
// splice corrupts the file. Here the spans come from the stored text itself; the scan's reading of
// it only pairs each hit with its stored block.
func spliceSyncBlocks(stored string, hits []wikisync.SyncHit, canon wikisync.CanonIndex) (string, bool) {
	doc := frontmatter.Read(stored)
	blocks := wikisync.ParseSyncBlocks(doc.Body)
	scanned := wikisync.ParseSyncBlocks(frontmatter.Read(catalogue.DecodeText([]byte(stored))).Body)
	if len(blocks) != len(scanned) {
		return "", false
	}
	want := make(map[int]bool, len(hits))
	for _, h := range hits {
		want[h.Block.Start] = true
	}
	var out strings.Builder
	last, done := 0, 0
	for i, s := range scanned {
		b := blocks[i]
		if b.ID != s.ID || b.Source != s.Source || b.Hash != s.Hash || b.MarkerParsed != s.MarkerParsed || b.Malformed != s.Malformed {
			return "", false
		}
		if !want[s.Start] {
			continue
		}
		payload := canon[wikisync.CanonKey{Rel: strings.TrimLeft(s.Source, "/"), ID: s.ID}]
		out.WriteString(doc.Body[last:b.Start])
		out.WriteString(renderSyncBlock(s.ID, s.Source, payload))
		last = b.End
		done++
	}
	if done != len(hits) {
		return "", false
	}
	out.WriteString(doc.Body[last:])
	return doc.Head + out.String(), true
}
