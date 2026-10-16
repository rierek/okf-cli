package cli

import (
	"fmt"
	"slices"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/okferr"
)

// Entry is one command of the directory.
type Entry struct {
	// Name is the command as typed after okf.
	Name string
	// Group is the purpose that the overview files it under: navigation, search, tags or
	// maintenance.
	Group string
	// Summary is one line: its help in the command list and the description of
	// okf <name> --help.
	Summary string
	// Hidden keeps the command callable but out of the overview, the usage line, the command
	// list and the invalid-choice message of the top level.
	Hidden bool
	// CatalogueFree makes dispatch run the handler without resolving a catalogue root.
	CatalogueFree bool
}

// The help texts of the global options (cli/okf/parser.py).
const (
	rootHelp   = "catalogue root (default: the nearest catalogue above cwd, else root in ~/.config/okf/config.toml; hard-fails if neither)"
	globalHelp = "use the root in ~/.config/okf/config.toml, even when a catalogue lies above cwd (not with --root)"
)

// overviewWidth is the wrap column of the overview in okf --help.
const overviewWidth = 96

// App is the okf command line: the command directory and what the command packages attached
// to its entries. NewApp makes one; the packages attach to it at startup, then Parse runs.
type App struct {
	entries []Entry
	specs   map[string]Spec
}

// NewApp returns an App over the command directory with nothing attached. It panics on a
// directory entry without a name, with a group that the overview does not know or with a
// name that another entry has.
func NewApp() *App {
	entries := slices.Clone(directory)
	slices.SortFunc(entries, func(a, b Entry) int { return strings.Compare(a.Name, b.Name) })
	for i, e := range entries {
		if e.Name == "" || !slices.Contains(groupOrder[:], e.Group) || i > 0 && entries[i-1].Name == e.Name {
			panic(fmt.Sprintf("cli: bad directory entry %q (group %q)", e.Name, e.Group))
		}
	}
	return &App{entries: entries, specs: map[string]Spec{}}
}

// Directory is the command directory in name order, hidden entries included.
func (a *App) Directory() []Entry { return slices.Clone(a.entries) }

// Attach gives the directory command name its arguments, verbs and handler. It panics, which
// stops the binary at startup, when name is not in the directory, when the command already has
// a spec or when the spec is malformed.
func (a *App) Attach(name string, s Spec) {
	if _, ok := a.entry(name); !ok {
		panic(fmt.Sprintf("cli: attach to %q: not in the command directory", name))
	}
	if _, ok := a.specs[name]; ok {
		panic(fmt.Sprintf("cli: command %q attached twice", name))
	}
	validate(name, s)
	a.specs[name] = s
}

func (a *App) entry(name string) (Entry, bool) {
	i, ok := slices.BinarySearchFunc(a.entries, name, func(e Entry, name string) int { return strings.Compare(e.Name, name) })
	if !ok {
		return Entry{}, false
	}
	return a.entries[i], true
}

// Parse parses the command line (os.Args[1:]) as the Python argparse parser of okf does. On
// success it names the command with its arguments and handler. A -h/--help request returns a
// *HelpOutput, an argument error a *UsageError; both end the run, see their documentation.
func (a *App) Parse(argv []string) (*Parsed, error) {
	top := a.topParser()
	ns, extras, err := top.parseKnown(argv)
	if err != nil {
		return nil, err
	}
	if len(extras) > 0 {
		return nil, top.usageError("unrecognized arguments: " + strings.Join(extras, " "))
	}
	name, _ := ns["cmd"].(string)
	entry, _ := a.entry(name)
	args := &Args{Path: []string{name}, vals: ns}
	if verb, _ := ns[name+"_verb"].(string); verb != "" {
		args.Path = append(args.Path, verb)
	}
	args.Root, _ = ns["root"].(string)
	args.UseGlobal, _ = ns["use_global"].(bool)
	args.JSON, _ = ns["json"].(bool)
	handler := a.specs[name].Handler
	if handler == nil {
		handler = func(string, *Args) (any, error) {
			return nil, okferr.Newf(okferr.Internal, "ERROR: `%s` is not yet ported to the Go binary", name)
		}
	}
	return &Parsed{Args: args, Entry: entry, Handler: handler}, nil
}

// CommandUsage is the usage text of the command path, as Python's format_usage() of its parser
// gives it at the current terminal width: CommandUsage("find"), CommandUsage("ctx", "show"),
// CommandUsage() for okf itself. prime embeds it for find. It panics for a path that is no command.
func (a *App) CommandUsage(path ...string) string { return a.parserAt(path).formatUsage() }

// CommandHelp is the full --help text of the command path, as Python's format_help() gives it.
func (a *App) CommandHelp(path ...string) string { return a.parserAt(path).formatHelp() }

// parserAt builds the parser of okf (no path), of a command, or of one verb of a command.
func (a *App) parserAt(path []string) *parser {
	if len(path) == 0 {
		return a.topParser()
	}
	if _, ok := a.entry(path[0]); !ok || len(path) > 2 {
		panic(fmt.Sprintf("cli: no command %q", strings.Join(path, " ")))
	}
	p := a.commandParser(path[0])
	if len(path) == 1 {
		return p
	}
	if i := slices.IndexFunc(p.actions, func(act *action) bool { return act.kind == kindParsers && act.sub.has(path[1]) }); i >= 0 {
		return p.actions[i].sub.build(path[1])
	}
	panic(fmt.Sprintf("cli: no command %q", strings.Join(path, " ")))
}

// topParser is the parser of okf itself: --root, --global and the command to run.
func (a *App) topParser() *parser {
	p := newParser("okf", topDescription, []Arg{
		{Flags: []string{"--root"}, Help: rootHelp},
		{Flags: []string{"--global"}, Dest: "use_global", Action: StoreTrue, Help: globalHelp},
	}, nil)
	p.raw = true
	p.epilog = func() string { return RenderOverview(a.entries, overviewWidth, true) }
	sub := &subparsers{build: a.commandParser}
	for _, e := range a.entries {
		sub.entries = append(sub.entries, subEntry{name: e.Name, help: e.Summary, hidden: e.Hidden})
	}
	p.addSubparsers("cmd", "", "", sub)
	return p
}

// commandParser is the parser of one command; a command nobody attached takes anything and
// leaves the complaint to its handler.
func (a *App) commandParser(name string) *parser {
	e, _ := a.entry(name)
	spec, attached := a.specs[name]
	p := newParser("okf "+name, e.Summary, spec.Args, spec.Exclusive)
	p.lenient = !attached
	p.raw = spec.Raw
	if spec.Epilog != "" {
		p.epilog = func() string { return spec.Epilog }
	}
	if len(spec.Verbs) == 0 {
		return p
	}
	sub := &subparsers{build: func(verb string) *parser {
		i := slices.IndexFunc(spec.Verbs, func(v Verb) bool { return v.Name == verb })
		v := spec.Verbs[i]
		vp := newParser(p.prog+" "+verb, v.Description, v.Args, v.Exclusive)
		vp.intermixed = spec.Intermixed
		return vp
	}}
	for _, v := range spec.Verbs {
		sub.entries = append(sub.entries, subEntry{name: v.Name, help: v.Help})
	}
	p.addSubparsers(name+"_verb", spec.VerbMetavar, spec.VerbHelp, sub)
	return p
}
