// Package ctx is the `ctx` command: curated, ordered reading lists ("context bundles") per topic,
// stored as _ctx/<slug>.md (Python okf.ctx). It holds the 14 verbs, the `ctx <slug>` shorthand and
// save, the one writer of a ctx file. The ctx file model (parse, render, findings, path
// normalisation) is package ctxfile, the move core of `rename` is package move, the index refresh
// is package indexwrite and the finding report is package check; this package keeps no copy of
// them.
//
// Every refusal is raised before the first change a call makes on disk (directory creation, write,
// move, delete, index refresh); `ctx edit` is the exception only in that the editor's own edits
// are the user's.
package ctx

import (
	"fmt"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/cli"
	"nas/volume1/data/git/okf-tools/go/internal/complete"
	"nas/volume1/data/git/okf-tools/go/internal/ctxfile"
	"nas/volume1/data/git/okf-tools/go/internal/okferr"
)

// handlers is Python CTX_DISPATCH: one handler per verb.
var handlers = map[string]cli.Handler{
	"add": runAdd, "check": runCheck, "create": runCreate, "drop": runDrop, "edit": runEdit,
	"inbound": runInbound, "list": runList, "move": runMove, "outbound": runOutbound,
	"read": runRead, "remove": runRemove, "rename": runRename, "show": runShow, "toc": runToc,
}

// run is Python cmd_ctx: the handler of the verb the command line named.
func run(root string, a *cli.Args) (any, error) { return handlers[a.Path[1]](root, a) }

// Register attaches `ctx` with its 14 verbs and wires the completers of their arguments.
func Register(app *cli.App) {
	app.Attach("ctx", cli.Spec{
		Verbs:       verbs(),
		VerbMetavar: "VERB",
		VerbHelp:    "ctx verb; `ctx <slug>` is short for `ctx show <slug>`",
		Intermixed:  true,
		Handler:     run,
	})
	for _, verb := range []string{"add", "check", "create", "drop", "edit", "inbound", "move",
		"outbound", "read", "remove", "show", "toc"} {
		complete.Attach([]string{"ctx", verb}, "slug", complete.CtxSlugs)
	}
	complete.Attach([]string{"ctx", "rename"}, "old", complete.CtxSlugs)
	complete.Attach([]string{"ctx", "add"}, "path", complete.Concepts)
	complete.Attach([]string{"ctx", "create"}, "paths", complete.Concepts)
	complete.Attach([]string{"ctx", "create"}, "import_file", complete.Files)
	complete.Attach([]string{"ctx", "drop"}, "path", complete.Files)
	complete.Attach([]string{"ctx", "move"}, "path", complete.Files)
	complete.Attach([]string{"ctx", "list"}, "for_path", complete.Files)
}

// verbs is Python add_ctx_parser: the verbs in the order of the verb list of `ctx --help`.
func verbs() []cli.Verb {
	slug := cli.Arg{Dest: "slug", Help: "ctx slug"}
	entryPath := func(help string) cli.Arg {
		return cli.Arg{Dest: "path", Metavar: []string{"PATH"}, Help: help}
	}
	file := cli.Arg{Flags: []string{"--file"}, Metavar: []string{"X"},
		Help: "only the entry whose title, path or stem equals X (case-insensitive)"}
	internal := cli.Arg{Flags: []string{"--include-internal"}, Action: cli.StoreTrue,
		Help: "also list links between members of the ctx"}
	return []cli.Verb{
		{
			Name: "add", Help: "add one entry to a ctx bundle",
			Description: "add PATH as required entry (default: last position) or as reference entry",
			Args: []cli.Arg{
				slug,
				entryPath("concept or file path"),
				{Flags: []string{"--pos"}, Type: cli.Int, Help: "required position (clamped to 1..n+1)"},
				{Flags: []string{"--mode"}, Choices: ctxfile.CtxModes, Default: "pflicht", Help: "entry mode"},
				{Flags: []string{"--comment"}, Default: "", Help: "entry comment"},
				cli.JSON(),
			},
		},
		{
			Name: "check", Help: "validate ctx bundles",
			Description: "report ctx errors and warnings in the `check` line format; exit 1 on any error",
			Args: []cli.Arg{
				{Dest: "slug", Nargs: cli.Optional, Help: "ctx slug (default: all)"},
				{Flags: []string{"--stale"}, Action: cli.StoreTrue,
					Help: "warn for every member modified after the ctx file"},
				cli.JSON(),
			},
		},
		{
			Name: "create", Help: "create a ctx bundle from paths and/or an import file",
			Description: "create _ctx/<slug>.md; every path becomes a required entry, " +
				"ordered alphabetically by normalised path",
			Args: []cli.Arg{
				{Dest: "slug", Help: "new ctx slug: lowercase letters, digits, hyphens"},
				{Dest: "paths", Nargs: cli.ZeroOrMore, Metavar: []string{"PATH"},
					Help: "concept or file path to add as required entry"},
				{Dest: "import_file", Flags: []string{"--import"}, Metavar: []string{"FILE"},
					Help: "read one path per line (blank and # lines skipped, " +
						"text after a TAB is the entry comment)"},
				{Flags: []string{"--description"}, Help: "one-line description of the bundle"},
				cli.JSON(),
			},
		},
		{
			Name: "drop", Help: "remove one entry from a ctx bundle",
			Description: "remove an entry (also when its file is gone); required positions are " +
				"renumbered 1..n",
			Args: []cli.Arg{slug, entryPath("entry path"), cli.JSON()},
		},
		{
			Name: "edit", Help: "open a ctx bundle in $VISUAL/$EDITOR/vi and validate it",
			Description: "open _ctx/<slug>.md in $VISUAL, else $EDITOR, else vi; afterwards refresh " +
				"the _ctx index and run `ctx check` on the file; exit 1 on errors",
			Args: []cli.Arg{slug, cli.JSON()},
		},
		{
			Name: "list", Help: "list ctx bundles with entry and required counts",
			Description: "list ctx bundles: slug, description, entry and required counts",
			Args: []cli.Arg{
				{Dest: "for_path", Flags: []string{"--for"}, Metavar: []string{"PATH"},
					Help: "only bundles whose entries contain PATH (also when the file is gone)"},
				cli.JSON(),
			},
		},
		{
			Name: "move", Help: "reorder an entry or change its mode",
			Description: "move an entry to required position N (--pos) and/or change its mode; " +
				"required positions are renumbered 1..n",
			Args: []cli.Arg{
				slug,
				entryPath("entry path"),
				{Flags: []string{"--pos"}, Type: cli.Int, Help: "required position (clamped to 1..n)"},
				{Flags: []string{"--mode"}, Choices: ctxfile.CtxModes, Help: "new mode"},
				cli.JSON(),
			},
		},
		{
			Name: "outbound", Help: "list the links each entry points to",
			Description: "per entry, markdown link targets; missing targets are marked [missing], " +
				"dead entries [DEAD]; other members are excluded unless --include-internal",
			Args: []cli.Arg{slug, file, internal, cli.JSON()},
		},
		{
			Name: "inbound", Help: "list the files that link to each entry",
			Description: "per entry, the files linking to it; other members are excluded unless " +
				"--include-internal; files under _ctx/ are always excluded",
			Args: []cli.Arg{slug, file, internal, cli.JSON()},
		},
		{
			Name: "read", Help: "print the full content of every required entry",
			Description: "print every required entry of a ctx in position order, each after a " +
				"`===== i/p <abspath> =====` separator; reference entries are not printed; " +
				"exit 1 when a required entry is dead",
			Args: []cli.Arg{slug, cli.JSON()},
		},
		{
			Name: "remove", Help: "delete a ctx bundle and list files that still link to it",
			Description: "delete _ctx/<slug>.md, refresh the _ctx index and list every file " +
				"that still links to the removed ctx",
			Args: []cli.Arg{slug, cli.JSON()},
		},
		{
			Name: "rename", Help: "rename a ctx bundle and rewrite inbound links",
			Description: "move _ctx/<old>.md to _ctx/<new>.md; inbound links and the _ctx index follow",
			Args: []cli.Arg{
				{Dest: "old", Help: "current ctx slug"},
				{Dest: "new", Help: "new ctx slug: lowercase letters, digits, hyphens"},
				cli.JSON(),
			},
		},
		{
			Name: "show", Help: "list a ctx in reading order with live metadata and token estimates",
			Description: "list the required entries in reading order, then the reference entries; " +
				"`ctx <slug>` is short for `ctx show <slug>`; exit 1 when an entry is dead",
			Args: []cli.Arg{slug, cli.JSON()},
		},
		{
			Name: "toc", Help: "print the headings of every entry",
			Description: "print per entry an H1 with the entry path, then the member's headings " +
				"demoted by one level; dead entries are marked [DEAD]",
			Args: []cli.Arg{
				slug,
				{Flags: []string{"--depth"}, Type: cli.Int, Default: 0, Metavar: []string{"N"},
					Help: "only headings of original level <= N (default 0 = all)"},
				cli.JSON(),
			},
		},
	}
}

// ctxRel is the catalogue-relative path of the file of a ctx, `_ctx/<slug>.md`.
func ctxRel(slug string) string { return catalogue.CtxDir + "/" + slug + ".md" }

// die is Python _ctx_die: a refusal with the message prefix `ctx: `.
func die(kind okferr.Kind, format string, args ...any) error {
	return okferr.New(kind, "ctx: "+fmt.Sprintf(format, args...))
}
