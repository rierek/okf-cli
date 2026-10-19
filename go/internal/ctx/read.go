package ctx

import (
	"cmp"
	"fmt"
	"slices"
	"strconv"
	"strings"
	"unicode/utf8"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/cli"
	"nas/volume1/data/git/okf-tools/go/internal/ctxfile"
	"nas/volume1/data/git/okf-tools/go/internal/envelope"
	"nas/volume1/data/git/okf-tools/go/internal/frontmatter"
	"nas/volume1/data/git/okf-tools/go/internal/okferr"
	"nas/volume1/data/git/okf-tools/go/internal/stdio"
)

// member is one entry of a ctx with the live metadata of its file (Python _ctx_members row).
type member struct {
	pos                     *int
	mode, path, abspath     string
	title, typ, description string
	comment                 string
	alive                   bool
	chars, tokens           int
}

func (m member) required() bool { return m.mode == "pflicht" }

// row is the JSON object of a member, in Python's key order.
func (m member) row() envelope.Obj {
	return envelope.O("pos", m.pos, "mode", m.mode, "path", m.path, "abspath", m.abspath,
		"title", m.title, "type", m.typ, "description", m.description, "comment", m.comment,
		"alive", m.alive, "chars", m.chars, "tokens", m.tokens)
}

// byPos sorts items by position, stable (Python sorted(..., key=pos)). Python cannot compare a
// missing position (`-`) with a number, so it fails for two or more items when one has none; so
// does this, as an internal error instead of a traceback.
func byPos[T any](slug string, items []T, pos func(T) *int) ([]T, error) {
	out := slices.Clone(items)
	if len(out) >= 2 {
		for _, it := range out {
			if pos(it) == nil {
				return nil, okferr.Newf(okferr.Internal,
					"ctx: %s has a required entry without a position; fix with okf ctx edit, see okf ctx check", slug)
			}
		}
	}
	slices.SortStableFunc(out, func(a, b T) int {
		var pa, pb int
		if p := pos(a); p != nil {
			pa = *p
		}
		if p := pos(b); p != nil {
			pb = *p
		}
		return cmp.Compare(pa, pb)
	})
	return out, nil
}

// members is Python _ctx_members: the ctx with its entries and their live metadata, the required
// entries first in position order, then the others in file order.
func members(root, slug string) (ctxfile.LoadedCtx, []member, error) {
	c, err := ctxfile.LoadCtx(root, slug)
	if err != nil {
		return c, nil, err
	}
	var required, rest []member
	for _, e := range c.Entries {
		ap := ctxfile.CtxEntryAbspath(root, e.Path)
		m := member{pos: e.Pos, mode: e.Mode, path: e.Path, abspath: ap, comment: e.Comment,
			title: ap[strings.LastIndexByte(ap, '/')+1:], alive: catalogue.RealFS.IsFile(ap)}
		if m.alive {
			if strings.HasSuffix(ap, ".md") {
				meta, err := catalogue.MetaOf(ap, catalogue.RealFS)
				if err != nil {
					return c, nil, err
				}
				m.typ, m.title, m.description = meta.Type, meta.Title, meta.Description
			}
			text, err := catalogue.ReadFile(ap)
			if err != nil {
				return c, nil, err
			}
			m.chars = utf8.RuneCountInString(text) // characters of the decoded text, not bytes
		}
		m.tokens = catalogue.Tokens(m.chars)
		if m.required() {
			required = append(required, m)
		} else {
			rest = append(rest, m)
		}
	}
	if required, err = byPos(slug, required, func(m member) *int { return m.pos }); err != nil {
		return c, nil, err
	}
	return c, append(required, rest...), nil
}

// split is the required and the reference members of ms, each in the order of ms.
func split(ms []member) (required, reference []member) {
	for _, m := range ms {
		if m.required() {
			required = append(required, m)
		} else {
			reference = append(reference, m)
		}
	}
	return required, reference
}

// listRow is one ctx of `ctx list`.
type listRow struct {
	slug, description string
	entries, required int
}

func (r listRow) obj() envelope.Obj {
	return envelope.O("slug", r.slug, "description", r.description, "entries", r.entries,
		"required", r.required, "path", ctxRel(r.slug))
}

// listRows is Python _ctx_list_rows: one row per ctx, only those holding forPath when it is set.
func listRows(root string, forPath *string) ([]listRow, error) {
	var keep map[string]bool
	if forPath != nil {
		hits, err := ctxfile.CtxMemberships(root, *forPath)
		if err != nil {
			return nil, err
		}
		keep = map[string]bool{}
		for _, h := range hits {
			keep[h.Slug] = true
		}
	}
	slugs, err := catalogue.CtxSlugs(root)
	if err != nil {
		return nil, err
	}
	var rows []listRow
	for _, slug := range slugs {
		if keep != nil && !keep[slug] {
			continue
		}
		c, err := ctxfile.LoadCtx(root, slug)
		if err != nil {
			return nil, err
		}
		row := listRow{slug: slug, description: c.Description, entries: len(c.Entries)}
		for _, e := range c.Entries {
			if e.Mode == "pflicht" {
				row.required++
			}
		}
		rows = append(rows, row)
	}
	return rows, nil
}

// runList is Python cmd_ctx_list.
func runList(root string, a *cli.Args) (any, error) {
	var forPath *string
	if a.Has("for_path") {
		v := a.String("for_path")
		forPath = &v
	}
	rows, err := listRows(root, forPath)
	if err != nil {
		return nil, err
	}
	if a.JSON {
		objs := make([]envelope.Obj, len(rows))
		for i, r := range rows {
			objs[i] = r.obj()
		}
		return objs, nil
	}
	if len(rows) == 0 {
		if forPath == nil {
			stdio.Printf("no ctx bundles under %s\n", catalogue.Join(root, catalogue.CtxDir))
		}
		return nil, nil
	}
	width := 0
	for _, r := range rows {
		width = max(width, utf8.RuneCountInString(r.slug))
	}
	var sb strings.Builder
	for _, r := range rows {
		fmt.Fprintf(&sb, "  %-*s  %s  (%d entries, %d required)\n", width, r.slug, r.description, r.entries, r.required)
	}
	stdio.Print(sb.String())
	return nil, nil
}

// deadWarning is Python _ctx_dead_warning.
func deadWarning(slug string, k int) string {
	plural := "ies"
	if k == 1 {
		plural = "y"
	}
	return fmt.Sprintf("WARNING: %d dead entr%s — this list is incomplete; fix with `ctx edit %s`", k, plural, slug)
}

// posText is the position of a member as Python's str.format prints it: the number, or None.
func posText(p *int) string {
	if p == nil {
		return "None"
	}
	return strconv.Itoa(*p)
}

// runShow is Python cmd_ctx_show: the entries in reading order with live metadata.
func runShow(root string, a *cli.Args) (any, error) {
	slug := a.String("slug")
	c, ms, err := members(root, slug)
	if err != nil {
		return nil, err
	}
	required, reference := split(ms)
	dead, tokensRequired := 0, 0
	for _, m := range ms {
		if !m.alive {
			dead++
		}
	}
	for _, m := range required {
		tokensRequired += m.tokens
	}
	if a.JSON {
		rows := make([]envelope.Obj, len(ms))
		for i, m := range ms {
			rows[i] = m.row()
		}
		result := envelope.O("slug", slug, "description", c.Description, "path", ctxRel(slug),
			"entries", rows, "dead", dead, "tokens_required", tokensRequired)
		if dead > 0 {
			return nil, okferr.WithResult(okferr.NonConformant, deadWarning(slug, dead), result)
		}
		return result, nil
	}

	block := func(m member, head string) []string {
		var lines []string
		if !m.alive {
			lines = []string{head + "[DEAD] " + m.abspath}
		} else {
			label := "  " + m.title
			if m.typ != "" {
				label = "  [" + m.typ + "] " + m.title
			}
			lines = []string{fmt.Sprintf("%s%s%s  ~%d tok", head, m.abspath, label, m.tokens)}
			if m.description != "" && m.required() {
				lines = append(lines, "     "+m.description)
			}
		}
		if m.comment != "" {
			lines = append(lines, "     why: "+m.comment)
		}
		return lines
	}

	title := "ctx " + slug
	if c.Description != "" {
		title += " — " + c.Description
	}
	out := []string{title, "", "required — read in this order:"}
	for _, m := range required {
		out = append(out, block(m, "  "+posText(m.pos)+". ")...)
	}
	if len(required) == 0 {
		out = append(out, "  (none)")
	}
	if len(reference) > 0 {
		out = append(out, "reference — query when needed:")
		for _, m := range reference {
			out = append(out, block(m, "  - ")...)
		}
	}
	out = append(out, "", fmt.Sprintf("%d entries (%d required, %d reference), ~%d tokens for the required set",
		len(ms), len(required), len(reference), tokensRequired))
	if dead > 0 {
		out = append(out, deadWarning(slug, dead))
	}
	stdio.Println(strings.Join(out, "\n"))
	if dead > 0 {
		return nil, okferr.New(okferr.NonConformant, "")
	}
	return nil, nil
}

// runRead is Python cmd_ctx_read: the full text of every required entry.
func runRead(root string, a *cli.Args) (any, error) {
	slug := a.String("slug")
	_, ms, err := members(root, slug)
	if err != nil {
		return nil, err
	}
	required, _ := split(ms)
	refs := len(ms) - len(required)
	texts := make([]*string, len(required)) // nil for a dead entry
	rows := make([]envelope.Obj, len(required))
	allAlive := true
	for i, m := range required {
		if m.alive {
			text, err := catalogue.ReadFile(m.abspath)
			if err != nil {
				return nil, err
			}
			texts[i] = &text
		} else {
			allAlive = false
		}
		rows[i] = envelope.O("position", i+1, "path", m.path, "abspath", m.abspath, "alive", m.alive, "text", texts[i])
	}
	result := envelope.O("slug", slug, "entries", rows, "references_not_printed", refs)
	if !a.JSON {
		var sb strings.Builder
		for i, m := range required {
			if texts[i] == nil {
				fmt.Fprintf(&sb, "===== %d/%d [DEAD] %s =====\n", i+1, len(required), m.abspath)
				continue
			}
			fmt.Fprintf(&sb, "===== %d/%d %s =====\n", i+1, len(required), m.abspath)
			sb.WriteString(*texts[i])
			if !strings.HasSuffix(*texts[i], "\n") {
				sb.WriteByte('\n')
			}
		}
		if refs > 0 {
			plural := "ies"
			if refs == 1 {
				plural = "y"
			}
			fmt.Fprintf(&sb, "===== %d reference entr%s not printed — ctx show %s =====\n", refs, plural, slug)
		}
		stdio.Print(sb.String())
	}
	if !allAlive {
		return nil, okferr.WithResult(okferr.NonConformant, "", result)
	}
	return result, nil
}

// runToc is Python cmd_ctx_toc: the headings of every entry.
func runToc(root string, a *cli.Args) (any, error) {
	slug, depth := a.String("slug"), a.Int("depth")
	_, ms, err := members(root, slug)
	if err != nil {
		return nil, err
	}
	type entry struct {
		path     string
		alive    bool
		headings []catalogue.Heading
	}
	entries := make([]entry, len(ms))
	for i, m := range ms {
		e := entry{path: m.path, alive: m.alive}
		if m.alive && strings.HasSuffix(m.path, ".md") {
			text, err := catalogue.ReadFile(m.abspath)
			if err != nil {
				return nil, err
			}
			for _, h := range catalogue.IterHeadings(frontmatter.Read(text).Body) {
				if depth == 0 || h.Level <= depth {
					e.headings = append(e.headings, h)
				}
			}
		}
		entries[i] = e
	}
	if a.JSON {
		rows := make([]envelope.Obj, len(entries))
		for i, e := range entries {
			heads := make([]envelope.Obj, len(e.headings))
			for j, h := range e.headings {
				heads[j] = envelope.O("level", h.Level, "text", h.Text)
			}
			rows[i] = envelope.O("path", e.path, "alive", e.alive, "headings", heads)
		}
		return envelope.O("slug", slug, "entries", rows), nil
	}
	blocks := make([]string, len(entries))
	for i, e := range entries {
		head := "# " + e.path
		if !e.alive {
			head += " [DEAD]"
		}
		lines := []string{head}
		if e.alive {
			if len(e.headings) == 0 {
				lines = append(lines, "(no headings)")
			}
			for _, h := range e.headings {
				lines = append(lines, strings.Repeat("#", min(h.Level+1, 6))+" "+h.Text)
			}
		}
		blocks[i] = strings.Join(lines, "\n")
	}
	stdio.Println(strings.Join(blocks, "\n\n"))
	return nil, nil
}
