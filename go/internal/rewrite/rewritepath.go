package rewrite

import (
	"fmt"
	"path/filepath"
	"strings"
	"unicode"
	"unicode/utf8"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/cli"
	"nas/volume1/data/git/okf-tools/go/internal/complete"
	"nas/volume1/data/git/okf-tools/go/internal/diffs"
	"nas/volume1/data/git/okf-tools/go/internal/envelope"
)

// rewriteExts is Python REWRITE_EXTS: the file name suffixes rewrite-path touches (case-sensitive).
var rewriteExts = []string{".md", ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".rb",
	".yml", ".yaml", ".toml", ".json", ".txt", ".rst", ".cfg", ".ini", ".sh"}

// blocksPath reports whether r next to an occurrence makes it part of a longer path string:
// the class [\w./-] of Python `re` (a Unicode letter or number, `_`, `.`, `/`, `-`).
func blocksPath(r rune) bool {
	return r == '_' || r == '.' || r == '/' || r == '-' || unicode.IsLetter(r) || unicode.IsNumber(r)
}

// standalone is the pair of look-arounds (?<![\w./-]) and (?![\w./-]) at text[s:e].
func standalone(text string, s, e int) bool {
	if s > 0 {
		if r, _ := utf8.DecodeLastRuneInString(text[:s]); blocksPath(r) {
			return false
		}
	}
	if e < len(text) {
		if r, _ := utf8.DecodeRuneInString(text[e:]); blocksPath(r) {
			return false
		}
	}
	return true
}

// replaceStandalone is pat.subn(lambda _m: new, text) for the Python pattern
// `(?<![\w./-])<old>(?![\w./-])`: non-overlapping matches left to right, literal replacement.
// RE2 has no look-around, so the neighbours of every occurrence are tested by hand. An empty old
// matches at every position whose neighbours both stay outside the class.
func replaceStandalone(text, old, new string) (string, int) {
	var out strings.Builder
	n, last := 0, 0
	if old == "" {
		for i := 0; i <= len(text); {
			if standalone(text, i, i) {
				out.WriteString(text[last:i])
				out.WriteString(new)
				last = i
				n++
			}
			if i == len(text) {
				break
			}
			_, w := utf8.DecodeRuneInString(text[i:])
			i += w
		}
	} else {
		for from := 0; from <= len(text)-len(old); {
			k := strings.Index(text[from:], old)
			if k < 0 {
				break
			}
			s := from + k
			e := s + len(old)
			if standalone(text, s, e) {
				out.WriteString(text[last:s])
				out.WriteString(new)
				last, from = e, e
				n++
				continue
			}
			_, w := utf8.DecodeRuneInString(text[s:])
			from = s + w
		}
	}
	if n == 0 {
		return text, 0
	}
	out.WriteString(text[last:])
	return out.String(), n
}

// planRewritePath is Python rewrite_path: the literal old->new replace across the text files below
// scanRoot. It writes nothing and returns the number of files touched, the plan and the files
// that are not valid UTF-8.
func planRewritePath(scanRoot, old, new string) (touched int, plan []diffs.PlanEntry, skipped []string, err error) {
	skipped = []string{}
	catalogue.SortedWalk(scanRoot, func(dirpath string, dirnames, filenames []string) []string {
		if err != nil {
			return nil
		}
		for _, fn := range filenames {
			if !hasAnySuffix(fn, rewriteExts) {
				continue
			}
			ap := catalogue.Join(dirpath, fn)
			rel, rerr := filepath.Rel(scanRoot, ap)
			if rerr != nil {
				err = rerr
				return nil
			}
			rel = filepath.ToSlash(rel)
			text, ok, rerr := catalogue.ReadFileVerbatim(ap)
			if rerr != nil {
				err = rerr
				return nil
			}
			if !ok {
				skipped = append(skipped, rel)
				continue
			}
			if newText, n := replaceStandalone(text, old, new); n > 0 {
				touched++
				plan = append(plan, diffs.PlanEntry{Path: rel, Old: &text, New: &newText})
			}
		}
		return catalogue.PruneWalkDirs(dirnames)
	})
	return touched, plan, skipped, err
}

func hasAnySuffix(name string, suffixes []string) bool {
	for _, s := range suffixes {
		if strings.HasSuffix(name, s) {
			return true
		}
	}
	return false
}

// runRewritePath is Python cmd_rewrite_path.
func runRewritePath(root string, a *cli.Args) (any, error) {
	scanRoot := root
	if a.Has("scan_root") && a.String("scan_root") != "" {
		abs, err := catalogue.Abspath(a.String("scan_root"))
		if err != nil {
			return nil, err
		}
		scanRoot = abs
	}
	dry := a.Bool("check")
	touched, plan, skipped, err := planRewritePath(scanRoot, a.String("old"), a.String("new"))
	if err != nil {
		return nil, err
	}
	files := diffs.UnifiedDiffs(plan, nil)
	if !dry {
		if err := diffs.WritePlan(scanRoot, plan); err != nil {
			return nil, err
		}
	}
	if a.JSON {
		return envelope.O("applied", !dry, "files", diffs.JSONFiles(files), "skipped", skipped), nil
	}
	verb := "written"
	if dry {
		verb = "affected (dry-run)"
	}
	return nil, printFixReport(files, skipped, fmt.Sprintf("%d file(s) %s\n", touched, verb))
}

// registerRewritePath attaches rewrite-path and its completer.
func registerRewritePath(app *cli.App) {
	app.Attach("rewrite-path", cli.Spec{
		Args: []cli.Arg{
			{Dest: "old", Help: "literal path string to replace"},
			{Dest: "new", Help: "replacement path string"},
			{Flags: []string{"--scan-root"}, Help: "dir to scan (default: --root)"},
			{Flags: []string{"--check"}, Action: cli.StoreTrue, Help: "dry-run: report, write nothing"},
			cli.JSON(),
		},
		Handler: runRewritePath,
	})
	complete.Attach([]string{"rewrite-path"}, "scan_root", complete.Dirs)
}
