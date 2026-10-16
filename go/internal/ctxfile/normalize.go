package ctxfile

import (
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

// CtxEntryAbspath is Python ctx_entry_abspath: the file an entry path names. A path that starts
// with `~` or `/` lies outside the catalogue (`~` expanded); any other is relative to root.
func CtxEntryAbspath(root, path string) string {
	if strings.HasPrefix(path, "~") || strings.HasPrefix(path, "/") {
		return catalogue.ExpandUser(path)
	}
	return catalogue.Join(root, path)
}

// CtxNormalizePath is Python ctx_normalize_path: the entry path for a path as a user wrote it. A
// path inside the catalogue becomes relative to root (with `.md` added when only that file
// exists); one reached through a symlinked bundle becomes <bundle>/<path>; one below the home
// directory becomes `~/...`; any other stays absolute. The second result is false (Python None)
// when mustExist is set and the path names nothing.
//
// Deviation: Python raises when the working directory is gone (a relative path cannot be made
// absolute) and when root cannot be listed. The signature has no error, so the path is resolved
// without the working directory and a root that cannot be listed has no symlinked bundles;
// CtxMemberships reports the second case as an error.
func CtxNormalizePath(root, raw string, mustExist bool) (string, bool) {
	res, ok, _ := normalizePath(root, raw, mustExist)
	return res, ok
}

// normalizePath is CtxNormalizePath with the error that listing the bundles of root gave, if any.
func normalizePath(root, raw string, mustExist bool) (string, bool, error) {
	raw = pytext.Strip(raw)
	n := &normalizer{root: root, rootAbs: pyAbspath(root)}
	var res string
	switch {
	case strings.HasPrefix(raw, "~"):
		res = n.filesystem(catalogue.ExpandUser(raw))
	case strings.HasPrefix(raw, "/"):
		if n.catExists(raw[1:]) {
			res = n.inCatalogue(raw[1:])
		} else {
			res = n.filesystem(raw)
		}
	case n.catExists(raw):
		res = n.inCatalogue(raw)
	case pyExists(pyAbspath(raw)):
		res = n.filesystem(raw)
	default:
		res = n.inCatalogue(raw)
	}
	if mustExist && !pyExists(CtxEntryAbspath(root, res)) {
		return "", false, n.err
	}
	return res, true, n.err
}

// normalizer is the state of one normalizePath: the root as given and as an absolute path, and the
// first error of listing the bundles of root.
type normalizer struct {
	root, rootAbs string
	err           error
}

// catExists is Python cat_exists: rel names a file below root, with or without `.md`.
func (n *normalizer) catExists(rel string) bool {
	p := catalogue.Join(n.root, rel)
	return pyExists(p) || pyExists(p+".md")
}

// inCatalogue is Python catalogue(): rel as a path relative to root, `.md` added when only that
// file exists; a path that leaves root is taken as a file system path.
func (n *normalizer) inCatalogue(rel string) string {
	norm := pyNormpath(rel)
	if strings.HasPrefix(norm, "..") {
		return n.filesystem(pyAbspath(catalogue.Join(n.root, rel)))
	}
	if !pyExists(catalogue.Join(n.root, norm)) && pyExists(catalogue.Join(n.root, norm+".md")) {
		norm += ".md"
	}
	return norm
}

// filesystem is Python filesystem(): p, a file system path, as an entry path: relative to root
// when it lies below it, <bundle>/<path> when it lies below the target of a symlinked bundle,
// `~/...` below the home directory, else absolute.
func (n *normalizer) filesystem(p string) string {
	ap := pyAbspath(p)
	if pyUnder(ap, n.rootAbs) {
		return pyRelpath(ap, n.rootAbs)
	}
	real := pyRealpath(ap)
	bundles, err := catalogue.ListBundles(n.root)
	if err != nil && n.err == nil {
		n.err = err
	}
	for _, b := range bundles {
		bp := catalogue.Join(n.root, b)
		if !pyIslink(bp) {
			continue
		}
		if target := pyRealpath(bp); pyUnder(real, target) {
			return b + "/" + pyRelpath(real, target)
		}
	}
	home := pyAbspath(catalogue.ExpandUser("~"))
	if pyUnder(ap, home) {
		return "~/" + pyRelpath(ap, home)
	}
	return ap
}
