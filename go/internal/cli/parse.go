package cli

import (
	"errors"
	"fmt"
	"regexp"
	"slices"
	"strings"
	"unicode/utf8"

	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

// This file is a port of argparse.ArgumentParser._parse_known_args of Python 3.14, step by step
// and in its order, so that every command line ends in the same values or the same error.

// optTuple is one reading of an argument that looks like an option: the action it names (nil
// when this parser has no such option), the option string, the separator ("=" or "") and the
// text glued to it, when there is some.
type optTuple struct {
	act      *action
	str      string
	sep      string
	explicit string
	hasExp   bool
}

// run is one execution of _parse_known_args.
type run struct {
	p              *parser
	args           []string
	pattern        string // one letter per argument: A argument, O option, - the first "--"
	options        map[int][]optTuple
	ns             map[string]any
	positionals    []*action
	seen           map[*action]bool
	seenNonDefault map[*action]bool
	conflicts      map[*action][]*action
	extras         []string
	extrasPattern  []byte
	unrecognized   []string // what the subparsers could not use
}

// parseKnown is parse_known_args: the values of the parser's arguments and the arguments left
// over, or a *UsageError, or a *HelpOutput when -h ended the parse.
func (p *parser) parseKnown(args []string) (map[string]any, []string, error) {
	ns := map[string]any{}
	for _, a := range p.actions {
		if a.kind != kindHelp {
			ns[a.dest] = a.def
		}
	}
	r := &run{
		p: p, args: args, ns: ns, seen: map[*action]bool{}, seenNonDefault: map[*action]bool{},
		conflicts: map[*action][]*action{}, options: map[int][]optTuple{},
	}
	extras, err := r.parse()
	var ae *argError
	switch {
	case errors.As(err, &ae):
		return nil, nil, p.usageError(ae.Error())
	case err != nil:
		return nil, nil, err
	}
	return ns, append(extras, r.unrecognized...), nil
}

func (r *run) parse() ([]string, error) {
	p := r.p
	for _, g := range p.groups {
		for i, a := range g.actions {
			r.conflicts[a] = append(r.conflicts[a], g.actions[:i]...)
			r.conflicts[a] = append(r.conflicts[a], g.actions[i+1:]...)
		}
	}
	r.scan()
	for _, a := range p.actions {
		if !a.isOption() {
			r.positionals = append(r.positionals, a)
		}
	}
	maxOption := -1
	for i := range r.options {
		maxOption = max(maxOption, i)
	}
	start := 0
	for start <= maxOption {
		next := start
		for next <= maxOption {
			if _, ok := r.options[next]; ok {
				break
			}
			next++
		}
		if !p.intermixed && start != next {
			end, err := r.consumePositionals(start)
			if err != nil {
				return nil, err
			}
			if end > start {
				start = end
				continue
			}
		}
		if _, ok := r.options[start]; !ok {
			r.extras = append(r.extras, r.args[start:next]...)
			r.extrasPattern = append(r.extrasPattern, r.pattern[start:next]...)
			start = next
		}
		var err error
		if start, err = r.consumeOptional(start); err != nil {
			return nil, err
		}
	}
	if !p.intermixed {
		stop, err := r.consumePositionals(start)
		if err != nil {
			return nil, err
		}
		r.extras = append(r.extras, r.args[stop:]...)
	} else if err := r.consumeIntermixed(start); err != nil {
		return nil, err
	}
	return r.extras, r.finish()
}

// scan classifies every argument: the pattern letters, and the readings of those that look like
// options. All arguments after the first "--" are plain arguments.
func (r *run) scan() {
	pattern := make([]byte, 0, len(r.args))
	for i := 0; i < len(r.args); i++ {
		if r.args[i] == "--" {
			pattern = append(pattern, '-')
			for i++; i < len(r.args); i++ {
				pattern = append(pattern, 'A')
			}
			break
		}
		if tuples := r.p.parseOptional(r.args[i]); tuples != nil {
			r.options[i] = tuples
			pattern = append(pattern, 'O')
		} else {
			pattern = append(pattern, 'A')
		}
	}
	r.pattern = string(pattern)
}

// consumeIntermixed hands every argument that is no option, from the leftovers of the option
// scan, to the positionals at once; what they do not take stays in extras.
func (r *run) consumeIntermixed(start int) error {
	r.extras = append(r.extras, r.args[start:]...)
	r.extrasPattern = append(r.extrasPattern, r.pattern[start:]...)
	var args []string
	var pattern []byte
	for i, letter := range r.extrasPattern {
		if letter != 'O' {
			args = append(args, r.extras[i])
			pattern = append(pattern, letter)
		}
	}
	r.args, r.pattern = args, string(pattern)
	stop, err := r.consumePositionals(0)
	if err != nil {
		return err
	}
	kept := r.extras[:0:0]
	for i, letter := range r.extrasPattern {
		if stop > 0 && letter != 'O' {
			stop--
			continue
		}
		kept = append(kept, r.extras[i])
	}
	r.extras = kept
	return nil
}

// finish is the end of _parse_known_args: every required argument and group must have been given.
func (r *run) finish() error {
	var missing []string
	for _, a := range r.p.actions {
		if !r.seen[a] && a.required {
			missing = append(missing, a.name())
		}
	}
	if len(missing) > 0 {
		return &argError{msg: "the following arguments are required: " + strings.Join(missing, ", ")}
	}
	for _, g := range r.p.groups {
		if g.required && !slices.ContainsFunc(g.actions, func(a *action) bool { return r.seenNonDefault[a] }) {
			names := make([]string, len(g.actions))
			for i, a := range g.actions {
				names[i] = a.name()
			}
			return &argError{msg: "one of the arguments " + strings.Join(names, " ") + " is required"}
		}
	}
	return nil
}

// consumePositionals matches as many positionals as the arguments from start on allow, takes
// them and returns the index after their arguments.
func (r *run) consumePositionals(start int) (int, error) {
	counts := matchPartial(r.positionals, r.pattern[start:])
	for i, n := range counts {
		a := r.positionals[i]
		args := slices.Clone(r.args[start : start+n])
		// the first "--" is a separator, not an argument, unless a remainder takes it
		if i := slices.Index(args, "--"); i >= 0 && strings.Contains(r.pattern[start:start+n], "-") && (a.nargs != nParser || r.pattern[start] == '-') {
			args = slices.Delete(args, i, i+1)
		}
		start += n
		if err := r.takeAction(a, args); err != nil {
			return 0, err
		}
	}
	r.positionals = r.positionals[len(counts):]
	return start, nil
}

// consumeOptional takes the option at start with its values and returns the index after them.
func (r *run) consumeOptional(start int) (int, error) {
	tuples := r.options[start]
	if len(tuples) > 1 {
		names := make([]string, len(tuples))
		for i, t := range tuples {
			names[i] = t.str
		}
		return 0, &argError{msg: fmt.Sprintf("ambiguous option: %s could match %s", r.args[start], strings.Join(names, ", "))}
	}
	act, optString, sep, explicit, hasExp := tuples[0].act, tuples[0].str, tuples[0].sep, tuples[0].explicit, tuples[0].hasExp
	type taken struct {
		act  *action
		args []string
	}
	var takes []taken
	var stop int
	for {
		if act == nil {
			r.extras = append(r.extras, r.args[start])
			r.extrasPattern = append(r.extrasPattern, 'O')
			return start + 1, nil
		}
		if !hasExp {
			from := start + 1
			n, err := matchArgument(act, r.pattern[from:])
			if err != nil {
				return 0, err
			}
			stop = from + n
			takes = append(takes, taken{act, r.args[from:stop]})
			break
		}
		n, err := matchArgument(act, "A")
		if err != nil {
			return 0, err
		}
		if n == 0 && optString[1] != '-' && explicit != "" {
			// -xyz is -x -y -z while no option takes a value
			if sep != "" || explicit[0] == '-' {
				return 0, &argError{act, "ignored explicit argument " + pytext.ReprStr(explicit)}
			}
			takes = append(takes, taken{act, nil})
			first, size := utf8.DecodeRuneInString(explicit)
			optString = "-" + string(first)
			next, ok := r.p.byFlag[optString]
			if !ok {
				r.extras = append(r.extras, "-"+explicit)
				r.extrasPattern = append(r.extrasPattern, 'O')
				stop = start + 1
				break
			}
			act, explicit = next, explicit[size:]
			switch {
			case explicit == "":
				sep, hasExp = "", false
			case explicit[0] == '=':
				sep, explicit = "=", explicit[1:]
			default:
				sep = ""
			}
		} else if n == 1 {
			stop = start + 1
			takes = append(takes, taken{act, []string{explicit}})
			break
		} else {
			return 0, &argError{act, "ignored explicit argument " + pytext.ReprStr(explicit)}
		}
	}
	for _, t := range takes {
		if err := r.takeAction(t.act, t.args); err != nil {
			return 0, err
		}
	}
	return stop, nil
}

// takeAction converts the values of one argument, checks its exclusive group and runs it.
func (r *run) takeAction(a *action, args []string) error {
	r.seen[a] = true
	value, err := r.p.getValues(a, args)
	if err != nil {
		return err
	}
	if a.isOption() || len(args) > 0 {
		r.seenNonDefault[a] = true
		for _, c := range r.conflicts[a] {
			if r.seenNonDefault[c] {
				return &argError{a, "not allowed with argument " + c.name()}
			}
		}
	}
	switch a.kind {
	case kindStore:
		r.ns[a.dest] = value
	case kindStoreTrue:
		r.ns[a.dest] = true
	case kindAppend:
		r.ns[a.dest] = append(anyList(r.ns[a.dest]), value)
	case kindHelp:
		return &HelpOutput{Text: r.p.formatHelp()}
	case kindParsers:
		return r.callParser(a, value.([]string))
	}
	return nil
}

// anyList copies a list value (a default, or what an Append collected so far) as a []any.
func anyList(v any) []any {
	switch v := v.(type) {
	case []any:
		return slices.Clone(v)
	case []string:
		out := make([]any, len(v))
		for i, s := range v {
			out[i] = s
		}
		return out
	}
	return nil
}

// callParser is _SubParsersAction.__call__: the first value names the subparser, which parses
// the rest into its own values; those join the values of this parser, what it cannot use joins
// the leftovers.
func (r *run) callParser(a *action, values []string) error {
	r.ns[a.dest] = values[0]
	child := a.sub.build(values[0])
	ns, extras, err := child.parseKnown(values[1:])
	if err != nil {
		return err
	}
	for k, v := range ns {
		r.ns[k] = v
	}
	if !child.lenient {
		r.unrecognized = append(r.unrecognized, extras...)
	}
	return nil
}

// getValues is _get_values: the strings of one argument become its value.
func (p *parser) getValues(a *action, args []string) (any, error) {
	switch {
	case a.nargs == 0:
		return nil, nil
	case len(args) == 0 && a.nargs == nOptional:
		if a.isOption() {
			return nil, nil
		}
		return a.def, nil
	case len(args) == 0 && a.nargs == nStar && !a.isOption():
		if a.def != nil {
			return a.def, nil
		}
		return []any{}, nil
	case len(args) == 1 && (a.nargs == nOne || a.nargs == nOptional):
		return p.value(a, args[0])
	case a.nargs == nParser:
		if err := checkChoice(a, args[0]); err != nil {
			return nil, err
		}
		return args, nil
	}
	list := make([]any, len(args))
	for i, raw := range args {
		v, err := p.value(a, raw)
		if err != nil {
			return nil, err
		}
		list[i] = v
	}
	return list, nil
}

// value converts one string with the argument's type and checks it against its choices.
func (p *parser) value(a *action, raw string) (any, error) {
	var v any = raw
	if a.typ != nil {
		var msg string
		if v, msg = a.typ(raw); msg != "" {
			return nil, &argError{a, msg}
		}
	}
	return v, checkChoice(a, v)
}

// checkChoice is _check_value: the value must be one of the choices, or a known verb.
func checkChoice(a *action, v any) error {
	var choices []string
	switch {
	case a.kind == kindParsers:
		if a.sub.has(v.(string)) {
			return nil
		}
		choices = a.sub.shown()
	case a.choices == nil || slices.Contains(a.choices, fmt.Sprint(v)):
		return nil
	default:
		choices = a.choices
	}
	quoted := make([]string, len(choices))
	for i, c := range choices {
		quoted[i] = pytext.ReprStr(c)
	}
	return &argError{a, fmt.Sprintf("invalid choice: %s (choose from %s)", pytext.ReprStr(fmt.Sprint(v)), strings.Join(quoted, ", "))}
}

// matchArgument is _match_argument for an option: how many of the arguments after it, given as
// pattern letters, it takes.
func matchArgument(a *action, pattern string) (int, error) {
	leading := len(pattern) - len(strings.TrimLeft(pattern, "A"))
	n, ok := a.nargs, true
	switch a.nargs {
	case nOne:
		n, ok = 1, leading > 0
	case nOptional:
		n = min(leading, 1)
	case nStar:
		n = leading
	case nPlus:
		n, ok = leading, leading > 0
	default:
		ok = len(pattern) >= n && !strings.Contains(pattern[:n], "-")
	}
	if ok {
		return n, nil
	}
	msg := fmt.Sprintf("expected %d arguments", a.nargs)
	switch a.nargs {
	case 1:
		msg = "expected 1 argument"
	case nOne:
		msg = "expected one argument"
	case nPlus:
		msg = "expected at least one argument"
	}
	return 0, &argError{a, msg}
}

// nargsPattern is _get_nargs_pattern for a positional: the regular expression over the pattern
// letters that its arguments match, '--' (the letter -) allowed around them.
func nargsPattern(a *action) string {
	switch a.nargs {
	case nOne:
		return "(-*A-*)"
	case nOptional:
		return "(-*A?-*)"
	case nStar:
		return "(-*[A-]*)"
	case nPlus:
		return "(-*A[A-]*)"
	case nParser:
		return "(-*A[-AO]*)"
	}
	return fmt.Sprintf("((?:-*A){%d}-*)", a.nargs)
}

// matchPartial is _match_arguments_partial: the numbers of arguments the longest prefix of the
// positionals that matches the pattern letters takes.
func matchPartial(actions []*action, pattern string) []int {
	for i := len(actions); i > 0; i-- {
		var expr strings.Builder
		expr.WriteByte('^')
		for _, a := range actions[:i] {
			expr.WriteString(nargsPattern(a))
		}
		loc := regexp.MustCompile(expr.String()).FindStringSubmatchIndex(pattern)
		if loc == nil {
			continue
		}
		counts := make([]int, i)
		for g := range counts {
			counts[g] = loc[2*g+3] - loc[2*g+2]
		}
		if end := loc[1]; end < len(pattern) && pattern[end] == 'O' {
			for len(counts) > 0 && counts[len(counts)-1] == 0 {
				counts = counts[:len(counts)-1]
			}
		}
		return counts
	}
	return nil
}

// parseOptional is _parse_optional: nil when arg is meant as a positional, else every reading
// of it as an option (more than one when an abbreviation is ambiguous).
func (p *parser) parseOptional(arg string) []optTuple {
	if arg == "" || arg[0] != '-' {
		return nil
	}
	if a, ok := p.byFlag[arg]; ok {
		return []optTuple{{act: a, str: arg}}
	}
	if len(arg) == 1 {
		return nil
	}
	if name, value, ok := strings.Cut(arg, "="); ok {
		if a, found := p.byFlag[name]; found {
			return []optTuple{{act: a, str: name, sep: "=", explicit: value, hasExp: true}}
		}
	}
	if tuples := p.optionTuples(arg); len(tuples) > 0 {
		return tuples
	}
	if isNegativeNumber(arg) && !p.negOptions {
		return nil
	}
	if strings.Contains(arg, " ") {
		return nil
	}
	return []optTuple{{str: arg}}
}

// optionTuples is _get_option_tuples: the options that arg abbreviates, and for a single dash the
// short option whose value or siblings are glued to it.
func (p *parser) optionTuples(arg string) []optTuple {
	var tuples []optTuple
	prefix, value, hasValue := strings.Cut(arg, "=")
	sep := ""
	if hasValue {
		sep = "="
	}
	if arg[1] == '-' {
		for _, flag := range p.flagOrder {
			if strings.HasPrefix(flag, prefix) {
				tuples = append(tuples, optTuple{act: p.byFlag[flag], str: flag, sep: sep, explicit: value, hasExp: hasValue})
			}
		}
		return tuples
	}
	_, size := utf8.DecodeRuneInString(arg[1:])
	short := arg[:1+size]
	for _, flag := range p.flagOrder {
		switch {
		case flag == short:
			tuples = append(tuples, optTuple{act: p.byFlag[flag], str: flag, explicit: arg[len(short):], hasExp: true})
		case strings.HasPrefix(flag, prefix):
			tuples = append(tuples, optTuple{act: p.byFlag[flag], str: flag, sep: sep, explicit: value, hasExp: hasValue})
		}
	}
	return tuples
}
