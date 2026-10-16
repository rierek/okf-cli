package catalogue

import (
	"slices"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/frontmatter"
	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

// introMarkerRE matches the start of a line that cannot be an intro paragraph: a comment, a bullet
// or quote marker or a numbered item.
var introMarkerRE = pytext.Regexp(`^(?:<!--|[*\-+>]|\d+\.)`)

// SplitManagedBlock is Python _split_managed_block: body cut into (before, block, after) around
// the managed MarkStart..MarkEnd region, for a rewrite that keeps the block byte-identical.
// With a complete marker pair, block carries both markers and everything between them. With
// MarkStart but no MarkEnd, block carries everything from MarkStart to the end of body. Without
// MarkStart, before is the whole body and block and after are empty. Markers inside code fences
// count like any others.
func SplitManagedBlock(body string) (before, block, after string) {
	si := strings.Index(body, MarkStart)
	if si < 0 {
		return body, "", ""
	}
	ei := strings.Index(body[si:], MarkEnd)
	if ei < 0 {
		return body[:si], body[si:], ""
	}
	ei += si + len(MarkEnd)
	return body[:si], body[si:ei], body[ei:]
}

// MaskManagedBlock is Python _mask_managed_block: body without every MarkStart..MarkEnd region
// (non-greedy, the markers included), so a scan for hand-authored links in a reserved file never
// flags a generated one. A MarkStart without a later MarkEnd leaves the rest of body untouched.
func MaskManagedBlock(body string) string {
	if !strings.Contains(body, MarkStart) {
		return body
	}
	var out strings.Builder
	for {
		si := strings.Index(body, MarkStart)
		if si < 0 {
			break
		}
		ei := strings.Index(body[si+len(MarkStart):], MarkEnd)
		if ei < 0 {
			break
		}
		out.WriteString(body[:si])
		body = body[si+len(MarkStart)+ei+len(MarkEnd):]
	}
	out.WriteString(body)
	return out.String()
}

// Collapse is Python _collapse: every whitespace run becomes one space and the ends are trimmed.
// It is pytext.Collapse under the Python name.
func Collapse(s string) string { return pytext.Collapse(s) }

// IndexRow is one (title, name, description) row of an index block: a concept (name is its slug)
// or a subdirectory (name is its directory name).
type IndexRow struct {
	Title, Name, Description string
}

// sortByTitle is rows.sort(key=lambda x: x[0].casefold()): a stable sort by case-folded title.
func sortByTitle(rows []IndexRow) {
	type keyed struct {
		key string
		row IndexRow
	}
	ks := make([]keyed, len(rows))
	for i, r := range rows {
		ks[i] = keyed{pytext.Casefold(r.Title), r}
	}
	slices.SortStableFunc(ks, func(a, b keyed) int { return strings.Compare(a.key, b.key) })
	for i, k := range ks {
		rows[i] = k.row
	}
}

// ListDirConcepts is Python list_dir_concepts: the (title, slug, description) rows of the
// non-reserved .md files directly in dirpath, sorted by case-folded title. Titles that fold equal
// stay in file name order (ListDir is sorted; Python's os.listdir gave directory order).
func ListDirConcepts(dirpath string, fs TreeView) ([]IndexRow, error) {
	names, err := fs.ListDir(dirpath)
	if err != nil {
		return nil, err
	}
	rows := []IndexRow{}
	for _, fn := range names {
		if !strings.HasSuffix(fn, ".md") || IsReserved(fn) {
			continue
		}
		ap := Join(dirpath, fn)
		if !fs.IsFile(ap) {
			continue
		}
		m, err := MetaOf(ap, fs)
		if err != nil {
			return nil, err
		}
		rows = append(rows, IndexRow{m.Title, strings.TrimSuffix(fn, ".md"), m.Description})
	}
	sortByTitle(rows)
	return rows, nil
}

// IndexH1AndDesc is Python index_h1_and_desc: the first H1 text and the intro paragraph of an
// index file, read through fs with its frontmatter dropped. h1 is "" when there is no H1 (Python
// None; no caller tells it from an empty text). The intro is the first non-blank line after the
// first H1, only if it is a real paragraph: a heading, a comment, a bullet, a quote marker or a
// numbered item there means no intro, so desc is "".
func IndexH1AndDesc(ap string, fs TreeView) (h1, desc string, err error) {
	text, err := fs.Read(ap)
	if err != nil {
		return "", "", err
	}
	body := frontmatter.Read(text).Body
	lines := pytext.SplitLines(body, false)
	heads := IterHeadings(body)
	i := len(lines) // without an H1 the intro scan starts past the last line
	for _, h := range heads {
		if h.Level == 1 {
			h1, i = h.Text, h.Line+1
			break
		}
	}
	for ; i < len(lines); i++ {
		s := pytext.Strip(lines[i])
		if s == "" {
			continue
		}
		isHeading := slices.ContainsFunc(heads, func(h Heading) bool { return h.Line == i })
		if !isHeading && !introMarkerRE.MatchString(s) {
			desc = s
		}
		break
	}
	return h1, desc, nil
}

// ListSubdirsWithIndex is Python list_subdirs_with_index: the (title, subdirectory name,
// description) rows of the immediate subdirectories of dirpath that hold an index.md (any
// case), sorted by case-folded title. The title is the index's first H1, else the directory
// name. Dot directories and `assets` are skipped.
func ListSubdirsWithIndex(dirpath string, fs TreeView) ([]IndexRow, error) {
	names, err := fs.ListDir(dirpath)
	if err != nil {
		return nil, err
	}
	rows := []IndexRow{}
	for _, name := range names {
		p := Join(dirpath, name)
		if !fs.IsDir(p) || strings.HasPrefix(name, ".") || name == "assets" {
			continue
		}
		inner, err := fs.ListDir(p)
		if err != nil {
			return nil, err
		}
		idxName, ok := FindReservedName(inner, "index.md")
		if !ok {
			continue
		}
		h1, desc, err := IndexH1AndDesc(Join(p, idxName), fs)
		if err != nil {
			return nil, err
		}
		if h1 == "" {
			h1 = name
		}
		rows = append(rows, IndexRow{h1, name, desc})
	}
	sortByTitle(rows)
	return rows, nil
}
