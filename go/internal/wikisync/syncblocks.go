// Package wikisync is the wikilink resolver and the canon/sync-block model, and the commands
// `wikilinks`, `sync-export` and `sync-status` that read them (Python okf.wikilinks and the read
// half of okf.sync).
//
// It is the one place that parses canon and sync blocks, hashes a payload, indexes the canon
// blocks of a catalogue, classifies a sync block and resolves a wikilink; the check, rename and
// sync write verbs import it and never re-parse. The marker literals and patterns belong to
// catalogue (CanonEnd, SyncBody, SyncEnd, SyncOpenLit, SyncSpanRE, CanonOpenRE, SyncOpenRE) and
// are used from there.
//
// Offsets (Start, End) are byte offsets into the string the caller passed in, so a caller splices
// with them directly. Only Wikilink.SpanStart and SpanEnd are Unicode code-point offsets: they are
// the `span` the `wikilinks --json` report shows.
package wikisync

import (
	"crypto/sha1"
	"encoding/hex"
	"path/filepath"
	"regexp"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/frontmatter"
	"nas/volume1/data/git/okf-tools/go/internal/okferr"
	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

// Statuses are the six sync statuses in their fixed report order.
var Statuses = []string{"synced", "source-changed", "consumer-modified", "both-changed", "source-missing", "malformed"}

// syncOpenAnchored is catalogue.SyncOpenRE anchored at the start of its input (Python
// SYNC_OPEN_RE.match(body, start)), derived from it so the grammar stays in one place.
var syncOpenAnchored = regexp.MustCompile(`\A(?:` + catalogue.SyncOpenRE.String() + `)`)

// SyncHash is the fingerprint of a canon block payload: CRLF folded to LF, outer whitespace
// stripped, sha1, the first 12 hex characters. A line-ending translation or a trailing newline
// gained in transit does not read as a content change.
func SyncHash(payload string) string {
	sum := sha1.Sum([]byte(pytext.Strip(strings.ReplaceAll(payload, "\r\n", "\n"))))
	return hex.EncodeToString(sum[:])[:12]
}

// CanonBlock is one `okf:canon` block declared in a concept body.
type CanonBlock struct {
	ID, Payload string
	// Closed is false when the opening marker has no canon end marker: an unterminated marker is
	// reported, never guessed at. Payload is then empty and End is the end of the body.
	Closed     bool
	Start, End int
}

// ParseCanonBlocks is every canon block of one concept body in document order. body[Start:End]
// is the block from its opening marker through the end marker.
func ParseCanonBlocks(body string) []CanonBlock {
	var out []CanonBlock
	for _, m := range catalogue.CanonOpenRE.FindAllStringSubmatchIndex(body, -1) {
		blk := CanonBlock{ID: body[m[2]:m[3]], Start: m[0], End: len(body)}
		if i := strings.Index(body[m[1]:], catalogue.CanonEnd); i >= 0 {
			ei := m[1] + i
			blk.Payload, blk.Closed, blk.End = body[m[1]:ei], true, ei+len(catalogue.CanonEnd)
		}
		out = append(out, blk)
	}
	return out
}

// SyncBlock is one materialised canon block in a consumer body.
type SyncBlock struct {
	ID, Source, Hash, Payload string
	// MarkerParsed is false when the opening marker did not match the generated form; ID, Source
	// and Hash are then empty (null in JSON, `?` in text).
	MarkerParsed bool
	// Malformed is set for a block whose marker did not parse or whose body or end marker is
	// missing. A block that is not malformed spans body[Start:End] verbatim.
	Malformed  bool
	Start, End int
}

// ParseSyncBlocks is every materialised canon block of one consumer body in document order.
//
// The scan starts from each literal catalogue.SyncOpenLit rather than from the full-form pattern,
// so a hand-edited marker still produces a record (Malformed) instead of vanishing from every
// report: a block nobody can see is the one that silently turns a consumer authoritative. Every
// structural search is bounded by the next opening marker, so a malformed block never swallows
// the next one; a malformed block spans up to that bound.
func ParseSyncBlocks(body string) []SyncBlock {
	var starts []int
	for i := strings.Index(body, catalogue.SyncOpenLit); i >= 0; {
		starts = append(starts, i)
		next := strings.Index(body[i+1:], catalogue.SyncOpenLit)
		if next < 0 {
			break
		}
		i += 1 + next
	}
	idID := catalogue.SyncOpenRE.SubexpIndex("id")
	idSource := catalogue.SyncOpenRE.SubexpIndex("source")
	idHash := catalogue.SyncOpenRE.SubexpIndex("hash")
	out := make([]SyncBlock, 0, len(starts))
	for n, start := range starts {
		limit := len(body)
		if n+1 < len(starts) {
			limit = starts[n+1]
		}
		rec := SyncBlock{Start: start, End: limit, Malformed: true}
		m := syncOpenAnchored.FindStringSubmatchIndex(body[start:])
		if m == nil || start+m[1] > limit {
			out = append(out, rec)
			continue
		}
		openEnd := start + m[1]
		rec.MarkerParsed = true
		rec.ID = body[start+m[2*idID] : start+m[2*idID+1]]
		rec.Source = body[start+m[2*idSource] : start+m[2*idSource+1]]
		rec.Hash = body[start+m[2*idHash] : start+m[2*idHash+1]]
		bi := strings.Index(body[openEnd:limit], catalogue.SyncBody)
		if bi < 0 {
			out = append(out, rec)
			continue
		}
		bodyStart := openEnd + bi + len(catalogue.SyncBody)
		ei := strings.Index(body[bodyStart:limit], catalogue.SyncEnd)
		if ei < 0 {
			out = append(out, rec)
			continue
		}
		rec.Payload = body[bodyStart : bodyStart+ei]
		rec.End = bodyStart + ei + len(catalogue.SyncEnd)
		rec.Malformed = false
		out = append(out, rec)
	}
	return out
}

// CanonKey addresses one canon block: the owner concept spelled `bundle/concept.md` (no leading
// slash, an archived owner `_archive/bundle/concept.md`) and the block id.
type CanonKey struct{ Rel, ID string }

// CanonIndex maps every terminated canon block of a catalogue to its payload.
type CanonIndex map[CanonKey]string

// BuildCanonIndex walks the whole catalogue, the archive included and staging directories not
// pruned, and indexes every terminated canon block; the first declaration of a key wins. It costs
// one catalogue walk, so callers build it lazily and at most once per run.
//
// The archive is included because archiving an owner rewrites every consumer's `source=` to the
// `/_archive/...` path; the archived concept must stay a resolvable owner. Staging directories
// are not pruned because an owner living in one is a real file that consumers point at.
func BuildCanonIndex(root string) (CanonIndex, error) {
	idx := CanonIndex{}
	scopes, err := catalogue.ResolveScopes(root, "", true, false)
	if err != nil {
		return nil, err
	}
	for _, sc := range scopes {
		for ap := range catalogue.IterAllMd(sc.Path, false) {
			text, err := catalogue.ReadFile(ap)
			if err != nil {
				return nil, err
			}
			body := frontmatter.Read(text).Body
			if !strings.Contains(body, "okf:canon") {
				continue
			}
			rel := relSlash(root, ap)
			for _, blk := range ParseCanonBlocks(body) {
				if !blk.Closed {
					continue // unterminated: the canon-block check reports it
				}
				key := CanonKey{rel, blk.ID}
				if _, seen := idx[key]; !seen {
					idx[key] = blk.Payload
				}
			}
		}
	}
	return idx, nil
}

// Classify is one of the six Statuses of a parsed sync block against the canon index.
//
// consumer-modified and both-changed outrank source-changed: a local edit to a materialised copy
// is the failure this whole mechanism exists to catch, and re-materialising over it would destroy
// the only copy of that edit.
func Classify(b SyncBlock, idx CanonIndex) string {
	if b.Malformed || !strings.HasPrefix(b.Source, "/") {
		return "malformed"
	}
	payload, ok := idx[CanonKey{strings.TrimLeft(b.Source, "/"), b.ID}]
	if !ok {
		return "source-missing"
	}
	srcMatches := SyncHash(payload) == b.Hash
	localMatches := SyncHash(b.Payload) == b.Hash
	switch {
	case srcMatches && localMatches:
		return "synced"
	case localMatches:
		return "source-changed"
	case srcMatches:
		return "consumer-modified"
	}
	return "both-changed"
}

// SyncHit is one materialised block found by ScanSyncBlocks: the consumer's catalogue-relative
// path, its absolute path, the block and its status.
type SyncHit struct {
	Rel, Path string
	Block     SyncBlock
	Status    string
}

// ScanSyncBlocks is every materialised canon block under target (a bundle or `bundle/subdir`,
// the whole catalogue when empty), classified against the canon index it also returns. A non-nil
// source or blockID keeps only blocks whose source or id equals it exactly; a block whose marker
// did not parse has neither.
//
// The scope is the one `check` scans, deliberately: the two surfaces must agree on which files
// carry a sync block, or a block `check` errors on is one `sync-update` cannot reach.
func ScanSyncBlocks(root, target string, source, blockID *string) (CanonIndex, []SyncHit, error) {
	canon, err := BuildCanonIndex(root)
	if err != nil {
		return nil, nil, err
	}
	scopes, err := catalogue.ResolveScopes(root, target, false, false)
	if err != nil {
		return nil, nil, err
	}
	var out []SyncHit
	for _, sc := range scopes {
		for ap := range catalogue.IterAllMd(sc.Path, true) {
			text, err := catalogue.ReadFile(ap)
			if err != nil {
				return nil, nil, err
			}
			body := frontmatter.Read(text).Body
			if !strings.Contains(body, catalogue.SyncOpenLit) {
				continue
			}
			rel := relSlash(root, ap)
			for _, b := range ParseSyncBlocks(body) {
				if source != nil && (!b.MarkerParsed || b.Source != *source) {
					continue
				}
				if blockID != nil && (!b.MarkerParsed || b.ID != *blockID) {
					continue
				}
				out = append(out, SyncHit{Rel: rel, Path: ap, Block: b, Status: Classify(b, canon)})
			}
		}
	}
	return canon, out, nil
}

// CanonPayload is the payload of one canon block of a concept: its absolute path, its
// catalogue-relative path and the payload. A concept that does not resolve, a block the concept
// does not declare and a block without its end marker are all not_found. sync-export and
// sync-insert share it so both refuse identically.
func CanonPayload(root, concept, blockID string) (path, rel, payload string, err error) {
	path, err = catalogue.ResolveConcept(root, concept)
	if err != nil {
		return "", "", "", err
	}
	rel = relSlash(root, path)
	text, err := catalogue.ReadFile(path)
	if err != nil {
		return "", "", "", err
	}
	for _, blk := range ParseCanonBlocks(frontmatter.Read(text).Body) {
		if blk.ID != blockID {
			continue
		}
		if !blk.Closed {
			return "", "", "", okferr.Newf(okferr.NotFound, "canon block `%s` in %s has no closing %s",
				blockID, rel, catalogue.CanonEnd)
		}
		return path, rel, blk.Payload, nil
	}
	return "", "", "", okferr.Newf(okferr.NotFound, "no canon block `%s` in %s", blockID, rel)
}

// relSlash is the catalogue-relative path of ap, slash-separated (Python relpath + replace).
func relSlash(root, ap string) string {
	rel, err := filepath.Rel(root, ap)
	if err != nil {
		return filepath.ToSlash(ap)
	}
	return filepath.ToSlash(rel)
}
