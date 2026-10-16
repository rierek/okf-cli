// Package complete is the shell completion of the okf binary: the argcomplete environment
// protocol that cli/_okf and argcomplete's bash and fish code speak, the completers of the
// arguments and the script texts of the three shells.
//
// A command package wires its value arguments from its Register function:
//
//	complete.Attach([]string{"read"}, "path", complete.Concepts)
//	complete.Attach([]string{"ctx", "add"}, "slug", complete.CtxSlugs)
//
// An argument without a completer offers no values (Python: SuppressCompleter as the default);
// options, commands, verbs and choices complete without one.
package complete

import "strings"

// Candidate is one completion: the value and the description a shell may show next to it.
type Candidate struct {
	Value, Description string
}

// Completer returns the candidates of one argument in display order, unfiltered: the protocol
// keeps those that start with the prefix and formats them for the shell.
type Completer func(Context) []Candidate

// Context is what a completer knows about the line.
type Context struct {
	// Prefix is the part of the word under the cursor that the completer completes: for
	// --opt=PART it is PART.
	Prefix string
	// Root is the catalogue root the words of the line resolve to, `~` expanded. It is empty
	// when the resolution fails or the directory is missing; the catalogue completers then
	// offer nothing.
	Root   string
	values map[string]any
}

// Value is the value of the argument dest as far as the line gives it, or the default of the
// parser (nil for none).
func (c Context) Value(dest string) any { return c.values[dest] }

// String is Value as a string; "" when it is none.
func (c Context) String(dest string) string {
	s, _ := c.values[dest].(string)
	return s
}

// Bool is Value as a flag: true when the flag is on the line.
func (c Context) Bool(dest string) bool {
	b, _ := c.values[dest].(bool)
	return b
}

// attached are the completers by command path and dest. Only the global options are wired here;
// the command packages attach their own.
var attached = map[string]Completer{
	key(nil, "root"): Dirs,
}

func key(path []string, dest string) string { return strings.Join(path, " ") + "\x00" + dest }

// Attach gives the argument dest of the command path (nil for the global options, {"ctx", "add"}
// for a verb) its completer. It panics, which stops the binary at startup, when the argument
// already has one.
func Attach(path []string, dest string, c Completer) {
	k := key(path, dest)
	if _, ok := attached[k]; ok {
		panic("complete: " + strings.Join(append(append([]string{"okf"}, path...), dest), " ") + " has a completer already")
	}
	attached[k] = c
}
