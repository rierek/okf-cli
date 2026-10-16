package navigation

import (
	"bufio"
	"slices"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/cli"
	"nas/volume1/data/git/okf-tools/go/internal/envelope"
	"nas/volume1/data/git/okf-tools/go/internal/frontmatter"
	"nas/volume1/data/git/okf-tools/go/internal/linkscan"
	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

type followNode struct {
	path  string
	depth int
}

// followNodes is Python follow_nodes, the `read --follow` node list: BFS over markdown links
// from startAbs, root first at depth 0, each file once at its first depth. Neighbours of a node
// are its outbound targets in order of first appearance, then (inbound) the files linking to it
// sorted by catalogue-relative path. Depth 0 scans nothing; otherwise the catalogue is walked
// once and both link directions come from that one pass. Only scanned .md files are nodes.
func followNodes(root, startAbs string, depth int, inbound bool) ([]followNode, error) {
	if depth < 1 {
		return []followNode{{startAbs, 0}}, nil
	}
	seq, err := linkscan.IterRenameScanMd(root)
	if err != nil {
		return nil, err
	}
	files := slices.Collect(seq)
	byLower := map[string][]string{}
	for _, f := range files {
		l := pytext.Lower(f)
		byLower[l] = append(byLower[l], f)
	}
	var nodeErr error
	// a link may spell an existing file in another case: same file, same node
	node := func(p string) (string, bool) {
		for _, f := range byLower[pytext.Lower(p)] {
			same, err := catalogue.CtxSameFile(p, f)
			if err != nil && nodeErr == nil {
				nodeErr = err
			}
			if same {
				return f, true
			}
		}
		return "", false
	}
	out := map[string][]string{} // insertion-ordered set per file
	seenOut := map[[2]string]bool{}
	back := map[string]map[string]bool{}
	for _, f := range files {
		links, err := linkscan.FileMdLinks(root, f)
		if err != nil {
			return nil, err
		}
		for _, l := range links {
			t, ok := node(l.Resolved)
			if !ok {
				continue
			}
			if !seenOut[[2]string{f, t}] {
				seenOut[[2]string{f, t}] = true
				out[f] = append(out[f], t)
			}
			if back[t] == nil {
				back[t] = map[string]bool{}
			}
			back[t][f] = true
		}
	}
	if nodeErr != nil {
		return nil, nodeErr
	}
	start, ok := node(startAbs)
	if !ok {
		start = startAbs
	}
	seen := map[string]bool{start: true}
	order := []followNode{{start, 0}}
	frontier := []string{start}
	for d := 1; d <= depth; d++ {
		var next []string
		for _, n := range frontier {
			nbrs := slices.Clone(out[n])
			if inbound {
				var linking []string
				for f := range back[n] {
					linking = append(linking, f)
				}
				slices.SortFunc(linking, func(a, b string) int {
					pa, pb := conceptPath(root, a), conceptPath(root, b)
					switch {
					case pa < pb:
						return -1
					case pa > pb:
						return 1
					}
					return 0
				})
				nbrs = append(nbrs, linking...)
			}
			for _, m := range nbrs {
				if !seen[m] {
					seen[m] = true
					order = append(order, followNode{m, d})
					next = append(next, m)
				}
			}
		}
		frontier = next
	}
	return order, nil
}

// block is one record of the `read --follow` block.
type block struct {
	path, text, title, desc string
	depth, tokens           int
	reduced                 bool
}

func (b block) reducedText() string {
	if b.desc != "" {
		return b.title + "\n" + b.desc
	}
	return b.title
}

// obj is the record as the JSON envelope shows it.
func (b block) obj() envelope.Obj {
	rec := envelope.O("path", b.path, "depth", b.depth, "reduced", b.reduced)
	if b.reduced {
		rec = append(rec, envelope.Field{Key: "title", Value: b.title}, envelope.Field{Key: "description", Value: b.desc})
	} else {
		rec = append(rec, envelope.Field{Key: "text", Value: b.text})
	}
	return append(rec, envelope.Field{Key: "tokens", Value: b.tokens})
}

// followBlock is Python _follow_block: the root is always full; with --max-tokens the walk stops
// printing nodes in full at the first one that would push the running total over the budget (no
// later small node jumps ahead of it).
func followBlock(root string, a *cli.Args, startAbs, rootText string) ([]block, error) {
	nodes, err := followNodes(root, startAbs, a.Int("follow"), a.Bool("inbound"))
	if err != nil {
		return nil, err
	}
	var blocks []block
	used, reduced := 0, false
	for i, n := range nodes {
		text := rootText
		if i > 0 {
			if text, err = catalogue.ReadFile(n.path); err != nil {
				return nil, err
			}
		}
		if i > 0 && a.Has("max_tokens") && used+catalogue.Tokens(charLen(text)) > a.Int("max_tokens") {
			reduced = true
		}
		b := block{path: conceptPath(root, n.path), depth: n.depth, reduced: reduced}
		if reduced {
			_, b.title, b.desc = frontmatter.Meta(frontmatter.Read(text).Data(), stem(n.path))
			b.tokens = catalogue.Tokens(charLen(b.reducedText()))
		} else {
			b.text, b.tokens = text, catalogue.Tokens(charLen(text))
		}
		used += b.tokens
		blocks = append(blocks, b)
	}
	return blocks, nil
}

// printBlock is Python _print_block: one header line per node, `===== depth N path =====` plus
// ` [reduced]` for a node shown as title and description only.
func printBlock(w *bufio.Writer, blocks []block) {
	for _, b := range blocks {
		mark := ""
		if b.reduced {
			mark = " [reduced]"
		}
		printf(w, "===== depth %d %s%s =====\n", b.depth, b.path, mark)
		body := b.text
		if b.reduced {
			body = b.reducedText()
		}
		printf(w, "%s", body)
		if len(body) == 0 || body[len(body)-1] != '\n' {
			printf(w, "\n")
		}
	}
}
