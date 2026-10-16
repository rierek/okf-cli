package linkscan

import (
	"os"
	"path/filepath"
	"slices"
	"testing"
)

// mkTree writes files (path relative to the returned root, text) into a fresh temporary
// directory and returns that directory.
func mkTree(t *testing.T, files map[string]string) string {
	t.Helper()
	root := t.TempDir()
	for rel, text := range files {
		ap := filepath.Join(root, rel)
		if err := os.MkdirAll(filepath.Dir(ap), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(ap, []byte(text), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	return root
}

func TestResolveMdLink(t *testing.T) {
	const root, src = "/cat", "/cat/b/x.md"
	for _, tc := range []struct {
		raw  string
		want string // "" for no file link
	}{
		{"a.md", "/cat/b/a.md"},
		{"./a.md", "/cat/b/a.md"},
		{"../c/d.md", "/cat/c/d.md"},
		{"../../../out.md", "/out.md"},
		{"/b/a.md", "/cat/b/a.md"}, // a leading slash is the scan root, not the bundle
		{"///b/a.md", "/cat/b/a.md"},
		{"/", "/cat"},
		{"a.md#top", "/cat/b/a.md"},
		{"a.md?x=1#y", "/cat/b/a.md"},
		{" a.md ", "/cat/b/a.md"},
		{"HTTP://x/a.md", "/cat/b/HTTP:/x/a.md"}, // only lower-case schemes are URLs
		{"#top", ""},
		{"", ""},
		{"   ", ""},
		{"https://x.org/a.md", ""},
		{"http://x", ""},
		{"ftp://h/p", ""},
		{"a+b.c-d://x", ""},
		{"mailto:a@b", ""},
	} {
		got, ok, err := ResolveMdLink(root, src, tc.raw)
		if err != nil || got != tc.want || ok != (tc.want != "") {
			t.Errorf("ResolveMdLink(%q) = %q, %v, %v; want %q", tc.raw, got, ok, err, tc.want)
		}
	}
}

func TestBuildRefMatrix(t *testing.T) {
	for _, tc := range []struct {
		name   string
		files  map[string]string
		target string
		want   []Ref
	}{
		{"same directory and subdirectory",
			map[string]string{
				"docs/arch.md": "# Arch\n", "docs/overview.md": "see [arch](arch.md)\n",
				"README.md": "see [arch](docs/arch.md)\n"},
			"docs/arch.md", []Ref{{"README.md", "docs/arch.md"}, {"docs/overview.md", "arch.md"}}},
		{"the leading slash is the catalogue root",
			map[string]string{"docs/arch.md": "# Arch\n", "docs/x.md": "see [a](/docs/arch.md)\n"},
			"docs/arch.md", []Ref{{"docs/x.md", "/docs/arch.md"}}},
		{"the leading slash is the scan root, not the bundle root",
			map[string]string{"b1/x.md": "# X\n", "b1/foo.md": "[x](/b1/x.md)\n", "b2/bar.md": "[x](/b1/x.md)\n"},
			"b1/x.md", []Ref{{"b1/foo.md", "/b1/x.md"}, {"b2/bar.md", "/b1/x.md"}}},
		{"URL, mailto and fenced link are ignored, an anchor link counts",
			map[string]string{
				"docs/arch.md": "# Arch\n",
				"docs/x.md": "[ext](https://arch.md)\n[mail](mailto:arch.md)\n[frag](arch.md#top)\n" +
					"```\n[fenced](arch.md)\n```\n"},
			"docs/arch.md", []Ref{{"docs/x.md", "arch.md#top"}}},
		{".git and node_modules are pruned",
			map[string]string{
				"docs/arch.md": "# Arch\n", ".git/x.md": "[a](../docs/arch.md)\n",
				"node_modules/y.md": "[a](../docs/arch.md)\n", "docs/.git/z.md": "[a](../arch.md)\n"},
			"docs/arch.md", []Ref{}},
		{"no inbound link", map[string]string{"docs/arch.md": "# Arch\n"}, "docs/arch.md", []Ref{}},
		{"a link in a sync span is the owner's, the live one counts",
			map[string]string{"b/t.md": "# T\n", "b/sync.md": "# S\n\n" + syncBlock + "\n[live](t.md)\n"},
			"b/t.md", []Ref{{"b/sync.md", "t.md"}}},
		{"a link that is only a comment, code or an indented block is no reference",
			map[string]string{
				"b/t.md": "# T\n",
				"b/c.md": "<!-- [a](t.md) -->\n%% [b](t.md) %%\n`[c](t.md)`\n\n    [d](t.md)\n\n```\n[e](t.md)\n```\n"},
			"b/t.md", []Ref{}},
	} {
		t.Run(tc.name, func(t *testing.T) {
			root := mkTree(t, tc.files)
			got, err := BuildRefMatrix(root, filepath.Join(root, tc.target))
			if err != nil {
				t.Fatal(err)
			}
			if !slices.Equal(got, tc.want) {
				t.Errorf("BuildRefMatrix = %v, want %v", got, tc.want)
			}
		})
	}
}

func TestRefMatrixCaseVariants(t *testing.T) {
	root := mkTree(t, map[string]string{
		"b/same.md":     "# S\n",
		"b/twin.md":     "[x](Same.md) [y](same.md) [z](SAME.md)\n",
		"b/dangling.md": "[g](gone.md)\n",
	})
	// Two names for one inode stand in for a case-insensitive filesystem.
	if err := os.Link(filepath.Join(root, "b/same.md"), filepath.Join(root, "b/Same.md")); err != nil {
		t.Skip("no hard links:", err)
	}
	got, err := BuildRefMatrix(root, filepath.Join(root, "b/same.md"))
	want := []Ref{{"b/twin.md", "Same.md"}, {"b/twin.md", "same.md"}}
	if err != nil || !slices.Equal(got, want) {
		t.Errorf("BuildRefMatrix = %v, %v; want %v", got, err, want)
	}
	// A near miss of an existing file whose target does not exist fails on the target's stat, as
	// os.path.samefile does; a near miss that dangles on both sides is skipped before it.
	if _, err := BuildRefMatrix(root, filepath.Join(root, "b/SAME.md")); err == nil {
		t.Error("a case near miss of a missing target must fail")
	}
	if got, err := BuildRefMatrix(root, filepath.Join(root, "b/GONE.md")); err != nil || len(got) != 0 {
		t.Errorf("BuildRefMatrix of a dangling near miss = %v, %v; want nothing", got, err)
	}
}

func TestFileMdLinks(t *testing.T) {
	root := mkTree(t, map[string]string{"b/f.md": "---\ntype: Concept\nrelated: \"[fm](h.md)\"\n---\n" +
		"[live1](a.md)\n`[inline](b.md)` <!-- [comment](c.md) --> %% [percent](d.md) %%\n\n" +
		"```\n[fenced](e.md)\n```\n\n    [indented](f.md)\n\n[live2]( g.md#x )\n" +
		"[ext](https://x.org) [m](mailto:a@b) [t](#top)\n[nested](n<!--c-->.md)\n"})
	got, err := FileMdLinks(root, filepath.Join(root, "b/f.md"))
	b := filepath.Join(root, "b")
	// raw is cut from the original text: a masked span inside a target leaves no NUL in it.
	want := []Link{{"h.md", filepath.Join(b, "h.md")}, {"a.md", filepath.Join(b, "a.md")},
		{" g.md#x ", filepath.Join(b, "g.md")}, {"n<!--c-->.md", filepath.Join(b, "n<!--c-->.md")}}
	if err != nil || !slices.Equal(got, want) {
		t.Errorf("FileMdLinks = %v, %v; want %v", got, err, want)
	}
}

func TestOutboundLinks(t *testing.T) {
	root := mkTree(t, map[string]string{
		"d/a.md": "[x]( ../e/t.md?q ) [m](mailto:a@b) [g](gone.md#x) [u](https://u.org) [r](/e/t.md)\n",
		"e/t.md": "t\n"})
	got, err := OutboundLinks(root, filepath.Join(root, "d/a.md"))
	tgt := filepath.Join(root, "e/t.md")
	want := []Outbound{{" ../e/t.md?q ", tgt, true}, {"gone.md#x", filepath.Join(root, "d/gone.md"), false},
		{"/e/t.md", tgt, true}}
	if err != nil || !slices.Equal(got, want) {
		t.Errorf("OutboundLinks = %v, %v; want %v", got, err, want)
	}
	// The scan and the matrix share one resolution.
	var links []SourceLink
	for l, err := range IterMdLinks(root) {
		if err != nil {
			t.Fatal(err)
		}
		links = append(links, l)
	}
	if len(links) != 3 || links[0].Source != "d/a.md" || links[0].Raw != " ../e/t.md?q " || links[0].Resolved != tgt {
		t.Errorf("IterMdLinks = %v", links)
	}
}

func TestRefsDisplay(t *testing.T) {
	root, home := t.TempDir(), t.TempDir()
	t.Setenv("HOME", home)
	for _, tc := range []struct{ p, want string }{
		{filepath.Join(root, "b/x.md"), "b/x.md"},
		{filepath.Join(root, "b/../c/y.md"), "c/y.md"},
		{root, "."},
		{filepath.Join(home, "n/z.md"), "~/n/z.md"},
		{"/etc/hosts", "/etc/hosts"},
		{filepath.Join(root, "../elsewhere.md"), filepath.Join(root, "../elsewhere.md")},
	} {
		if got, err := RefsDisplay(root, tc.p); err != nil || got != tc.want {
			t.Errorf("RefsDisplay(%q) = %q, %v; want %q", tc.p, got, err, tc.want)
		}
	}
}

func TestScanFailures(t *testing.T) {
	root := t.TempDir()
	if _, err := IterRenameScanMd(filepath.Join(root, "missing")); err == nil {
		t.Error("a root that cannot be listed must fail")
	}
	// A dangling link named like a concept is listed as a file and cannot be read.
	if err := os.Symlink(filepath.Join(root, "nowhere"), filepath.Join(root, "bad.md")); err != nil {
		t.Skip("no symlinks:", err)
	}
	if _, err := BuildRefMatrix(root, filepath.Join(root, "x.md")); err == nil {
		t.Error("an unreadable file must fail the scan")
	}
	if _, err := OutboundLinks(root, filepath.Join(root, "bad.md")); err == nil {
		t.Error("an unreadable file must fail OutboundLinks")
	}
}
