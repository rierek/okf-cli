package cli

// Handler runs one command. root is the resolved catalogue root ("" for a catalogue-free
// command). In text mode the handler prints its own output to os.Stdout and returns nil data;
// in --json mode (a.JSON) it prints nothing and returns the envelope data. A returned error is
// an *okferr.Error or any other error, which counts as internal.
type Handler func(root string, a *Args) (any, error)

// Spec is everything a command package attaches to its directory entry: the arguments, the
// optional sub-verbs and the handler. The summary and group come from the directory.
type Spec struct {
	// Args are the positionals and options of the command, in registration order.
	Args []Arg
	// Exclusive lists the groups of Args of which at most one may be given.
	Exclusive []Exclusive
	// Verbs makes the command a verb table (ctx, registry): the first argument after the
	// command names one verb, which has its own arguments. The verb is stored under the dest
	// "<command>_verb" and is required.
	Verbs []Verb
	// VerbMetavar names the verb in usage lines and errors; empty shows the {a,b,...} list.
	VerbMetavar string
	// VerbHelp is the help line of the verb list in the command's --help.
	VerbHelp string
	// Epilog is the text after the options in the command's --help; empty for none.
	Epilog string
	// Raw keeps the line breaks of the summary and of the epilog in --help instead of wrapping
	// them (argparse RawDescriptionHelpFormatter).
	Raw bool
	// Intermixed lets the arguments of every verb mix positionals and options freely
	// (argparse parse_known_intermixed_args).
	Intermixed bool
	// Handler runs the command; it is required.
	Handler Handler
}

// Verb is one sub-command of a verb table.
type Verb struct {
	Name string
	// Help is the line of the verb list; Description is the text above the options of
	// okf <command> <verb> --help.
	Help, Description string
	Args              []Arg
	Exclusive         []Exclusive
}

// Exclusive is a mutually exclusive group: at most one of the named options may be given, or
// exactly one when Required is set.
type Exclusive struct {
	Required bool
	// Dests names the options of the group, in usage order.
	Dests []string
}

// Arg is one positional or option. The zero Action, Nargs and Type give the common case of
// argparse: one string value.
type Arg struct {
	// Dest names the value; an option without Dest takes it from its first long option
	// ("--scan-root" gives "scan_root").
	Dest string
	// Flags are the option strings ("--limit", "-n"); a positional has none.
	Flags []string
	// Action says what the argument does with its values.
	Action Action
	// Nargs says how many values the argument takes; ignored for a flag.
	Nargs Nargs
	// Type converts each value; nil keeps the string.
	Type Type
	// Choices restricts each value to these strings.
	Choices []string
	// Metavar names the values in usage and help: one name, or one per value.
	Metavar []string
	// Default is the value when the argument is absent; nil is Python's None.
	Default any
	// Required makes an absent option an error (a positional is required by its Nargs).
	Required bool
	// Help is the help text, wrapped by the formatter.
	Help string
}

// Action is the argparse action of an argument.
type Action uint8

// The actions the okf parsers use.
const (
	// Store keeps the converted value; with Nargs other than One it keeps a list.
	Store Action = iota
	// StoreTrue is a flag: its dest is true when the option is present, false otherwise.
	StoreTrue
	// Append collects one value (or list of values) per occurrence of the option.
	Append
)

// Nargs says how many values an argument takes. The zero value is exactly one, stored as a scalar.
type Nargs int

// The counts of argparse.
const (
	// One is nargs=None: exactly one value.
	One Nargs = iota
	// Optional is nargs="?": zero or one value.
	Optional
	// ZeroOrMore is nargs="*": any number of values.
	ZeroOrMore
	// OneOrMore is nargs="+": at least one value.
	OneOrMore
)

// Exactly is nargs=n for n >= 1: exactly n values, stored as a list.
func Exactly(n int) Nargs { return Nargs(n) + OneOrMore }

// JSON is the --json flag every command declares, with the help text of Python _add_output.
func JSON() Arg {
	return Arg{
		Flags:  []string{"--json"},
		Action: StoreTrue,
		Help:   "print one JSON envelope {command, ok, data, warnings, error}",
	}
}
