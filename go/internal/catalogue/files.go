// Package catalogue is the layer every command builds on: the catalogue root and its
// configuration, sorted walks, bundle and concept iteration, scope resolution, file access, the
// marker literals, headings and fenced blocks, the tag and type registry reader, the managed
// index-block readers and the ctx helpers (Python okf.catalogue, read side).
package catalogue

import (
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"unicode/utf8"
)

// DecodeText decodes file bytes as Python's open(path, encoding="utf-8", errors="replace") reads
// them: every ill-formed byte sequence becomes one U+FFFD (a truncated multi-byte sequence counts
// once, Python's "maximal subpart" rule, not once per byte as Go's string conversion does) and
// universal newlines turn \r\n and a lone \r into \n.
func DecodeText(b []byte) string {
	text := toValidUTF8(b)
	if strings.IndexByte(text, '\r') < 0 {
		return text
	}
	return strings.ReplaceAll(strings.ReplaceAll(text, "\r\n", "\n"), "\r", "\n")
}

func toValidUTF8(b []byte) string {
	if utf8.Valid(b) {
		return string(b)
	}
	var out strings.Builder
	out.Grow(len(b))
	for i := 0; i < len(b); {
		r, size := utf8.DecodeRune(b[i:])
		if r != utf8.RuneError || size > 1 {
			out.Write(b[i : i+size])
			i += size
			continue
		}
		out.WriteRune(utf8.RuneError)
		i += invalidPrefixLen(b[i:])
	}
	return out.String()
}

// invalidPrefixLen is the length of the maximal subpart of an ill-formed UTF-8 sequence at the
// start of b: the lead byte plus the continuation bytes that still fit a well-formed sequence.
func invalidPrefixLen(b []byte) int {
	lo, hi, need := byte(0x80), byte(0xbf), 0
	switch c := b[0]; {
	case c >= 0xc2 && c <= 0xdf:
		need = 1
	case c == 0xe0:
		lo, need = 0xa0, 2
	case c >= 0xe1 && c <= 0xec, c == 0xee, c == 0xef:
		need = 2
	case c == 0xed:
		hi, need = 0x9f, 2
	case c == 0xf0:
		lo, need = 0x90, 3
	case c >= 0xf1 && c <= 0xf3:
		need = 3
	case c == 0xf4:
		hi, need = 0x8f, 3
	default:
		return 1
	}
	n := 1
	for ; n <= need && n < len(b); n++ {
		if b[n] < lo || b[n] > hi {
			break
		}
		lo, hi = 0x80, 0xbf
	}
	return n
}

// ReadFile is Python read_file: the text of a file, undecodable bytes replaced, line endings
// translated to \n. Read errors are returned as they are.
func ReadFile(path string) (string, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return "", err
	}
	return DecodeText(b), nil
}

// ReadFileVerbatim is Python read_file_verbatim: the text exactly as stored, line endings and
// bytes untouched, and ok false when the file is not valid UTF-8 (a rewrite must then leave it
// alone). Read errors are returned as they are.
func ReadFileVerbatim(path string) (text string, ok bool, err error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return "", false, err
	}
	if !utf8.Valid(b) {
		return "", false, nil
	}
	return string(b), true, nil
}

// WalkFunc is called for every directory of a SortedWalk, top-down. dirnames and filenames are
// sorted names; the return value lists the subdirectories to descend into (a subset of dirnames,
// in the order to visit), which is Python's in-place pruning of the dirnames list. Symbolic
// links to directories appear in dirnames but are never descended into, as with os.walk.
type WalkFunc func(dirpath string, dirnames, filenames []string) (descend []string)

// SortedWalk is Python sorted_walk: os.walk with directories and files in sorted name order, so a
// listing, preview or write plan does not depend on the filesystem. Unreadable directories are
// skipped silently. A top that is not a directory yields nothing.
func SortedWalk(top string, fn WalkFunc) {
	entries, err := os.ReadDir(top)
	if err != nil {
		return
	}
	var dirnames, filenames []string
	for _, e := range entries {
		if isDirEntry(top, e) {
			dirnames = append(dirnames, e.Name())
		} else {
			filenames = append(filenames, e.Name())
		}
	}
	sort.Strings(dirnames)
	sort.Strings(filenames)
	for _, name := range fn(top, dirnames, filenames) {
		path := Join(top, name)
		if info, err := os.Lstat(path); err == nil && info.Mode()&os.ModeSymlink != 0 {
			continue
		}
		SortedWalk(path, fn)
	}
}

// isDirEntry is DirEntry.is_dir(): a symbolic link to a directory counts as a directory.
func isDirEntry(dir string, e fs.DirEntry) bool {
	if e.Type()&fs.ModeSymlink != 0 {
		info, err := os.Stat(filepath.Join(dir, e.Name()))
		return err == nil && info.IsDir()
	}
	return e.IsDir()
}

// TreeView is the catalogue tree as the index readers and renderers see it. They read the tree
// through one of these, so a planner (work package G) can hand them a view of a tree that does not
// exist yet; RealFS is the tree as it is on disk.
type TreeView interface {
	// ListDir lists the names in a directory, sorted (os.listdir is unsorted; sorted keeps ties
	// between equal titles stable on every filesystem).
	ListDir(dir string) ([]string, error)
	IsFile(path string) bool
	IsDir(path string) bool
	// Walk is SortedWalk over the view.
	Walk(top string, fn WalkFunc)
	// Read is ReadFile over the view.
	Read(path string) (string, error)
	// ReadVerbatim is ReadFileVerbatim over the view.
	ReadVerbatim(path string) (text string, ok bool, err error)
}

type realFS struct{}

// RealFS is the TreeView of the file system.
var RealFS TreeView = realFS{}

func (realFS) ListDir(dir string) ([]string, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	names := make([]string, len(entries))
	for i, e := range entries {
		names[i] = e.Name()
	}
	return names, nil
}

func (realFS) IsFile(path string) bool {
	info, err := os.Stat(path)
	return err == nil && info.Mode().IsRegular()
}

func (realFS) IsDir(path string) bool {
	info, err := os.Stat(path)
	return err == nil && info.IsDir()
}

func (realFS) Walk(top string, fn WalkFunc)     { SortedWalk(top, fn) }
func (realFS) Read(path string) (string, error) { return ReadFile(path) }
func (realFS) ReadVerbatim(path string) (string, bool, error) {
	return ReadFileVerbatim(path)
}
