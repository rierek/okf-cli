package tagwrite

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"unicode/utf8"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/diffs"
	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

// The registry writer: the one place a TAGS.md is written (Python catalogue.register_tags and the
// helpers below it). The file belongs to the human: okf only inserts entries, never re-renders it.

const (
	// tagsIntro is the text of a TAGS.md that does not exist yet.
	tagsIntro = "# TAGS.md \u2014 Registered Tag Vocabulary\n\n" +
		"Closed vocabulary for concept `tags:`. The `kc/tag/registered` conformance check\n" +
		"(warning; `check --strict` counts it toward the exit code) flags any tag not listed here.\n" +
		"Add a new tag only via `okf tags --register <tag> <description>` \u2014 reuse an existing\n" +
		"tag over minting a near-duplicate. A tag earns its place by aggregating content.\n\n"
	// tagsTableHead is the head of a new table.
	tagsTableHead = "| Tag | Description |\n|-----|-------------|\n"
	// tagDescMax is TAG_DESC_MAX: the longest description of a tag, in characters.
	tagDescMax = 150
)

// refusal is Python's ValueError of the registry writer: an input it refuses before it writes. The
// command reports it as invalid_input (`ERROR: <msg>`); any other error is an I/O failure.
type refusal struct{ msg string }

func (r *refusal) Error() string { return r.msg }

// renderRegistryEntry is Python render_registry_entry: one entry in `kind` form, "table" (a row)
// or "block" (a `### ` heading, an optional `rank:` line and the description). rank is "" for none.
func renderRegistryEntry(kind, value, desc, rank string) string {
	if kind == "table" {
		if rank != "" {
			return fmt.Sprintf("| `%s` | %s | %s |\n", value, rank, desc)
		}
		return fmt.Sprintf("| `%s` | %s |\n", value, desc)
	}
	out := fmt.Sprintf("### `%s`\n", value)
	if rank != "" {
		out += "rank: " + rank + "\n"
	}
	if desc != "" {
		out += desc + "\n"
	}
	return out
}

// splice is Python _splice: text inserted before line index at. The only change to existing text
// is a missing newline on the line before at.
func splice(lines []string, at int, text string) []string {
	if at > 0 && !strings.HasSuffix(lines[at-1], "\n") {
		lines[at-1] += "\n"
	}
	out := make([]string, 0, len(lines)+1)
	out = append(out, lines[:at]...)
	out = append(out, text)
	return append(out, lines[at:]...)
}

// blankLine is "\n" when the line before at holds text, so the inserted entry gets a separating
// blank line (Python _blank_before, which tests that the previous line is not blank).
func blankLine(lines []string, at int) string {
	if at > 0 && pytext.Strip(lines[at-1]) != "" {
		return "\n"
	}
	return ""
}

// insertTag is Python _insert_tag: text with one new entry inserted, in format, keeping every
// existing byte.
//
// A new entry lands only among entries of its own form: a block in the middle of a table would tear
// the table. A new block goes to the end of the last table's section: straight after the table it
// would swallow the following prose as its description (a block runs to the next heading). A new
// table goes before the first block: any later spot lies inside a block's span.
//
// Inserted lines always end in \n, so a CRLF file gets mixed line endings (Python limit, kept).
func insertTag(text, tag, desc, format string) string {
	lines := pytext.SplitLines(text, true)
	scan := catalogue.ScanRegistry(lines)
	var same, other []catalogue.RegistryEntry
	for _, e := range scan.Entries {
		if e.Kind == format {
			same = append(same, e)
		} else {
			other = append(other, e)
		}
	}
	var next *catalogue.RegistryEntry
	folded := pytext.Casefold(tag)
	for i := range same {
		if pytext.Casefold(same[i].Value) > folded {
			next = &same[i]
			break
		}
	}
	var at int
	var ins string
	if format == "table" {
		row := renderRegistryEntry("table", tag, desc, "")
		switch {
		case next != nil:
			at, ins = next.Start, row
		case len(same) > 0:
			at, ins = same[len(same)-1].Start+1, row
		case len(other) > 0:
			at = other[0].Start
			ins = blankLine(lines, at) + tagsTableHead + row + "\n"
		default:
			at = len(lines)
			ins = blankLine(lines, at) + tagsTableHead + row
		}
	} else {
		block := renderRegistryEntry("block", tag, desc, "")
		switch {
		case next != nil:
			at, ins = next.Start, block+"\n"
		case len(same) > 0:
			last := same[len(same)-1]
			at = last.End
			for at > last.Start+1 && pytext.Strip(lines[at-1]) == "" {
				at--
			}
			ins = "\n" + block
		default:
			at = len(lines)
			if len(other) > 0 {
				last := other[len(other)-1].Start
				for _, h := range scan.Headings {
					if h > last {
						at = h
						break
					}
				}
			}
			ins = blankLine(lines, at) + block
			if at < len(lines) {
				ins += "\n"
			}
		}
	}
	return strings.Join(splice(lines, at, ins), "")
}

// registerEntries is Python register_tags: the (tag, description) pairs added to TAGS.md, which is
// created when absent. It returns the tags added, in the order given, and those that were already
// registered (they keep their description). Every description is validated before anything is
// written: non-empty after trimming, at most tagDescMax characters, one line, no `|` (the `|` ban
// holds in both forms so `registry convert --to table` stays lossless). A refused input is a
// *refusal. Entries go in sorted by case-folded tag, in the form `.okf.toml` registry_format names
// (default table).
func registerEntries(root string, entries [][]string) (added, already []string, err error) {
	for _, e := range entries {
		tag, desc := e[0], pytext.Strip(e[1])
		switch {
		case desc == "":
			return nil, nil, &refusal{fmt.Sprintf("tag %s: description must not be empty", pytext.ReprStr(tag))}
		case utf8.RuneCountInString(desc) > tagDescMax:
			return nil, nil, &refusal{fmt.Sprintf("tag %s: description is %d chars, limit is %d",
				pytext.ReprStr(tag), utf8.RuneCountInString(desc), tagDescMax)}
		case strings.ContainsAny(desc, "|\n\r"):
			return nil, nil, &refusal{fmt.Sprintf("tag %s: description must be one line without '|'", pytext.ReprStr(tag))}
		}
	}
	p := filepath.Join(root, "TAGS.md")
	config, err := catalogue.LoadConfig(root)
	if err != nil {
		return nil, nil, err
	}
	format := "table"
	if f, ok := config["registry_format"].(string); ok {
		format = f
	}
	text := tagsIntro
	if info, statErr := os.Stat(p); statErr == nil && info.Mode().IsRegular() {
		stored, valid, readErr := catalogue.ReadFileVerbatim(p)
		if readErr != nil {
			return nil, nil, readErr
		}
		if !valid {
			return nil, nil, &refusal{"TAGS.md is not valid UTF-8; nothing written"}
		}
		text = stored
	}
	registered := map[string]bool{}
	for _, e := range catalogue.ScanRegistry(pytext.SplitLines(text, true)).Entries {
		registered[e.Value] = true
	}
	descOf := map[string]string{}
	listed := map[string]bool{}
	for _, e := range entries {
		tag := e[0]
		if !listed[tag] && registered[tag] {
			already = append(already, tag)
		}
		listed[tag] = true
		if _, dup := descOf[tag]; !registered[tag] && !dup {
			added = append(added, tag)
			descOf[tag] = pytext.Strip(e[1])
		}
	}
	if len(added) == 0 {
		return nil, already, nil
	}
	sorted := append([]string(nil), added...)
	sort.SliceStable(sorted, func(i, j int) bool { return pytext.Casefold(sorted[i]) < pytext.Casefold(sorted[j]) })
	for _, tag := range sorted {
		text = insertTag(text, tag, descOf[tag], format)
	}
	if err := diffs.WriteFileVerbatim(p, text); err != nil {
		return nil, nil, err
	}
	return added, already, nil
}
