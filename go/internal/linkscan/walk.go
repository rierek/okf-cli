package linkscan

import (
	"iter"
	"os"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
)

// IterRenameScanMd is every .md file the rename inbound scan must see, as absolute paths in scan
// order. The error is the failure to list the root's bundles; the walk itself skips what it
// cannot read.
//
// It is the traversal of a root-level walk under catalogue.PruneWalkDirs (dot-directories and
// node_modules out, `_`-prefixed staging directories and root-level files in, unlike
// catalogue.IterAllMd) plus a second pass over each symlinked bundle, because a walk does not
// descend into a symlinked subdirectory and catalogue bundles are symlinks. Either half alone
// leaves a stale reference behind: the root walk misses the mounts, a per-bundle walk misses
// root-level staging. No path is yielded twice: the root walk never enters a symlinked bundle.
//
// It is deliberately wider than the reporting surfaces: staging directories, root-level files and
// `assets/` are all rewritten. A stale reference in a file `wikilinks` never lists is still a
// stale reference, and the markdown half of the same rename already reaches every one of them;
// pruning here would leave a file with its markdown link updated and its wikilink dangling in the
// same line.
func IterRenameScanMd(root string) (iter.Seq[string], error) {
	bundles, err := catalogue.ListBundles(root)
	if err != nil {
		return nil, err
	}
	starts := []string{root}
	for _, b := range bundles {
		p := catalogue.Join(root, b)
		if info, err := os.Lstat(p); err == nil && info.Mode()&os.ModeSymlink != 0 {
			starts = append(starts, p)
		}
	}
	return func(yield func(string) bool) {
		stop := false
		for _, start := range starts {
			catalogue.SortedWalk(start, func(dirpath string, dirnames, filenames []string) []string {
				if stop {
					return nil
				}
				for _, fn := range filenames {
					if strings.HasSuffix(fn, ".md") && !yield(catalogue.Join(dirpath, fn)) {
						stop = true
						return nil
					}
				}
				return catalogue.PruneWalkDirs(dirnames)
			})
			if stop {
				return
			}
		}
	}, nil
}
