package ctxfile

import (
	"os"
	"slices"
	"strconv"
	"strings"
	"unicode/utf8"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/frontmatter"
	"nas/volume1/data/git/okf-tools/go/internal/okferr"
	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

// ctxFile is Python ctx_file: <root>/_ctx/<slug>.md.
func ctxFile(root, slug string) string {
	return catalogue.Join(catalogue.Join(root, catalogue.CtxDir), slug+".md")
}

// LoadCtx is Python load_ctx: the ctx file of a slug, parsed. A slug without a ctx file is a
// not_found error `ctx: unknown slug: <slug>`.
func LoadCtx(root, slug string) (LoadedCtx, error) {
	f := ctxFile(root, slug)
	if !catalogue.RealFS.IsFile(f) {
		return LoadedCtx{}, okferr.New(okferr.NotFound, "ctx: unknown slug: "+slug)
	}
	text, err := catalogue.ReadFile(f)
	if err != nil {
		return LoadedCtx{}, err
	}
	desc, entries, problems := ParseCtx(text)
	return LoadedCtx{Slug: slug, Description: desc, Entries: entries, Problems: problems}, nil
}

// CtxMemberships is Python ctx_memberships: every entry, with the slug of its ctx, that names the
// file path stands for (the path normalised as CtxNormalizePath does without the existence check),
// in slug order.
func CtxMemberships(root, path string) ([]CtxMembership, error) {
	norm, _, err := normalizePath(root, path, false)
	if err != nil {
		return nil, err
	}
	slugs, err := catalogue.CtxSlugs(root)
	if err != nil {
		return nil, err
	}
	out := []CtxMembership{}
	for _, slug := range slugs {
		c, err := LoadCtx(root, slug)
		if err != nil {
			return nil, err
		}
		for _, e := range c.Entries {
			if e.Path == norm {
				out = append(out, CtxMembership{Slug: slug, Entry: e})
			}
		}
	}
	return out, nil
}

// posText is Python pos_s: the position of an entry as the table writes it.
func posText(e CtxEntry) string {
	if e.Pos == nil {
		return "-"
	}
	return strconv.Itoa(*e.Pos)
}

// dropLastRunes is s[:-n] for a str: s without its last n characters, "" when it has fewer.
func dropLastRunes(s string, n int) string {
	for ; n > 0 && s != ""; n-- {
		_, size := utf8.DecodeLastRuneInString(s)
		s = s[:len(s)-size]
	}
	return s
}

// pyMtime is os.path.getmtime: the modification time as Python's float, seconds plus nanoseconds
// times 1e-9 (the conversion keeps the product rounded, as the C expression does).
func pyMtime(path string) (float64, error) {
	info, err := os.Stat(path)
	if err != nil {
		return 0, err
	}
	t := info.ModTime()
	return float64(t.Unix()) + float64(1e-9*float64(t.Nanosecond())), nil
}

// CtxFindings is Python ctx_findings: the problems of the ctx file at path (absolute, the
// _ctx/<slug>.md of root), one `kc/ctx/*` sub-rule per kind, in the order the rules check them:
// type, slug, rows that cannot be read, modes, required positions, reference positions, then per
// entry duplicate and dead, then empty description and archived entries, and last (stale set)
// entries changed after the ctx file. The stale check compares modification times.
func CtxFindings(root, path string, stale bool) ([]CtxFinding, error) {
	text, err := catalogue.ReadFile(path)
	if err != nil {
		return nil, err
	}
	doc := frontmatter.Read(text)
	desc, entries, problems := parseCtx(doc)
	out := []CtxFinding{}
	if typ := pytext.Strip(frontmatter.Text(doc.Data(), "type", "")); typ != CtxType {
		out = append(out, CtxFinding{"kc/ctx/type", `type is "` + typ + `", expected "` + CtxType + `"`})
	}
	stem := dropLastRunes(pyBasename(path), 3)
	if bad := CtxSlugProblem(stem); bad != "" {
		out = append(out, CtxFinding{"kc/ctx/slug", `slug "` + stem + `" invalid: ` + bad})
	}
	for _, p := range problems {
		out = append(out, CtxFinding{"kc/ctx/row-format", p})
	}
	for _, e := range entries {
		if !slices.Contains(CtxModes, e.Mode) {
			out = append(out, CtxFinding{"kc/ctx/mode",
				"pos " + posText(e) + `: mode "` + e.Mode + `" is not pflicht or nachschlag`})
		}
	}
	var required []CtxEntry
	for _, e := range entries {
		if e.Mode == "pflicht" {
			required = append(required, e)
		}
	}
	inOrder := true
	positions := make([]string, len(required))
	for i, e := range required {
		inOrder = inOrder && e.Pos != nil && *e.Pos == i+1
		positions[i] = posText(e)
	}
	if !inOrder {
		out = append(out, CtxFinding{"kc/ctx/required-positions",
			"required positions are not 1.." + strconv.Itoa(len(required)) + " in table order: " +
				strings.Join(positions, ", ")})
	}
	for _, e := range entries {
		if e.Mode == "nachschlag" && e.Pos != nil {
			out = append(out, CtxFinding{"kc/ctx/reference-position",
				"reference entry carries pos " + strconv.Itoa(*e.Pos) + " (use -)"})
		}
	}
	seen := map[string]bool{}
	late := []CtxFinding{}
	for _, e := range entries {
		p := e.Path
		if seen[p] {
			out = append(out, CtxFinding{"kc/ctx/duplicate-entry", "duplicate entry: " + p})
		}
		seen[p] = true
		mp := CtxEntryAbspath(root, p)
		if !catalogue.RealFS.IsFile(mp) {
			out = append(out, CtxFinding{"kc/ctx/dead-entry", "dead entry: " + p})
		} else if stale {
			entryTime, err := pyMtime(mp)
			if err != nil {
				return nil, err
			}
			ctxTime, err := pyMtime(path)
			if err != nil {
				return nil, err
			}
			// ponytail: mtime comparison; switch to git dates if checkouts reset mtimes
			if entryTime > ctxTime {
				late = append(late, CtxFinding{"kc/ctx/stale-entry", "stale: " + p + " changed after this ctx file"})
			}
		}
	}
	if pytext.Strip(desc) == "" {
		out = append(out, CtxFinding{"kc/ctx/empty-description", "empty description"})
	}
	for _, e := range entries {
		if strings.HasPrefix(e.Path, "_archive/") {
			out = append(out, CtxFinding{"kc/ctx/archived-entry", "entry under _archive/: " + e.Path})
		}
	}
	return append(out, late...), nil
}
