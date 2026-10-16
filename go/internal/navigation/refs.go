package navigation

import (
	"os"
	"path/filepath"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/cli"
	"nas/volume1/data/git/okf-tools/go/internal/envelope"
	"nas/volume1/data/git/okf-tools/go/internal/linkscan"
	"nas/volume1/data/git/okf-tools/go/internal/okferr"
)

func refsSpec() cli.Spec {
	return cli.Spec{
		Args: []cli.Arg{
			{Dest: "path", Help: "target file (abs, or relative to --root)"},
			{Flags: []string{"--scan-root"}, Help: "dir to scan (default: --root); pass repo root for repo-wide"},
			{Dest: "only_in", Flags: []string{"--in"}, Action: cli.StoreTrue, Help: "only inbound links"},
			{Dest: "only_out", Flags: []string{"--out"}, Action: cli.StoreTrue, Help: "only outbound links"},
			cli.JSON(),
		},
		Exclusive: []cli.Exclusive{{Dests: []string{"only_in", "only_out"}}},
		Handler:   runRefs,
	}
}

func exists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}

// runRefs is Python cmd_refs: the inbound and outbound markdown links of one file.
func runRefs(root string, a *cli.Args) (any, error) {
	scanRoot := root
	if s := a.String("scan_root"); s != "" {
		var err error
		if scanRoot, err = catalogue.Abspath(s); err != nil {
			return nil, err
		}
	}
	path := a.String("path")
	target := path
	if !filepath.IsAbs(path) {
		// resolve against scan_root (the tree the path lives in) when given, else root; prefer
		// whichever actually exists.
		target = catalogue.Join(scanRoot, path)
		if !exists(target) {
			target = catalogue.Join(root, path)
		}
	}
	if !exists(target) {
		return nil, okferr.Newf(okferr.NotFound, "refs: target not found: %s", path)
	}
	wantIn, wantOut := !a.Bool("only_out"), !a.Bool("only_in")
	var hits []linkscan.Ref
	if wantIn {
		var err error
		if hits, err = linkscan.BuildRefMatrix(scanRoot, target); err != nil {
			return nil, err
		}
	}
	type outbound struct {
		link, target string
		exists       bool
	}
	var out []outbound
	if info, err := os.Stat(target); wantOut && strings.HasSuffix(target, ".md") && err == nil && info.Mode().IsRegular() {
		links, err := linkscan.OutboundLinks(scanRoot, target)
		if err != nil {
			return nil, err
		}
		for _, l := range links {
			shown, err := linkscan.RefsDisplay(scanRoot, l.Target)
			if err != nil {
				return nil, err
			}
			out = append(out, outbound{l.Raw, shown, l.Exists})
		}
	}
	if a.JSON {
		abs, err := catalogue.Abspath(target)
		if err != nil {
			return nil, err
		}
		rel, err := filepath.Rel(scanRoot, abs)
		if err != nil {
			return nil, err
		}
		d := envelope.O("target", filepath.ToSlash(rel))
		if wantIn {
			in := make([]envelope.Obj, len(hits))
			for i, h := range hits {
				in[i] = envelope.O("source", h.Source, "link", h.Raw)
			}
			d.Set("inbound", in)
		}
		if wantOut {
			o := make([]envelope.Obj, len(out))
			for i, l := range out {
				o[i] = envelope.O("link", l.link, "target", l.target, "exists", l.exists)
			}
			d.Set("outbound", o)
		}
		return d, nil
	}
	w := newOut()
	defer w.Flush()
	if wantIn {
		printf(w, "inbound (%d):\n", len(hits))
		for _, h := range hits {
			printf(w, "  %s  ->  %s\n", h.Source, h.Raw)
		}
		if len(hits) == 0 {
			printf(w, "  (none)\n")
		}
	}
	if wantOut {
		printf(w, "outbound (%d):\n", len(out))
		for _, l := range out {
			missing := ""
			if !l.exists {
				missing = "  [missing]"
			}
			printf(w, "  %s  ->  %s%s\n", l.link, l.target, missing)
		}
		if len(out) == 0 {
			printf(w, "  (none)\n")
		}
	}
	return nil, nil
}
