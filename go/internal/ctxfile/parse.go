package ctxfile

import (
	"regexp"
	"strconv"
	"strings"
	"unicode"
	"unicode/utf8"

	"nas/volume1/data/git/okf-tools/go/internal/frontmatter"
	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

// ctxCols are the header cells of the table, compared in lower case (Python _CTX_COLS).
var ctxCols = [4]string{"pos", "mode", "path", "comment"}

var (
	// linkCellRE is the path cell of an entry inside the catalogue: a markdown link.
	linkCellRE = regexp.MustCompile(`^\[[^\]]*\]\((.*)\)$`)
	// codeCellRE is the path cell of an entry outside it: a code span.
	codeCellRE = regexp.MustCompile("^`([^`]+)`$")
)

// ctxCells is Python _ctx_cells: the stripped cells of a table row. A `|` splits unless a
// backslash precedes it, and one closing `|` that is not escaped ends the row.
func ctxCells(line string) []string {
	body := pytext.Strip(line)
	_, first := utf8.DecodeRuneInString(body) // the opening `|`
	body = body[first:]
	if strings.HasSuffix(body, "|") && !strings.HasSuffix(body, `\|`) {
		body = body[:len(body)-1]
	}
	var cells []string
	start := 0
	for i := range len(body) { // re.split(r"(?<!\\)\|", body); both marks are one byte
		if body[i] == '|' && (i == 0 || body[i-1] != '\\') {
			cells = append(cells, pytext.Strip(body[start:i]))
			start = i + 1
		}
	}
	return append(cells, pytext.Strip(body[start:]))
}

// isCtxHeader reports whether a row is the header `| pos | mode | path | comment |`, in any case.
func isCtxHeader(line string) bool {
	cells := ctxCells(line)
	if len(cells) != len(ctxCols) {
		return false
	}
	for i, c := range cells {
		if pytext.Lower(c) != ctxCols[i] {
			return false
		}
	}
	return true
}

// decimalValue is the value of a character that Python's \d matches and int() reads: a Unicode
// decimal digit (category Nd). The digits of a script are encoded as one run of ten, zero first.
func decimalValue(r rune) (int, bool) {
	if r >= '0' && r <= '9' {
		return int(r - '0'), true
	}
	if !unicode.Is(unicode.Nd, r) {
		return 0, false
	}
	for _, rg := range unicode.Nd.R16 {
		if lo, hi := rune(rg.Lo), rune(rg.Hi); lo <= r && r <= hi {
			return int(r-lo) % 10, true
		}
	}
	for _, rg := range unicode.Nd.R32 {
		if lo, hi := rune(rg.Lo), rune(rg.Hi); lo <= r && r <= hi {
			return int(r-lo) % 10, true
		}
	}
	return 0, false
}

// ctxPos reads a pos cell that is not `-` as Python does: re.fullmatch(r"-?\d+") then int(). isInt
// is false when the cell does not match; fits is false when it does but the number is beyond
// int (Python's integers have no limit, a Pos does).
func ctxPos(cell string) (pos int, isInt, fits bool) {
	digits := strings.TrimPrefix(cell, "-")
	if digits == "" {
		return 0, false, false
	}
	var ascii strings.Builder
	if len(digits) != len(cell) {
		ascii.WriteByte('-')
	}
	for _, r := range digits {
		d, ok := decimalValue(r)
		if !ok {
			return 0, false, false
		}
		ascii.WriteByte(byte('0' + d))
	}
	pos, err := strconv.Atoi(ascii.String())
	return pos, true, err == nil
}

// ParseCtx is Python parse_ctx: the description, the entries and the problems of a ctx file text.
// The first row of the table that reads `| pos | mode | path | comment |` starts it; its rows
// follow the separator row up to the first line that is no row. A row that cannot be read is
// reported in problems (its number counts from the first row after the separator) and is not an
// entry. The modes are lower-cased; whether they are valid is a finding of CtxFindings.
//
// Deviation: a pos that is an integer beyond the range of int is reported as a problem of its
// row; Python reads it. Entries and problems are empty, never nil.
func ParseCtx(text string) (description string, entries []CtxEntry, problems []string) {
	return parseCtx(frontmatter.Read(text))
}

func parseCtx(doc frontmatter.Doc) (string, []CtxEntry, []string) {
	desc := frontmatter.Text(doc.Data(), "description", "")
	lines := pytext.SplitLines(doc.Body, false)
	start := -1
	for i, ln := range lines {
		if strings.HasPrefix(ln, "|") && isCtxHeader(ln) {
			start = i
			break
		}
	}
	entries, problems := []CtxEntry{}, []string{}
	if start < 0 {
		return desc, entries, []string{`no table with header "pos | mode | path | comment"`}
	}
	rows := []string{}
	if start+2 < len(lines) {
		rows = lines[start+2:]
	}
	n := 0
	for _, ln := range rows {
		if !strings.HasPrefix(ln, "|") {
			break
		}
		n++
		cells := ctxCells(ln)
		if len(cells) != 4 {
			problems = append(problems, "row "+strconv.Itoa(n)+": expected 4 cells, found "+strconv.Itoa(len(cells)))
			continue
		}
		posCell, mode, pathCell, comment := cells[0], cells[1], cells[2], cells[3]
		var pos *int
		if posCell != "-" {
			v, isInt, fits := ctxPos(posCell)
			if !isInt {
				problems = append(problems, "row "+strconv.Itoa(n)+": pos \""+posCell+"\" is neither an integer nor -")
				continue
			}
			if !fits {
				problems = append(problems, "row "+strconv.Itoa(n)+": pos \""+posCell+"\" is out of range")
				continue
			}
			pos = &v
		}
		var path string
		if m := linkCellRE.FindStringSubmatch(pathCell); m != nil {
			path = strings.TrimPrefix(m[1], "/")
		} else if m := codeCellRE.FindStringSubmatch(pathCell); m != nil {
			path = m[1]
		} else {
			problems = append(problems, "row "+strconv.Itoa(n)+": path cell is neither a catalogue link nor a code span")
			continue
		}
		entries = append(entries, CtxEntry{Pos: pos, Mode: pytext.Lower(mode), Path: path,
			Comment: strings.ReplaceAll(comment, `\|`, "|")})
	}
	return desc, entries, problems
}
