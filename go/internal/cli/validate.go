package cli

import (
	"fmt"
	"strings"
)

// validate panics when a spec could not be turned into a parser: the mistakes that argparse
// reports as exceptions while a parser is built, found when the command attaches.
func validate(name string, s Spec) {
	fail := func(format string, args ...any) {
		panic(fmt.Sprintf("cli: command %q: ", name) + fmt.Sprintf(format, args...))
	}
	if s.Handler == nil {
		fail("no handler")
	}
	validateArgs(fail, s.Args, s.Exclusive)
	seen := map[string]bool{}
	for _, v := range s.Verbs {
		if v.Name == "" || seen[v.Name] {
			fail("verb %q is empty or repeated", v.Name)
		}
		seen[v.Name] = true
		validateArgs(func(format string, args ...any) { fail("verb %q: "+format, append([]any{v.Name}, args...)...) }, v.Args, v.Exclusive)
	}
}

// validateArgs checks the arguments of one parser: dests and option strings are unique, a flag
// is an option, a metavar fits its count and an exclusive group holds optional options.
func validateArgs(fail func(string, ...any), args []Arg, exclusive []Exclusive) {
	dests := map[string]*Arg{}
	flags := map[string]bool{"-h": true, "--help": true}
	for i := range args {
		arg := &args[i]
		dest := arg.Dest
		for _, flag := range arg.Flags {
			if !strings.HasPrefix(flag, "-") || len(flag) < 2 || flags[flag] {
				fail("option string %q is malformed or repeated", flag)
			}
			flags[flag] = true
		}
		if len(arg.Flags) > 0 && dest == "" {
			dest = destOf(arg.Flags)
		}
		if dest == "" || dests[dest] != nil {
			fail("argument %q has no dest or repeats one", dest)
		}
		dests[dest] = arg
		switch {
		case len(arg.Flags) == 0 && (arg.Action != Store || arg.Required):
			fail("positional %q takes the store action and is required by its count", dest)
		case arg.Action == StoreTrue && (arg.Nargs != One || arg.Type != nil || arg.Choices != nil):
			fail("flag %q takes no values", dest)
		case !metavarFits(arg.Nargs, len(arg.Metavar)):
			fail("metavar of %q does not fit its count", dest)
		case arg.Nargs < One:
			fail("argument %q has an invalid count", dest)
		}
	}
	for _, e := range exclusive {
		for _, dest := range e.Dests {
			if arg := dests[dest]; arg == nil || len(arg.Flags) == 0 || arg.Required {
				fail("exclusive group names %q, which is no optional option", dest)
			}
		}
	}
}

// metavarFits mirrors the check of argparse.add_argument that a metavar tuple matches nargs.
func metavarFits(n Nargs, names int) bool {
	switch {
	case names <= 1:
		return true
	case n == One || n == Optional:
		return false
	case n == ZeroOrMore || n == OneOrMore:
		return names == 2
	}
	return names == int(n-OneOrMore)
}
