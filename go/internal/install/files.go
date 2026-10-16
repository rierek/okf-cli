package install

import (
	"errors"
	"io"
	"io/fs"
	"os"
	"regexp"
	"strings"
	"syscall"
	"unicode/utf8"

	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

// step is one line of the plan: what will be done (status create, update, remove), what is fine
// (ok), what is left alone (skip) and what cannot be done (blocked, failed).
type step struct {
	group, subject, status, detail string
	apply                          func() error
	done                           bool
}

func newStep(group, subject, status, detail string, apply func() error) *step {
	return &step{group: group, subject: subject, status: status, detail: detail, apply: apply}
}

func isChange(status string) bool {
	return status == "create" || status == "update" || status == "remove"
}

// --- text helpers ------------------------------------------------------------

// readText is read(): the file as UTF-8 text without any newline translation, None when absent.
func readText(path string) (opt, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		if pathMissing(err) {
			return none, nil
		}
		return none, osError(err)
	}
	if !utf8.Valid(b) {
		return none, unsafe(path + " is not UTF-8 text")
	}
	return some(string(b)), nil
}

// pathMissing is Python's FileNotFoundError: ENOENT only (a missing file in a path that runs
// through a regular file is NotADirectoryError, an OSError).
func pathMissing(err error) bool {
	return errors.Is(err, fs.ErrNotExist)
}

// linesOf is lines_of: the lines of a text without CRLF.
func linesOf(text string) ([]string, error) {
	if strings.Contains(text, "\r") {
		return nil, unsafe("the file uses CRLF line endings")
	}
	switch {
	case strings.HasSuffix(text, "\n"):
		return splitLines(text)[:len(splitLines(text))-1], nil
	case text != "":
		return splitLines(text), nil
	}
	return nil, nil
}

func join(lines []string) string {
	if len(lines) == 0 {
		return ""
	}
	return strings.Join(lines, "\n") + "\n"
}

// findBlock is find_block: the line span of our begin/end markers, nil when there are none.
func findBlock(lines []string) (*[2]int, error) {
	var s, e []int
	for i, l := range lines {
		switch pytext.Strip(l) {
		case begin:
			s = append(s, i)
		case end:
			e = append(e, i)
		}
	}
	if len(s) == 0 && len(e) == 0 {
		return nil, nil
	}
	if len(s) != 1 || len(e) != 1 || e[0] < s[0] {
		return nil, unsafe("the okf begin/end markers are unbalanced; fix or remove them by hand")
	}
	return &[2]int{s[0], e[0]}, nil
}

// putBlock is put_block: lines with our block replaced, else inserted after line `at` (when
// at >= 0), else appended after one blank separator line (dropBlock takes that line out again).
func putBlock(lines, block []string, at int) ([]string, error) {
	span, err := findBlock(lines)
	if err != nil {
		return nil, err
	}
	out := []string{}
	switch {
	case span != nil:
		out = append(out, lines[:span[0]]...)
		out = append(out, block...)
		out = append(out, lines[span[1]+1:]...)
	case at >= 0:
		out = append(out, lines[:at+1]...)
		out = append(out, block...)
		out = append(out, lines[at+1:]...)
	default:
		out = append(out, lines...)
		if len(lines) > 0 {
			out = append(out, "")
		}
		out = append(out, block...)
	}
	return out, nil
}

func dropBlock(lines []string) ([]string, error) {
	span, err := findBlock(lines)
	if err != nil || span == nil {
		return lines, err
	}
	s, e := span[0], span[1]
	if s > 0 && lines[s-1] == "" && e == len(lines)-1 {
		s--
	}
	out := append([]string{}, lines[:s]...)
	return append(out, lines[e+1:]...), nil
}

// mentions is `needle in any non-comment line`: what the user's own rc already does.
func mentions(lines []string, needle string) bool {
	for _, l := range lines {
		if !strings.HasPrefix(pytext.Lstrip(l), "#") && strings.Contains(l, needle) {
			return true
		}
	}
	return false
}

// --- files -------------------------------------------------------------------

type transform func(old opt) (opt, error)

// edit is the atomic write of transform(old text) through a symlinked dotfile; the first edit of
// an existing file keeps `<file>.okf-cli.bak`.
func edit(path string, t transform, backup bool, mode os.FileMode) error {
	real := realpath(path) // a symlinked dotfile is written through, never replaced
	old, err := readText(real)
	if err != nil {
		return err
	}
	next, err := t(old)
	if err != nil {
		return err
	}
	if next == old {
		return nil
	}
	if !next.Ok {
		return osError(os.Remove(real))
	}
	if err := os.MkdirAll(pyDirname(real), 0o777); err != nil {
		return osError(err)
	}
	if old.Ok && backup && !exists(real+".okf-cli.bak") {
		if err := copyFile(real, real+".okf-cli.bak"); err != nil {
			return osError(err)
		}
	}
	tmp := pyJoin(pyDirname(real), ".okf-cli.tmp."+pyBasename(real))
	if err := os.WriteFile(tmp, []byte(next.S), 0o666); err != nil {
		return osError(err)
	}
	switch {
	case old.Ok:
		if err := copyMode(real, tmp); err != nil {
			return osError(err)
		}
	case mode != 0:
		if err := os.Chmod(tmp, mode); err != nil {
			return osError(err)
		}
	}
	return osError(os.Rename(tmp, real))
}

// copyMode is shutil.copymode.
func copyMode(src, dst string) error {
	info, err := os.Stat(src)
	if err != nil {
		return err
	}
	return os.Chmod(dst, info.Mode()&(os.ModePerm|os.ModeSetuid|os.ModeSetgid|os.ModeSticky))
}

// copyFile is shutil.copy2 for a regular file: bytes and permission bits, the modification time
// included.
func copyFile(src, dst string) error {
	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()
	info, err := in.Stat()
	if err != nil {
		return err
	}
	if info.IsDir() {
		return &fs.PathError{Op: "open", Path: src, Err: syscall.EISDIR}
	}
	out, err := os.OpenFile(dst, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, 0o666)
	if err != nil {
		return err
	}
	if _, err := io.Copy(out, in); err != nil {
		out.Close()
		return err
	}
	if err := out.Close(); err != nil {
		return err
	}
	if err := os.Chmod(dst, info.Mode()&(os.ModePerm|os.ModeSetuid|os.ModeSetgid|os.ModeSticky)); err != nil {
		return err
	}
	return os.Chtimes(dst, info.ModTime(), info.ModTime())
}

// fileStep is one file edited through t(old text or None) -> new text or None. The same
// transform plans (dry) and applies (on fresh content).
func fileStep(c *ctx, group, subject, path string, t transform, what, manual string, backup bool, mode os.FileMode) *step {
	old, err := readText(realpath(path))
	var next opt
	if err == nil {
		next, err = t(old)
	}
	switch e := err.(type) {
	case nil:
	case *skipErr:
		return newStep(group, subject, "skip", e.Error(), nil)
	default:
		detail := e.Error()
		if manual != "" {
			detail += "\n" + manual
		}
		return newStep(group, subject, "blocked", detail, nil)
	}
	if next == old {
		return newStep(group, subject, "ok", what, nil)
	}
	status := "update"
	switch {
	case !next.Ok:
		status = "remove"
	case !old.Ok:
		status = "create"
	}
	removed := !next.Ok
	return newStep(group, subject, status, what, func() error {
		if err := edit(path, t, backup, mode); err != nil {
			return err
		}
		if removed {
			prune(c, pyDirname(path))
		}
		return nil
	})
}

// --- symlinks / copies (skills, zsh completion) ------------------------------

func clear(p string) error {
	switch {
	case islink(p) || isfile(p):
		return osError(os.Remove(p))
	case isdir(p):
		return osError(os.RemoveAll(p))
	}
	return nil
}

// prune removes the empty directories an uninstall left behind; never HOME, above it or an
// agent's own directory.
func prune(c *ctx, d string) {
	home := realpath(c.home)
	stop := map[string]bool{home: true}
	for _, h := range harnesses {
		stop[realpath(c.harnessDir(h))] = true
	}
	for {
		r := realpath(d)
		if !strings.HasPrefix(r, home+"/") || stop[r] {
			return
		}
		if syscall.Rmdir(d) != nil {
			return
		}
		d = pyDirname(d)
	}
}

// tree maps relative path to bytes for every file under path, as os.walk sees it: no
// __pycache__ directories, no .DS_Store files, symlinked directories not entered.
func tree(path string) (map[string][]byte, error) {
	out := map[string][]byte{}
	var walk func(dir, rel string) error
	walk = func(dir, rel string) error {
		entries, err := os.ReadDir(dir)
		if err != nil {
			return nil // os.walk skips what it cannot list
		}
		for _, e := range entries {
			p := pyJoin(dir, e.Name())
			r := e.Name()
			if rel != "" {
				r = rel + "/" + e.Name()
			}
			if isdir(p) { // follows a symlink, like DirEntry.is_dir
				if e.Name() == "__pycache__" || e.Type()&fs.ModeSymlink != 0 {
					continue
				}
				if err := walk(p, r); err != nil {
					return err
				}
				continue
			}
			if e.Name() == ".DS_Store" {
				continue
			}
			b, err := os.ReadFile(p)
			if err != nil {
				return err
			}
			out[r] = b
		}
		return nil
	}
	if !isdir(path) {
		return out, nil
	}
	return out, walk(path, "")
}

// same is whether dest is a copy of the directory src.
func same(src, dest string) bool {
	a, err := tree(dest)
	if err != nil {
		return false
	}
	b, err := tree(src)
	if err != nil || len(a) != len(b) {
		return false
	}
	for k, v := range a {
		if w, ok := b[k]; !ok || string(v) != string(w) {
			return false
		}
	}
	return true
}

var skillHead = regexp.MustCompile(`^---\r?\n(?:[^\n]*\n)*?name:[ \t]*okf[ \t]*\r?\n`)

// mine says p is an okf install of this thing: the okf skill directory or the zsh completion file.
func mine(p string) bool {
	if isdir(p) {
		head, err := readText(pyJoin(p, "SKILL.md"))
		return err == nil && skillHead.MatchString(head.or(""))
	}
	text, err := readText(p)
	return err == nil && strings.HasPrefix(text.or(""), "#compdef okf\n")
}

// putState is the state of dest as an install of src: ok, stale, foreign or absent.
func putState(src, dest string, copy bool) string {
	parts := strings.Split(src, "/")
	if len(parts) > 2 {
		parts = parts[len(parts)-2:]
	}
	tail := strings.Join(parts, "/")
	if islink(dest) {
		if !copy && realpath(dest) == realpath(src) {
			return "ok"
		}
		target, _ := os.Readlink(dest)
		if strings.HasSuffix(strings.TrimRight(target, "/"), tail) || mine(dest) {
			return "stale"
		}
		return "foreign"
	}
	if lexists(dest) {
		if copy && same(src, dest) {
			return "ok"
		}
		if mine(dest) {
			return "stale"
		}
		return "foreign"
	}
	return "absent"
}

// put places src at dest: a symlink, or a copy; atomic through a temporary sibling.
func put(src, dest string, copy bool) error {
	if err := os.MkdirAll(pyDirname(dest), 0o777); err != nil {
		return osError(err)
	}
	tmp := pyJoin(pyDirname(dest), ".okf-cli.tmp."+pyBasename(dest))
	if err := clear(tmp); err != nil {
		return err
	}
	switch {
	case !copy:
		if err := os.Symlink(src, tmp); err != nil {
			return osError(err)
		}
	case isdir(src):
		if err := copyTree(src, tmp); err != nil {
			return osError(err)
		}
	default:
		if err := copyFile(src, tmp); err != nil {
			return osError(err)
		}
	}
	if err := clear(dest); err != nil {
		return err
	}
	return osError(os.Rename(tmp, dest))
}

// copyTree is shutil.copytree(src, dst, ignore=(.DS_Store, __pycache__)): symlinks are followed,
// directories keep their permission bits.
func copyTree(src, dst string) error {
	entries, err := os.ReadDir(src)
	if err != nil {
		return err
	}
	if err := os.MkdirAll(dst, 0o777); err != nil {
		return err
	}
	for _, e := range entries {
		if e.Name() == ".DS_Store" || e.Name() == "__pycache__" {
			continue
		}
		s, d := pyJoin(src, e.Name()), pyJoin(dst, e.Name())
		if isdir(s) {
			err = copyTree(s, d)
		} else {
			err = copyFile(s, d)
		}
		if err != nil {
			return err
		}
	}
	return copyMode(src, dst)
}

// putStep is the step that makes dest an install of src (or removes it).
func putStep(c *ctx, group, subject, src, dest string, copy, un bool, note string) *step {
	if !un && !exists(src) {
		return newStep(group, subject, "blocked", "source not found: "+c.short(src), nil)
	}
	state := putState(src, dest, copy)
	var what string
	if copy {
		what = c.short(dest) + " (copy of " + c.short(src) + ")"
	} else {
		what = c.short(dest) + " -> " + c.short(src)
	}
	if note != "" {
		what += "  [" + note + "]"
	}
	if un {
		switch state {
		case "absent":
			return newStep(group, subject, "ok", "", nil)
		case "foreign":
			return newStep(group, subject, "skip", c.short(dest)+" is not okf's; left alone", nil)
		}
		return newStep(group, subject, "remove", what, func() error {
			if err := clear(dest); err != nil {
				return err
			}
			prune(c, pyDirname(dest))
			return nil
		})
	}
	switch state {
	case "ok":
		return newStep(group, subject, "ok", what, nil)
	case "foreign":
		return newStep(group, subject, "blocked", c.short(dest)+" exists and is not okf's; move it away, then re-run", nil)
	}
	status := "update"
	if state == "absent" {
		status = "create"
	}
	return newStep(group, subject, status, what, func() error { return put(src, dest, copy) })
}
