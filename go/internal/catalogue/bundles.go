package catalogue

import (
	"iter"
	"os"
	"path/filepath"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/okferr"
)

// IsBundleDir is Python is_bundle_dir: the ctx directory and every directory whose name starts
// with neither `.` nor `_`.
func IsBundleDir(name string) bool {
	return name == CtxDir || (!strings.HasPrefix(name, ".") && !strings.HasPrefix(name, "_"))
}

// RequireBundleDir refuses a bundle argument that names no directory under root. The test is
// existence, deliberately not IsBundleDir: a `_`-prefixed directory is not a bundle for listing
// but is a real, printable directory.
func RequireBundleDir(root, bundle string) error {
	if !isDir(Join(root, filepath.Clean(bundle))) {
		return okferr.Newf(okferr.NotFound, "not a directory: %s", bundle)
	}
	return nil
}

// ListBundles is Python list_bundles: the bundle directories directly under root, sorted.
func ListBundles(root string) ([]string, error) {
	entries, err := os.ReadDir(root)
	if err != nil {
		return nil, err
	}
	out := []string{}
	for _, e := range entries { // ReadDir is sorted by name
		if isDirEntry(root, e) && IsBundleDir(e.Name()) {
			out = append(out, e.Name())
		}
	}
	return out, nil
}

// ListIndexableBundles is Python list_indexable_bundles: the narrower bundle set for index and
// search call sites only (build-index, the staleness counters, find's whole-catalogue scope). A
// `.okf.toml` `bundle` key names exactly one real bundle among many scaffolding directories; the
// set is that bundle, empty when it does not exist on disk. Without the key it is ListBundles.
// configRoot is where `.okf.toml` is read when it differs from root (the `_archive/<bundle>`
// mirror has no config of its own); "" means root. Never used for wikilink or crosslink
// resolution, `check` or any presentation surface.
func ListIndexableBundles(root, configRoot string) ([]string, error) {
	if configRoot == "" {
		configRoot = root
	}
	config, err := LoadConfig(configRoot)
	if err != nil {
		return nil, err
	}
	bundle, _ := config["bundle"].(string)
	if bundle == "" {
		return ListBundles(root)
	}
	if isDir(filepath.Join(root, bundle)) {
		return []string{bundle}, nil
	}
	return []string{}, nil
}

// ListSearchBundles is Python list_search_bundles: every bundle with includeTopics, else the
// indexable ones.
func ListSearchBundles(root string, includeTopics bool, configRoot string) ([]string, error) {
	if includeTopics {
		return ListBundles(root)
	}
	return ListIndexableBundles(root, configRoot)
}

// PruneWalkDirs is Python _prune_walk_dirs: the directories a walk descends into, without
// node_modules and dot-directories.
func PruneWalkDirs(dirnames []string) []string {
	out := make([]string, 0, len(dirnames))
	for _, d := range dirnames {
		if d != "node_modules" && !strings.HasPrefix(d, ".") {
			out = append(out, d)
		}
	}
	return out
}

// pruneConceptDirs is the directory filter of IterConcepts and IterAllMd: dot-directories and
// `assets` always, `_`-prefixed staging directories when pruneStaging is set.
func pruneConceptDirs(dirnames []string, pruneStaging bool) []string {
	out := make([]string, 0, len(dirnames))
	for _, d := range dirnames {
		if strings.HasPrefix(d, ".") || d == "assets" || (pruneStaging && strings.HasPrefix(d, "_")) {
			continue
		}
		out = append(out, d)
	}
	return out
}

// IterConcepts is Python iter_concepts: (concept id, absolute path) of every non-reserved .md
// under a bundle, in walk order (a directory's files before its subdirectories). Dot-directories
// and `assets` are pruned; with pruneStaging the `_`-prefixed staging directories are pruned too
// (every read path; the tag-mutation writers pass false).
func IterConcepts(bundlePath string, pruneStaging bool) iter.Seq2[string, string] {
	return func(yield func(string, string) bool) {
		stop := false
		SortedWalk(bundlePath, func(dirpath string, dirnames, filenames []string) []string {
			if stop {
				return nil
			}
			for _, fn := range filenames {
				if !strings.HasSuffix(fn, ".md") || IsReserved(fn) {
					continue
				}
				ap := Join(dirpath, fn)
				rel, err := filepath.Rel(bundlePath, ap)
				if err != nil {
					continue
				}
				if !yield(filepath.ToSlash(strings.TrimSuffix(rel, ".md")), ap) {
					stop = true
					return nil
				}
			}
			return pruneConceptDirs(dirnames, pruneStaging)
		})
	}
}

// IterAllMd is Python iter_all_md: the absolute path of every .md under a bundle, reserved files
// included, in walk order. Dot-directories and `assets` are pruned, and with pruneStaging the
// `_`-prefixed staging directories.
func IterAllMd(bundlePath string, pruneStaging bool) iter.Seq[string] {
	return func(yield func(string) bool) {
		stop := false
		SortedWalk(bundlePath, func(dirpath string, dirnames, filenames []string) []string {
			if stop {
				return nil
			}
			for _, fn := range filenames {
				if strings.HasSuffix(fn, ".md") && !yield(Join(dirpath, fn)) {
					stop = true
					return nil
				}
			}
			return pruneConceptDirs(dirnames, pruneStaging)
		})
	}
}

// Scope is one directory a scan visits: its bundle label (`_archive/<bundle>` for the archive
// mirror, "" for a path outside the root) and its path.
type Scope struct {
	Bundle string
	Path   string
}

// ResolveScopes is Python resolve_scopes: the (bundle, path) pairs for target (`<bundle>` or
// `<bundle>/<subdir>`), or every bundle of the catalogue when target is "". It is the one
// function the commands that traverse the catalogue share, so the answer does not depend on the
// caller. indexableOnly narrows the unscoped enumeration to ListIndexableBundles (find only; it
// must default to false). With includeArchive an unscoped call appends every bundle registered
// under `_archive/`, labelled `_archive/<bundle>`; a scoped call never appends the archive. It
// does not check that the target exists (RequireBundleDir does).
func ResolveScopes(root, target string, includeArchive, indexableOnly bool) ([]Scope, error) {
	bundles := func(r, configRoot string) ([]string, error) {
		if indexableOnly {
			return ListIndexableBundles(r, configRoot)
		}
		return ListBundles(r)
	}
	all := func() ([]Scope, error) {
		names, err := bundles(root, "")
		if err != nil {
			return nil, err
		}
		scopes := make([]Scope, len(names))
		for i, b := range names {
			scopes[i] = Scope{b, filepath.Join(root, b)}
		}
		return scopes, nil
	}
	var scopes []Scope
	var err error
	switch {
	case target != "" && filepath.IsAbs(target):
		// An absolute target addresses a directory directly; joining it to root would discard
		// root and rescope the scan onto a path that does not exist.
		tp := filepath.Clean(target)
		rel, relErr := filepath.Rel(root, tp)
		if relErr != nil || strings.HasPrefix(rel, "..") {
			return []Scope{{"", tp}}, nil
		}
		scopes = []Scope{{strings.SplitN(filepath.ToSlash(rel), "/", 2)[0], tp}}
	case target != "":
		// Normalised: an unnormalised `./a` would yield bundle "." and defeat every
		// bundle-name-keyed rule.
		norm := strings.Trim(filepath.ToSlash(filepath.Clean(target)), "/")
		if norm == "." || norm == "" {
			scopes, err = all()
		} else {
			scopes = []Scope{{strings.SplitN(norm, "/", 2)[0], filepath.Join(root, norm)}}
		}
	default:
		scopes, err = all()
	}
	if err != nil {
		return nil, err
	}
	if !includeArchive || target != "" {
		return scopes, nil // the archive is reached unscoped only
	}
	archiveRoot := filepath.Join(root, "_archive")
	if !isDir(archiveRoot) {
		return scopes, nil
	}
	archived, err := bundles(archiveRoot, root)
	if err != nil {
		return nil, err
	}
	for _, b := range archived {
		scopes = append(scopes, Scope{"_archive/" + b, filepath.Join(archiveRoot, b)})
	}
	return scopes, nil
}

// ResolveConcept is Python resolve_concept: `<bundle>/<concept-id>` (with or without `.md`) to an
// absolute file. A reference that names a directory resolves to that directory's index.md; the
// concept file wins over the directory reading. Otherwise not_found.
func ResolveConcept(root, path string) (string, error) {
	ref := strings.TrimSuffix(path, ".md")
	ap := Join(root, ref+".md")
	if isFile(ap) {
		return ap, nil
	}
	asDir := Join(root, ref)
	if isDir(asDir) {
		names, err := RealFS.ListDir(asDir)
		if err == nil {
			if idx, ok := FindReservedName(names, "index.md"); ok {
				return filepath.Join(asDir, idx), nil
			}
		}
		return "", okferr.Newf(okferr.NotFound, "not found: %s is a directory without an index.md", path)
	}
	return "", okferr.Newf(okferr.NotFound, "not found: %s", path)
}
