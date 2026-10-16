package history

import (
	"os"
	"path/filepath"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
)

// realpath is Python os.path.realpath (non-strict): the absolute path with every symbolic link
// resolved as far as the path exists, the rest of it kept as written. A link loop stops where it
// was found. It follows posixpath.realpath step by step, `..` after a link included.
func realpath(filename string) string {
	path := "/"
	if !strings.HasPrefix(filename, "/") {
		wd, err := catalogue.Getwd()
		if err != nil {
			return filepath.Clean(filename)
		}
		path = wd
	}
	// rest is the stack of parts still to resolve, the next one last. After a link is followed
	// the stack holds the link's own path and then a mark, so that the resolved path is recorded
	// when the mark is reached again.
	type part struct {
		name string
		mark bool
	}
	parts := strings.Split(filename, "/")
	rest := make([]part, len(parts))
	for i, name := range parts {
		rest[len(parts)-1-i] = part{name: name}
	}
	seen := map[string]*string{} // link path -> its resolved path, nil while it is being resolved
	for len(rest) > 0 {
		current := rest[len(rest)-1]
		rest = rest[:len(rest)-1]
		if current.mark {
			link := rest[len(rest)-1].name
			rest = rest[:len(rest)-1]
			resolved := path
			seen[link] = &resolved
			continue
		}
		switch current.name {
		case "", ".":
			continue
		case "..":
			path = path[:strings.LastIndex(path, "/")]
			if path == "" {
				path = "/"
			}
			continue
		}
		next := path + "/" + current.name
		if path == "/" {
			next = "/" + current.name
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
		rest = append(rest, part{name: next}, part{mark: true})
		targetParts := strings.Split(target, "/")
		for i := len(targetParts) - 1; i >= 0; i-- {
			rest = append(rest, part{name: targetParts[i]})
		}
	}
	return path
}
