package ctx

import (
	"fmt"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/cli"
	"nas/volume1/data/git/okf-tools/go/internal/envelope"
	"nas/volume1/data/git/okf-tools/go/internal/linkscan"
	"nas/volume1/data/git/okf-tools/go/internal/okferr"
	"nas/volume1/data/git/okf-tools/go/internal/pytext"
	"nas/volume1/data/git/okf-tools/go/internal/stdio"
)

func runInbound(root string, a *cli.Args) (any, error)  { return nav(root, a, "inbound") }
func runOutbound(root string, a *cli.Args) (any, error) { return nav(root, a, "outbound") }

// splitextRoot is os.path.splitext(p)[0]: p without its extension, where leading dots never start
// one.
func splitextRoot(p string) string {
	slash, dot := strings.LastIndexByte(p, '/'), strings.LastIndexByte(p, '.')
	if dot <= slash {
		return p
	}
	if strings.Trim(p[slash+1:dot], ".") == "" { // the name before the last dot is dots only
		return p
	}
	return p[:dot]
}

// navLink is one link of a member: the file that links to it (inbound), or the target it links to
// and whether that exists (outbound), with the link as written.
type navLink struct {
	source, target, raw string
	exists              bool
}

// obj is the JSON object of a link, in Python's key order.
func (l navLink) obj(inbound bool) envelope.Obj {
	if inbound {
		return envelope.O("source", l.source, "link", l.raw)
	}
	return envelope.O("target", l.target, "link", l.raw, "exists", l.exists)
}

func (l navLink) line(inbound bool) string {
	if inbound {
		return fmt.Sprintf("  <- %s  (%s)", l.source, l.raw)
	}
	missing := ""
	if !l.exists {
		missing = "  [missing]"
	}
	return fmt.Sprintf("  -> %s  (%s)%s", l.target, l.raw, missing)
}

// nav is Python _ctx_nav, the shared body of `inbound` and `outbound`: per member, the files that
// link to it or the targets it links to, without the links between members unless asked.
func nav(root string, a *cli.Args, direction string) (any, error) {
	slug, file, include := a.String("slug"), a.String("file"), a.Bool("include_internal")
	inbound := direction == "inbound"
	_, ms, err := members(root, slug)
	if err != nil {
		return nil, err
	}
	abs := make([]string, len(ms))
	for i, m := range ms {
		if abs[i], err = catalogue.Abspath(m.abspath); err != nil {
			return nil, err
		}
	}
	shown := make([]int, len(ms))
	for i := range ms {
		shown[i] = i
	}
	if file != "" {
		x := pytext.Lower(file)
		shown = shown[:0]
		for i, m := range ms {
			base := m.path[strings.LastIndexByte(m.path, '/')+1:]
			if x == pytext.Lower(m.title) || x == pytext.Lower(m.path) || x == pytext.Lower(splitextRoot(base)) {
				shown = append(shown, i)
			}
		}
		if len(shown) == 0 {
			return nil, die(okferr.NotFound, `no entry in %s matches --file "%s"`, slug, file)
		}
		if len(shown) > 1 {
			paths := make([]string, len(shown))
			for j, i := range shown {
				paths[j] = ms[i].path
			}
			return nil, die(okferr.InvalidInput, `--file "%s" matches several entries: %s`, file, strings.Join(paths, ", "))
		}
	}
	byLower := map[string][]int{}
	for i := range ms {
		key := pytext.Lower(abs[i])
		byLower[key] = append(byLower[key], i)
	}
	// owners are the members that are the file ap (Python owners()).
	owners := func(ap string) ([]int, error) {
		var out []int
		for _, i := range byLower[pytext.Lower(ap)] {
			same, err := catalogue.CtxSameFile(ap, abs[i])
			if err != nil {
				return nil, err
			}
			if same {
				out = append(out, i)
			}
		}
		return out, nil
	}

	links := make([][]navLink, len(ms))
	if inbound {
		// one catalogue scan per call; the links are bucketed by member afterwards
		for l, err := range linkscan.IterMdLinks(root) {
			if err != nil {
				return nil, err
			}
			if strings.HasPrefix(l.Source, catalogue.CtxDir+"/") {
				continue
			}
			targets, err := owners(l.Resolved)
			if err != nil {
				return nil, err
			}
			for _, i := range targets {
				if !include {
					srcAbs, err := catalogue.Abspath(catalogue.Join(root, l.Source))
					if err != nil {
						return nil, err
					}
					fromMember, err := owners(srcAbs)
					if err != nil {
						return nil, err
					}
					if len(fromMember) > 0 {
						continue
					}
				}
				links[i] = append(links[i], navLink{source: l.Source, raw: l.Raw})
			}
		}
	} else {
		for _, i := range shown {
			if !ms[i].alive || !strings.HasSuffix(ms[i].path, ".md") {
				continue
			}
			outs, err := linkscan.OutboundLinks(root, abs[i])
			if err != nil {
				return nil, err
			}
			for _, o := range outs {
				if !include {
					toMember, err := owners(o.Target)
					if err != nil {
						return nil, err
					}
					if len(toMember) > 0 {
						continue
					}
				}
				target, err := linkscan.RefsDisplay(root, o.Target)
				if err != nil {
					return nil, err
				}
				links[i] = append(links[i], navLink{target: target, raw: o.Raw, exists: o.Exists})
			}
		}
	}

	if a.JSON {
		rows := make([]envelope.Obj, len(shown))
		for j, i := range shown {
			objs := make([]envelope.Obj, len(links[i]))
			for k, l := range links[i] {
				objs[k] = l.obj(inbound)
			}
			row := envelope.O("path", ms[i].path)
			if !inbound {
				row.Set("dead", !ms[i].alive)
			}
			row.Set("links", objs)
			rows[j] = row
		}
		return envelope.O("slug", slug, "direction", direction, "include_internal", include, "members", rows), nil
	}

	scope := "external targets only"
	if inbound {
		scope = "external sources only"
	}
	if include {
		scope = "including internal links"
	}
	out := []string{fmt.Sprintf("%s — ctx %s, %d member(s), %s:", direction, slug, len(shown), scope)}
	for _, i := range shown {
		m := ms[i]
		if !inbound && !m.alive {
			out = append(out, m.path+" [DEAD]")
			continue
		}
		out = append(out, m.path)
		for _, l := range links[i] {
			out = append(out, l.line(inbound))
		}
		if len(links[i]) == 0 {
			out = append(out, "  (none)")
		}
	}
	stdio.Println(strings.Join(out, "\n"))
	return nil, nil
}
