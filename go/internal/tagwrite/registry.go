package tagwrite

import (
	"fmt"
	"os"
	"path/filepath"
	"slices"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/cli"
	"nas/volume1/data/git/okf-tools/go/internal/diffs"
	"nas/volume1/data/git/okf-tools/go/internal/envelope"
	"nas/volume1/data/git/okf-tools/go/internal/okferr"
	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

var (
	rankLineRE  = pytext.Regexp(`^rank:\s*(` + strings.Join(catalogue.RegistryRanks, "|") + `)\s*$`)
	separatorRE = pytext.Regexp(`^\|[\s:|-]+\|?\s*$`)
)

// registryHeads are the table heads of a converted registry, by file and by whether any entry has a rank.
var registryHeads = map[[2]string]string{
	{"TAGS.md", "plain"}:   tagsTableHead,
	{"TAGS.md", "ranked"}:  "| Tag | rank | Description |\n|-----|:----:|-------------|\n",
	{"TYPES.md", "plain"}:  "| type | Meaning |\n|------|---------|\n",
	{"TYPES.md", "ranked"}: "| type | rank | Meaning |\n|------|:----:|---------|\n",
}

func registerRegistry(app *cli.App) {
	app.Attach("registry", cli.Spec{
		Verbs: []cli.Verb{{
			Name: "convert",
			Help: "rewrite every entry of one registry file in the target form",
			Description: "rewrite every entry of <root>/TAGS.md or <root>/TYPES.md in table or block form; " +
				"text outside the entries stays byte for byte; previews a unified diff unless --apply",
			Args: []cli.Arg{
				{Dest: "file", Choices: []string{"TAGS.md", "TYPES.md"},
					Help: "registry file under the catalogue root (types_source is not followed)"},
				{Flags: []string{"--to"}, Required: true, Choices: catalogue.RegistryFormats, Help: "target form"},
				{Flags: []string{"--apply"}, Action: cli.StoreTrue, Help: "write changes (default: dry-run preview only)"},
				cli.JSON(),
			},
		}},
		VerbMetavar: "VERB",
		VerbHelp:    "registry verb",
		Handler:     runRegistry,
	})
}

// refuse is Python _refuse: the conversion stops at line index with `<file>:<line>: <message>`.
func refuse(filename string, lineIndex int, format string, args ...any) error {
	return okferr.Newf(okferr.InvalidInput, "%s:%d: %s", filename, lineIndex+1, fmt.Sprintf(format, args...))
}

// entryFields is Python _entry_fields: the rank (or "") and the description lines of one entry.
func entryFields(lines []string, e catalogue.RegistryEntry) (rank string, desc []string) {
	if e.Kind == "table" {
		cells := strings.Split(strings.Trim(pytext.Strip(lines[e.Start]), "|"), "|")
		var text string
		if len(cells) >= 3 && slices.Contains(catalogue.RegistryRanks, pytext.Strip(cells[1])) {
			rank, text = pytext.Strip(cells[1]), pytext.Strip(strings.Join(cells[2:], "|"))
		} else if len(cells) > 1 {
			text = pytext.Strip(strings.Join(cells[1:], "|"))
		}
		if text != "" {
			desc = []string{text}
		}
		return rank, desc
	}
	for _, l := range lines[e.Start+1 : e.End] {
		if s := pytext.Strip(l); s != "" {
			desc = append(desc, s)
		}
	}
	if len(desc) > 0 {
		if m := rankLineRE.FindStringSubmatch(desc[0]); m != nil {
			rank, desc = m[1], desc[1:]
		}
	}
	return rank, desc
}

// tableRuns is Python _table_runs: the maximal runs [start, end) of non-fenced lines that start with
// `|` and hold a table entry.
func tableRuns(lines []string, scan catalogue.RegistryScan) [][2]int {
	starts := map[int]bool{}
	for _, e := range scan.Entries {
		if e.Kind == "table" {
			starts[e.Start] = true
		}
	}
	var runs [][2]int
	for i := 0; i < len(lines); {
		if scan.Fenced[i] || !strings.HasPrefix(lines[i], "|") {
			i++
			continue
		}
		j := i
		for j < len(lines) && !scan.Fenced[j] && strings.HasPrefix(lines[j], "|") {
			j++
		}
		for k := i; k < j; k++ {
			if starts[k] {
				runs = append(runs, [2]int{i, j})
				break
			}
		}
		i = j
	}
	return runs
}

// toBlock is Python _to_block: every table run replaced by block entries. It returns the lines and
// the number of entries rewritten; the first thing it cannot convert safely is a refusal and nothing
// is returned.
func toBlock(lines []string, filename string) ([]string, int, error) {
	scan := catalogue.ScanRegistry(lines)
	entries := map[int]catalogue.RegistryEntry{}
	for _, e := range scan.Entries {
		if e.Kind == "table" {
			entries[e.Start] = e
		}
	}
	runs := tableRuns(lines, scan)
	type plan struct {
		a, b int
		text string
		n    int
	}
	var plans []plan
	for n, run := range runs {
		a, b := run[0], run[1]
		_, headEntry := entries[a]
		for i := a; i < b; i++ {
			if _, ok := entries[i]; ok {
				continue
			}
			isHead := (i == a && b-a > 1 && separatorRE.MatchString(lines[a+1])) ||
				(i == a+1 && !headEntry && separatorRE.MatchString(lines[i]))
			if !isHead {
				return nil, 0, refuse(filename, i, "table mixes registry rows with other rows; convert it by hand")
			}
		}
		// Text after the table would become part of the last block (a block runs to the next
		// heading); the next table run is fine, it turns into blocks too.
		limit := len(lines)
		if h := slices.IndexFunc(scan.Headings, func(h int) bool { return h >= b }); h >= 0 {
			limit = scan.Headings[h]
		}
		if n+1 < len(runs) {
			limit = min(limit, runs[n+1][0])
		}
		for i := b; i < limit; i++ {
			if pytext.Strip(lines[i]) != "" {
				return nil, 0, refuse(filename, i, "text after the table would become part of the last block; "+
					"move it above the table or under its own heading")
			}
		}
		var blocks []string
		for i := a; i < b; i++ {
			e, ok := entries[i]
			if !ok {
				continue
			}
			rank, desc := entryFields(lines, e)
			if len(desc) > 0 && strings.Contains(desc[0], "|") {
				return nil, 0, refuse(filename, i, "row `%s` has more than one description cell; convert it by hand", e.Value)
			}
			text := ""
			if len(desc) > 0 {
				text = desc[0]
			}
			blocks = append(blocks, renderRegistryEntry("block", e.Value, text, rank))
		}
		plans = append(plans, plan{a, b, strings.Join(blocks, "\n"), len(blocks)})
	}
	total := 0
	for k := len(plans) - 1; k >= 0; k-- {
		p := plans[k]
		lines = slices.Replace(lines, p.a, p.b, p.text)
		total += p.n
	}
	return lines, total, nil
}

// toTable is Python _to_table: every run of adjacent block entries replaced by one table.
func toTable(lines []string, filename string) ([]string, int, error) {
	scan := catalogue.ScanRegistry(lines)
	var groups [][]catalogue.RegistryEntry
	count := 0
	for _, e := range scan.Entries {
		if e.Kind != "block" {
			continue
		}
		count++
		if n := len(groups); n > 0 && groups[n-1][len(groups[n-1])-1].End == e.Start {
			groups[n-1] = append(groups[n-1], e)
		} else {
			groups = append(groups, []catalogue.RegistryEntry{e})
		}
	}
	type plan struct {
		start, stop int
		text        string
	}
	var plans []plan
	for _, group := range groups {
		type row struct{ value, desc, rank string }
		rows := make([]row, len(group))
		ranked := false
		for i, e := range group {
			rank, desc := entryFields(lines, e)
			if len(desc) > 1 {
				return nil, 0, refuse(filename, e.Start, "block `%s` has a multi-line description; a table cell holds one line", e.Value)
			}
			if len(desc) > 0 && strings.Contains(desc[0], "|") {
				return nil, 0, refuse(filename, e.Start, "block `%s` description contains '|'", e.Value)
			}
			rows[i] = row{value: e.Value, rank: rank}
			if len(desc) > 0 {
				rows[i].desc = desc[0]
			}
			ranked = ranked || rank != ""
		}
		last := group[len(group)-1]
		stop := last.End
		for stop > last.Start+1 && pytext.Strip(lines[stop-1]) == "" {
			stop--
		}
		start := group[0].Start
		head := registryHeads[[2]string{filename, "plain"}]
		if ranked {
			head = registryHeads[[2]string{filename, "ranked"}]
		}
		if start > 0 && pytext.Strip(lines[start-1]) != "" {
			head = "\n" + head
		}
		var text strings.Builder
		text.WriteString(head)
		for _, r := range rows {
			rank := ""
			if ranked {
				rank = r.rank
				if rank == "" {
					rank = "\u2014"
				}
			}
			text.WriteString(renderRegistryEntry("table", r.value, r.desc, rank))
		}
		plans = append(plans, plan{start, stop, text.String()})
	}
	for k := len(plans) - 1; k >= 0; k-- {
		p := plans[k]
		lines = slices.Replace(lines, p.start, p.stop, p.text)
	}
	return lines, count, nil
}

// convertRegistry is Python convert_registry: the new text and the number of entries rewritten.
// Text outside the converted entries stays byte for byte; every refusal comes before anything is
// returned.
func convertRegistry(text, filename, to string) (string, int, error) {
	lines := pytext.SplitLines(text, true)
	var n int
	var err error
	if to == "block" {
		lines, n, err = toBlock(lines, filename)
	} else {
		lines, n, err = toTable(lines, filename)
	}
	if err != nil {
		return "", 0, err
	}
	return strings.Join(lines, ""), n, nil
}

// runRegistry is Python cmd_registry (the one verb, convert).
func runRegistry(root string, a *cli.Args) (any, error) {
	file, to := a.String("file"), a.String("to")
	p := filepath.Join(root, file)
	if info, err := os.Stat(p); err != nil || !info.Mode().IsRegular() {
		return nil, okferr.Newf(okferr.NotFound, "%s not found under %s", file, root)
	}
	old, valid, err := catalogue.ReadFileVerbatim(p)
	if err != nil {
		return nil, err
	}
	if !valid {
		return nil, okferr.Newf(okferr.InvalidInput, "%s is not valid UTF-8", file)
	}
	text, n, err := convertRegistry(old, file, to)
	if err != nil {
		return nil, err
	}
	files := diffs.UnifiedDiffs([]diffs.PlanEntry{planEntry(file, old, text)}, nil)
	apply := a.Bool("apply")
	if apply && text != old {
		if err := diffs.WriteFileVerbatim(p, text); err != nil {
			return nil, err
		}
	}
	if a.JSON {
		return envelope.O("file", file, "to", to, "applied", apply, "converted", n, "files", diffData(files)), nil
	}
	w := newOut()
	defer w.Flush()
	printDiffs(w, files)
	plural, verb := "ies", "would rewrite"
	if n == 1 {
		plural = "y"
	}
	if apply {
		verb = "rewrote"
	}
	fmt.Fprintf(w, "registry convert: %d entr%s in %s %s as %s\n", n, plural, file, verb, to)
	return nil, nil
}
