package cli

import "strings"

// This file is the hook of the shell completion into the parser. Python's argcomplete does not
// read the parser, it runs argparse over the words before the cursor with every action patched,
// and asks the patched parsers afterwards which arguments were still open. Probe does the same
// with the Go port of argparse, so the answers are the same ones for every nargs, exclusive
// group and verb table. The completion protocol itself is in package complete.

// probeState is argcomplete's global state while one completion run parses: the parsers that
// were entered, the positionals that were taken and how many strings each action consumed.
type probeState struct {
	consumed map[*action]int // _num_consumed_args, cleared at the start of every parser
	runs     []*run          // active_parsers, the top parser first
	visited  []visit         // visited_positionals
}

// visit is one entry of visited_positionals: a parser that was entered, or a positional that
// took its values.
type visit struct {
	r   *run
	act *action
}

// start is the patch of a parser together with the first lines of its _parse_known_args.
func (pr *probeState) start(r *run) {
	pr.runs = append(pr.runs, r)
	pr.visited = append(pr.visited, visit{r: r})
	clear(pr.consumed)
}

// isOpen is action_is_open: the action could still take more strings after n of them.
func isOpen(a *action, n int) bool {
	switch {
	case a.kind == kindParsers || a.nargs == nStar || a.nargs == nPlus:
		return true
	case a.nargs == nOptional || a.nargs == nOne:
		return n == 0
	}
	return n < a.nargs
}

// Probe is what the completion reads after the words before the cursor were parsed: the values
// found so far and the state of the parser the last word ended in.
type Probe struct {
	// Values are the argument values read so far, by dest, with the defaults of the parsers that
	// were entered; the values of an argument that was not given are Python's defaults.
	Values map[string]any
	// Path names the parser the words ended in: no element for okf itself, the command, and the
	// verb of a verb table.
	Path []string
	// Actions are the arguments of that parser in registration order, -h/--help first.
	Actions []ProbeAction
	// Active are the indexes of the Actions that can still take the next word
	// (active_actions).
	Active []int
	// Next is the index of the positional that comes next, or -1 for none.
	Next int
}

// ProbeAction is one argument of the parser the words ended in.
type ProbeAction struct {
	ArgInfo
	// Subs are the commands or verbs of the subparsers action, whose Kind is "parsers" and
	// whose Nargs is "A...".
	Subs []ProbeSub
	// Consumed is how many strings the argument took in the last parser that ran.
	Consumed int
	// Allowed is false when an argument of the same exclusive group was already given.
	Allowed bool
}

// ProbeSub is one name of a subparsers action.
type ProbeSub struct {
	Name, Help string
	Hidden     bool
}

// Probe parses the words that came before the cursor, as argcomplete does with the patched
// parsers, and returns what the completers of the word under the cursor need. A parse error ends
// the parse and is not an error here: the line is incomplete by nature.
func (a *App) Probe(words []string) *Probe {
	pr := &probeState{consumed: map[*action]int{}}
	ns, _, _ := a.topParser().parseKnownProbe(words, pr)
	last := pr.runs[len(pr.runs)-1]
	p := &Probe{Values: ns, Path: strings.Fields(last.p.prog)[1:], Next: -1}
	index := map[*action]int{}
	for i, act := range last.p.actions {
		index[act] = i
		pa := ProbeAction{ArgInfo: argInfo(act), Consumed: pr.consumed[act], Allowed: true}
		if act.kind == kindParsers {
			pa.ArgInfo.Nargs, pa.ArgInfo.Kind = "A...", "parsers"
			for _, e := range act.sub.entries {
				pa.Subs = append(pa.Subs, ProbeSub{Name: e.name, Help: e.help, Hidden: e.hidden})
			}
		}
		for _, c := range last.conflicts[act] {
			if last.seenNonDefault[c] {
				pa.Allowed = false
			}
		}
		p.Actions = append(p.Actions, pa)
	}
	for _, act := range last.active {
		p.Active = append(p.Active, index[act])
	}
	p.Next = nextPositional(last, pr.visited[len(pr.visited)-1])
	return p
}

// nextPositional is CompletionFinder._get_next_positional.
func nextPositional(last *run, v visit) int {
	var positionals []int
	for i, act := range last.p.actions {
		if !act.isOption() {
			positionals = append(positionals, i)
		}
	}
	if len(positionals) == 0 {
		return -1
	}
	if v.r == last {
		return positionals[0]
	}
	i := 0
	for ; i < len(positionals); i++ {
		if last.p.actions[positionals[i]] == v.act {
			break
		}
	}
	if i == len(positionals) { // not found: Python's loop variable stays on the last index
		i--
	}
	if i+1 < len(positionals) {
		return positionals[i+1]
	}
	return -1
}
