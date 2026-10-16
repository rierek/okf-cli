// Package navigation is the read-only navigation commands: index, prime, read, toc, list, recent,
// visualize and refs (Python okf.navigation, okf.index, okf.prime, okf.recent).
package navigation

import (
	"bufio"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"slices"
	"strconv"
	"strings"
	"unicode/utf8"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/cli"
	"nas/volume1/data/git/okf-tools/go/internal/complete"
	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

// Register attaches the eight commands and the completers of their values.
func Register(app *cli.App) {
	app.Attach("index", cli.Spec{Args: indexArgs(), Handler: runIndex})
	app.Attach("prime", cli.Spec{Args: primeArgs(), Handler: func(root string, a *cli.Args) (any, error) {
		return runPrime(app, root, a)
	}})
	app.Attach("read", readSpec())
	app.Attach("toc", cli.Spec{Args: tocArgs(), Handler: runToc})
	app.Attach("list", cli.Spec{Args: []cli.Arg{cli.WhereArg(), cli.JSON()}, Handler: runList})
	app.Attach("recent", cli.Spec{Args: recentArgs(), Handler: runRecent})
	app.Attach("visualize", cli.Spec{Args: visualizeArgs(), Handler: runVisualize})
	app.Attach("refs", refsSpec())

	complete.Attach([]string{"index"}, "bundle", complete.Bundles)
	complete.Attach([]string{"read"}, "path", complete.Concepts)
	complete.Attach([]string{"toc"}, "path", complete.Concepts)
	complete.Attach([]string{"refs"}, "path", complete.ConceptFiles)
	complete.Attach([]string{"refs"}, "scan_root", complete.Dirs)
	complete.Attach([]string{"visualize"}, "bundle", complete.Bundles)
	complete.Attach([]string{"visualize"}, "out", complete.Files)
}

// newOut is the buffered text output of a handler; flush it before returning.
func newOut() *bufio.Writer { return bufio.NewWriter(os.Stdout) }

// printf is fmt.Fprintf on the handler's output.
func printf(w io.Writer, format string, a ...any) { fmt.Fprintf(w, format, a...) }

// conceptPath is `<bundle>/<concept-id>` of an absolute concept file, as find and list print it:
// the path relative to root without the `.md`.
func conceptPath(root, ap string) string {
	rel, err := filepath.Rel(root, ap)
	if err != nil {
		rel = ap
	}
	return strings.TrimSuffix(filepath.ToSlash(rel), ".md")
}

// stem is os.path.basename(ap)[:-3]: the base name without its last three characters.
func stem(ap string) string {
	base := ap[strings.LastIndexByte(ap, '/')+1:]
	for n := 0; n < 3 && base != ""; n++ {
		_, size := utf8.DecodeLastRuneInString(base)
		base = base[:len(base)-size]
	}
	return base
}

// charLen is Python len(s): the number of code points.
func charLen(s string) int { return utf8.RuneCountInString(s) }

// ljust is str.ljust(width).
func ljust(s string, width int) string {
	if n := charLen(s); n < width {
		return s + strings.Repeat(" ", width-n)
	}
	return s
}

// count is the Python _count(minimum) argument type: an int of at least minimum.
func count(minimum int) cli.Type {
	return func(raw string) (any, string) {
		n := minimum - 1
		if v, msg := cli.Int(raw); msg == "" {
			n = v.(int)
		}
		if n < minimum {
			return nil, pytext.ReprStr(raw) + " is not an integer of at least " + strconv.Itoa(minimum)
		}
		return n, ""
	}
}

// asciiJSON is json.dumps's ensure_ascii pass over text Marshal wrote with ensure_ascii off: every
// character above U+007F becomes \uXXXX (a surrogate pair above U+FFFF).
func asciiJSON(s string) string {
	var b strings.Builder
	for _, r := range s {
		switch {
		case r < 0x80:
			b.WriteRune(r)
		case r > 0xFFFF:
			r -= 0x10000
			fmt.Fprintf(&b, "\\u%04x\\u%04x", 0xD800+(r>>10), 0xDC00+(r&0x3FF))
		default:
			fmt.Fprintf(&b, "\\u%04x", r)
		}
	}
	return b.String()
}

type concept struct{ cid, ap string }

// sortedConcepts is Python sorted(iter_concepts(bp)): the concepts of a bundle by concept id.
func sortedConcepts(bp string) []concept {
	var cs []concept
	for cid, ap := range catalogue.IterConcepts(bp, true) {
		cs = append(cs, concept{cid, ap})
	}
	slices.SortFunc(cs, func(a, b concept) int { return strings.Compare(a.cid, b.cid) })
	return cs
}
