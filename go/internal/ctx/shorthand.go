package ctx

import (
	"slices"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/ctxfile"
)

// Shorthand is Python _ctx_shorthand, the rewrite of the raw command line that runs before the
// parse: `ctx` becomes `ctx list`, `ctx --list` becomes `ctx list` and `ctx <word>`, where word is
// neither a verb nor an option, becomes `ctx show <word>`. It acts only when the first command
// word behind the global options is `ctx` (`--root` takes a value, every other option does not)
// and returns every other command line as it is.
func Shorthand(argv []string) []string {
	i := 0
	for i < len(argv) && strings.HasPrefix(argv[i], "-") {
		if argv[i] == "--root" {
			i += 2
		} else {
			i++
		}
	}
	if i >= len(argv) || argv[i] != "ctx" {
		return argv
	}
	rest := argv[i+1:]
	switch {
	case len(rest) == 0:
		rest = []string{"list"}
	case rest[0] == "--list":
		rest = append([]string{"list"}, rest[1:]...)
	case !slices.Contains(ctxfile.CtxVerbs, rest[0]) && !strings.HasPrefix(rest[0], "-"):
		rest = append([]string{"show"}, rest...)
	}
	return append(slices.Clone(argv[:i+1]), rest...)
}
