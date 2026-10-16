package linkscan

import (
	"os"
	"path/filepath"
	"slices"
	"testing"
)

func TestIterRenameScanMd(t *testing.T) {
	mounted := mkTree(t, map[string]string{"m1/x.md": "x\n", "m1/sub/y.md": "y\n"})
	root := mkTree(t, map[string]string{
		"README.md":            "root-level file\n",
		"notes.md":             "root-level file\n",
		"notes.txt":            "not markdown\n",
		"_stage/s.md":          "staging directory\n",
		"b1/a.md":              "bundle\n",
		"b1/sub/deep.md":       "bundle\n",
		".git/x.md":            "pruned\n",
		".hidden/h.md":         "pruned\n",
		"node_modules/n.md":    "pruned\n",
		"b1/node_modules/z.md": "pruned\n",
		"b1/.git/c.md":         "pruned\n",
	})
	// A symlinked bundle is invisible to the root walk and is walked on its own; a symlinked
	// directory that is no bundle (a leading underscore) is not.
	if err := os.Symlink(filepath.Join(mounted, "m1"), filepath.Join(root, "m1")); err != nil {
		t.Skip("no symlinks:", err)
	}
	if err := os.Symlink(filepath.Join(mounted, "m1"), filepath.Join(root, "_mount")); err != nil {
		t.Fatal(err)
	}
	seq, err := IterRenameScanMd(root)
	if err != nil {
		t.Fatal(err)
	}
	var want []string
	for _, rel := range []string{"README.md", "notes.md", "_stage/s.md", "b1/a.md", "b1/sub/deep.md", "m1/x.md", "m1/sub/y.md"} {
		want = append(want, filepath.Join(root, rel))
	}
	if got := slices.Collect(seq); !slices.Equal(got, want) {
		t.Errorf("IterRenameScanMd =\n%v\nwant\n%v", got, want)
	}
	// The consumer may stop early.
	for range seq {
		break
	}
}
