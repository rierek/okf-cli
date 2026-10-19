package complete

import (
	"os"
	"strconv"
	"strings"
	"unicode/utf8"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/cli"
)

// Requested says whether the environment asks for a completion run instead of a command: the
// shell code sets _ARGCOMPLETE (argcomplete.autocomplete checks the same).
func Requested() bool {
	_, ok := os.LookupEnv("_ARGCOMPLETE")
	return ok
}

// Run answers one completion request and returns the exit code of the process, without running
// a command. It is argcomplete 3.7.2 CompletionFinder.__call__ with the okf parser: the line is
// COMP_LINE up to COMP_POINT, the candidates go to the file _ARGCOMPLETE_STDOUT_FILENAME or to
// file descriptor 8, separated by _ARGCOMPLETE_IFS (default \v).
func Run(app *cli.App) int {
	var out *os.File
	if name, ok := os.LookupEnv("_ARGCOMPLETE_STDOUT_FILENAME"); ok {
		f, err := os.Create(name)
		if err != nil {
			return 1
		}
		out = f
	} else {
		out = os.NewFile(8, "fd8")
		if _, err := out.Stat(); err != nil {
			return 1
		}
	}
	defer out.Close()

	ifs, ok := os.LookupEnv("_ARGCOMPLETE_IFS")
	if !ok {
		ifs = "\v"
	}
	dfs := os.Getenv("_ARGCOMPLETE_DFS")
	if utf8.RuneCountInString(ifs) != 1 || dfs != "" && utf8.RuneCountInString(dfs) != 1 {
		return 1
	}
	line, ok := os.LookupEnv("COMP_LINE")
	point, err := strconv.Atoi(os.Getenv("COMP_POINT"))
	skip, err2 := strconv.Atoi(os.Getenv("_ARGCOMPLETE"))
	if !ok || err != nil || err2 != nil {
		return 1
	}
	shell := os.Getenv("_ARGCOMPLETE_SHELL")

	prequote, prefix, _, words, lastBreak := splitLine(line, point, os.Getenv("_ARGCOMPLETE_COMP_WORDBREAKS"))
	words = words[min(max(skip-1, 0), len(words)):]
	if prefix != "" && prefix[0] == '-' && strings.Contains(prefix, "=") {
		// --optional=PARTIAL_VALUE: the parser gets the optional
		words = append(words, prefix[:strings.Index(prefix, "=")])
	}
	f := &finder{
		display:       map[string]string{},
		alwaysOptions: !slicesContain(words, "--"),
		appendSpace:   os.Getenv("_ARGCOMPLETE_SUPPRESS_SPACE") != "1",
		shell:         shell,
	}
	completions := f.complete(app.Probe(words[min(1, len(words)):]), prefix)
	completions = f.quote(dedupe(completions), prequote, lastBreak)

	if dfs != "" {
		completions = joinDisplay(completions, f.display, ifs, dfs)
	}
	if shell == "zsh" {
		for i, c := range completions {
			d, ok := f.display[c]
			if !ok {
				d = "None" // Python formats a missing description as None
			}
			completions[i] = c + ":" + d
		}
	}
	if _, err := out.WriteString(strings.Join(completions, ifs)); err != nil {
		return 1
	}
	return 0
}

// joinDisplay is the _ARGCOMPLETE_DFS form: value, DFS, description, with the IFS of the
// description turned into a space.
func joinDisplay(completions []string, display map[string]string, ifs, dfs string) []string {
	out := make([]string, len(completions))
	for i, c := range completions {
		out[i] = c + dfs + strings.ReplaceAll(display[c], ifs, " ")
	}
	return out
}

func slicesContain(s []string, v string) bool {
	for _, x := range s {
		if x == v {
			return true
		}
	}
	return false
}

// finder is CompletionFinder for one run.
type finder struct {
	display       map[string]string // _display_completions: the description of a completion
	alwaysOptions bool              // always_complete_options; off after a "--" word
	appendSpace   bool
	shell         string
}

// complete is collect_completions: the options of the parser the line ended in, the commands or
// verbs when they come next, then what the completers of the open arguments offer.
func (f *finder) complete(probe *cli.Probe, prefix string) []string {
	var completions []string
	if f.alwaysOptions || prefix != "" && prefix[0] == '-' {
		completions = f.options(probe, prefix)
	}
	if probe.Next >= 0 && probe.Actions[probe.Next].Kind == "parsers" {
		completions = append(completions, f.subcommands(probe.Actions[probe.Next], prefix)...)
	}
	return f.active(probe, prefix, completions)
}

// options is _get_option_completions.
func (f *finder) options(probe *cli.Probe, prefix string) []string {
	for _, a := range probe.Actions {
		for _, flag := range a.Flags {
			if strings.HasPrefix(flag, prefix) {
				f.display[flag] = helpOf(a.Help)
			}
		}
	}
	var out []string
	for _, a := range probe.Actions {
		if !a.Allowed || a.Kind == "parsers" {
			continue
		}
		if prefix != "" || f.alwaysOptions {
			for _, flag := range a.Flags {
				if strings.HasPrefix(flag, prefix) {
					out = append(out, flag)
				}
			}
		}
	}
	return out
}

// subcommands is _get_subparser_completions; a hidden command never shows.
func (f *finder) subcommands(a cli.ProbeAction, prefix string) []string {
	var out []string
	for _, s := range a.Subs {
		if !s.Hidden && strings.HasPrefix(s.Name, prefix) {
			f.display[s.Name] = helpOf(s.Help)
			out = append(out, s.Name)
		}
	}
	return out
}

// helpOf is _get_action_help; Python expands %-formats of the help text.
func helpOf(help string) string {
	if strings.Contains(help, "%") {
		return strings.ReplaceAll(help, "%%", "%")
	}
	return help
}

// active is _complete_active_option: run the completers of the arguments that can take the word.
func (f *finder) active(probe *cli.Probe, prefix string, completions []string) []string {
	isOptional := prefix != "" && prefix[0] == '-'
	optionalPrefix := ""
	var greedy []int
	for _, i := range probe.Active {
		if isGreedy(probe.Actions[i], isOptional) {
			greedy = append(greedy, i)
		}
	}
	active := probe.Active
	switch {
	case len(greedy) > 0:
		// the action fails to parse unless the word goes to it: it alone completes the word
		f.display = map[string]string{}
		completions = nil
		active = greedy
	case isOptional:
		eq := strings.Index(prefix, "=")
		if eq < 0 {
			return completions // only a word that is no option runs completers
		}
		optionalPrefix, prefix = prefix[:eq], prefix[eq+1:]
	}

	remaining := false
	for _, i := range active {
		a := probe.Actions[i]
		if a.Positional {
			if isOpen(a) {
				// positionals after this one may slide down into it: run all remaining completers
				remaining = true
			}
			if !remaining && isSatisfied(a) && !isOpen(a) {
				continue
			}
		}
		var got []Candidate
		completer, ok := attached[key(probe.Path, a.Dest)]
		switch {
		case ok:
			got = completer(f.context(probe, prefix))
		case a.Choices != nil && a.Kind != "parsers":
			for _, c := range a.Choices {
				got = append(got, Candidate{c, helpOf(a.Help)})
			}
		default:
			continue // no completer: nothing to offer (SuppressCompleter, or the subparsers action)
		}
		for _, c := range got {
			if strings.HasPrefix(c.Value, prefix) {
				completions = append(completions, c.Value)
				f.display[c.Value] = c.Description
			}
		}
		if optionalPrefix != "" {
			for j, c := range completions {
				completions[j] = optionalPrefix + "=" + c
			}
		}
	}
	return completions
}

// context resolves the root the words so far name, as _completion_root does: a failing
// resolution or a missing directory gives no root.
func (f *finder) context(probe *cli.Probe, prefix string) Context {
	c := Context{Prefix: prefix, values: probe.Values}
	root, err := catalogue.CatalogueRoot(c.String("root"), c.Bool("use_global"))
	if err == nil && root != "" && catalogue.RealFS.IsDir(root) {
		c.Root = root
	}
	return c
}

// isSatisfied is action_is_satisfied: the parse would not fail if no more words came.
func isSatisfied(a cli.ProbeAction) bool {
	switch a.Nargs {
	case "?", "*":
		return true
	case "+":
		return a.Consumed >= 1
	case "A...":
		return false
	case "":
		return a.Consumed == 1
	}
	n, _ := strconv.Atoi(a.Nargs)
	return a.Consumed == n
}

// isOpen is action_is_open: the action could take more words.
func isOpen(a cli.ProbeAction) bool {
	switch a.Nargs {
	case "*", "+", "A...":
		return true
	case "?", "":
		return a.Consumed == 0
	}
	n, _ := strconv.Atoi(a.Nargs)
	return a.Consumed < n
}

// isGreedy is action_is_greedy: the action takes the next word whatever it is. No okf argument
// has nargs=REMAINDER, so only an option that still lacks its value is.
func isGreedy(a cli.ProbeAction, isOptional bool) bool {
	return !a.Positional && !isOptional && !isSatisfied(a)
}

func dedupe(in []string) []string {
	var out []string
	seen := map[string]bool{}
	for _, c := range in {
		if !seen[c] {
			seen[c] = true
			out = append(out, c)
		}
	}
	return out
}

// quote is quote_completions: escape what the shell would split or expand, drop what bash cut
// off at a wordbreak, and for a single candidate that is no prefix of a longer word add a space.
func (f *finder) quote(completions []string, prequote string, lastBreak int) []string {
	special := `\`
	switch prequote {
	case "":
		if lastBreak >= 0 {
			for i, c := range completions {
				r := []rune(c)
				completions[i] = string(r[min(lastBreak+1, len(r)):])
			}
		}
		special += "();<>|&!`$*?[]{} \t\n\"'"
	case `"`:
		special += "\"`$!"
	}
	switch {
	case f.shell == "tcsh" || f.shell == "fish":
		special = "" // tcsh and fish escape for themselves
	case prequote == "'":
		// nothing can be escaped in single quotes: close, escape, reopen
		special = ""
		for i, c := range completions {
			completions[i] = strings.ReplaceAll(c, "'", `'\''`)
		}
	}
	escape := `\`
	if f.shell == "powershell" {
		escape = "`"
		special = strings.ReplaceAll(special, "`", "")
	} else if f.shell == "zsh" {
		special += ":"
	}
	escaped := make([]string, len(completions))
	for i, c := range completions {
		e := c
		for _, ch := range special {
			e = strings.ReplaceAll(e, string(ch), escape+string(ch))
		}
		escaped[i] = e
		if d, ok := f.display[c]; ok {
			f.display[e] = d
		}
	}
	if f.appendSpace && len(escaped) == 1 && prequote == "" && !strings.HasSuffix(escaped[0], "=") &&
		!strings.HasSuffix(escaped[0], "/") && !strings.HasSuffix(escaped[0], ":") {
		escaped[0] += " "
	}
	return escaped
}
