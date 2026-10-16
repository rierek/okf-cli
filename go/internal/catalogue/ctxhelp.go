package catalogue

import (
	"os"
	"sort"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

// CtxSlugs is Python ctx_slugs: the slugs of the ctx files under <root>/_ctx (every .md that is
// not a reserved name, minus the extension), sorted by slug. Empty when the directory is missing.
func CtxSlugs(root string) ([]string, error) {
	dir := Join(root, CtxDir)
	if !isDir(dir) {
		return []string{}, nil
	}
	names, err := RealFS.ListDir(dir)
	if err != nil {
		return nil, err
	}
	slugs := []string{}
	for _, fn := range names {
		if strings.HasSuffix(fn, ".md") && !IsReserved(fn) {
			slugs = append(slugs, strings.TrimSuffix(fn, ".md"))
		}
	}
	sort.Strings(slugs) // by slug, not by file name: "a-b" sorts before "a.md" but after "a"
	return slugs, nil
}

// Tokens is Python _tokens: the token estimate of a text, (chars + 3) / 4. chars is the number of
// characters (code points, Python len(); utf8.RuneCountInString), never negative.
func Tokens(chars int) int { return (chars + 3) / 4 }

// CtxSameFile is Python _ctx_same_file: whether two absolute paths name one file. They do when
// they are equal, or when they differ only in case and are the same existing file (a
// case-insensitive file system). Like Python's os.path.samefile, it returns the stat error when a
// exists and b does not.
func CtxSameFile(a, b string) (bool, error) {
	if a == b {
		return true, nil
	}
	if pytext.Lower(a) != pytext.Lower(b) {
		return false, nil
	}
	ia, err := os.Stat(a)
	if err != nil {
		return false, nil // os.path.exists(a) is false
	}
	ib, err := os.Stat(b)
	if err != nil {
		return false, err
	}
	return os.SameFile(ia, ib), nil
}
