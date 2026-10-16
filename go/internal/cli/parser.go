package cli

import (
	"strings"
)

// actKind is the argparse action class of an argument.
type actKind uint8

const (
	kindStore actKind = iota
	kindStoreTrue
	kindAppend
	kindHelp
	kindParsers // the subparsers action: a command or verb name and the arguments it takes
)

// The nargs of an action. A count of zero or more is the number of values itself: 0 for a
// flag, N for nargs=N.
const (
	nOne      = -1 // nargs=None
	nOptional = -2 // "?"
	nStar     = -3 // "*"
	nPlus     = -4 // "+"
	nParser   = -5 // argparse.PARSER, "A..."
)

// action is one argument of a parser, resolved: argparse's Action.
type action struct {
	kind     actKind
	dest     string
	flags    []string
	nargs    int
	typ      Type
	choices  []string
	metavar  []string
	def      any
	required bool
	help     string
	sub      *subparsers
}

func (a *action) isOption() bool { return len(a.flags) > 0 }

// name is argparse's _get_action_name: how an error message calls the argument.
func (a *action) name() string {
	switch {
	case a.isOption():
		return strings.Join(a.flags, "/")
	case len(a.metavar) == 1:
		return a.metavar[0]
	case len(a.metavar) > 1 && (a.nargs == nStar && len(a.metavar) == 2 || a.nargs == nPlus):
		return a.metavar[0] + "[, " + a.metavar[1] + "]"
	case len(a.metavar) > 1:
		return strings.Join(a.metavar, ", ")
	}
	return a.dest
}

// subparsers is the choice of a verb table: the names that can follow, each with the line of the
// verb list, and the way to build the parser of one of them when it is chosen.
type subparsers struct {
	entries []subEntry
	build   func(name string) *parser
}

type subEntry struct {
	name, help string
	hidden     bool
}

// shown are the names the usage line, the verb list and the invalid-choice message mention.
func (s *subparsers) shown() []string {
	var names []string
	for _, e := range s.entries {
		if !e.hidden {
			names = append(names, e.name)
		}
	}
	return names
}

func (s *subparsers) has(name string) bool {
	for _, e := range s.entries {
		if e.name == name {
			return true
		}
	}
	return false
}

// group is a mutually exclusive group of options.
type group struct {
	required bool
	actions  []*action
}

// parser is one argparse.ArgumentParser: the top level, a command or a verb.
type parser struct {
	prog        string
	description string
	epilog      func() string // the text after the arguments, built when the help is
	raw         bool          // description and epilog keep their line breaks (RawDescriptionHelpFormatter)
	intermixed  bool          // positionals and options mix freely
	lenient     bool          // a command nobody attached: it swallows what it cannot parse
	negOptions  bool          // an option string looks like a negative number
	actions     []*action
	groups      []*group
	byFlag      map[string]*action
	flagOrder   []string
}

// newParser builds the parser of prog: -h/--help, then args in order, then the exclusive groups.
func newParser(prog, description string, args []Arg, exclusive []Exclusive) *parser {
	p := &parser{prog: prog, description: description, byFlag: map[string]*action{}}
	p.add(&action{kind: kindHelp, dest: "help", flags: []string{"-h", "--help"}, help: "show this help message and exit"})
	for _, arg := range args {
		p.add(newAction(arg))
	}
	for _, e := range exclusive {
		g := &group{required: e.Required}
		for _, dest := range e.Dests {
			g.actions = append(g.actions, p.byDest(dest))
		}
		p.groups = append(p.groups, g)
	}
	return p
}

func (p *parser) add(a *action) {
	p.actions = append(p.actions, a)
	for _, flag := range a.flags {
		p.byFlag[flag] = a
		p.flagOrder = append(p.flagOrder, flag)
		if isNegativeNumber(flag) {
			p.negOptions = true
		}
	}
}

func (p *parser) byDest(dest string) *action {
	for _, a := range p.actions {
		if a.dest == dest {
			return a
		}
	}
	return nil
}

// addSubparsers adds the subparsers action: the required choice of one verb or command.
func (p *parser) addSubparsers(dest string, metavar, help string, sub *subparsers) {
	a := &action{kind: kindParsers, dest: dest, nargs: nParser, required: true, help: help, sub: sub}
	if metavar != "" {
		a.metavar = []string{metavar}
	}
	p.add(a)
}

// newAction resolves one Arg: dest from the first long option, the nargs and the required flag
// of a positional from its count.
func newAction(arg Arg) *action {
	a := &action{
		dest: arg.Dest, flags: arg.Flags, typ: arg.Type, choices: arg.Choices,
		metavar: arg.Metavar, def: arg.Default, required: arg.Required, help: arg.Help,
	}
	if a.dest == "" {
		a.dest = destOf(arg.Flags)
	}
	switch arg.Action {
	case StoreTrue:
		a.kind, a.nargs, a.def = kindStoreTrue, 0, false
		return a
	case Append:
		a.kind = kindAppend
	}
	switch {
	case arg.Nargs == One:
		a.nargs = nOne
	case arg.Nargs == Optional:
		a.nargs = nOptional
	case arg.Nargs == ZeroOrMore:
		a.nargs = nStar
	case arg.Nargs == OneOrMore:
		a.nargs = nPlus
	default:
		a.nargs = int(arg.Nargs - OneOrMore)
	}
	if !a.isOption() {
		a.required = a.nargs != nOptional && a.nargs != nStar
	}
	return a
}

// destOf infers the dest of an option as argparse does: the first long option, else the first
// option, without its dashes and with underscores for the inner ones.
func destOf(flags []string) string {
	flag := flags[0]
	for _, f := range flags {
		if strings.HasPrefix(f, "--") {
			flag = f
			break
		}
	}
	return strings.ReplaceAll(strings.TrimLeft(flag, "-"), "-", "_")
}

// isNegativeNumber is argparse's _negative_number_matcher, the regex -\.?\d at the start.
func isNegativeNumber(s string) bool {
	if len(s) < 2 || s[0] != '-' {
		return false
	}
	s = s[1:]
	if s[0] == '.' {
		s = s[1:]
	}
	return s != "" && s[0] >= '0' && s[0] <= '9'
}
