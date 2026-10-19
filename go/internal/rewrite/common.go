package rewrite

import (
	"fmt"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/diffs"
	"nas/volume1/data/git/okf-tools/go/internal/stdio"
)

// printFixReport is Python _print_fix_report followed by the closing line: every diff text as it
// is, the files that are not valid UTF-8, then tail (the closing lines).
func printFixReport(files []diffs.FileDiff, skipped []string, tail string) {
	var sb strings.Builder
	diffs.PrintFiles(&sb, files)
	for _, rel := range skipped {
		fmt.Fprintf(&sb, "skipped        %s  (not valid UTF-8)\n", rel)
	}
	sb.WriteString(tail)
	stdio.Print(sb.String())
}
