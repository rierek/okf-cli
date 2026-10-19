package cli

import (
	"fmt"
	"strings"
)

// Parsed is a successful parse: what to run and with which arguments.
type Parsed struct {
	// Args is the command line as the handler reads it.
	Args *Args
	// Entry is the directory entry of the command; dispatch skips the catalogue root
	// resolution when Entry.CatalogueFree is set.
	Entry Entry
	// Handler runs the command. A directory command without an attached handler gets one
	// that returns an okferr.Internal error naming the command as not yet ported.
	Handler Handler
}

// Args holds the parsed command line: the command path, the global options and the typed
// values of the command's arguments by dest. The values are never nil-checked for the
// caller: an absent value reads as the zero value, Has tells present from absent.
type Args struct {
	// Path is the command and its verb: ["read"], ["ctx", "show"].
	Path []string
	// Root is the raw --root value; it is "" when the option is absent (the last one wins).
	Root string
	// UseGlobal is the --global flag.
	UseGlobal bool
	// JSON is the --json flag of the command.
	JSON bool
	vals map[string]any
}

// Name is the command as typed, Python command_name(args): "read", or "ctx show" for a verb.
func (a *Args) Name() string { return strings.Join(a.Path, " ") }

// Has reports whether dest holds a value: given on the command line or defaulted to something
// other than None. A flag and an option with a default always have one.
func (a *Args) Has(dest string) bool { return a.vals[dest] != nil }

// Value is the stored value of dest, nil when absent: a string, int or float64 for one
// value, the converted value of a custom Type, a []any for several values (an Append holds
// one entry per occurrence, a list itself for Nargs above one).
func (a *Args) Value(dest string) any { return a.vals[dest] }

// String is the string value of dest, "" when absent.
func (a *Args) String(dest string) string {
	switch v := a.vals[dest].(type) {
	case nil:
		return ""
	case string:
		return v
	default:
		panic(wrongType(dest, v, "a string"))
	}
}

// Bool is the value of a flag.
func (a *Args) Bool(dest string) bool {
	switch v := a.vals[dest].(type) {
	case nil:
		return false
	case bool:
		return v
	default:
		panic(wrongType(dest, v, "a bool"))
	}
}

// Int is the value of an argument of Type Int (or of a custom Type that returns an int), 0
// when absent.
func (a *Args) Int(dest string) int {
	switch v := a.vals[dest].(type) {
	case nil:
		return 0
	case int:
		return v
	default:
		panic(wrongType(dest, v, "an int"))
	}
}

// Float is the value of an argument of Type Float, 0 when absent.
func (a *Args) Float(dest string) float64 {
	switch v := a.vals[dest].(type) {
	case nil:
		return 0
	case float64:
		return v
	default:
		panic(wrongType(dest, v, "a float64"))
	}
}

// Strings is the list of string values of dest: the values of a positional or option with
// several, or the occurrences of an Append. It is nil when absent.
func (a *Args) Strings(dest string) []string {
	switch v := a.vals[dest].(type) {
	case nil:
		return nil
	case []string:
		return v
	case []any:
		return stringsOf(dest, v)
	default:
		panic(wrongType(dest, v, "a list of strings"))
	}
}

// StringLists is the value of an Append option with Nargs above one: one list per occurrence.
func (a *Args) StringLists(dest string) [][]string {
	switch v := a.vals[dest].(type) {
	case nil:
		return nil
	case []any:
		lists := make([][]string, len(v))
		for i, item := range v {
			list, ok := item.([]any)
			if !ok {
				panic(wrongType(dest, item, "a list of string lists"))
			}
			lists[i] = stringsOf(dest, list)
		}
		return lists
	default:
		panic(wrongType(dest, v, "a list of string lists"))
	}
}

func stringsOf(dest string, list []any) []string {
	out := make([]string, len(list))
	for i, item := range list {
		s, ok := item.(string)
		if !ok {
			panic(wrongType(dest, item, "a list of strings"))
		}
		out[i] = s
	}
	return out
}

// wrongType describes a programming error: the accessor does not fit the declared argument.
func wrongType(dest string, got any, want string) string {
	return fmt.Sprintf("cli: argument %q holds %T, not %s", dest, got, want)
}
