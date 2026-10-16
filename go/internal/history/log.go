package history

import (
	"bytes"
	"fmt"
	"iter"
	"strings"
	"time"

	"nas/volume1/data/git/okf-tools/go/internal/frontmatter"
	"nas/volume1/data/git/okf-tools/go/internal/spec"
)

// zeros is the id of no object, the old side of an added file.
const zeros = "0000000000000000000000000000000000000000"

// event is one change of one path by one commit: the index of the commit in scopeLog.commits, the
// raw status (`A`, `M`, `D`, `R087`, ...), the old path of a rename and the blob ids before and
// after.
type event struct {
	idx            int
	status         string
	oldPath        string
	oldSHA, newSHA string
}

// scopeLog is the commits and per-path changes of one scope, newest commit first.
type scopeLog struct {
	top     string
	commits []Commit
	byPath  map[string][]event // path -> its events, newest commit first
	blobs   *blobs             // started when a version is first asked for
	docs    map[string]frontmatter.Doc
}

// parseLog reads the output of the `git log` of this package: per commit `\x01`, the committer
// instant, `\x1f`, the author email, NUL, and the raw changes `:<modes> <old> <new> <status>`
// each followed by NUL, its path and, for a rename, the second path and NUL.
func parseLog(top string, raw []byte) (*scopeLog, error) {
	l := &scopeLog{top: top, byPath: map[string][]event{}, docs: map[string]frontmatter.Doc{}}
	chunks := bytes.Split(raw, []byte{1})
	for _, chunk := range chunks[1:] {
		head, rest, _ := bytes.Cut(chunk, []byte{0})
		when, email, _ := strings.Cut(decode(head), "\x1f")
		at, _ := spec.ParseOkfDatetimeText(when)
		l.commits = append(l.commits, Commit{Time: at, Email: email})
		fields := strings.Split(decode(rest), "\x00")
		for i := 0; i < len(fields); {
			record := strings.TrimLeft(fields[i], "\n")
			if !strings.HasPrefix(record, ":") {
				i++
				continue
			}
			parts := strings.Split(record[1:], " ")
			if len(parts) != 5 || parts[4] == "" {
				return nil, fmt.Errorf("git log: unexpected change record %q", record)
			}
			status := parts[4]
			width := 1
			if status[0] == 'R' || status[0] == 'C' {
				width = 2
			}
			if i+1 >= len(fields) {
				return nil, fmt.Errorf("git log: change record %q has no path", record)
			}
			paths := fields[i+1 : min(i+1+width, len(fields))]
			key := paths[len(paths)-1]
			l.byPath[key] = append(l.byPath[key],
				event{idx: len(l.commits) - 1, status: status, oldPath: paths[0], oldSHA: parts[2], newSHA: parts[3]})
			i += 1 + width
		}
	}
	return l, nil
}

// follow is the events of path, newest first, through its renames: after a rename the walk goes
// on with the old path and the commits older than the rename.
func (l *scopeLog) follow(path string) iter.Seq[event] {
	return func(yield func(event) bool) {
		floor := -1
		for {
			renamed := false
			for _, ev := range l.byPath[path] {
				if ev.idx <= floor {
					continue
				}
				if !yield(ev) {
					return
				}
				if ev.status[0] == 'R' {
					path, floor, renamed = ev.oldPath, ev.idx, true
					break
				}
			}
			if !renamed {
				return
			}
		}
	}
}

// doc is the frontmatter reading of a blob version, asked of git once.
func (l *scopeLog) doc(sha string) (frontmatter.Doc, error) {
	if d, ok := l.docs[sha]; ok {
		return d, nil
	}
	if l.blobs == nil {
		b, err := startBlobs(l.top)
		if err != nil {
			return frontmatter.Doc{}, err
		}
		l.blobs = b
	}
	text := ""
	if sha != zeros {
		var err error
		if text, _, err = l.blobs.text(sha); err != nil {
			return frontmatter.Doc{}, err
		}
	}
	d := frontmatter.Read(text)
	l.docs[sha] = d
	return d, nil
}

// changes reports whether the event changed the body of the file and whether it changed
// `generated.at`, compared as an instant. A deletion changes neither; an addition changes the body
// and `generated.at` when the new version has one.
func (l *scopeLog) changes(ev event) (body, generated bool, err error) {
	if ev.status[0] == 'D' {
		return false, false, nil
	}
	added, err := l.doc(ev.newSHA)
	if err != nil {
		return false, false, err
	}
	if ev.status[0] == 'A' {
		_, has := generatedAt(added)
		return true, has, nil
	}
	old, err := l.doc(ev.oldSHA)
	if err != nil {
		return false, false, err
	}
	oldAt, oldHas := generatedAt(old)
	newAt, newHas := generatedAt(added)
	return old.Body != added.Body, oldHas != newHas || (oldHas && !oldAt.Equal(newAt)), nil
}

// generatedAt is the `generated.at` instant of a version, when it has a valid one.
func generatedAt(d frontmatter.Doc) (time.Time, bool) {
	generated := frontmatter.Lookup(d.Root, "generated")
	if !frontmatter.IsMap(generated) {
		return time.Time{}, false
	}
	return spec.ParseOkfDatetime(frontmatter.Lookup(generated, "at"))
}

func (l *scopeLog) close() error {
	if l.blobs == nil {
		return nil
	}
	return l.blobs.close()
}
