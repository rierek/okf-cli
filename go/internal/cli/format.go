package cli

import (
	"strings"
	"unicode/utf8"

	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

// This file is a port of argparse.HelpFormatter of Python 3.14 (without colour): the usage
// line with its wrapping, the sections of arguments, the help columns and the description and
// epilog texts. Lengths count code points.

// formatter carries the layout of one help or usage text.
type formatter struct {
	width        int // the text width: the terminal columns minus two
	maxHelpPos   int
	indent       int
	actionMaxLen int
}

func newFormatter() *formatter {
	width := terminalColumns() - 2
	return &formatter{width: width, maxHelpPos: min(24, max(width-20, 4))}
}

func rlen(s string) int { return utf8.RuneCountInString(s) }

// usageError is parser.error: the usage of p and one error line.
func (p *parser) usageError(msg string) *UsageError {
	return &UsageError{Text: p.formatUsage() + p.prog + ": error: " + msg + "\n"}
}

// formatUsage is parser.format_usage: "usage: ..." and a newline.
func (p *parser) formatUsage() string {
	return finishHelp(newFormatter().usage(p))
}

// formatHelp is parser.format_help.
func (p *parser) formatHelp() string {
	f := newFormatter()
	var b strings.Builder
	b.WriteString(f.usage(p))
	if p.description != "" {
		b.WriteString(f.text(p.description, p.raw))
	}
	var positionals, options []*action
	for _, a := range p.actions {
		if a.isOption() {
			options = append(options, a)
		} else {
			positionals = append(positionals, a)
		}
	}
	sections := []struct {
		title   string
		actions []*action
	}{{"positional arguments", positionals}, {"options", options}}
	f.indent = 2
	for _, section := range sections {
		for _, a := range section.actions {
			f.actionMaxLen = max(f.actionMaxLen, rlen(f.invocation(a))+f.indent)
			for _, sub := range subActions(a) {
				f.actionMaxLen = max(f.actionMaxLen, rlen(f.invocation(sub))+f.indent+2)
			}
		}
	}
	for _, section := range sections {
		var items strings.Builder
		for _, a := range section.actions {
			items.WriteString(f.action(a))
		}
		if items.Len() > 0 {
			b.WriteString("\n" + section.title + ":\n" + items.String() + "\n")
		}
	}
	f.indent = 0
	if p.epilog != nil {
		b.WriteString(f.text(p.epilog(), p.raw))
	}
	return finishHelp(b.String())
}

// finishHelp is the end of HelpFormatter.format_help: runs of blank lines shrink to one blank
// line and the text ends with exactly one newline.
func finishHelp(help string) string {
	var b strings.Builder
	newlines := 0
	for i := range len(help) {
		if help[i] == '\n' {
			newlines++
			if newlines > 2 {
				continue
			}
		} else {
			newlines = 0
		}
		b.WriteByte(help[i])
	}
	return strings.Trim(b.String(), "\n") + "\n"
}

// text is HelpFormatter._format_text: a description or epilog, raw or wrapped to the width.
func (f *formatter) text(t string, raw bool) string {
	if raw {
		return t + "\n\n"
	}
	return pytext.Fill(collapse(t), max(f.width-f.indent, 11), "", "") + "\n\n"
}

// collapse is the preparation of _split_lines and _fill_text: every run of ASCII whitespace
// becomes one space and the ends are stripped.
func collapse(t string) string {
	var b strings.Builder
	space := false
	for _, r := range t {
		if r == ' ' || r >= '\t' && r <= '\r' {
			if !space {
				b.WriteByte(' ')
			}
			space = true
			continue
		}
		space = false
		b.WriteRune(r)
	}
	return pytext.Strip(b.String())
}

// usage is HelpFormatter._format_usage: "usage: " and the program with the parts of its
// arguments, wrapped to the width, then a blank line.
func (f *formatter) usage(p *parser) string {
	const prefix = "usage: "
	prog := p.prog
	parts, posStart := f.usageParts(p)
	usage := strings.Join(append([]string{prog}, parts...), " ")
	textWidth := f.width - f.indent
	if rlen(prefix)+rlen(usage) > textWidth {
		optParts, posParts := parts[:posStart], parts[posStart:]
		getLines := func(parts []string, indent string, first bool) []string {
			var lines, line []string
			lineLen := len(indent) - 1
			if first {
				lineLen = rlen(prefix) - 1
			}
			for _, part := range parts {
				partLen := rlen(part)
				if lineLen+1+partLen > textWidth && len(line) > 0 {
					lines = append(lines, indent+strings.Join(line, " "))
					line = nil
					lineLen = len(indent) - 1
				}
				line = append(line, part)
				lineLen += partLen + 1
			}
			if len(line) > 0 {
				lines = append(lines, indent+strings.Join(line, " "))
			}
			if first {
				lines[0] = lines[0][len(indent):]
			}
			return lines
		}
		var lines []string
		if progLen := rlen(prog); 4*(rlen(prefix)+progLen) <= 3*textWidth {
			indent := strings.Repeat(" ", rlen(prefix)+progLen+1)
			switch {
			case len(optParts) > 0:
				lines = getLines(append([]string{prog}, optParts...), indent, true)
				lines = append(lines, getLines(posParts, indent, false)...)
			case len(posParts) > 0:
				lines = getLines(append([]string{prog}, posParts...), indent, true)
			default:
				lines = []string{prog}
			}
		} else {
			indent := strings.Repeat(" ", rlen(prefix))
			lines = getLines(parts, indent, false)
			if len(lines) > 1 {
				lines = append(getLines(optParts, indent, false), getLines(posParts, indent, false)...)
			}
			lines = append([]string{prog}, lines...)
		}
		usage = strings.Join(lines, "\n")
	}
	return prefix + prog + strings.TrimPrefix(usage, prog) + "\n\n"
}

// usageItem is one unit of the usage line: an argument, or a mutually exclusive group of options.
type usageItem struct {
	required bool
	actions  []*action
}

// usageParts is HelpFormatter._get_actions_usage_parts: the text of every argument in usage
// order (options first, positionals after) and the index where the positionals begin. The
// options of a mutually exclusive group stand together at the place of the first of them.
func (f *formatter) usageParts(p *parser) ([]string, int) {
	groupOf := map[*action]*group{}
	for _, g := range p.groups {
		for _, a := range g.actions {
			groupOf[a] = g
		}
	}
	var optionals, positionals []usageItem
	done := map[*action]bool{}
	for _, a := range p.actions {
		switch {
		case !a.isOption():
			positionals = append(positionals, usageItem{actions: []*action{a}})
		case !done[a]:
			done[a] = true
			item := usageItem{actions: []*action{a}}
			if g := groupOf[a]; g != nil {
				item.required = g.required
				for _, other := range g.actions {
					if !done[other] {
						done[other] = true
						item.actions = append(item.actions, other)
					}
				}
			}
			optionals = append(optionals, item)
		}
	}
	var parts []string
	posStart := -1
	for i, item := range append(optionals, positionals...) {
		start := len(parts)
		if i == len(optionals) {
			posStart = start
		}
		inGroup := len(item.actions) > 1
		for _, a := range item.actions {
			var part string
			switch {
			case !a.isOption():
				part = f.formatArgs(a, a.dest)
			case a.nargs == 0:
				part = a.flags[0]
			default:
				part = a.flags[0] + " " + f.formatArgs(a, strings.ToUpper(a.dest))
			}
			if a.isOption() && !(a.required || item.required || inGroup) {
				part = "[" + part + "]"
			}
			parts = append(parts, part)
		}
		if inGroup {
			open, closing := "[", "]"
			if item.required {
				open, closing = "(", ")"
			}
			parts[start] = open + parts[start]
			for j := start; j < len(parts)-1; j++ {
				parts[j] += " |"
			}
			parts[len(parts)-1] += closing
		}
	}
	if posStart < 0 {
		posStart = len(parts)
	}
	return parts, posStart
}

// metavars is the metavar formatter of HelpFormatter: the name or names an argument shows,
// repeated to the size when it has only one.
func metavars(a *action, def string, size int) []string {
	var names []string
	switch {
	case len(a.metavar) > 0:
		names = a.metavar
	case a.kind == kindParsers:
		names = []string{"{" + strings.Join(a.sub.shown(), ",") + "}"}
	case a.choices != nil:
		names = []string{"{" + strings.Join(a.choices, ",") + "}"}
	default:
		names = []string{def}
	}
	if len(names) == 1 {
		out := make([]string, size)
		for i := range out {
			out[i] = names[0]
		}
		return out
	}
	return names
}

// formatArgs is HelpFormatter._format_args: how an argument shows its values, "N", "[N]",
// "[N ...]", "N [N ...]", "N ..." or one name per value.
func (f *formatter) formatArgs(a *action, def string) string {
	switch a.nargs {
	case nOne:
		return metavars(a, def, 1)[0]
	case nOptional:
		return "[" + metavars(a, def, 1)[0] + "]"
	case nStar:
		m := metavars(a, def, 1)
		if len(m) == 2 {
			return "[" + m[0] + " [" + m[1] + " ...]]"
		}
		return "[" + m[0] + " ...]"
	case nPlus:
		m := metavars(a, def, 2)
		return m[0] + " [" + m[1] + " ...]"
	case nParser:
		return metavars(a, def, 1)[0] + " ..."
	}
	return strings.Join(metavars(a, def, a.nargs), " ")
}

// invocation is HelpFormatter._format_action_invocation: the left column of an argument.
func (f *formatter) invocation(a *action) string {
	switch {
	case !a.isOption():
		return strings.Join(metavars(a, a.dest, 1), " ")
	case a.nargs == 0:
		return strings.Join(a.flags, ", ")
	}
	return strings.Join(a.flags, ", ") + " " + f.formatArgs(a, strings.ToUpper(a.dest))
}

// subActions are the pseudo-actions that list the choices of a subparsers action.
func subActions(a *action) []*action {
	if a.kind != kindParsers {
		return nil
	}
	var subs []*action
	for _, e := range a.sub.entries {
		if !e.hidden {
			subs = append(subs, &action{dest: e.name, metavar: []string{e.name}, help: e.help})
		}
	}
	return subs
}

// action is HelpFormatter._format_action: the left column, the help wrapped into the right
// column, then the choices of a subparsers action one level deeper.
func (f *formatter) action(a *action) string {
	helpPos := min(f.actionMaxLen+2, f.maxHelpPos)
	helpWidth := max(f.width-helpPos, 11)
	actionWidth := helpPos - f.indent - 2
	header := f.invocation(a)
	indentFirst := 0
	pad := strings.Repeat(" ", f.indent)
	switch {
	case a.help == "":
		header = pad + header + "\n"
	case rlen(header) <= actionWidth:
		header = pad + header + strings.Repeat(" ", actionWidth-rlen(header)) + "  "
	default:
		header = pad + header + "\n"
		indentFirst = helpPos
	}
	var b strings.Builder
	b.WriteString(header)
	if pytext.Strip(a.help) != "" {
		for i, line := range pytext.Wrap(collapse(a.help), helpWidth, "", "") {
			if i == 0 {
				b.WriteString(strings.Repeat(" ", indentFirst) + line + "\n")
			} else {
				b.WriteString(strings.Repeat(" ", helpPos) + line + "\n")
			}
		}
	} else if !strings.HasSuffix(header, "\n") {
		b.WriteString("\n")
	}
	f.indent += 2
	for _, sub := range subActions(a) {
		b.WriteString(f.action(sub))
	}
	f.indent -= 2
	return b.String()
}
