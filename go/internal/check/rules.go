package check

import (
	"fmt"
	"os"
	"path/filepath"
	"slices"
	"sort"
	"strings"

	"go.yaml.in/yaml/v3"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/ctxfile"
	"nas/volume1/data/git/okf-tools/go/internal/frontmatter"
	"nas/volume1/data/git/okf-tools/go/internal/pytext"
	"nas/volume1/data/git/okf-tools/go/internal/wikisync"
)

// FilenameForbiddenChars are the characters a concept filename (without its `.md`) must not hold:
// the 13 characters `#^[]|\:?*"<>%`. The rule kc/name/filename-chars and the new-filename guard of
// `rename` and `archive` read this one value.
const FilenameForbiddenChars = `#^[]|\:?*"<>%`

// ForbiddenFilenameChars is the forbidden characters name holds in its stem, sorted and joined: the
// name without its last three characters (`.md`). It is "" for a name that holds none.
func ForbiddenFilenameChars(name string) string {
	runes := []rune(name)
	if len(runes) >= 3 {
		runes = runes[:len(runes)-3]
	} else {
		runes = nil
	}
	var bad []rune
	for _, r := range runes {
		if strings.ContainsRune(FilenameForbiddenChars, r) && !slices.Contains(bad, r) {
			bad = append(bad, r)
		}
	}
	slices.Sort(bad)
	return string(bad)
}

// germanFMKeys are the frontmatter keys kc/frontmatter/english-keys flags.
var germanFMKeys = map[string]bool{"titel": true, "beschreibung": true, "typ": true, "stichworte": true,
	"datum": true, "zusammenfassung": true}

// typeOf is the stripped text of the `type` key.
func typeOf(c *fileCtx) string { return pytext.Strip(frontmatter.Text(c.fm, "type", "")) }

func checkFrontmatterParseable(c *fileCtx) []string {
	if c.isReserved || c.hasFM {
		return nil
	}
	if c.fmError != "" {
		return []string{"no parseable frontmatter: " + c.fmError}
	}
	return []string{"no parseable frontmatter"}
}

func checkTypeNonempty(c *fileCtx) []string {
	if c.isReserved || !c.hasFM || typeOf(c) != "" {
		return nil
	}
	return []string{"missing/empty `type`"}
}

func checkReservedNoType(c *fileCtx) []string {
	if !c.isReserved || !c.hasFM || typeOf(c) == "" {
		return nil
	}
	return []string{"reserved file must not carry `type`"}
}

func checkFilenameChars(c *fileCtx) []string {
	if c.isReserved {
		return nil
	}
	if bad := ForbiddenFilenameChars(c.fn); bad != "" {
		return []string{"forbidden char(s) in filename: " + bad}
	}
	return nil
}

func checkTypeRegistered(c *fileCtx) []string {
	if c.isReserved || !c.hasFM || c.run.typesSet == nil {
		return nil
	}
	if t := typeOf(c); t != "" && !c.run.typesSet[t] {
		return []string{fmt.Sprintf("type `%s` not registered in TYPES.md", t)}
	}
	return nil
}

// checkTagRegistered is the closed-vocabulary gate: every frontmatter tag must be in TAGS.md. It is
// a no-op when TAGS.md is absent. The severity is warning, so it surfaces new tags without
// blocking; `check --strict` counts it toward the exit code and keeps the severity.
func checkTagRegistered(c *fileCtx) []string {
	if c.isReserved || !c.hasFM || c.run.tagsSet == nil {
		return nil
	}
	var out []string
	for _, t := range frontmatter.Tags(c.fm) {
		if !c.run.tagsSet[t] {
			out = append(out, fmt.Sprintf("tag `%s` not registered in TAGS.md", t))
		}
	}
	return out
}

func checkEnglishKeys(c *fileCtx) []string {
	if c.isReserved || !c.hasFM {
		return nil
	}
	var hits []string
	for _, p := range frontmatter.Items(c.fm) {
		if k := p.Key; k.Kind == yaml.ScalarNode && k.ShortTag() == "!!str" && germanFMKeys[k.Value] {
			hits = append(hits, k.Value)
		}
	}
	if len(hits) == 0 {
		return nil
	}
	sort.Strings(hits)
	return []string{"German frontmatter key(s): " + strings.Join(hits, ", ")}
}

// checkTagsBlockForm is a local convention (this catalogue, not the OKF spec): `tags` must be a
// YAML block list, not inline `[a, b]`. An empty `[]` is fine.
func checkTagsBlockForm(c *fileCtx) []string {
	if c.isReserved || !c.hasFM || frontmatter.FlowTags(c.fm) == nil {
		return nil
	}
	return []string{"tags field uses inline form — local convention requires YAML block-list"}
}

// checkCrosslinkFormat: cross-links must be catalogue-root-absolute (`/bundle/subdir/concept.md`,
// the leading `/` is the catalogue root, the Obsidian vault root). It flags relative links, which
// resolve inconsistently and orphan in Obsidian, and leading-`/` links that do not resolve to a
// real file from the catalogue root (legacy bundle-relative links and typos). Reserved files are a
// link source too; the managed index block is masked out first so its generated links never
// warn. A symlinked external bundle keeps the portable bundle-relative form and is audited in its
// own repository.
func checkCrosslinkFormat(c *fileCtx) []string {
	if info, err := os.Lstat(catalogue.Join(c.root, c.bundle)); err == nil && info.Mode()&os.ModeSymlink != 0 {
		return nil
	}
	scan, _ := MaskCodeSpans(catalogue.MaskManagedBlock(c.body))
	var relative, dangling []string
	for _, m := range catalogue.CrosslinkRE.FindAllStringSubmatch(scan, -1) {
		tgt, _, _ := strings.Cut(m[2], "#")
		tgt, _, _ = strings.Cut(tgt, "?")
		tgt = pytext.Strip(tgt)
		if !strings.HasSuffix(tgt, ".md") || strings.HasPrefix(tgt, "http://") ||
			strings.HasPrefix(tgt, "https://") || strings.HasPrefix(tgt, "mailto:") {
			continue
		}
		if !strings.HasPrefix(tgt, "/") {
			relative = append(relative, tgt)
		} else if !catalogue.RealFS.IsFile(catalogue.Join(c.root, strings.TrimLeft(tgt, "/"))) {
			dangling = append(dangling, tgt)
		}
	}
	var msgs []string
	if len(relative) > 0 {
		msgs = append(msgs, "non catalogue-absolute link(s) (use /bundle/…): "+strings.Join(relative, ", "))
	}
	if len(dangling) > 0 {
		msgs = append(msgs, "catalogue-absolute link(s) not resolving from root: "+strings.Join(dangling, ", "))
	}
	return msgs
}

// checkSupersededByResolves: `superseded_by` is a pointer, and a pointer to nothing is the same
// violation class as a dead crosslink: an error, part of the `0 violations` commit gate. The
// resolution is the catalogue-root-absolute one of the crosslink rule.
func checkSupersededByResolves(c *fileCtx) []string {
	if c.isReserved || !c.hasFM {
		return nil
	}
	sb := pytext.Strip(frontmatter.Text(c.fm, "superseded_by", ""))
	if sb == "" || catalogue.RealFS.IsFile(catalogue.Join(c.root, strings.TrimLeft(sb, "/"))) {
		return nil
	}
	return []string{"superseded_by target does not resolve: " + sb}
}

// checkSupersededByScope: `superseded_by` is defined only for `type: Decision` concepts. Another
// type carrying the field is a warning, not an error.
func checkSupersededByScope(c *fileCtx) []string {
	if c.isReserved || !c.hasFM {
		return nil
	}
	if pytext.Strip(frontmatter.Text(c.fm, "superseded_by", "")) == "" {
		return nil
	}
	t := typeOf(c)
	if t == "Decision" {
		return nil
	}
	if t == "" {
		t = "<empty>"
	}
	return []string{"superseded_by used on non-Decision concept (type=" + t + ")"}
}

func checkXMLLikeTags(c *fileCtx) []string {
	if c.isReserved {
		return nil
	}
	hits := FindXMLLikeTags(c.body)
	if len(hits) == 0 {
		return nil
	}
	uniq := slices.Clone(hits)
	sort.Strings(uniq)
	uniq = slices.Compact(uniq)
	return []string{"angle-bracket placeholder(s) not in code-fence: " + strings.Join(uniq, ", ")}
}

func checkWikilinkResolvableRule(c *fileCtx) ([]string, error) {
	return wikisync.CheckWikilinkResolvable(c.bundle, c.rel, c.text, c.run.wlChecked, c.run.wlIndex), nil
}

// syncRecord is a materialised block of a consumer body with its status against the canon index.
type syncRecord struct {
	block  wikisync.SyncBlock
	status string
}

// syncRecords classifies the sync blocks of one file, or returns none without paying for the canon
// index: the early exit is the performance contract of the two sync rules, a catalogue with no
// materialised block must not trigger the catalogue walk the index costs.
func syncRecords(c *fileCtx) ([]syncRecord, error) {
	if !strings.Contains(c.body, catalogue.SyncOpenLit) {
		return nil, nil
	}
	if !c.syncLoaded {
		idx, err := c.run.canonIndex()
		if err != nil {
			return nil, err
		}
		for _, b := range wikisync.ParseSyncBlocks(c.body) {
			c.sync = append(c.sync, syncRecord{b, wikisync.Classify(b, idx)})
		}
		c.syncLoaded = true
	}
	return c.sync, nil
}

// checkSyncIntegrity reports a materialised canon block whose markers are broken, whose owner is
// gone or whose payload was edited locally. `consumer-modified` is an error, not a warning: a
// consumer that holds an edited copy of foreign canon has silently become a second authority.
func checkSyncIntegrity(c *fileCtx) ([]string, error) {
	recs, err := syncRecords(c)
	var out []string
	for _, r := range recs {
		switch r.status {
		case "malformed", "source-missing", "consumer-modified", "both-changed":
			out = append(out, fmt.Sprintf("sync block `%s` from %s: %s", orQuestion(r.block.ID), orQuestion(r.block.Source), r.status))
		}
	}
	return out, err
}

// checkSyncStale warns when the owner's block moved on while the local copy is untouched:
// mechanically repairable, so it never blocks.
func checkSyncStale(c *fileCtx) ([]string, error) {
	recs, err := syncRecords(c)
	var out []string
	for _, r := range recs {
		if r.status == "source-changed" {
			out = append(out, fmt.Sprintf("sync block `%s` from %s is outdated — run sync-update", r.block.ID, r.block.Source))
		}
	}
	return out, err
}

func orQuestion(s string) string {
	if s == "" {
		return "?"
	}
	return s
}

// checkCanonBlocks is the owner-side integrity, free of the index: an unterminated `okf:canon`
// marker, or one id declared twice in the same concept, which would make `(source, id)`
// addressing ambiguous for every consumer of it.
func checkCanonBlocks(c *fileCtx) []string {
	var out []string
	seen := map[string]bool{}
	for _, blk := range wikisync.ParseCanonBlocks(c.body) {
		if !blk.Closed {
			out = append(out, fmt.Sprintf("canon block `%s` has no closing %s", blk.ID, catalogue.CanonEnd))
		}
		if seen[blk.ID] {
			out = append(out, fmt.Sprintf("canon block id `%s` declared twice", blk.ID))
		}
		seen[blk.ID] = true
	}
	return out
}

// ctxRule is one ctx sub-rule: the ctx findings of a file are read once, and this rule keeps the
// ones that carry its own ID.
func ctxRule(id, severity string) Rule {
	return fileRuleErr(id, severity, "", func(c *fileCtx) ([]string, error) {
		if c.bundle != catalogue.CtxDir || c.isReserved {
			return nil, nil
		}
		if !c.ctxLoaded {
			found, err := ctxfile.CtxFindings(c.root, c.ap, false)
			if err != nil {
				return nil, err
			}
			c.ctxFindings, c.ctxLoaded = found, true
		}
		var out []string
		for _, f := range c.ctxFindings {
			if f.Rule == id {
				out = append(out, f.Message)
			}
		}
		return out, nil
	})
}

// assetPlacement is Python check_asset_placement: the non-md, non-hidden files of a bundle outside
// its assets/ directory, relative to the bundle path.
func assetPlacement(bundlePath string) []string {
	var bad []string
	catalogue.SortedWalk(bundlePath, func(dirpath string, dirnames, filenames []string) []string {
		for _, fn := range filenames {
			if strings.HasSuffix(fn, ".md") || strings.HasPrefix(fn, ".") {
				continue
			}
			rel, err := filepath.Rel(bundlePath, catalogue.Join(dirpath, fn))
			if err != nil {
				rel = fn
			}
			bad = append(bad, filepath.ToSlash(rel))
		}
		descend := make([]string, 0, len(dirnames))
		for _, d := range dirnames {
			if !strings.HasPrefix(d, ".") && !strings.HasPrefix(d, "_") && d != "assets" {
				descend = append(descend, d)
			}
		}
		return descend
	})
	return bad
}

func checkAssetPlacementRule(b *bundleCtx) ([]pathMessage, error) {
	var out []pathMessage
	for _, rel := range assetPlacement(b.bp) {
		out = append(out, pathMessage{b.bundle + "/" + rel, "non-md file outside assets/"})
	}
	return out, nil
}

// entryFileDescription is Python check_entry_file_description: the entry file of a bundle
// (INDEX-MAP.md preferred, else index.md) must carry an H1 and a real intro paragraph, which
// `index --full` surfaces as the bundle's `description`. It returns 0 to 2 messages.
func entryFileDescription(bundlePath string) ([]string, error) {
	for _, fn := range []string{"INDEX-MAP.md", "index.md"} {
		fp := catalogue.Join(bundlePath, fn)
		if !catalogue.RealFS.IsFile(fp) {
			continue
		}
		h1, desc, err := catalogue.IndexH1AndDesc(fp, catalogue.RealFS)
		if err != nil {
			return nil, err
		}
		var msgs []string
		if h1 == "" {
			msgs = append(msgs, fn+" missing H1")
		}
		if pytext.Strip(desc) == "" {
			msgs = append(msgs, fn+" missing intro paragraph (used as bundle description)")
		}
		return msgs, nil
	}
	return []string{"no entry file (INDEX-MAP.md/index.md) found"}, nil
}

func checkEntryFileDescriptionRule(b *bundleCtx) ([]pathMessage, error) {
	msgs, err := entryFileDescription(b.bp)
	out := make([]pathMessage, len(msgs))
	for i, m := range msgs {
		out[i] = pathMessage{b.bundle, m}
	}
	return out, err
}
