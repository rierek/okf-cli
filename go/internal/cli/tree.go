package cli

import (
	"slices"
	"strconv"
)

// Tree is the read-only view of the whole command line, for the shell completion: the global
// options and every command with its arguments and verbs. The Python parser is the model:
// every parser has -h/--help, which is listed with the kind "help".
type Tree struct {
	// Options are the global options: -h/--help, --root and --global.
	Options []ArgInfo
	// Commands are all directory commands in name order, hidden ones included (check Hidden).
	Commands []CommandInfo
}

// CommandInfo is one command of the Tree, or one verb of a command.
type CommandInfo struct {
	Name string
	// Group and CatalogueFree come from the directory entry; they are empty for a verb.
	Group         string
	CatalogueFree bool
	// Summary is the line of the command list (of the verb list for a verb); Description is the
	// text above the options of its --help, which is the summary for a command.
	Summary, Description string
	// Hidden is the directory flag; a verb is never hidden.
	Hidden bool
	// Args are the arguments of the command itself, -h/--help first.
	Args []ArgInfo
	// Verbs are the verbs of a verb table in the order of the verb list; none for a plain command.
	Verbs []CommandInfo
}

// ArgInfo is one argument as the completion needs it.
type ArgInfo struct {
	// Dest names the value. Flags are the option strings; a positional has none.
	Dest  string
	Flags []string
	// Positional is true for an argument without option strings.
	Positional bool
	// Nargs is "" for exactly one value (argparse nargs=None), "?", "*", "+" or the number of
	// values: "0" for a flag, "2" for two.
	Nargs string
	// Choices are the allowed values, nil when any value is.
	Choices []string
	// Kind is the action: "store", "store_true", "append" or "help".
	Kind string
	// Metavar is the name or names shown for the values; nil when the argument shows its dest
	// or its choices.
	Metavar  []string
	Help     string
	Required bool
}

// Tree builds the command tree from what is attached now.
func (a *App) Tree() *Tree {
	t := &Tree{Options: argInfos(a.topParser())}
	for _, e := range a.entries {
		p := a.commandParser(e.Name)
		c := CommandInfo{
			Name: e.Name, Group: e.Group, CatalogueFree: e.CatalogueFree, Summary: e.Summary,
			Description: p.description, Hidden: e.Hidden, Args: argInfos(p),
		}
		if i := slices.IndexFunc(p.actions, func(act *action) bool { return act.kind == kindParsers }); i >= 0 {
			sub := p.actions[i].sub
			for _, v := range sub.entries {
				vp := sub.build(v.name)
				c.Verbs = append(c.Verbs, CommandInfo{Name: v.name, Summary: v.help, Description: vp.description, Args: argInfos(vp)})
			}
		}
		t.Commands = append(t.Commands, c)
	}
	return t
}

// argInfos lists the arguments of a parser, leaving out the subparsers action.
func argInfos(p *parser) []ArgInfo {
	var infos []ArgInfo
	for _, act := range p.actions {
		if act.kind != kindParsers {
			infos = append(infos, argInfo(act))
		}
	}
	return infos
}

func argInfo(a *action) ArgInfo {
	info := ArgInfo{
		Dest: a.dest, Flags: slices.Clone(a.flags), Positional: !a.isOption(), Choices: slices.Clone(a.choices),
		Metavar: slices.Clone(a.metavar), Help: a.help, Required: a.required,
	}
	switch a.nargs {
	case nOne:
	case nOptional:
		info.Nargs = "?"
	case nStar:
		info.Nargs = "*"
	case nPlus:
		info.Nargs = "+"
	default:
		info.Nargs = strconv.Itoa(a.nargs)
	}
	switch a.kind {
	case kindStore:
		info.Kind = "store"
	case kindStoreTrue:
		info.Kind = "store_true"
	case kindAppend:
		info.Kind = "append"
	case kindHelp:
		info.Kind = "help"
	}
	return info
}
