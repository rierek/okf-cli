// Package cli is the command line of the okf binary: the command directory, the argument parser,
// the help texts and the introspection that the shell completion reads. The parser reproduces
// Python's argparse as the okf CLI used it (Python 3.14): the same abbreviations of long
// options, "--opt=value", "--", intermixed positionals, negative numbers as values, the same
// usage errors and the same --help layout byte for byte, for any COLUMNS.
//
// # The directory
//
// directory.go lists every command with its group, summary, Hidden flag and CatalogueFree
// flag. A command that is only in Go is one more line there; Hidden keeps it callable but out
// of the overview, the usage line, the command list and the invalid-choice message.
//
// # Attaching a command
//
// A command package exports one function, takes the App and attaches the Spec of each command
// it owns, by name. There are no globals and no init functions. Attaching to a name that is not
// in the directory, attaching twice and a malformed Spec panic, which stops the binary at
// startup. A directory command nobody attached still parses (it swallows its arguments) and
// answers with an okferr.Internal error that names it as not yet ported.
//
//	func Register(app *cli.App) {
//		app.Attach("read", cli.Spec{
//			Args: []cli.Arg{
//				{Dest: "path", Help: "<bundle>/<concept-id> of the page to print"},
//				{Flags: []string{"--section"}, Metavar: []string{"HEADING"}, Help: "print only this section"},
//				{Flags: []string{"--body-only"}, Action: cli.StoreTrue, Help: "print everything after the frontmatter"},
//				{Flags: []string{"--follow"}, Type: cli.Int, Metavar: []string{"N"}, Help: "also print linked pages"},
//				cli.JSON(),
//			},
//			Exclusive: []cli.Exclusive{{Dests: []string{"section", "body_only"}}},
//			Handler:   func(root string, a *cli.Args) (any, error) { return read(root, a) },
//		})
//	}
//
// The dest of an option without Dest comes from its first long option ("--body-only" gives
// "body_only"), as in argparse. Every command declares --json with cli.JSON, which carries the
// help text of Python's _add_output. Positionals take the count from Arg.Nargs: One (the
// default), Optional, ZeroOrMore, OneOrMore or Exactly(n). A command that needs the App itself,
// such as prime for the overview and the help of find, captures it in its Handler.
//
// A command with sub-verbs (ctx, registry) lists them in Spec.Verbs and has one Handler for
// all of them, which switches on Args.Path; the verb is stored under the dest "<command>_verb"
// and Args.Path is ["ctx", "show"]. Spec.Intermixed lets the arguments of its verbs mix
// positionals and options. Spec.Epilog and Spec.Raw give the epilog of the command help and
// keep the line breaks of its texts.
//
// # Handlers
//
// A Handler reads the parsed arguments by dest and prints its own text through package stdio in text
// mode; in --json mode (a.JSON) it prints nothing and returns the data of the envelope:
//
//	func read(root string, a *cli.Args) (any, error) {
//		path, follow := a.String("path"), a.Int("follow")
//		if a.Has("section") { /* a.String("section") */ }
//		if a.JSON {
//			return map[string]any{"path": path}, nil
//		}
//		stdio.Println(path)
//		return nil, nil
//	}
//
// String, Bool, Int, Float, Strings and StringLists read a value as the Type of its argument
// made it and give the zero value when it is absent; Has tells absent from present. An accessor
// that does not fit the argument panics, a programming error.
//
// # Running
//
// The entry point creates the App, lets every command package register, runs Parse and
// dispatches. Steps that rewrite the arguments before parsing (the "ctx <slug>" shorthand) run
// before Parse in the entry point.
//
//	app := cli.NewApp()
//	read.Register(app)
//	parsed, err := app.Parse(os.Args[1:])
//	switch e := err.(type) {
//	case nil:
//	case *cli.HelpOutput: // -h: print to stdout, exit 0
//	case *cli.UsageError: // an argument error: print to stderr, exit 2
//	}
//	root := ""
//	if !parsed.Entry.CatalogueFree { /* resolve parsed.Args.Root, parsed.Args.UseGlobal */ }
//	data, err := parsed.Handler(root, parsed.Args)
//
// # Help, overview, introspection
//
// The help width is $COLUMNS, else the terminal on stdout, else 80, minus two, as
// shutil.get_terminal_size gives it to argparse. RenderOverview renders the purpose-grouped
// command overview (the epilog of okf --help and the command section of prime); CommandHelp and
// CommandUsage give the help and usage text of one command. Tree is the read-only view of the
// whole command line (global options, commands, verbs, arguments) for the shell completion.
package cli
