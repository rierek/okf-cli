package navigation

import (
	"os"
	"path"
	"path/filepath"
	"regexp"
	"sort"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/cli"
	"nas/volume1/data/git/okf-tools/go/internal/envelope"
	"nas/volume1/data/git/okf-tools/go/internal/frontmatter"
	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

func visualizeArgs() []cli.Arg {
	return []cli.Arg{
		{Dest: "bundle", Help: "bundle to render the graph for"},
		{Flags: []string{"--out"}, Help: "output path (default: <bundle>/assets/viz.html)"},
		cli.JSON(),
	}
}

var (
	vizLinkRE  = regexp.MustCompile(`\[[^\]]+\]\(([^)]+)\)`)
	vizFenceRE = regexp.MustCompile("(?s)```.*?```")
)

type vizNode struct{ id, title, typ, body string }

// bundleGraph is Python bundle_graph: the nodes (concepts, by concept id) and edges (in-bundle
// markdown links, as written, duplicates kept) of one bundle.
func bundleGraph(root, bundle string) ([]envelope.Obj, []envelope.Obj, error) {
	concepts := map[string]string{} // cid -> abspath
	var ids []string
	for cid, ap := range catalogue.IterConcepts(catalogue.Join(root, bundle), true) {
		concepts[cid] = ap
		ids = append(ids, cid)
	}
	sort.Strings(ids)
	nodes, edges := []envelope.Obj{}, []envelope.Obj{}
	for _, cid := range ids {
		text, err := catalogue.ReadFile(concepts[cid])
		if err != nil {
			return nil, nil, err
		}
		doc := frontmatter.Read(text)
		title := frontmatter.Text(doc.Data(), "title", "")
		if title == "" {
			title = cid
		}
		nodes = append(nodes, envelope.O("id", cid, "title", title,
			"type", frontmatter.Text(doc.Data(), "type", ""), "body", doc.Body))
		cdir := path.Dir(cid)
		if cdir == "." {
			cdir = ""
		}
		for _, m := range vizLinkRE.FindAllStringSubmatch(vizFenceRE.ReplaceAllString(doc.Body, ""), -1) {
			head, _, _ := strings.Cut(m[1], "#")
			tgt := pytext.Strip(head)
			if !strings.HasSuffix(tgt, ".md") || strings.HasPrefix(tgt, "http") || strings.HasPrefix(tgt, "..") {
				continue
			}
			var dest string
			if strings.HasPrefix(tgt, "/") {
				// catalogue-root-absolute (/bundle/subdir/concept.md): strip the leading /bundle/ to
				// get the bundle-relative cid. A link into a different bundle won't match this
				// bundle's concepts and is dropped: only in-bundle edges are built.
				dest = tgt[1 : len(tgt)-3]
				if dest == bundle {
					dest = ""
				} else if strings.HasPrefix(dest, bundle+"/") {
					dest = dest[len(bundle)+1:]
				}
			} else {
				dest = path.Clean(path.Join(cdir, tgt[:len(tgt)-3]))
			}
			if _, ok := concepts[dest]; ok && dest != cid {
				edges = append(edges, envelope.O("source", cid, "target", dest))
			}
		}
	}
	return nodes, edges, nil
}

// runVisualize is Python cmd_visualize: writes the graph page, nothing else.
func runVisualize(root string, a *cli.Args) (any, error) {
	bundle := a.String("bundle")
	if err := catalogue.RequireBundleDir(root, bundle); err != nil {
		return nil, err
	}
	nodes, edges, err := bundleGraph(root, bundle)
	if err != nil {
		return nil, err
	}
	out := a.String("out")
	if out == "" {
		out = filepath.Join(root, bundle, "assets", "viz.html")
	}
	data, err := envelope.Marshal(envelope.O("name", bundle, "nodes", nodes, "edges", edges))
	if err != nil {
		return nil, err
	}
	html := strings.ReplaceAll(vizTemplate, "__DATA__", asciiJSON(string(data)))
	html = strings.ReplaceAll(html, "__NAME__", bundle)
	if err := os.MkdirAll(filepath.Dir(out), 0o777); err != nil {
		return nil, err
	}
	if err := os.WriteFile(out, []byte(html), 0o666); err != nil {
		return nil, err
	}
	if a.JSON {
		return envelope.O("applied", true, "path", out, "nodes", len(nodes), "edges", len(edges)), nil
	}
	w := newOut()
	defer w.Flush()
	printf(w, "wrote %s (%d nodes, %d edges)\n", out, len(nodes), len(edges))
	return nil, nil
}
