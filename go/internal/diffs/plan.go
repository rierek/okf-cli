package diffs

import (
	"errors"
	"os"
	"strings"
	"unicode/utf8"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
)

// WriteFileVerbatim is Python write_file_verbatim: text written as UTF-8 with no newline
// translation, the file created or truncated. Python raises UnicodeEncodeError on a str that holds
// a lone surrogate, after it has truncated the file; text that is not valid UTF-8 is that str
// here, and is refused before the file is touched.
func WriteFileVerbatim(path, text string) error {
	if !utf8.ValidString(text) {
		return errors.New("write " + path + ": text is not valid UTF-8")
	}
	f, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, 0o666)
	if err != nil {
		return err
	}
	_, err = f.WriteString(text)
	if cerr := f.Close(); err == nil {
		err = cerr
	}
	return err
}

// WritePlan is Python write_plan: it writes the new text of every entry under root, byte for byte,
// creating missing directories. Entries whose texts are equal are left alone, and so are entries
// that delete a file (nil New): the caller removes or moves that file. The first failure stops
// the run; the entries before it stay written.
func WritePlan(root string, plan []PlanEntry) error {
	for _, e := range plan {
		if e.New == nil || sameText(e.Old, e.New) {
			continue
		}
		ap := catalogue.Join(root, e.Path)
		if err := os.MkdirAll(dirname(ap), 0o777); err != nil {
			return err
		}
		if err := WriteFileVerbatim(ap, *e.New); err != nil {
			return err
		}
	}
	return nil
}

// dirname is Python os.path.dirname: everything before the last "/", without the trailing
// slashes unless the head is all slashes. Unlike filepath.Dir it does not clean the path, so a
// `..` behind a symbolic link still resolves in the file system, as it did for Python.
func dirname(p string) string {
	head := p[:strings.LastIndexByte(p, '/')+1]
	if strings.Trim(head, "/") != "" {
		head = strings.TrimRight(head, "/")
	}
	return head
}
