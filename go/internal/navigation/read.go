package navigation

import (
	"slices"
	"sort"
	"strconv"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/cli"
	"nas/volume1/data/git/okf-tools/go/internal/envelope"
	"nas/volume1/data/git/okf-tools/go/internal/frontmatter"
	"nas/volume1/data/git/okf-tools/go/internal/okferr"
	"nas/volume1/data/git/okf-tools/go/internal/pytext"
	"nas/volume1/data/git/okf-tools/go/internal/spec"
)

func readSpec() cli.Spec {
	return cli.Spec{
		Args: []cli.Arg{
			{Dest: "path", Help: "<bundle>/<concept-id> of the page to print"},
			{Flags: []string{"--section"}, Metavar: []string{"HEADING"},
				Help: "print only this section: heading text (case-insensitive, exact) up to " +
					"the next heading of equal or higher level, sub-sections included; " +
					"'A > B' resolves B inside A"},
			{Flags: []string{"--frontmatter-only"}, Action: cli.StoreTrue,
				Help: "print only the frontmatter block, delimiters included"},
			{Flags: []string{"--body-only"}, Action: cli.StoreTrue,
				Help: "print everything after the frontmatter block"},
			{Flags: []string{"--follow"}, Type: count(0), Metavar: []string{"N"},
				Help: "also print the concepts the page links to, up to N hops deep, as one block " +
					"(BFS, each page once); combines with --section (narrows the root), not with " +
					"--frontmatter-only or --body-only"},
			{Flags: []string{"--inbound"}, Action: cli.StoreTrue,
				Help: "with --follow: the pages linking to a page count as its neighbours too"},
			{Flags: []string{"--max-tokens"}, Type: count(1), Metavar: []string{"K"},
				Help: "with --follow: keep the block within K tokens (chars/4); the root always " +
					"prints in full, from the first page that does not fit on, pages show " +
					"title and description only"},
			cli.JSON(),
		},
		Exclusive: []cli.Exclusive{{Dests: []string{"section", "frontmatter_only", "body_only"}}},
		Handler:   runRead,
	}
}

// splitHeadBody is Python _split_head_body: the frontmatter block with both delimiter lines and
// its last newline, and the rest. Without frontmatter the block is "" and the rest is the text.
func splitHeadBody(doc frontmatter.Doc) (head, body string) {
	if doc.Head != "" && strings.HasPrefix(doc.Body, "\n") {
		return doc.Head + "\n", doc.Body[1:]
	}
	return doc.Head, doc.Body
}

// runRead is Python cmd_read.
func runRead(root string, a *cli.Args) (any, error) {
	if a.Has("follow") && (a.Bool("frontmatter_only") || a.Bool("body_only")) {
		return nil, okferr.New(okferr.InvalidInput, "error: --follow is not allowed with --frontmatter-only or --body-only")
	}
	ap, err := catalogue.ResolveConcept(root, a.String("path"))
	if err != nil {
		return nil, err
	}
	text, err := catalogue.ReadFile(ap)
	if err != nil {
		return nil, err
	}
	doc := frontmatter.Read(text)
	head, body := splitHeadBody(doc)
	var out, end string
	switch {
	case a.Has("section"):
		lines, err := readSection(body, a.String("section"), strings.Count(head, "\n")+1)
		if err != nil {
			return nil, err
		}
		out, end = strings.Join(lines, "\n"), "\n"
	case a.Bool("frontmatter_only"):
		out, end = head, ""
	case a.Bool("body_only"):
		out, end = body, "\n"
	default:
		out, end = text, "\n"
	}
	w := newOut()
	defer w.Flush()
	if a.Int("follow") > 0 {
		nodes, err := followBlock(root, a, ap, out+end)
		if err != nil {
			return nil, err
		}
		if a.JSON {
			objs := make([]envelope.Obj, len(nodes))
			for i, n := range nodes {
				objs[i] = n.obj()
			}
			return envelope.O("nodes", objs), nil
		}
		printBlock(w, nodes)
		return nil, nil
	}
	if a.JSON {
		tier, stale := spec.TrustFields(doc.Data(), spec.Utcnow())
		return envelope.O("path", conceptPath(root, ap), "text", out+end, "tier", tier, "stale", stale), nil
	}
	printf(w, "%s%s", out, end)
	return nil, nil
}

// inside is Python _inside: the indexes of the headings inside the section of heads[k].
func inside(heads []catalogue.Heading, k int) []int {
	var out []int
	for j := k + 1; j < len(heads) && heads[j].Level > heads[k].Level; j++ {
		out = append(out, j)
	}
	return out
}

// headingPath is Python _heading_path: the heading texts from the top-level ancestor down to
// heads[k], joined by " > ".
func headingPath(heads []catalogue.Heading, k int) string {
	path, level := []string{heads[k].Text}, heads[k].Level
	for j := k - 1; j >= 0; j-- {
		if heads[j].Level < level {
			path = append(path, heads[j].Text)
			level = heads[j].Level
		}
	}
	slices.Reverse(path)
	return strings.Join(path, " > ")
}

// readSection is Python _read_section: the lines of the one section `section` ("A" or
// "A > B > ...") names in body. A segment matches heading text case-insensitively and exactly;
// each later segment only inside the section of the previous match. Several matches are
// invalid_input listing every candidate's heading path and file line, none is not_found.
// firstFileLine is the 1-based file line of the body's line 0.
func readSection(body, section string, firstFileLine int) ([]string, error) {
	lines, heads := pytext.SplitLines(body, false), catalogue.IterHeadings(body)
	segments := strings.Split(section, ">")
	for i, s := range segments {
		segments[i] = pytext.Casefold(pytext.Strip(s))
	}
	var hits []int
	for k, h := range heads {
		if pytext.Casefold(h.Text) == segments[0] {
			hits = append(hits, k)
		}
	}
	for _, seg := range segments[1:] {
		found := map[int]bool{}
		for _, k := range hits {
			for _, j := range inside(heads, k) {
				if pytext.Casefold(heads[j].Text) == seg {
					found[j] = true
				}
			}
		}
		hits = hits[:0:0]
		for j := range found {
			hits = append(hits, j)
		}
		sort.Ints(hits)
	}
	if len(hits) == 0 {
		return nil, okferr.Newf(okferr.NotFound, "section not found: %s", section)
	}
	if len(hits) > 1 {
		candidates := make([]envelope.Obj, len(hits))
		var listed []string
		for i, k := range hits {
			heading, line := headingPath(heads, k), firstFileLine+heads[k].Line
			candidates[i] = envelope.O("heading", heading, "line", line)
			listed = append(listed, "  line "+strconv.Itoa(line)+": "+heading)
		}
		return nil, okferr.WithResult(okferr.InvalidInput,
			"ambiguous section: "+section+" matches "+strconv.Itoa(len(hits))+" headings\n"+strings.Join(listed, "\n"),
			envelope.O("candidates", candidates))
	}
	k := hits[0]
	after := k + 1
	if in := inside(heads, k); len(in) > 0 {
		after = in[len(in)-1] + 1
	}
	if after < len(heads) {
		return lines[heads[k].Line:heads[after].Line], nil
	}
	return lines[heads[k].Line:], nil
}
