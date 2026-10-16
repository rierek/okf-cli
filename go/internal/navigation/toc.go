package navigation

import (
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/cli"
	"nas/volume1/data/git/okf-tools/go/internal/envelope"
	"nas/volume1/data/git/okf-tools/go/internal/frontmatter"
)

func tocArgs() []cli.Arg {
	return []cli.Arg{
		{Dest: "path", Help: "<bundle>/<concept-id> to list headings for"},
		{Flags: []string{"--level"}, Type: cli.Int, Default: 2,
			Help: "heading level to list (default 2 = h2); 0 = full indented tree"},
		cli.JSON(),
	}
}

// runToc is Python cmd_toc: the headings of one concept at one level, or all as an indented tree.
func runToc(root string, a *cli.Args) (any, error) {
	ap, err := catalogue.ResolveConcept(root, a.String("path"))
	if err != nil {
		return nil, err
	}
	text, err := catalogue.ReadFile(ap)
	if err != nil {
		return nil, err
	}
	doc := frontmatter.Read(text)
	typ, title, _ := frontmatter.Meta(doc.Data(), stem(ap))
	level := a.Int("level")
	var heads []catalogue.Heading
	for _, h := range catalogue.IterHeadings(doc.Body) {
		if level == 0 || h.Level == level {
			heads = append(heads, h)
		}
	}
	if a.JSON {
		items := make([]envelope.Obj, len(heads))
		for i, h := range heads {
			items[i] = envelope.O("level", h.Level, "text", h.Text)
		}
		return envelope.O("path", conceptPath(root, ap), "title", title, "type", typ, "headings", items), nil
	}
	w := newOut()
	defer w.Flush()
	printf(w, "# %s  [%s]\n", title, typ)
	for _, h := range heads {
		if level == 0 {
			printf(w, "%s- %s\n", strings.Repeat("  ", h.Level-1), h.Text)
		} else {
			printf(w, "- %s\n", h.Text)
		}
	}
	if len(heads) == 0 {
		if level != 0 {
			printf(w, "(no h%d headings)\n", level)
		} else {
			printf(w, "(no headings)\n")
		}
	}
	return nil, nil
}
