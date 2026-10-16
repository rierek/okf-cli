package move

import (
	"os"
	"regexp"
	"slices"
	"sort"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/frontmatter"
	"nas/volume1/data/git/okf-tools/go/internal/linkscan"
	"nas/volume1/data/git/okf-tools/go/internal/pytext"
	"nas/volume1/data/git/okf-tools/go/internal/wikisync"
)

// The statuses of a WikilinkRecord. A `rewrite` is spliced into its file; the other two are only
// reported.
const (
	StatusRewrite           = "rewrite"
	StatusSkippedAmbiguous  = "skipped-ambiguous"
	StatusCollisionAffected = "collision-affected"
)

// LinkRewrite is one markdown link target and the text that replaces it.
type LinkRewrite struct{ Old, New string }

// InboundRewrite is a link in the file Source (relative to the root) that points at the moved
// concept, and its replacement.
type InboundRewrite struct{ Source, Old, New string }

// SyncSource is a consumer concept (relative to the root) whose materialised canon blocks record
// the moved concept as their `source=`, and how many of them there are.
type SyncSource struct {
	Consumer string
	Blocks   int
}

// WikilinkRecord is one wikilink occurrence of the rename scan the move touches or reports: the
// wikisync record (Source, Region, Raw, Page; Start and End are offsets in the LF-normalised text
// the plan scanned, not in the stored file) with the plan's verdict. Status is one of the three
// Status constants and Candidates the paths the occurrence resolved to (after the move for a
// collision-affected one). NewRaw is the replacement token of a `rewrite` and empty otherwise.
// TurnsAmbiguous is set when the occurrence resolved to one concept before the move and does not
// afterwards.
type WikilinkRecord struct {
	wikisync.Wikilink
	NewRaw         string
	TurnsAmbiguous bool
}

// RenamePlan is the reference rewrites a move requires, computed without touching the disk (Python
// plan_rename).
type RenamePlan struct {
	// Inbound are the markdown links pointing at the moved file, the file itself excluded.
	Inbound []InboundRewrite
	// Outbound are the moved file's own links; only for a move across bundles, within a bundle
	// they stay valid.
	Outbound []LinkRewrite
	// Wikilinks are the occurrences with status rewrite, skipped-ambiguous or collision-affected.
	Wikilinks []WikilinkRecord
	// WikilinkCollisions are the concepts that already carry the new basename.
	WikilinkCollisions []string
	// Bundles are the affected bundle names, sorted: the reindex targets.
	Bundles []string
	// SyncSources are the consumers whose canon blocks name the moved file as source.
	SyncSources []SyncSource
}

// bundleOf is the top-level bundle directory a path lives in: its first part under root.
func bundleOf(root, abspath string) string {
	first, _, _ := strings.Cut(pyRelpath(pyAbspath(abspath), root), "/")
	return first
}

// linkExpr is the canonical OKF link string to dstAbs: catalogue-root-absolute
// (`/bundle/subdir/concept.md`). The leading `/` is the catalogue root, which is the Obsidian vault
// root, so one form addresses same- and cross-bundle targets and resolves for okf and Obsidian alike.
func linkExpr(root, dstAbs string) string {
	return "/" + pyRelpath(pyAbspath(dstAbs), root)
}

// splitLinkSuffix splits a link target into its path and its #anchor/?query tail, kept verbatim
// so a rewrite preserves deep links.
func splitLinkSuffix(raw string) (path, suffix string) {
	if i := strings.IndexAny(raw, "#?"); i != -1 {
		return raw[:i], raw[i:]
	}
	return raw, ""
}

var urlSchemeRE = regexp.MustCompile(`^[a-z][a-z0-9+.-]*://`)

// resolveLinkTarget is the absolute path a markdown link target raw, written in srcAbs, resolves
// to: catalogue-root-absolute (`/...`, the Obsidian vault root rather than the bundle root) or
// relative to the source's directory. ok is false for an external, anchor-only or non-.md link.
func resolveLinkTarget(root, srcAbs, raw string) (string, bool) {
	path, _ := splitLinkSuffix(pytext.Strip(raw))
	if !strings.HasSuffix(path, ".md") || urlSchemeRE.MatchString(path) || strings.HasPrefix(path, "mailto:") {
		return "", false
	}
	if strings.HasPrefix(path, "/") {
		return pyAbspath(catalogue.Join(root, strings.TrimLeft(path, "/"))), true
	}
	return pyAbspath(catalogue.Join(pyDirname(srcAbs), path)), true
}

// dedupe drops repeats and keeps the first occurrence of each, in order.
func dedupe[T comparable](xs []T) []T {
	seen := make(map[T]bool, len(xs))
	var out []T
	for _, x := range xs {
		if !seen[x] {
			seen[x] = true
			out = append(out, x)
		}
	}
	return out
}

// listdir is os.listdir: the names in directory order, not sorted.
func listdir(dir string) ([]string, error) {
	f, err := os.Open(dir)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	return f.Readdirnames(-1)
}

// canonicalCasePath is abspath respelled the way the filesystem stores it.
//
// On a case-insensitive filesystem the caller may name a file in any casing, and every downstream
// comparison (the basename index, the markdown ref matrix, the self-reference check) then compares
// the caller's spelling against the scan's. Normalising once here keeps those comparisons exact
// rather than case-folded, which matters because a folded comparison would be wrong on a
// case-sensitive filesystem. The first entry in directory order that matches case-insensitively
// wins, as with os.listdir.
func canonicalCasePath(root, abspath string) string {
	rel := pyRelpath(abspath, root)
	if strings.HasPrefix(rel, "..") {
		return abspath
	}
	cur := root
	for _, seg := range strings.Split(rel, "/") {
		match := ""
		if names, err := listdir(cur); err == nil {
			low := pytext.Lower(seg)
			for _, e := range names {
				if pytext.Lower(e) == low {
					match = e
					break
				}
			}
		}
		if match == "" {
			match = seg
		}
		cur = catalogue.Join(cur, match)
	}
	return cur
}

// dropMd is name without its last three characters, the `.md` every caller has checked for.
func dropMd(name string) string {
	if len(name) < 3 {
		return ""
	}
	return name[:len(name)-3]
}

// lastSegment is the part of a wikilink page after its last `/`.
func lastSegment(page string) string { return page[strings.LastIndex(page, "/")+1:] }

// rewriteWikilinkRaw is `[[old|Label]]` -> `[[new|Label]]`, given the target's new
// catalogue-root-absolute path. Alias, heading/block suffix and an explicit `.md` carry over
// verbatim, so a deep link survives the rename.
//
// A path-qualified link keeps a path of the same depth, re-derived from the NEW location: carrying
// the old prefix over unchanged turned `[[a/old]]` into `[[a/new]]` after a move to bundle `b`, an
// address that resolves to nothing.
func rewriteWikilinkRaw(raw, newLink string) string {
	inner := raw[2 : len(raw)-2]
	cut := len(inner)
	if i := strings.IndexAny(inner, "#|"); i != -1 {
		cut = i
	}
	head, rest := inner[:cut], inner[cut:]
	md := ""
	if strings.HasSuffix(head, ".md") {
		md = ".md"
		head = head[:len(head)-3]
	}
	depth := len(strings.Split(head, "/"))
	segments := strings.Split(dropMd(strings.TrimLeft(newLink, "/")), "/")
	if depth > len(segments) {
		depth = len(segments)
	}
	return "[[" + strings.Join(segments[len(segments)-depth:], "/") + md + rest + "]]"
}

// samePath reports whether cands is exactly the one path link, case-insensitively.
func samePath(cands []string, link string) bool {
	return len(cands) == 1 && pytext.Lower(cands[0]) == pytext.Lower(link)
}

// containsPath reports whether cands holds the path link, case-insensitively.
func containsPath(cands []string, link string) bool {
	low := pytext.Lower(link)
	return slices.ContainsFunc(cands, func(c string) bool { return pytext.Lower(c) == low })
}

// indexAfterMove is the basename index as it will look once the move has happened.
//
// collisions are folded in because they come from the rename scan's wider reach: a same-named
// draft in staging is invisible to the index but visible to Obsidian, so leaving it out made the
// simulation call an address unique that the app will show as ambiguous.
//
// index already carries the archive precedence (it came out of BuildBasenameIndex), so every key
// untouched by the move stays correct by construction. The slot the move LANDS in is the one
// exception: it gains a brand-new candidate (newLink, plus any collisions) that was never subject
// to that precedence pass, so it is re-applied here. Archiving a concept whose basename an active
// concept still holds must not leave the freshly archived path next to that survivor as a second
// candidate; the survivor alone must win, exactly as in a freshly rebuilt index.
//
// The landing slot's key is the plain lower-cased basename, not the NFC-normalised key the index
// uses: Python does the same, so a basename that is not in NFC lands in a slot no lookup reads.
func indexAfterMove(index wikisync.BasenameIndex, oldLink, newLink string, collisions []string) wikisync.BasenameIndex {
	out := make(wikisync.BasenameIndex, len(index)+1)
	oldLow := pytext.Lower(oldLink)
	for k, v := range index {
		var kept []string
		for _, c := range v {
			if pytext.Lower(c) != oldLow {
				kept = append(kept, c)
			}
		}
		if len(kept) > 0 {
			out[k] = kept
		}
	}
	key := pytext.Lower(dropMd(pyBasename(newLink)))
	slot := dedupe(slices.Concat(out[key], []string{newLink}, collisions))
	out[key] = wikisync.ApplyArchivePrecedence(slot)
	return out
}

// planWikilinkRewrites is the wikilink half of PlanRename: the occurrences that are rewritten,
// skipped as ambiguous or affected by a collision, and the concepts that ALREADY carry the new
// basename.
//
// Renaming into an occupied basename turns every rewritten `[[old]]`, and every pre-existing
// `[[new]]` elsewhere, from a unique address into an ambiguous one, which is the very corruption
// the skipped-ambiguous rule refuses to commit. The caller decides; this function only refuses to
// hide it.
//
// A plain `[[name]]` carries no path, so a move keeping the basename leaves it valid, but a
// path-qualified `[[dir/name]]` does not survive one, which is why there is no basename
// short-circuit: every candidate occurrence is compared against the token the move would produce,
// and only a difference is planned. An occurrence whose page part is ambiguous is reported, never
// rewritten: guessing which of several same-named concepts the author meant is a coin flip.
func planWikilinkRewrites(root, oldAbs, newAbs string) ([]WikilinkRecord, []string, error) {
	oldBase, newBase := dropMd(pyBasename(oldAbs)), dropMd(pyBasename(newAbs))
	index, err := wikisync.BuildBasenameIndex(root)
	if err != nil {
		return nil, nil, err
	}
	oldLink := "/" + pyRelpath(oldAbs, root)
	newLink := "/" + pyRelpath(newAbs, root)
	seq, err := linkscan.IterRenameScanMd(root)
	if err != nil {
		return nil, nil, err
	}
	files := slices.Collect(seq)
	// Collisions come from the rename scan's own reach, not from the resolution index: the index
	// skips staging, assets and root-level files, every one of which this rename rewrites and
	// Obsidian itself indexes.
	oldLow, newLow := pytext.Lower(oldLink), pytext.Lower(newLink)
	newKey := wikisync.NormalizeKey(newBase)
	var collisions []string
	for _, ap := range files {
		c := "/" + pyRelpath(ap, root)
		low := pytext.Lower(c)
		if wikisync.NormalizeKey(dropMd(pyBasename(c))) == newKey && low != oldLow && low != newLow {
			collisions = append(collisions, c)
		}
	}
	sort.Strings(collisions)
	// Casefolded, because Resolve is (D06). A case-sensitive filter here silently excluded every
	// case-variant inbound link from the plan, which the very rename that was supposed to carry
	// them would have orphaned.
	oldKey := wikisync.NormalizeKey(oldBase)
	after := indexAfterMove(index, oldLink, newLink, collisions)
	var out []WikilinkRecord
	for _, ap := range files {
		rel := pyRelpath(ap, root)
		text, err := catalogue.ReadFile(ap)
		if err != nil {
			return nil, nil, err
		}
		for _, w := range wikisync.ParseWikilinks(text, rel) {
			key := wikisync.NormalizeKey(lastSegment(w.Page))
			if key != oldKey && key != newKey {
				continue
			}
			// Resolve the occurrence against the catalogue as it is and as it will be. Deciding
			// from the token alone missed the case where the token does not change but its
			// meaning does: a basename-preserving move into a bundle where another concept shares
			// the name turned a unique address ambiguous with nothing to rewrite and nothing said.
			status, cands := wikisync.Resolve(index, rel, w.Page)
			wasOurs := status == "resolved" && samePath(cands, oldLink)
			newRaw := w.Raw
			if wasOurs {
				newRaw = rewriteWikilinkRaw(w.Raw, newLink)
			}
			pageAfter, _, _ := wikisync.SplitWikilinkInner(newRaw[2 : len(newRaw)-2])
			statusAfter, candsAfter := wikisync.Resolve(after, rel, pageAfter)
			turns := status == "resolved" && statusAfter != "resolved"
			rec := WikilinkRecord{Wikilink: w}
			switch {
			case wasOurs && newRaw != w.Raw:
				rec.Status, rec.Candidates, rec.NewRaw, rec.TurnsAmbiguous = StatusRewrite, cands, newRaw, turns
			case key == oldKey && status == "ambiguous" && containsPath(cands, oldLink):
				rec.Status, rec.Candidates = StatusSkippedAmbiguous, cands
			case turns:
				// Either a bystander already pointing at the basename this move is about to
				// occupy, or a link whose token does not change but whose target set does. Both
				// lose a unique address without a byte of them being touched.
				rec.Status, rec.Candidates, rec.TurnsAmbiguous = StatusCollisionAffected, candsAfter, true
			default:
				continue
			}
			out = append(out, rec)
		}
	}
	return out, collisions, nil
}

// PlanRename computes the reference rewrites a move oldAbs -> newAbs requires WITHOUT touching
// disk, so it also drives the dry-run preview. The paths are absolute.
func PlanRename(root, oldAbs, newAbs string) (*RenamePlan, error) {
	oldAbs, newAbs = pyAbspath(oldAbs), pyAbspath(newAbs)
	plan := &RenamePlan{}
	refs, err := linkscan.BuildRefMatrix(root, oldAbs)
	if err != nil {
		return nil, err
	}
	for _, r := range refs {
		if pyAbspath(catalogue.Join(root, r.Source)) == oldAbs {
			continue // self-reference: handled by the outbound pass
		}
		_, suffix := splitLinkSuffix(r.Raw)
		if newRaw := linkExpr(root, newAbs) + suffix; newRaw != r.Raw {
			plan.Inbound = append(plan.Inbound, InboundRewrite{r.Source, r.Raw, newRaw})
		}
	}
	if bundleOf(root, oldAbs) != bundleOf(root, newAbs) {
		src := oldAbs
		if !pyExists(oldAbs) {
			src = newAbs
		}
		srcText, err := catalogue.ReadFile(src)
		if err != nil {
			return nil, err
		}
		// Same mask the applier uses, or the plan reports rewrites the applier then declines to
		// make: the old ```-only strip left inline-code and indented examples in the plan and out
		// of the file.
		masked := linkscan.WikilinkScanText(srcText)
		for _, m := range catalogue.CrosslinkRE.FindAllStringSubmatchIndex(masked, -1) {
			raw := srcText[m[4]:m[5]]
			tgt, ok := resolveLinkTarget(root, oldAbs, raw)
			if !ok || !catalogue.RealFS.IsFile(tgt) {
				continue
			}
			_, suffix := splitLinkSuffix(raw)
			if newRaw := linkExpr(root, tgt) + suffix; newRaw != raw {
				plan.Outbound = append(plan.Outbound, LinkRewrite{raw, newRaw})
			}
		}
		plan.Outbound = dedupe(plan.Outbound)
	}
	bundles := []string{bundleOf(root, oldAbs), bundleOf(root, newAbs)}
	sort.Strings(bundles)
	plan.Bundles = slices.Compact(bundles)
	plan.Wikilinks, plan.WikilinkCollisions, err = planWikilinkRewrites(root, oldAbs, newAbs)
	if err != nil {
		return nil, err
	}
	plan.SyncSources, err = findSyncSourceRefs(root, "/"+pyRelpath(oldAbs, root))
	if err != nil {
		return nil, err
	}
	return plan, nil
}

// findSyncSourceRefs lists every concept carrying at least one materialised canon block whose
// `source=` is exactly sourceValue, with the number of such blocks, sorted by concept.
//
// Without this a rename of a canonical concept breaks the whole ownership graph into
// `source-missing`: the markdown link rewriters never see a `source=` attribute, because it is
// not a link. Staging directories are not pruned: a consumer in `_inbox`, `_archive` and the like
// must also get its `source=` repointed.
func findSyncSourceRefs(root, sourceValue string) ([]SyncSource, error) {
	scopes, err := catalogue.ResolveScopes(root, "", true, false)
	if err != nil {
		return nil, err
	}
	var out []SyncSource
	for _, sc := range scopes {
		for ap := range catalogue.IterAllMd(sc.Path, false) {
			text, err := catalogue.ReadFile(ap)
			if err != nil {
				return nil, err
			}
			// The body is a suffix of the text, so a text without the marker has no body with it.
			if !strings.Contains(text, catalogue.SyncOpenLit) {
				continue
			}
			body := frontmatter.Read(text).Body
			if !strings.Contains(body, catalogue.SyncOpenLit) {
				continue
			}
			n := 0
			for _, b := range wikisync.ParseSyncBlocks(body) {
				if b.Source == sourceValue {
					n++
				}
			}
			if n > 0 {
				out = append(out, SyncSource{pyRelpath(ap, root), n})
			}
		}
	}
	sort.SliceStable(out, func(i, j int) bool { return out[i].Consumer < out[j].Consumer })
	return out, nil
}
