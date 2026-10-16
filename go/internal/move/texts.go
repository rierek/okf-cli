package move

import (
	"os"
	"sort"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/ctxfile"
	"nas/volume1/data/git/okf-tools/go/internal/diffs"
	"nas/volume1/data/git/okf-tools/go/internal/envelope"
	"nas/volume1/data/git/okf-tools/go/internal/indexwrite"
	"nas/volume1/data/git/okf-tools/go/internal/linkscan"
	"nas/volume1/data/git/okf-tools/go/internal/wikisync"
)

// syncSourceText is text with every `source=oldSource` sync marker repointed at newSource, and the
// number of them. Only that attribute's slice is spliced, so the payload, the recorded hash and
// the attribution line stay byte-identical: the block was not re-materialised, only its owner
// moved.
func syncSourceText(text, oldSource, newSource string) (string, int) {
	group := 2 * catalogue.SyncOpenRE.SubexpIndex("source")
	var b strings.Builder
	last, n := 0, 0
	for _, m := range catalogue.SyncOpenRE.FindAllStringSubmatchIndex(text, -1) {
		a, e := m[group], m[group+1]
		if text[a:e] != oldSource {
			continue
		}
		b.WriteString(text[last:a])
		b.WriteString(newSource)
		last = e
		n++
	}
	if n == 0 {
		return text, 0
	}
	b.WriteString(text[last:])
	return b.String(), n
}

// linkRewriteText is text with its markdown link targets rewritten, spliced by offset over the same
// dead-zone mask BuildRefMatrix used to find them.
//
// A whole-file replace edited bytes the planner never reported: a link inside a code fence was
// rewritten and not counted, so the run changed a documentation sample while claiming a smaller
// edit than it made. A target listed twice keeps its last replacement.
func linkRewriteText(text string, rewrites []LinkRewrite) string {
	mapping := make(map[string]string, len(rewrites))
	for _, r := range rewrites {
		mapping[r.Old] = r.New
	}
	var b strings.Builder
	last := 0
	for _, m := range catalogue.CrosslinkRE.FindAllStringSubmatchIndex(linkscan.WikilinkScanText(text), -1) {
		a, e := m[4], m[5]
		newRaw, ok := mapping[text[a:e]]
		if !ok {
			continue
		}
		b.WriteString(text[last:a])
		b.WriteString(newRaw)
		last = e
	}
	b.WriteString(text[last:])
	return b.String()
}

// wikilinkRewriteText is text with its wikilinks rewritten. renameMap maps an old raw token to its
// replacement; every occurrence the scanner accepts and the map names is spliced in by offset.
// Splicing by offset, instead of replacing the token string, is what guarantees an identical-looking
// `[[old]]` inside a fence, an indented block or a comment is never touched: the scanner never
// returned it, so no offset points at it.
func wikilinkRewriteText(text string, renameMap map[string]string) string {
	var b strings.Builder
	last := 0
	for _, w := range wikisync.ParseWikilinks(text, "") {
		newRaw, ok := renameMap[w.Raw]
		if !ok {
			continue
		}
		b.WriteString(text[last:w.Start])
		b.WriteString(newRaw)
		last = w.End
	}
	b.WriteString(text[last:])
	return b.String()
}

// plannedFS is the catalogue tree after a write run that removes the absolute paths in removed
// and writes texts ({absolute path: text}), computed without touching the disk.
type plannedFS struct {
	removed map[string]bool
	texts   map[string]string
}

var _ catalogue.TreeView = (*plannedFS)(nil)

// ListDir lists the names the real directory keeps and the planned files below it, sorted.
func (f *plannedFS) ListDir(d string) ([]string, error) {
	names := map[string]bool{}
	if catalogue.RealFS.IsDir(d) {
		real, err := os.ReadDir(d)
		if err != nil {
			return nil, err
		}
		for _, e := range real {
			if !f.removed[catalogue.Join(d, e.Name())] {
				names[e.Name()] = true
			}
		}
	}
	pre := strings.TrimRight(d, "/") + "/"
	for p := range f.texts {
		if strings.HasPrefix(p, pre) {
			first, _, _ := strings.Cut(p[len(pre):], "/")
			names[first] = true
		}
	}
	out := make([]string, 0, len(names))
	for n := range names {
		out = append(out, n)
	}
	sort.Strings(out)
	return out, nil
}

func (f *plannedFS) IsFile(p string) bool {
	if _, ok := f.texts[p]; ok {
		return true
	}
	return !f.removed[p] && catalogue.RealFS.IsFile(p)
}

func (f *plannedFS) IsDir(p string) bool {
	pre := strings.TrimRight(p, "/") + "/"
	for t := range f.texts {
		if strings.HasPrefix(t, pre) {
			return true
		}
	}
	return !f.removed[p] && catalogue.RealFS.IsDir(p)
}

// Walk lists each directory top-down; a symbolic link to a directory is listed and not entered.
func (f *plannedFS) Walk(top string, fn catalogue.WalkFunc) {
	names, err := f.ListDir(top)
	if err != nil {
		return
	}
	var dirs, files []string
	for _, n := range names {
		if f.IsDir(catalogue.Join(top, n)) {
			dirs = append(dirs, n)
		} else {
			files = append(files, n)
		}
	}
	for _, d := range fn(top, dirs, files) {
		if p := catalogue.Join(top, d); !pyIslink(p) {
			f.Walk(p, fn)
		}
	}
}

func (f *plannedFS) Read(p string) (string, error) {
	if t, ok := f.texts[p]; ok {
		return lfNormalised(t), nil
	}
	return catalogue.ReadFile(p)
}

func (f *plannedFS) ReadVerbatim(p string) (string, bool, error) {
	if t, ok := f.texts[p]; ok {
		return t, true, nil
	}
	return catalogue.ReadFileVerbatim(p)
}

// lfNormalised is text with CRLF and lone CR line endings turned into LF.
func lfNormalised(text string) string {
	return strings.ReplaceAll(strings.ReplaceAll(text, "\r\n", "\n"), "\r", "\n")
}

// ctxNote names a ctx bundle that lists the moved concept but has rows the parser cannot read, so
// it is left as it is.
type ctxNote struct {
	Slug     string
	Problems int
}

// moveInfo carries the counts and ctx parse problems the report lines of a move name.
type moveInfo struct {
	syncBlocks    int
	ctxNotes      []ctxNote
	inboundFiles  int
	wikilinkFiles int
	reindexed     int
}

// textSet is the texts of a write run in first-touch order: stored is what a file holds now, cur
// what the run makes of it. A nil text is a file that does not exist (stored) or that is not valid
// UTF-8 (both), and stays out of the plan.
type textSet struct {
	order       []string
	cur, stored map[string]*string
}

func newTextSet() *textSet {
	return &textSet{cur: map[string]*string{}, stored: map[string]*string{}}
}

// set gives rel its new text; a new rel joins the order, an existing one keeps its place.
func (s *textSet) set(rel string, t *string) {
	if _, ok := s.cur[rel]; !ok {
		s.order = append(s.order, rel)
	}
	s.cur[rel] = t
}

// putStored records the stored text of rel unless it already has one.
func (s *textSet) putStored(rel string, t *string) {
	if _, ok := s.stored[rel]; !ok {
		s.stored[rel] = t
	}
}

// idxEntry is the stored and the planned text of one index file.
type idxEntry struct{ old, new *string }

// idxPlan is the index files a reindex plan names, in plan order.
type idxPlan struct {
	order   []string
	entries map[string]idxEntry
}

func newIdxPlan() *idxPlan { return &idxPlan{entries: map[string]idxEntry{}} }

func (p *idxPlan) add(es []diffs.PlanEntry) {
	for _, e := range es {
		if _, ok := p.entries[e.Path]; !ok {
			p.order = append(p.order, e.Path)
		}
		p.entries[e.Path] = idxEntry{e.Old, e.New}
	}
}

// planMoveTexts is the whole write run of a move as text, before anything is written: the entries
// are (rel path, stored text, new text) of the moved file, of every file with a rewritten link,
// wikilink or sync `source=`, of the ctx bundle files and of the managed index files of the
// affected bundles, the last two computed for the tree after the move. moves is {new rel: old rel}
// for the moved file. A destination that exists is overwritten: its text is the old side of the
// new path's entry and the old path is deleted instead of moved. Undecodable files stay out of the
// plan, as the splice writers always left them alone.
func planMoveTexts(root, oldAbs, newAbs string, plan *RenamePlan, wlRewrite []WikilinkRecord,
	ctxHits []ctxfile.CtxMembership) ([]diffs.PlanEntry, map[string]string, moveInfo, error) {
	oldRel, newRel := pyRelpath(oldAbs, root), pyRelpath(newAbs, root)
	ts := newTextSet()
	final := func(rel string) string {
		if rel == oldRel {
			return newRel
		}
		return rel
	}
	textOf := func(rel string) (*string, error) {
		if t, ok := ts.cur[rel]; ok {
			return t, nil
		}
		src := catalogue.Join(root, rel)
		if rel == newRel {
			src = oldAbs
		}
		text, ok, err := catalogue.ReadFileVerbatim(src)
		if err != nil {
			return nil, err
		}
		var t *string
		if ok {
			t = &text
		} else {
			envelope.Note("skipping " + src + " — not valid UTF-8")
		}
		ts.set(rel, t)
		ts.stored[rel] = t
		return t, nil
	}
	edit := func(rel string, fn func(string) string) error {
		t, err := textOf(rel)
		if err != nil || t == nil {
			return err
		}
		ts.set(rel, new(fn(*t)))
		return nil
	}
	var info moveInfo

	if _, err := textOf(newRel); err != nil {
		return nil, nil, info, err
	}
	if len(plan.Outbound) > 0 {
		if err := edit(newRel, func(t string) string { return linkRewriteText(t, plan.Outbound) }); err != nil {
			return nil, nil, info, err
		}
	}
	var srcOrder []string
	bySrc := map[string][]LinkRewrite{}
	for _, in := range plan.Inbound {
		src := final(in.Source)
		if _, ok := bySrc[src]; !ok {
			srcOrder = append(srcOrder, src)
		}
		bySrc[src] = append(bySrc[src], LinkRewrite{in.Old, in.New})
	}
	for _, rel := range srcOrder {
		rw := dedupe(bySrc[rel])
		if err := edit(rel, func(t string) string { return linkRewriteText(t, rw) }); err != nil {
			return nil, nil, info, err
		}
	}
	var wlOrder []string
	wlBySrc := map[string]map[string]string{}
	for _, r := range wlRewrite {
		src := final(r.Source)
		if wlBySrc[src] == nil {
			wlOrder = append(wlOrder, src)
			wlBySrc[src] = map[string]string{}
		}
		wlBySrc[src][r.Raw] = r.NewRaw
	}
	for _, rel := range wlOrder {
		renameMap := wlBySrc[rel]
		if err := edit(rel, func(t string) string { return wikilinkRewriteText(t, renameMap) }); err != nil {
			return nil, nil, info, err
		}
	}
	// The `source=` attribute of a materialised canon block is not a link, so neither link
	// rewriter touches it; without this the move silently breaks every consumer of the moved
	// concept's canon blocks into `source-missing`.
	for _, ss := range plan.SyncSources {
		err := edit(final(ss.Consumer), func(t string) string {
			t, n := syncSourceText(t, "/"+oldRel, "/"+newRel)
			info.syncBlocks += n
			return t
		})
		if err != nil {
			return nil, nil, info, err
		}
	}

	ctxRefresh := false
	seenSlug := map[string]bool{}
	for _, hit := range ctxHits {
		if seenSlug[hit.Slug] {
			continue
		}
		seenSlug[hit.Slug] = true
		rel := final(catalogue.CtxDir + "/" + hit.Slug + ".md")
		t, err := textOf(rel)
		if err != nil {
			return nil, nil, info, err
		}
		if t == nil {
			continue
		}
		text := lfNormalised(*t)
		desc, entries, problems := ctxfile.ParseCtx(text)
		if len(problems) > 0 {
			info.ctxNotes = append(info.ctxNotes, ctxNote{hit.Slug, len(problems)})
			continue
		}
		// A rejection of the ctx file's frontmatter ends the move before anything is written.
		next, err := ctxfile.CtxText(ctxfile.Ctx{Slug: hit.Slug, Description: desc, Entries: entries}, &text)
		if err != nil {
			return nil, nil, info, err
		}
		ts.set(rel, &next)
		ctxRefresh = true
	}
	ctxIndex := catalogue.CtxDir + "/index.md"
	if ctxRefresh && !pyExists(catalogue.Join(root, ctxIndex)) {
		ts.stored[ctxIndex] = nil
		ts.set(ctxIndex, new(indexwrite.CtxIndexSkeleton))
	}

	// Managed index blocks for the tree after the move: PlanReindex reads it through plannedFS.
	view := make(map[string]string, len(ts.order)+1)
	for _, rel := range ts.order {
		if t := ts.cur[rel]; t != nil {
			view[catalogue.Join(root, rel)] = *t
		}
	}
	if _, ok := view[newAbs]; !ok {
		text, err := catalogue.ReadFile(oldAbs)
		if err != nil {
			return nil, nil, info, err
		}
		view[newAbs] = text
	}
	fs := &plannedFS{removed: map[string]bool{oldAbs: true}, texts: view}
	bundleIdx, ctxIdx := newIdxPlan(), newIdxPlan()
	for _, b := range plan.Bundles {
		es, _, err := indexwrite.PlanReindex(root, catalogue.Join(root, b), false, false, fs)
		if err != nil {
			return nil, nil, info, err
		}
		bundleIdx.add(es)
	}
	if ctxRefresh {
		es, _, err := indexwrite.PlanReindex(root, catalogue.Join(root, catalogue.CtxDir), false, false, fs)
		if err != nil {
			return nil, nil, info, err
		}
		ctxIdx.add(es)
	}
	// {**ctx_idx, **bundle_idx}: the ctx files first, a bundle file of the same path overriding.
	merged := append([]string(nil), ctxIdx.order...)
	for _, rel := range bundleIdx.order {
		if _, ok := ctxIdx.entries[rel]; !ok {
			merged = append(merged, rel)
		}
	}
	for _, rel := range merged {
		e, ok := bundleIdx.entries[rel]
		if !ok {
			e = ctxIdx.entries[rel]
		}
		ts.putStored(rel, e.old)
		ts.set(rel, e.new)
	}

	var entries []diffs.PlanEntry
	for _, rel := range ts.order {
		if t := ts.cur[rel]; t != nil && rel != newRel {
			entries = append(entries, diffs.PlanEntry{Path: rel, Old: ts.stored[rel], New: t})
		}
	}
	moves := map[string]string{}
	if moved := ts.cur[newRel]; moved != nil {
		overwrites := false
		if pyExists(newAbs) {
			same, err := pySamefile(oldAbs, newAbs)
			if err != nil {
				return nil, nil, info, err
			}
			overwrites = !same
		}
		if overwrites {
			dest, ok, err := catalogue.ReadFileVerbatim(newAbs)
			if err != nil {
				return nil, nil, info, err
			}
			if ok {
				entries = append(entries,
					diffs.PlanEntry{Path: newRel, Old: &dest, New: moved},
					diffs.PlanEntry{Path: oldRel, Old: ts.stored[newRel], New: nil})
			}
		} else {
			entries = append(entries, diffs.PlanEntry{Path: newRel, Old: ts.stored[newRel], New: moved})
			moves[newRel] = oldRel
		}
	}
	info.inboundFiles, info.wikilinkFiles, info.reindexed = len(srcOrder), len(wlOrder), len(bundleIdx.order)
	return entries, moves, info, nil
}
