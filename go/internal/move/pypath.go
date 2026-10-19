package move

import (
	"os"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
)

// The path functions of Python's posixpath that the move core is built on. Go's filepath.Clean,
// filepath.Rel and filepath.EvalSymlinks differ from them in cases a catalogue path can reach:
// Clean drops the double leading slash POSIX (and Python) keep, and EvalSymlinks fails on a path
// whose tail does not exist where realpath resolves the part that does.

// pyNormpath is os.path.normpath: `.` and empty parts dropped, `..` folded into its parent (kept
// in front of a relative path, dropped at the root), exactly two leading slashes preserved and
// three or more reduced to one.
func pyNormpath(p string) string {
	if p == "" {
		return "."
	}
	initial := 0
	if strings.HasPrefix(p, "/") {
		initial = 1
		if strings.HasPrefix(p, "//") && !strings.HasPrefix(p, "///") {
			initial = 2
		}
	}
	var comps []string
	for _, c := range strings.Split(p, "/") {
		if c == "" || c == "." {
			continue
		}
		if c != ".." || (initial == 0 && len(comps) == 0) || (len(comps) > 0 && comps[len(comps)-1] == "..") {
			comps = append(comps, c)
		} else if len(comps) > 0 {
			comps = comps[:len(comps)-1]
		}
	}
	if out := strings.Repeat("/", initial) + strings.Join(comps, "/"); out != "" {
		return out
	}
	return "."
}

// pyAbspath is os.path.abspath: a relative path is joined to the working directory, then
// normalised. Python raises when there is no working directory; the path is then normalised as it
// stands.
func pyAbspath(p string) string {
	if !strings.HasPrefix(p, "/") {
		if wd, err := catalogue.Getwd(); err == nil {
			p = catalogue.Join(wd, p)
		}
	}
	return pyNormpath(p)
}

// pyRelpath is os.path.relpath: the path from start to p, both made absolute first. The result is
// `.` for two equal paths.
func pyRelpath(p, start string) string {
	startList, pathList := pathParts(pyAbspath(start)), pathParts(pyAbspath(p))
	i := 0
	for i < len(startList) && i < len(pathList) && startList[i] == pathList[i] {
		i++
	}
	rel := make([]string, 0, len(startList)-i+len(pathList)-i)
	for range len(startList) - i {
		rel = append(rel, "..")
	}
	rel = append(rel, pathList[i:]...)
	if len(rel) == 0 {
		return "."
	}
	return strings.Join(rel, "/")
}

// pathParts splits an absolute normalised path into its parts, empty for the root.
func pathParts(abs string) []string {
	tail := strings.TrimLeft(abs, "/")
	if tail == "" {
		return nil
	}
	return strings.Split(tail, "/")
}

// pyCommonpath is os.path.commonpath([a, b]) for two absolute paths: the longest common run of
// parts, `.` parts and empty parts ignored, `..` kept as a part.
func pyCommonpath(a, b string) string {
	split := func(p string) []string {
		var out []string
		for _, c := range strings.Split(p, "/") {
			if c != "" && c != "." {
				out = append(out, c)
			}
		}
		return out
	}
	pa, pb := split(a), split(b)
	n := 0
	for n < len(pa) && n < len(pb) && pa[n] == pb[n] {
		n++
	}
	return "/" + strings.Join(pa[:n], "/")
}

// pyDirname is os.path.dirname: everything before the last slash, trailing slashes dropped unless
// the head is all slashes.
func pyDirname(p string) string {
	head := p[:strings.LastIndex(p, "/")+1]
	if strings.Trim(head, "/") != "" {
		head = strings.TrimRight(head, "/")
	}
	return head
}

// pyBasename is os.path.basename.
func pyBasename(p string) string { return p[strings.LastIndex(p, "/")+1:] }

// pyExists is os.path.exists: the path names something, a symbolic link followed.
func pyExists(p string) bool {
	_, err := os.Stat(p)
	return err == nil
}

// pyIslink is os.path.islink.
func pyIslink(p string) bool {
	info, err := os.Lstat(p)
	return err == nil && info.Mode()&os.ModeSymlink != 0
}

// pySamefile is os.path.samefile: both paths are stat-ed (links followed) and name one file. The
// error is the stat failure Python raises.
func pySamefile(a, b string) (bool, error) {
	ia, err := os.Stat(a)
	if err != nil {
		return false, err
	}
	ib, err := os.Stat(b)
	if err != nil {
		return false, err
	}
	return os.SameFile(ia, ib), nil
}

// under reports whether path is base or lies below it (path == base or path.startswith(base + sep)).
func under(path, base string) bool {
	return path == base || strings.HasPrefix(path, base+"/")
}

// pyRealpath is os.path.realpath (not strict): the absolute path with every symbolic link
// resolved as far as the path exists, the rest of it kept as written. A link loop stops where it
// was found. It follows posixpath.realpath of Python 3.14 step by step, `..` after a link
// included. Python raises when a relative path has no working directory; the path is then
// normalised as it stands.
func pyRealpath(filename string) string {
	path := "/"
	if !strings.HasPrefix(filename, "/") {
		wd, err := catalogue.Getwd()
		if err != nil {
			return pyNormpath(filename)
		}
		path = wd
	}
	// rest is the stack of parts still to resolve, the next one on top. After a link is followed
	// it holds the link's own path under a marker, so that the resolved path is recorded when
	// the marker is popped again.
	type part struct {
		name   string
		marker bool
	}
	names := strings.Split(filename, "/")
	rest := make([]part, len(names))
	for i, name := range names {
		rest[len(names)-1-i] = part{name: name}
	}
	partCount := len(names)      // the parts of rest without the markers and the link paths
	seen := map[string]*string{} // link path -> its resolved path, nil while it is being resolved
	for partCount > 0 {
		cur := rest[len(rest)-1]
		rest = rest[:len(rest)-1]
		if cur.marker {
			link := rest[len(rest)-1].name
			rest = rest[:len(rest)-1]
			resolved := path
			seen[link] = &resolved
			continue
		}
		partCount--
		switch cur.name {
		case "", ".":
			continue
		case "..":
			path = path[:strings.LastIndex(path, "/")]
			if path == "" {
				path = "/"
			}
			continue
		}
		next := path + "/" + cur.name
		if path == "/" {
			next = "/" + cur.name
		}
		info, err := os.Lstat(next)
		if err != nil || info.Mode()&os.ModeSymlink == 0 {
			path = next
			continue
		}
		if resolved, found := seen[next]; found {
			if resolved != nil {
				path = *resolved
			} else {
				path = next // a link loop
			}
			continue
		}
		target, err := os.Readlink(next)
		if err != nil {
			path = next
			continue
		}
		if strings.HasPrefix(target, "/") {
			path = "/"
		}
		seen[next] = nil
		rest = append(rest, part{name: next}, part{marker: true})
		targetParts := strings.Split(target, "/")
		for i := len(targetParts) - 1; i >= 0; i-- {
			rest = append(rest, part{name: targetParts[i]})
		}
		partCount += len(targetParts)
	}
	return path
}
