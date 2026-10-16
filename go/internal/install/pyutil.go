package install

import (
	"errors"
	"io/fs"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"unicode/utf8"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

// The errors a step can end with, the four classes of Python okf_install (Skip, Unsafe, Failed and
// OSError). Their text is the text of the Python exception: it lands in the step's detail.
type (
	skipErr   struct{ msg string }
	unsafeErr struct{ msg string }
	failedErr struct{ msg string }
	osErr     struct{ msg string }
)

func (e *skipErr) Error() string   { return e.msg }
func (e *unsafeErr) Error() string { return e.msg }
func (e *failedErr) Error() string { return e.msg }
func (e *osErr) Error() string     { return e.msg }

func skip(msg string) error   { return &skipErr{msg} }
func unsafe(msg string) error { return &unsafeErr{msg} }

// osError turns a Go I/O error into the text Python's OSError carries: `[Errno 13] Permission
// denied: '/path'`, and `'old' -> 'new'` for a rename.
func osError(err error) error {
	if err == nil {
		return nil
	}
	var errno syscall.Errno
	if !errors.As(err, &errno) {
		return &osErr{err.Error()}
	}
	text := "[Errno " + strconv.Itoa(int(errno)) + "] " + capitalize(errno.Error())
	var le *os.LinkError
	var pe *fs.PathError
	switch {
	case errors.As(err, &le):
		text += ": " + pytext.ReprStr(le.Old) + " -> " + pytext.ReprStr(le.New)
	case errors.As(err, &pe):
		text += ": " + pytext.ReprStr(pe.Path)
	}
	return &osErr{text}
}

func capitalize(s string) string {
	if s == "" {
		return s
	}
	r, n := utf8.DecodeRuneInString(s)
	return strings.ToUpper(string(r)) + s[n:]
}

// opt is Python's `str | None`: Ok is false for None.
type opt struct {
	S  string
	Ok bool
}

func some(s string) opt { return opt{s, true} }

var none = opt{}

func (o opt) or(def string) string {
	if o.Ok {
		return o.S
	}
	return def
}

// pyJoin is posixpath.join: an absolute part restarts the path, nothing is normalised.
func pyJoin(parts ...string) string {
	path := parts[0]
	for _, b := range parts[1:] {
		switch {
		case strings.HasPrefix(b, "/"):
			path = b
		case path == "" || strings.HasSuffix(path, "/"):
			path += b
		default:
			path += "/" + b
		}
	}
	return path
}

// pyBasename is posixpath.basename.
func pyBasename(p string) string { return p[strings.LastIndex(p, "/")+1:] }

// pyDirname is posixpath.dirname.
func pyDirname(p string) string {
	head := p[:strings.LastIndex(p, "/")+1]
	if head != "" && strings.Trim(head, "/") != "" {
		head = strings.TrimRight(head, "/")
	}
	return head
}

// pyQuote is shlex.quote.
func pyQuote(s string) string {
	if s == "" {
		return "''"
	}
	safe := true
	for _, c := range []byte(s) {
		if !(c >= 'a' && c <= 'z' || c >= 'A' && c <= 'Z' || c >= '0' && c <= '9' || strings.IndexByte("_@%+=:,./-", c) >= 0) {
			safe = false
			break
		}
	}
	if safe {
		return s
	}
	return "'" + strings.ReplaceAll(s, "'", `'"'"'`) + "'"
}

// shlexJoin is shlex.join.
func shlexJoin(argv []string) string {
	q := make([]string, len(argv))
	for i, a := range argv {
		q[i] = pyQuote(a)
	}
	return strings.Join(q, " ")
}

func abspath(p string) string {
	if a, err := catalogue.Abspath(p); err == nil {
		return a
	}
	return filepath.Clean(p)
}

func lexists(p string) bool {
	_, err := os.Lstat(p)
	return err == nil
}

func islink(p string) bool {
	fi, err := os.Lstat(p)
	return err == nil && fi.Mode()&os.ModeSymlink != 0
}

func isdir(p string) bool {
	fi, err := os.Stat(p)
	return err == nil && fi.IsDir()
}

func isfile(p string) bool {
	fi, err := os.Stat(p)
	return err == nil && fi.Mode().IsRegular()
}

func exists(p string) bool {
	_, err := os.Stat(p)
	return err == nil
}

// realpath is Python os.path.realpath (non-strict): every symbolic link resolved as far as the
// path exists, the rest kept as written. It follows posixpath.realpath step by step.
func realpath(filename string) string {
	path := "/"
	if !strings.HasPrefix(filename, "/") {
		wd, err := catalogue.Getwd()
		if err != nil {
			return filepath.Clean(filename)
		}
		path = wd
	}
	type part struct {
		name string
		mark bool
	}
	parts := strings.Split(filename, "/")
	rest := make([]part, len(parts))
	for i, name := range parts {
		rest[len(parts)-1-i] = part{name: name}
	}
	seen := map[string]*string{}
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

// splitLines is str.split("\n").
func splitLines(s string) []string { return strings.Split(s, "\n") }
