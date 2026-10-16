package tagwrite

import (
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"unicode/utf8"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/cli"
	"nas/volume1/data/git/okf-tools/go/internal/complete"
	"nas/volume1/data/git/okf-tools/go/internal/envelope"
	"nas/volume1/data/git/okf-tools/go/internal/okferr"
	"nas/volume1/data/git/okf-tools/go/internal/tagvec"
)

func registerTags(app *cli.App) {
	app.Attach("tags", cli.Spec{
		Args: []cli.Arg{
			{Dest: "query", Nargs: cli.ZeroOrMore,
				Help: "candidate tag(s) to fuzzy-search against the tag universe; omit for full audit dump"},
			{Flags: []string{"--limit"}, Type: cli.Int, Default: 8, Help: "max matches per candidate (default 8)"},
			{Flags: []string{"--singletons"}, Action: cli.StoreTrue, Help: "full-dump mode only: show tags used exactly once"},
			{Flags: []string{"--register"}, Action: cli.Append, Nargs: cli.Exactly(2), Metavar: []string{"TAG", "DESCRIPTION"},
				Help: "add a tag to the TAGS.md registry (closed-vocabulary allow-list); " +
					"DESCRIPTION is required, max 150 chars; repeat the option for several tags"},
			{Flags: []string{"--validate"}, Nargs: cli.OneOrMore, Metavar: []string{"TAG"},
				Help: "check tag(s) against TAGS.md; exit 1 if any are unregistered"},
			cli.JSON(),
		},
		Handler: runTags,
	})
	complete.Attach([]string{"tags"}, "validate", complete.Tags)
}

// runTags is Python cmd_tags: registration first, then validation, else the listing or the search.
func runTags(root string, a *cli.Args) (any, error) {
	if entries := a.StringLists("register"); len(entries) > 0 {
		return tagsRegister(root, a, entries)
	}
	if a.Has("validate") {
		return tagsValidate(root, a)
	}
	counts, err := catalogue.AllTags(root)
	if err != nil {
		return nil, err
	}
	w := newOut()
	defer w.Flush()
	if queries := a.Strings("query"); len(queries) > 0 {
		return tagsSearch(w, a, counts, queries)
	}
	rows := counts.Ranked()
	if a.Bool("singletons") {
		single := rows[:0:0]
		for _, r := range rows {
			if r.Count == 1 {
				single = append(single, r)
			}
		}
		rows = single
	}
	if a.JSON {
		list := make([]envelope.Obj, len(rows))
		for i, r := range rows {
			list[i] = envelope.O("tag", r.Tag, "count", r.Count)
		}
		return envelope.O("tags", list), nil
	}
	switch {
	case len(counts) == 0:
		fmt.Fprintln(w, "(no tags found)")
	case len(rows) == 0:
		fmt.Fprintln(w, "(no singleton tags)")
	default:
		width := 0
		for _, r := range rows {
			width = max(width, utf8.RuneCountInString(r.Tag))
		}
		for _, r := range rows {
			fmt.Fprintf(w, "  %s  %d\n", ljust(r.Tag, width), r.Count)
		}
	}
	return nil, nil
}

// ljust is str.ljust(width): padding counts code points.
func ljust(s string, width int) string {
	if n := utf8.RuneCountInString(s); n < width {
		return s + strings.Repeat(" ", width-n)
	}
	return s
}

// tagsRegister is the --register branch of cmd_tags: registration in TAGS.md, then the best-effort
// embedding of the new tags.
func tagsRegister(root string, a *cli.Args, entries [][]string) (any, error) {
	added, already, err := registerEntries(root, entries)
	var refused *refusal
	if errors.As(err, &refused) {
		return nil, okferr.New(okferr.InvalidInput, "ERROR: "+refused.msg)
	}
	if err != nil {
		return nil, err
	}
	if len(added) > 0 {
		if !a.JSON {
			fmt.Printf("registered %d new tag(s) in TAGS.md: %s\n", len(added), strings.Join(added, ", "))
		}
		autoEmbedNewTags(root, added)
	}
	if len(already) > 0 && !a.JSON {
		fmt.Printf("already registered: %s\n", strings.Join(already, ", "))
	}
	return envelope.O("registered", added, "already_registered", already), nil
}

// autoEmbedNewTags is Python auto_embed_new_tags: the best-effort bge-m3 embedding of newly
// registered tags, scoped to just those (never a full re-embed), so that registration and embedding
// coverage do not drift apart. It never fails: `tags --register` must succeed without a reachable
// Ollama; a failure is one stderr warning. Vectors are written only after a successful embedding.
func autoEmbedNewTags(root string, tags []string) {
	rows, err := embedNewTags(root, tags)
	if err != nil {
		fmt.Fprintf(os.Stderr, "warning: auto-embed skipped for new tag(s) (%s) \u2014 "+
			"run cli/embeddings/build_tagvec.py --produce manually later\n", err)
		return
	}
	if rows > 0 {
		fmt.Fprintf(os.Stderr, "auto-embedded %d new tag(s) (bge-m3)\n", rows)
	}
}

// embedNewTags plans the delta of tags against the store, embeds it and writes the rows; it returns
// the number of rows written.
func embedNewTags(root string, tags []string) (int, error) {
	const model = "bge-m3"
	output := filepath.Join(root, ".tagvec", "tag_vectors.sqlite")
	delta, err := tagvec.PlanDelta(tags, model, output)
	if err != nil || len(delta) == 0 {
		return 0, err
	}
	texts := make([]string, len(delta))
	for i, t := range delta {
		texts[i] = t.Text
	}
	vectors, err := tagvec.EmbedBGEM3(texts)
	if err != nil {
		return 0, err
	}
	rows := make([]tagvec.TagRow, len(delta))
	for i, t := range delta {
		rows[i] = tagvec.TagRow{Key: t.Key, Tag: t.Item, Model: model, Dim: tagvec.Dim(model), Vec: tagvec.PackVec(vectors[i])}
	}
	if err := tagvec.WriteTagRows(output, rows); err != nil {
		return 0, err
	}
	return len(rows), nil
}

// tagsValidate is the --validate branch of cmd_tags: every tag against the registry; an unknown tag
// ends with non_conformant (exit 4) and the result as data.
func tagsValidate(root string, a *cli.Args) (any, error) {
	known, err := catalogue.LoadTags(root, "")
	if err != nil {
		return nil, err
	}
	if known == nil {
		if !a.JSON {
			fmt.Println("(no TAGS.md \u2014 closed vocabulary not enabled)")
		}
		return envelope.O("closed_vocabulary", false, "unknown", []string{}), nil
	}
	checked := a.Strings("validate")
	unknown := []string{}
	for _, t := range checked {
		if !known[t] {
			unknown = append(unknown, t)
		}
	}
	if !a.JSON {
		for _, t := range unknown {
			fmt.Printf("UNKNOWN  %s\n", t)
		}
		if len(unknown) == 0 {
			fmt.Printf("OK \u2014 all %d known\n", len(checked))
		} else {
			fmt.Printf("%d UNKNOWN \u2014 register with: okf tags --register <tag> \"<description, max %d chars>\"\n",
				len(unknown), tagDescMax)
		}
	}
	result := envelope.O("closed_vocabulary", true, "unknown", unknown)
	if len(unknown) > 0 {
		return nil, okferr.WithResult(okferr.NonConformant, "", result)
	}
	return result, nil
}

// tagsSearch is the query branch of cmd_tags: every query fuzzy-searched against the tags in use.
func tagsSearch(w io.Writer, a *cli.Args, counts catalogue.TagCounts, queries []string) (any, error) {
	universe := counts.Sorted()
	limit := a.Int("limit")
	type match struct {
		tag   string
		count int
	}
	type search struct {
		query   string
		matches []match
	}
	searches := make([]search, len(queries))
	for i, q := range queries {
		searches[i].query = q
		for _, tag := range fuzzyMatches(q, universe, limit) {
			searches[i].matches = append(searches[i].matches, match{tag, counts[tag]})
		}
	}
	if a.JSON {
		list := make([]envelope.Obj, len(searches))
		for i, s := range searches {
			matches := make([]envelope.Obj, len(s.matches))
			for k, m := range s.matches {
				matches[k] = envelope.O("tag", m.tag, "count", m.count)
			}
			list[i] = envelope.O("query", s.query, "matches", matches)
		}
		return envelope.O("searches", list), nil
	}
	for _, s := range searches {
		fmt.Fprintf(w, "== searched: %s ==\n", s.query)
		if len(s.matches) == 0 {
			fmt.Fprintln(w, "  (no match \u2014 new tag)")
		}
		for _, m := range s.matches {
			fmt.Fprintf(w, "  - %s  (%d)\n", m.tag, m.count)
		}
		fmt.Fprintln(w)
	}
	return nil, nil
}
