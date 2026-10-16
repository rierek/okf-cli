package navigation

import (
	"os/exec"
	"path/filepath"
	"regexp"
	"slices"
	"strconv"
	"strings"
	"time"

	"go.yaml.in/yaml/v3"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/cli"
	"nas/volume1/data/git/okf-tools/go/internal/envelope"
	"nas/volume1/data/git/okf-tools/go/internal/frontmatter"
	"nas/volume1/data/git/okf-tools/go/internal/okferr"
	"nas/volume1/data/git/okf-tools/go/internal/pytext"
	"nas/volume1/data/git/okf-tools/go/internal/spec"
	"nas/volume1/data/git/okf-tools/go/internal/where"
)

// recent dates a concept by the commit that added it: git is the one source (the frontmatter
// timestamp is a migration batch stamp, mtime is rewritten by every bulk command).

const (
	uncommitted = "(uncommitted)"
	createdFmt  = "2006-01-02 15:04"
)

var recentTsRE = regexp.MustCompile(`^@([0-9]+)$`)

func recentArgs() []cli.Arg {
	return []cli.Arg{
		{Flags: []string{"--limit"}, Type: cli.Int, Default: 10, Help: "max results to print (default 10)"},
		cli.WhereArg(),
		cli.JSON(),
	}
}

// parseAddEvents is Python parse_add_events: {repo_rel_path: unix_ts} from the stanza stream of
// `git log --no-renames --diff-filter=A --format=@%at --name-only`. git emits newest-commit-first,
// so the first sighting of a path is its latest add and is kept. Only `@<digits>` opens a
// stanza; paths before any stanza header have no timestamp and are dropped.
func parseAddEvents(stdout string) map[string]int64 {
	events := map[string]int64{}
	var ts int64
	have := false
	for _, line := range pytext.SplitLines(stdout, false) {
		if pytext.Strip(line) == "" {
			continue
		}
		if m := recentTsRE.FindStringSubmatch(line); m != nil {
			ts, _ = strconv.ParseInt(m[1], 10, 64)
			have = true
		} else if have {
			if _, seen := events[line]; !seen {
				events[line] = ts
			}
		}
	}
	return events
}

// conceptGitKey is Python concept_git_key: the repo-relative path git prints for one concept,
// composed from the bundle's repo-relative prefix and the concept id, never derived from the
// absolute path (relpath does not resolve symlinks).
func conceptGitKey(prefix, cid string) string {
	if prefix != "" {
		return prefix + "/" + cid + ".md"
	}
	return cid + ".md"
}

type recentScope struct {
	bundle, path string
	repo         string // "" for none
	prefix       string
}

type repoMembers struct {
	repo     string
	prefixes []string
}

// groupScopesByRepo is Python group_scopes_by_repo: one entry per repository in first-seen order,
// so one git process runs per repository however many bundles it owns. Scopes without a
// repository are dropped.
func groupScopesByRepo(scopes []recentScope) []repoMembers {
	var out []repoMembers
	for _, s := range scopes {
		if s.repo == "" {
			continue
		}
		i := slices.IndexFunc(out, func(m repoMembers) bool { return m.repo == s.repo })
		if i < 0 {
			out = append(out, repoMembers{repo: s.repo})
			i = len(out) - 1
		}
		if s.prefix != "" {
			out[i].prefixes = append(out[i].prefixes, s.prefix)
		}
	}
	return out
}

type recentRow struct {
	path string
	ts   int64
	has  bool
}

// rankRecent is Python rank_recent: the top limit rows, newest first, undated rows after every
// dated one, equal timestamps by path.
func rankRecent(entries []recentRow, limit int) []recentRow {
	if limit <= 0 {
		return nil
	}
	ordered := slices.Clone(entries)
	slices.SortStableFunc(ordered, func(a, b recentRow) int {
		switch {
		case a.has != b.has:
			if a.has {
				return -1
			}
			return 1
		case a.has && a.ts != b.ts:
			if a.ts > b.ts {
				return -1
			}
			return 1
		}
		return strings.Compare(a.path, b.path)
	})
	if len(ordered) > limit {
		ordered = ordered[:limit]
	}
	return ordered
}

// formatCreated is Python format_created: local time, or a placeholder padded to the same width.
func formatCreated(r recentRow) string {
	if !r.has {
		return ljust(uncommitted, len(createdFmt))
	}
	return time.Unix(r.ts, 0).Format(createdFmt)
}

// gitAddEvents is Python _git_add_events: the output of exactly one git process, ok false when it
// cannot run or fails. --no-renames is load-bearing: with rename detection a `git mv` is class R
// and --diff-filter=A drops it. core.quotepath=false keeps a path with an umlaut raw.
func gitAddEvents(repo string, prefixes []string) (string, bool) {
	if len(prefixes) == 0 {
		prefixes = []string{"."}
	}
	args := append([]string{"-C", repo, "-c", "core.quotepath=false", "log",
		"--no-renames", "--diff-filter=A", "--format=@%at", "--name-only", "--"}, prefixes...)
	out, err := exec.Command("git", args...).Output()
	if err != nil {
		return "", false
	}
	return catalogue.DecodeText(out), true
}

// realpath is os.path.realpath for a path that exists: symlinks resolved.
func realpath(p string) string {
	if r, err := filepath.EvalSymlinks(p); err == nil {
		return r
	}
	return filepath.Clean(p)
}

func relSlash(path, start string) string {
	rel, err := filepath.Rel(start, path)
	if err != nil {
		return path
	}
	return filepath.ToSlash(rel)
}

// recentScopes is Python _recent_scopes: every scope with its repository and the repository-
// relative prefix of its bundle. Classification is by realpath, not by the last component being
// a link.
func recentScopes(root string, includeArchive bool) ([]recentScope, error) {
	realroot := realpath(root)
	rootTop, reason := catalogue.GitToplevel(realroot)
	switch reason {
	case "no-git":
		return nil, okferr.New(okferr.Internal, "recent: git binary not found — this command reads creation dates from git history")
	case "no-repo":
		return nil, okferr.New(okferr.InvalidInput, "recent: catalogue root is not a git repository — no history to read")
	}
	rootPrefix := relSlash(realroot, rootTop)
	if rootPrefix == "." {
		rootPrefix = ""
	}
	resolved, err := catalogue.ResolveScopes(root, "", includeArchive, false)
	if err != nil {
		return nil, err
	}
	var scopes []recentScope
	for _, s := range resolved {
		real := realpath(s.Path)
		if real == realroot || strings.HasPrefix(real, realroot+"/") {
			sub := relSlash(real, realroot)
			if sub == "." {
				sub = ""
			}
			prefix := strings.Join(slices.DeleteFunc([]string{rootPrefix, sub}, func(p string) bool { return p == "" }), "/")
			scopes = append(scopes, recentScope{s.Bundle, s.Path, rootTop, prefix})
			continue
		}
		repo, why := catalogue.GitToplevel(real)
		if why != "" {
			envelope.Note("bundle `" + s.Bundle + "` resolves outside any git repository — its concepts are " +
				"listed undated; run `git init` in " + real)
			scopes = append(scopes, recentScope{s.Bundle, s.Path, "", ""})
			continue
		}
		prefix := relSlash(real, repo)
		if prefix == "." {
			prefix = ""
		}
		scopes = append(scopes, recentScope{s.Bundle, s.Path, repo, prefix})
	}
	return scopes, nil
}

type recentMeta struct {
	meta catalogue.Meta
	fm   *yaml.Node
}

// runRecent is Python cmd_recent: the most recently created concepts, newest first.
func runRecent(root string, a *cli.Args) (any, error) {
	var expr *string
	if a.Has("where") {
		s := a.String("where")
		expr = &s
	}
	filters, err := where.CompileWhere(expr, false, nil)
	if err != nil {
		return nil, err
	}
	scopes, err := recentScopes(root, filters.IncludeArchive())
	if err != nil {
		return nil, err
	}
	byRepo := map[string]map[string]int64{}
	for _, g := range groupScopesByRepo(scopes) {
		stdout, ok := gitAddEvents(g.repo, g.prefixes)
		if !ok {
			envelope.Note("git log failed in " + g.repo + " — its concepts are listed undated; check the repository")
			continue
		}
		byRepo[g.repo] = parseAddEvents(stdout)
	}

	var entries []recentRow
	meta := map[string]recentMeta{}
	datedRepo := map[string]bool{}
	for _, s := range scopes {
		var events map[string]int64
		if s.repo != "" {
			events = byRepo[s.repo]
		}
		for cid, ap := range catalogue.IterConcepts(s.path, true) {
			path := conceptPath(root, ap)
			if filters.HasExpression() {
				// one read feeding the whole predicate and the frontmatter meta
				text, err := catalogue.ReadFile(ap)
				if err != nil {
					return nil, err
				}
				fm := frontmatter.Read(text).Data()
				if !filters.MatchesLoaded(path, fm) {
					continue
				}
				typ, title, desc := frontmatter.Meta(fm, cid)
				meta[path] = recentMeta{catalogue.Meta{Type: typ, Title: title, Description: desc}, fm}
			}
			row := recentRow{path: path}
			if events != nil {
				row.ts, row.has = events[conceptGitKey(s.prefix, cid)]
			}
			datedRepo[path] = events != nil
			entries = append(entries, row)
		}
	}

	total := len(entries)
	rows := rankRecent(entries, a.Int("limit"))
	// Without a filter no file was read yet: frontmatter is fetched for the surviving rows only.
	for _, r := range rows {
		if _, ok := meta[r.path]; !ok {
			m, fm, err := catalogue.MetaAndFm(catalogue.Join(root, r.path+".md"), catalogue.RealFS)
			if err != nil {
				return nil, err
			}
			meta[r.path] = recentMeta{m, fm}
		}
	}
	undated := 0
	for _, e := range entries {
		if !e.has && datedRepo[e.path] {
			undated++
		}
	}
	if undated > 0 {
		envelope.Note(strconv.Itoa(undated) + " concept(s) have no commit that added them — listed undated at " +
			"the end; commit them to give them a creation date")
	}

	if a.JSON {
		now := filters.Now()
		out := make([]envelope.Obj, len(rows))
		for i, r := range rows {
			m := meta[r.path]
			var created, createdTs any
			if r.has {
				created, createdTs = time.Unix(r.ts, 0).Format("2006-01-02T15:04:05-07:00"), r.ts
			}
			tier, stale := spec.TrustFields(m.fm, now)
			out[i] = envelope.O("created", created, "created_ts", createdTs, "title", m.meta.Title,
				"type", m.meta.Type, "path", r.path, "description", m.meta.Description,
				"tier", tier, "stale", stale)
		}
		return out, nil
	}
	w := newOut()
	defer w.Flush()
	if len(rows) == 0 {
		printf(w, "(no matches)\n")
		return nil, nil
	}
	width := 0
	for _, r := range rows {
		width = max(width, charLen(meta[r.path].meta.Type))
	}
	for _, r := range rows {
		printf(w, "%s  %s  %s\n", formatCreated(r), ljust(meta[r.path].meta.Type, width), r.path)
	}
	// `recent` truncates by default, so a bare count would read as the size of the catalogue:
	// both numbers, always.
	printf(w, "recent: %d of %d concept(s)\n", len(rows), total)
	return nil, nil
}
