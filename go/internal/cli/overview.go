package cli

import (
	"slices"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

// groupOrder is Python's _GROUP_ORDER: the order of the purposes in the overview.
var groupOrder = [...]string{"navigation", "search", "tags", "maintenance"}

// RenderOverview is render_command_overview: "commands by purpose:", then each group with its
// commands by name, every summary wrapped to width behind the name, and, with footer, a pointer
// to `okf <command> --help`. Hidden entries are left out. It is the epilog of okf --help
// (width 96, footer) and the command section of prime. The width must be positive.
func RenderOverview(entries []Entry, width int, footer bool) string {
	lines := []string{"commands by purpose:"}
	for _, group := range groupOrder {
		var members []Entry
		for _, e := range entries {
			if e.Group == group && !e.Hidden {
				members = append(members, e)
			}
		}
		if len(members) == 0 {
			continue
		}
		slices.SortFunc(members, func(a, b Entry) int { return strings.Compare(a.Name, b.Name) })
		lines = append(lines, "  "+group+":")
		for _, e := range members {
			lead := "    " + e.Name + strings.Repeat(" ", max(16-rlen(e.Name), 0)) + " "
			lines = append(lines, pytext.Fill(e.Summary, width, lead, strings.Repeat(" ", 21)))
		}
	}
	if footer {
		lines = append(lines, "", "run `okf <command> --help` for one command's options.")
	}
	return strings.Join(lines, "\n")
}
