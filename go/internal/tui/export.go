package tui

import (
	"fmt"
	"strings"
)

// exportText renders the buffer entries for the hand-off (SPEC D13): the header line
// `Fundstellen aus okf (<n>)`, then one block per entry in buffer order: `## <title>`,
// `@<absolute path>`, a line with type, bundle and tags, the description, and the note under a `## Notes` heading.
// A field an entry does not have leaves its line out. The text ends with a newline and never with
// an Enter: the target pane gets it as typed text.
func exportText(entries []bufferEntry) string {
	var b strings.Builder
	fmt.Fprintf(&b, "Fundstellen aus okf (%d)\n", len(entries))
	for _, e := range entries {
		b.WriteString("\n## " + e.Title + "\n@" + e.Abs + "\n")
		var meta []string
		if e.Type != "" {
			meta = append(meta, "type: "+e.Type)
		}
		if e.Bundle != "" {
			meta = append(meta, "bundle: "+e.Bundle)
		}
		if len(e.Tags) > 0 {
			meta = append(meta, "tags: "+strings.Join(e.Tags, ", "))
		}
		if len(meta) > 0 {
			b.WriteString(strings.Join(meta, " · ") + "\n")
		}
		if e.Description != "" {
			b.WriteString(e.Description + "\n")
		}
		if e.Note != "" {
			b.WriteString("\n## Notes\n\n" + e.Note)
			if !strings.HasSuffix(e.Note, "\n") {
				b.WriteString("\n")
			}
		}
	}
	return b.String()
}
