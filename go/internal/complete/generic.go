package complete

import (
	"fmt"
	"os"
	"os/exec"
	"slices"
	"sort"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/frontmatter"
	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

// The generic completers, one per kind of value, with the semantics of their Python counterparts
// in cli/okf/parser_support.py and cli/okf/ctx.py. The catalogue ones read the root of the
// context and offer nothing without one.

// Tags are the tags in use, most used first, the usage count as the description (_complete_tags).
func Tags(c Context) []Candidate {
	if c.Root == "" {
		return nil
	}
	counts, err := catalogue.AllTags(c.Root)
	if err != nil {
		return nil
	}
	var out []Candidate
	for _, t := range counts.Ranked() {
		out = append(out, Candidate{t.Tag, fmt.Sprintf("concepts: %d", t.Count)})
	}
	return out
}

// Bundles are the bundles of the catalogue (_complete_bundles).
func Bundles(c Context) []Candidate {
	if c.Root == "" {
		return nil
	}
	return values(bundles(c.Root))
}

// Scopes are every <bundle> and every <bundle>/<subdir> that holds a concept (_complete_scopes).
func Scopes(c Context) []Candidate {
	if c.Root == "" {
		return nil
	}
	set := map[string]bool{}
	for _, b := range bundles(c.Root) {
		set[b] = true
		for id := range catalogue.IterConcepts(catalogue.Join(c.Root, b), true) {
			parts := strings.Split(id, "/")
			parts = parts[:len(parts)-1]
			for i := 1; i <= len(parts); i++ {
				set[strings.Join(append([]string{b}, parts[:i]...), "/")] = true
			}
		}
	}
	out := make([]string, 0, len(set))
	for s := range set {
		out = append(out, s)
	}
	sort.Strings(out) // UTF-8 byte order is code point order, as Python's sorted
	return values(out)
}

// Concepts are the <bundle>/<concept-id> references (_complete_concepts): those of the
// `_archive/` mirror once the prefix starts with `_archive/` or the flag restore is on the line.
func Concepts(c Context) []Candidate { return concepts(c, "") }

// ConceptFiles are the same references with `.md`, for arguments that take a file path
// (_complete_concept_files).
func ConceptFiles(c Context) []Candidate { return concepts(c, ".md") }

func concepts(c Context, suffix string) []Candidate {
	if c.Root == "" {
		return nil
	}
	root, lead := c.Root, ""
	if strings.HasPrefix(c.Prefix, "_archive/") || c.Bool("restore") {
		root, lead = catalogue.Join(root, "_archive"), "_archive/"
		if !catalogue.RealFS.IsDir(root) {
			return nil
		}
	}
	var out []string
	for _, b := range bundles(root) {
		for id := range catalogue.IterConcepts(catalogue.Join(root, b), true) {
			out = append(out, lead+b+"/"+id+suffix)
		}
	}
	sort.Strings(out)
	return values(out)
}

// CtxSlugs are the slugs of the ctx bundles with their description (_complete_ctx_slugs).
func CtxSlugs(c Context) []Candidate {
	if c.Root == "" {
		return nil
	}
	slugs, err := catalogue.CtxSlugs(c.Root)
	if err != nil {
		return nil
	}
	var out []Candidate
	for _, s := range slugs {
		desc := ""
		if text, err := catalogue.ReadFile(catalogue.Join(catalogue.Join(c.Root, catalogue.CtxDir), s+".md")); err == nil {
			desc = frontmatter.Text(frontmatter.Read(text).Data(), "description", "")
		}
		out = append(out, Candidate{s, desc})
	}
	return out
}

// Dirs are the directories that start like the prefix (argcomplete DirectoriesCompleter): each
// with a trailing `/`, in directory order, relative to the working directory like the prefix. A
// leading `~` of the prefix is expanded in the candidates, so a raw `~/x` prefix keeps none of
// them, as in Python.
func Dirs(c Context) []Candidate {
	expanded := catalogue.ExpandUser(c.Prefix)
	dir, incomplete := pyDirname(expanded), expanded[strings.LastIndex(expanded, "/")+1:]
	f, err := os.Open(orDot(dir))
	if err != nil {
		return nil
	}
	defer f.Close()
	names, _ := f.Readdirnames(-1) // directory order, like os.listdir
	var out []Candidate
	for _, name := range names {
		if !strings.HasPrefix(name, incomplete) {
			continue
		}
		candidate := pyJoin(dir, name)
		if st, err := os.Stat(candidate); err == nil && st.IsDir() {
			out = append(out, Candidate{Value: candidate + "/"})
		}
	}
	return out
}

// Files are the files and directories that start like the prefix (argcomplete FilesCompleter):
// what bash's compgen finds, the directories with a trailing `/` after the files.
func Files(c Context) []Candidate {
	var files []string
	seen := map[string]bool{}
	dirs := compgen("directory", c.Prefix)
	for _, f := range compgen("file", c.Prefix) {
		if !seen[f] && !slices.Contains(dirs, f) {
			seen[f] = true
			files = append(files, f)
		}
	}
	for _, d := range dirs {
		files = append(files, d+"/")
	}
	return values(files)
}

// compgen is _call(["bash", "-c", "bind; compgen -A <kind> -- <prefix>"]): the lines bash prints,
// none when it fails.
func compgen(kind, prefix string) []string {
	cmd := exec.Command("bash", "-c", "bind; compgen -A "+kind+" -- "+shQuote(prefix))
	out, err := cmd.Output()
	if err != nil {
		return nil
	}
	return pytext.SplitLines(string(out), false)
}

// shQuote is shlex.quote.
func shQuote(s string) string {
	if s == "" {
		return "''"
	}
	safe := true
	for _, r := range s {
		if !(r >= 'a' && r <= 'z' || r >= 'A' && r <= 'Z' || r >= '0' && r <= '9' || strings.ContainsRune("_@%+=:,./-", r)) {
			safe = false
			break
		}
	}
	if safe {
		return s
	}
	return "'" + strings.ReplaceAll(s, "'", `'"'"'`) + "'"
}

func bundles(root string) []string {
	b, _ := catalogue.ListBundles(root)
	return b
}

func values(vs []string) []Candidate {
	out := make([]Candidate, len(vs))
	for i, v := range vs {
		out[i].Value = v
	}
	return out
}

func orDot(dir string) string {
	if dir == "" {
		return "."
	}
	return dir
}

// pyDirname is posixpath.dirname.
func pyDirname(p string) string {
	head := p[:strings.LastIndex(p, "/")+1]
	if head != "" && strings.Trim(head, "/") != "" {
		head = strings.TrimRight(head, "/")
	}
	return head
}

// pyJoin is posixpath.join for two parts.
func pyJoin(a, b string) string {
	switch {
	case strings.HasPrefix(b, "/"):
		return b
	case a == "" || strings.HasSuffix(a, "/"):
		return a + b
	}
	return a + "/" + b
}
