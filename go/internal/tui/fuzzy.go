// Copied from lif internal/tui/fuzzy.go at commit d0cd455.

package tui

import "strings"

// fuzzyMatch reports whether query is a (case-insensitive, rune-based) subsequence of target. An
// empty query matches everything.
func fuzzyMatch(query, target string) bool {
	q := []rune(strings.ToLower(query))
	t := []rune(strings.ToLower(target))
	i := 0
	for _, tc := range t {
		if i < len(q) && tc == q[i] {
			i++
		}
	}
	return i == len(q)
}
