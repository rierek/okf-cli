package navigation

import (
	"sort"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/cli"
	"nas/volume1/data/git/okf-tools/go/internal/envelope"
	"nas/volume1/data/git/okf-tools/go/internal/okferr"
	"nas/volume1/data/git/okf-tools/go/internal/pytext"
	"nas/volume1/data/git/okf-tools/go/internal/spec"
	"nas/volume1/data/git/okf-tools/go/internal/where"
)

type listHit struct {
	title, typ, path, desc string
	tier                   string
	stale                  bool
}

// runList is Python cmd_list: the complete set a required --where selects, sorted by title.
func runList(root string, a *cli.Args) (any, error) {
	if !a.Has("where") {
		return nil, okferr.New(okferr.InvalidInput, "(error: pass --where, e.g. --where 'type = Runbook')")
	}
	expr := a.String("where")
	filters, err := where.CompileWhere(&expr, false, nil)
	if err != nil {
		return nil, err
	}
	now := filters.Now()
	scopes, err := catalogue.ResolveScopes(root, "", filters.IncludeArchive(), false)
	if err != nil {
		return nil, err
	}
	var hits []listHit
	for _, scope := range scopes {
		for _, ap := range catalogue.IterConcepts(scope.Path, true) {
			meta, fm, err := catalogue.MetaAndFm(ap, catalogue.RealFS)
			if err != nil {
				return nil, err
			}
			path := conceptPath(root, ap)
			if !filters.MatchesLoaded(path, fm) {
				continue
			}
			tier, stale := spec.TrustFields(fm, now)
			hits = append(hits, listHit{meta.Title, meta.Type, path, meta.Description, tier, stale})
		}
	}
	sort.SliceStable(hits, func(i, j int) bool { return pytext.Casefold(hits[i].title) < pytext.Casefold(hits[j].title) })
	if a.JSON {
		out := make([]envelope.Obj, len(hits))
		for i, h := range hits {
			out[i] = envelope.O("title", h.title, "type", h.typ, "path", h.path, "description", h.desc,
				"tier", h.tier, "stale", h.stale)
		}
		return out, nil
	}
	w := newOut()
	defer w.Flush()
	if len(hits) == 0 {
		printf(w, "(no matches)\n")
		return nil, nil
	}
	for _, h := range hits {
		printf(w, "------\ntitle: %s\ntype: %s\npath: %s\ndescription: %s\n", h.title, h.typ, h.path, h.desc)
	}
	printf(w, "------\nlist: %d concept(s)\n", len(hits))
	return nil, nil
}
