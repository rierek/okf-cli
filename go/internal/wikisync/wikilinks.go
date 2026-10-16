package wikisync

import (
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"unicode/utf8"

	"golang.org/x/text/unicode/norm"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/envelope"
	"nas/volume1/data/git/okf-tools/go/internal/linkscan"
	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

// Obsidian's native link form. The markdown-link scanners anchor on "](", so none of them sees a
// [[…]]: a rename that rewrote only the markdown links would orphan every inbound wikilink. This
// file is the wikilink counterpart for reading: parse, resolve, report.

// wikilinkRE matches `[[inner]]` with an optional embed `!`; group 2 is the inner text.
var wikilinkRE = regexp.MustCompile(`(!?)\[\[([^\[\]\n]+)\]\]`)

// Wikilink is one `[[…]]` occurrence of a file plus, after ResolveAll, how it resolves.
type Wikilink struct {
	// Source is the catalogue-relative path of the file; Region is `frontmatter` or `body`.
	Source, Region string
	// Raw is `[[inner]]` without the embed `!`: text[Start:End] == Raw.
	Raw string
	// Page is the target page part (path allowed, no `.md`); Alias and Suffix are nil when absent.
	Page          string
	Alias, Suffix *string
	Embed         bool
	// Start and End are byte offsets of Raw in the original text; SpanStart and SpanEnd are the
	// same offsets in Unicode code points (the `span` of the report).
	Start, End         int
	SpanStart, SpanEnd int
	// Status is resolved, ambiguous or unresolved; Candidates are the paths it resolved to.
	Status     string
	Candidates []string
}

// SplitWikilinkInner is the (page, alias, suffix) of the text between `[[` and `]]`. The grammar is
// `[[page#suffix|alias]]`: the `#` binds to the page part only. An alias may contain one
// (`[[dotnet|C#]]`), so the alias is never re-split. A trailing `.md` of the page is dropped
// case-insensitively. alias and suffix are nil when absent; an empty suffix reads as absent.
func SplitWikilinkInner(inner string) (page string, alias, suffix *string) {
	pagePart, rest, hasAlias := strings.Cut(inner, "|")
	page, sfx, hasSuffix := strings.Cut(pagePart, "#")
	page = pytext.Strip(page)
	if strings.HasSuffix(pytext.Lower(page), ".md") {
		page = page[:len(page)-3]
	}
	if hasAlias {
		a := pytext.Strip(rest)
		alias = &a
	}
	if hasSuffix {
		if s := pytext.Strip(sfx); s != "" {
			suffix = &s
		}
	}
	return page, alias, suffix
}

// ParseWikilinks is every `[[…]]` occurrence of one file's text, minus the status and candidates
// the resolver fills in; in-file anchors (`[[#heading]]`) are skipped. Matches are found on the
// masked scan copy of linkscan and cut from the original, so Raw never carries mask bytes and
// text[Start:End] == Raw.
func ParseWikilinks(text, source string) []Wikilink {
	fmEnd := linkscan.WikilinkRegions(text)[0].End
	var out []Wikilink
	pos, cp := 0, 0 // running byte offset and code-point offset
	for _, m := range wikilinkRE.FindAllStringSubmatchIndex(linkscan.WikilinkScanTextAt(text, fmEnd), -1) {
		inner := text[m[4]:m[5]]
		page, alias, suffix := SplitWikilinkInner(inner)
		if page == "" {
			continue
		}
		w := Wikilink{
			Source: source, Region: "body", Raw: "[[" + inner + "]]", Page: page,
			Alias: alias, Suffix: suffix, Embed: m[3] > m[2], Start: m[4] - 2, End: m[5] + 2,
		}
		if m[0] < fmEnd {
			w.Region = "frontmatter"
		}
		cp += utf8.RuneCountInString(text[pos:w.Start])
		w.SpanStart = cp
		cp += utf8.RuneCountInString(text[w.Start:w.End])
		w.SpanEnd = cp
		pos = w.End
		out = append(out, w)
	}
	return out
}

// ApplyArchivePrecedence is the precedence rule over one basename's possibly mixed candidate list:
// active candidates win outright whenever one exists; archived candidates (`/_archive/...`) are the
// fallback only when none does. The result is sorted. BuildBasenameIndex and rename's move
// simulation share it, so a change to the rule cannot land in only one of them.
func ApplyArchivePrecedence(cands []string) []string {
	var active []string
	for _, c := range cands {
		if !strings.HasPrefix(pytext.Lower(c), "/_archive/") {
			active = append(active, c)
		}
	}
	if active == nil {
		active = append([]string(nil), cands...)
	}
	sort.Strings(active)
	return active
}

// NormalizeKey is a basename key for case- and NFC-insensitive matching: NFC first, then
// lower-casing. It matches Obsidian's toLowerCase(), not case folding: `[[STRASSE]]` does not
// resolve to `Straße.md`. NFC makes a key from an NFD file name (APFS) equal one typed in NFC.
func NormalizeKey(s string) string { return pytext.Lower(norm.NFC.String(s)) }

// BasenameIndex maps a normalised basename (no `.md`) to the sorted catalogue-root-absolute
// paths (`/bundle/…/x.md`) of every non-reserved concept of that name. A wikilink carries no path,
// so the basename is its address.
type BasenameIndex map[string][]string

// BuildBasenameIndex indexes every non-reserved concept of the bundles, then folds `_archive/<bundle>/**`
// in as a second tier: an archived concept still resolves an inbound `[[x]]`, but a basename with
// at least one active candidate drops its archived candidates entirely.
//
// It walks with the staging-pruning walk, so the set of link targets is the set of files the
// reporting and check surfaces scan as sources; it walks per bundle because the walk does not
// descend into symlinked directories and bundles may be symlinks.
func BuildBasenameIndex(root string) (BasenameIndex, error) {
	idx := BasenameIndex{}
	add := func(dir string, names []string) {
		for _, b := range names {
			for ap := range catalogue.IterAllMd(catalogue.Join(dir, b), true) {
				fn := filepath.Base(ap)
				if catalogue.IsReserved(fn) {
					continue
				}
				key := NormalizeKey(fn[:len(fn)-3])
				idx[key] = append(idx[key], "/"+relSlash(root, ap))
			}
		}
	}
	names, err := catalogue.ListBundles(root)
	if err != nil {
		return nil, err
	}
	add(root, names)
	archiveRoot := catalogue.Join(root, "_archive")
	if catalogue.RealFS.IsDir(archiveRoot) {
		archived, err := catalogue.ListBundles(archiveRoot)
		if err != nil {
			return nil, err
		}
		add(archiveRoot, archived)
	}
	for k, v := range idx {
		idx[k] = ApplyArchivePrecedence(v)
	}
	return idx, nil
}

// Resolve is the (status, candidates) of one page part seen in the file sourceRel. The order,
// matching how Obsidian narrows a target:
//  1. every concept whose basename equals the last segment of the page part;
//  2. if the page part carries a path (`[[dir/name]]`), only the candidates whose path ends in
//     it. A path matching nothing is unresolved, not a fallback to the bare basename;
//  3. on a remaining collision, the linking file's own bundle wins when exactly one candidate
//     lives there.
func Resolve(idx BasenameIndex, sourceRel, page string) (status string, candidates []string) {
	last := page[strings.LastIndex(page, "/")+1:]
	cands := idx[NormalizeKey(last)]
	if len(cands) == 0 {
		return "unresolved", nil
	}
	if strings.Contains(page, "/") {
		tail := NormalizeKey("/" + strings.Trim(page, "/") + ".md")
		var kept []string
		for _, c := range cands {
			if strings.HasSuffix(NormalizeKey(c), tail) {
				kept = append(kept, c)
			}
		}
		if cands = kept; len(cands) == 0 {
			return "unresolved", nil
		}
	}
	if len(cands) == 1 {
		return "resolved", append([]string(nil), cands...)
	}
	own := pytext.Lower(strings.SplitN(sourceRel, "/", 2)[0])
	var same []string
	for _, c := range cands {
		if pytext.Lower(strings.SplitN(strings.TrimLeft(c, "/"), "/", 2)[0]) == own {
			same = append(same, c)
		}
	}
	if len(same) == 1 {
		return "resolved", same
	}
	return "ambiguous", append([]string(nil), cands...)
}

// ResolveAll fills Status and Candidates of every link in place.
func ResolveAll(idx BasenameIndex, links []Wikilink) {
	for i := range links {
		links[i].Status, links[i].Candidates = Resolve(idx, links[i].Source, links[i].Page)
	}
}

// ScanWikilinks is every resolved wikilink under target (a bundle or `bundle/subdir`, the whole
// catalogue when empty) over the reporting walk: staging directories and `assets/` are excluded,
// reserved files are included. A nil idx is built from root.
func ScanWikilinks(root, target string, idx BasenameIndex) ([]Wikilink, error) {
	if idx == nil {
		var err error
		if idx, err = BuildBasenameIndex(root); err != nil {
			return nil, err
		}
	}
	scopes, err := catalogue.ResolveScopes(root, target, false, false)
	if err != nil {
		return nil, err
	}
	var out []Wikilink
	for _, sc := range scopes {
		for ap := range catalogue.IterAllMd(sc.Path, true) {
			text, err := catalogue.ReadFile(ap)
			if err != nil {
				return nil, err
			}
			links := ParseWikilinks(text, relSlash(root, ap))
			ResolveAll(idx, links)
			out = append(out, links...)
		}
	}
	return out, nil
}

// CheckedBundles is the opt-in set of the wikilink check, from the `wikilink_checked_bundles` key
// of the config: lowercased bundle names. An absent key means the empty set, so the rule ships
// silent and is switched on per bundle. A value the gate cannot honour is announced as a call note
// instead of switching the rule off silently:
//   - not an array of strings: the set stays empty;
//   - a name that is no bundle of root: noted, the name stays in the set. root == "" skips this note.
func CheckedBundles(cfg map[string]any, root string) map[string]bool {
	v, ok := cfg["wikilink_checked_bundles"]
	if !ok {
		return map[string]bool{}
	}
	list, isList := v.([]any)
	var names []string
	for _, x := range list {
		s, isStr := x.(string)
		if !isStr {
			isList = false
			break
		}
		names = append(names, s)
	}
	if !isList {
		envelope.Note("wikilink_checked_bundles must be an array of bundle names; got " +
			pytext.Repr(v) + " — wikilink check stays off")
		return map[string]bool{}
	}
	// Lowercased: the store's filesystem is case-insensitive, so `check A` reaches bundle `a`.
	out := make(map[string]bool, len(names))
	for _, n := range names {
		out[pytext.Lower(n)] = true
	}
	if root == "" {
		return out
	}
	bundles, err := catalogue.ListBundles(root)
	if err != nil {
		return out
	}
	known := make(map[string]bool, len(bundles))
	for _, b := range bundles {
		known[pytext.Lower(b)] = true
	}
	var unknown []string
	for _, n := range names {
		if !known[pytext.Lower(n)] {
			unknown = append(unknown, n)
		}
	}
	sort.Strings(unknown)
	if len(unknown) > 0 {
		envelope.Note("wikilink_checked_bundles names non-bundle(s): " + strings.Join(unknown, ", ") +
			" — no file will be checked for them")
	}
	return out
}

// CheckWikilinkResolvable is the check behind rule kc/link/wikilink-resolvable: zero or one message
// `unresolved wikilink target(s): <raw>, <raw>…` naming every unresolved or ambiguous link of the
// file. bundle is compared lowercased; the result is empty when the bundle is not in the checked
// set or a middle path segment of rel starts with `.` or `_` or equals `assets`.
func CheckWikilinkResolvable(bundle, rel, text string, checked map[string]bool, idx BasenameIndex) []string {
	if len(checked) == 0 || !checked[pytext.Lower(bundle)] {
		return nil
	}
	segs := strings.Split(rel, "/")
	if len(segs) > 2 {
		for _, s := range segs[1 : len(segs)-1] {
			if strings.HasPrefix(s, ".") || strings.HasPrefix(s, "_") || s == "assets" {
				return nil
			}
		}
	}
	links := ParseWikilinks(text, rel)
	ResolveAll(idx, links)
	var bad []string
	for _, l := range links {
		if l.Status != "resolved" {
			bad = append(bad, l.Raw)
		}
	}
	if len(bad) == 0 {
		return nil
	}
	return []string{"unresolved wikilink target(s): " + strings.Join(bad, ", ")}
}
