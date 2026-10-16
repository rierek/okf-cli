package rewrite

import (
	"fmt"
	"os"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/diffs"
)

// printFixReport is Python _print_fix_report followed by the closing line: every diff text as it
// is, the files that are not valid UTF-8, then the summary printed from format and args.
func printFixReport(files []diffs.FileDiff, skipped []string, format string, args ...any) error {
	var sb strings.Builder
	diffs.PrintFiles(&sb, files)
	for _, rel := range skipped {
		fmt.Fprintf(&sb, "skipped        %s  (not valid UTF-8)\n", rel)
	}
	fmt.Fprintf(&sb, format, args...)
	_, err := os.Stdout.WriteString(sb.String())
	return err
}
