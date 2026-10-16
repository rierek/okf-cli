// Command okf is the Go port of the okf CLI: navigation, search and maintenance for an OKF
// Knowledge Catalogue, one static executable without a Python runtime.
//
// Layout (binding for every command work package): the module is `go/` with its own go.mod; this
// package is the entry point and the one place that wires things together; the shared core lives in
// the packages under go/internal (okferr, pytext, frontmatter, catalogue, envelope, stdio, cli, where,
// spec, history, linkscan, sqlstore, tagvec, complete); each command owns one package under go/internal with
// one Register(app *cli.App) function. A new command package adds ONE entry to `commands` below,
// the mirror of Python's COMMAND_MODULES; there is no discovery.
package main

import (
	"fmt"
	"os"

	"nas/volume1/data/git/okf-tools/go/internal/buildtagvec"
	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/check"
	"nas/volume1/data/git/okf-tools/go/internal/cli"
	"nas/volume1/data/git/okf-tools/go/internal/complete"
	"nas/volume1/data/git/okf-tools/go/internal/ctx"
	"nas/volume1/data/git/okf-tools/go/internal/envelope"
	"nas/volume1/data/git/okf-tools/go/internal/find"
	"nas/volume1/data/git/okf-tools/go/internal/fts"
	"nas/volume1/data/git/okf-tools/go/internal/indexwrite"
	"nas/volume1/data/git/okf-tools/go/internal/info"
	"nas/volume1/data/git/okf-tools/go/internal/install"
	"nas/volume1/data/git/okf-tools/go/internal/move"
	"nas/volume1/data/git/okf-tools/go/internal/navigation"
	"nas/volume1/data/git/okf-tools/go/internal/okferr"
	"nas/volume1/data/git/okf-tools/go/internal/rewrite"
	"nas/volume1/data/git/okf-tools/go/internal/semantic"
	"nas/volume1/data/git/okf-tools/go/internal/stdio"
	"nas/volume1/data/git/okf-tools/go/internal/tagwrite"
	"nas/volume1/data/git/okf-tools/go/internal/wikisync"
)

// commands lists the command packages, each exporting Register(*cli.App). A directory command whose
// package is not listed answers with a "not yet ported" error.
var commands = []func(*cli.App){
	check.Register,
	ctx.Register,
	buildtagvec.Register,
	find.Register,
	fts.Register,
	indexwrite.Register,
	info.Register,
	install.Register,
	move.Register,
	rewrite.Register,
	semantic.Register,
	navigation.Register,
	wikisync.Register,
	tagwrite.Register,
}

// main makes a broken pipe an error of the write (stdio.Init) and ends with the status that takes
// a failed write of stdout into account (stdio.Exit).
func main() {
	stdio.Init()
	os.Exit(stdio.Exit(run(os.Args[1:])))
}

// run parses argv, dispatches and returns the process exit code (Python main()).
func run(argv []string) int {
	app := cli.NewApp()
	for _, register := range commands {
		register(app)
	}
	// Steps that rewrite or answer before the parse are wired here, in this order: the shell
	// completion protocol (_ARGCOMPLETE), which sees the command line as typed, and the
	// `ctx <slug>` shorthand.
	if complete.Requested() {
		return complete.Run(app)
	}
	parsed, err := app.Parse(ctx.Shorthand(argv))
	switch e := err.(type) {
	case nil:
	case *cli.HelpOutput:
		stdio.Print(e.Text)
		return 0
	case *cli.UsageError:
		fmt.Fprint(os.Stderr, e.Text)
		return 2
	default:
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	call := func() (any, error) { return dispatch(parsed) }
	if parsed.Args.JSON {
		return envelope.Run(parsed.Args.Name(), call)
	}
	if _, err := call(); err != nil {
		failure := okferr.As(err)
		if failure.Message != "" {
			fmt.Fprintln(os.Stderr, failure.Message)
		}
		return failure.Code()
	}
	return 0
}

// dispatch is the call proper (Python _dispatch): the catalogue-free commands run without a root;
// every other command gets the resolved root after the root checks and the marker note.
func dispatch(p *cli.Parsed) (any, error) {
	if p.Entry.CatalogueFree {
		return p.Handler("", p.Args)
	}
	root, err := catalogue.CatalogueRoot(p.Args.Root, p.Args.UseGlobal)
	if err != nil {
		return nil, err
	}
	if root == "" {
		return nil, okferr.Newf(okferr.NotFound,
			"ERROR: no catalogue found in cwd or its ancestors and no root in %s; pass --root <path>",
			catalogue.UserConfigPath())
	}
	if !catalogue.RealFS.IsDir(root) {
		return nil, okferr.Newf(okferr.NotFound, "ERROR: root not found: %s (pass --root <path>)", root)
	}
	if p.Args.Root != "" && !catalogue.HasMarker(root) {
		// An explicit --root keeps working with no marker, so this never blocks. But every write
		// command emits paths as "/" + relpath(dest, root): a --root one level above the real
		// catalogue silently prefixes every emitted link with the extra segment.
		envelope.Note(fmt.Sprintf("--root %s carries no catalogue marker (.okf.toml or SPEC.md+TYPES.md) "+
			"— if this is not the real catalogue root, write commands will silently emit wrong paths", root))
	}
	return p.Handler(root, p.Args)
}
