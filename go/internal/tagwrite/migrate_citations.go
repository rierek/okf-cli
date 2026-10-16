package tagwrite

import (
	"regexp"
	"strings"
	"unicode/utf8"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/linkscan"
	"nas/volume1/data/git/okf-tools/go/internal/pytext"
	"nas/volume1/data/git/okf-tools/go/internal/yamlpatch"
)

var (
	// citationHeadings are the case-folded titles of a citation section (Python CITATION_HEADINGS).
	citationHeadings = map[string]bool{"citations": true, "quellen": true, "sources": true}
	// citationURL is the `url` alternative of Python RESOURCE_RE.
	citationURL = pytext.Regexp("https?://[^\\s<>`)]+")
	// citationFileExt is Python FILE_EXT_RE.
	citationFileExt = regexp.MustCompile(`\.[A-Za-z0-9]{1,8}$`)
)

// citationResources is Python _resources: the resources of one block text, in order of appearance.
// RE2 has no backreference, so the three alternatives of RESOURCE_RE (a link, an inline code span,
// a bare URL) are each searched in the rest of the text and the earliest start wins, as in the
// finditer scan. They start with different characters, so two never start together.
func citationResources(text string) []string {
	var out []string
	for rest := text; rest != ""; {
		var hit [3][]int // link, code span, URL: the leftmost match of each
		hit[0] = catalogue.CrosslinkRE.FindStringSubmatchIndex(rest)
		if spans := linkscan.InlineCodeSpans(rest); len(spans) > 0 {
			hit[1] = spans[0]
		}
		hit[2] = citationURL.FindStringIndex(rest)
		first := -1
		for i, h := range hit {
			if h != nil && (first < 0 || h[0] < hit[first][0]) {
				first = i
			}
		}
		if first < 0 {
			break
		}
		h := hit[first]
		switch first {
		case 0:
			target := pytext.Fields(strings.Trim(pytext.Strip(rest[h[4]:h[5]]), "<>"))
			if len(target) > 0 {
				out = append(out, target[0])
			}
		case 1:
			code := pytext.Strip(strings.Trim(rest[h[0]:h[1]], "`"))
			if strings.Contains(code, "/") || citationFileExt.MatchString(code) {
				out = append(out, code)
			}
		default:
			out = append(out, strings.TrimRight(rest[h[0]:h[1]], ".,;:!?"))
		}
		rest = rest[h[1]:]
	}
	nonEmpty := out[:0]
	for _, r := range out {
		if r != "" {
			nonEmpty = append(nonEmpty, r)
		}
	}
	return nonEmpty
}

// citationHTML is Python HTML_BLOCK_RE.match(s), `<(?:[!?/]|[A-Za-z](?![A-Za-z0-9+.-]*:[^\s<>]*>))`:
// a `<` that opens a declaration, a closing tag or a tag, but not an autolink `<scheme:...>`.
func citationHTML(s string) bool {
	if len(s) < 2 || s[0] != '<' {
		return false
	}
	c := s[1]
	if c == '!' || c == '?' || c == '/' {
		return true
	}
	if !(c >= 'A' && c <= 'Z' || c >= 'a' && c <= 'z') {
		return false
	}
	i := 2
	for i < len(s) && (s[i] >= 'A' && s[i] <= 'Z' || s[i] >= 'a' && s[i] <= 'z' || s[i] >= '0' && s[i] <= '9' ||
		s[i] == '+' || s[i] == '.' || s[i] == '-') {
		i++
	}
	if i >= len(s) || s[i] != ':' {
		return true
	}
	for i++; i < len(s); {
		r, size := utf8.DecodeRuneInString(s[i:])
		if r == '<' || r == '>' || pytext.IsSpace(r) {
			break
		}
		i += size
	}
	return i >= len(s) || s[i] != '>'
}

// citationBlocks is Python _citation_blocks: the blocks (a paragraph or a list item, as one text)
// of the lines of a section, or the reason the section does not migrate mechanically.
func citationBlocks(lines []string) ([]string, string) {
	if len(catalogue.FenceLineSpans(lines)) > 0 {
		return nil, "section holds fenced code"
	}
	var blocks [][]string
	open := false // Python `cur is not None`: the last block still takes continuation lines
	for _, line := range lines {
		s := pytext.Strip(line)
		item := linkscan.ListItemRE.MatchString(line)
		switch {
		case s == "":
			open = false
		case strings.HasPrefix(s, "|"):
			return nil, "section holds a table"
		case strings.HasPrefix(s, ">"):
			return nil, "section holds a quote"
		case citationHTML(s):
			return nil, "section holds an HTML block"
		case !open && !item && (strings.HasPrefix(line, "    ") || strings.HasPrefix(line, "\t")):
			return nil, "section holds an indented code block"
		case item:
			blocks = append(blocks, []string{pytext.Strip(linkscan.ListItemRE.ReplaceAllString(line, ""))})
			open = true
		case !open:
			blocks = append(blocks, []string{s})
			open = true
		default:
			blocks[len(blocks)-1] = append(blocks[len(blocks)-1], s)
		}
	}
	texts := make([]string, len(blocks))
	for i, b := range blocks {
		texts[i] = strings.Join(b, " ")
	}
	return texts, ""
}

// citationSources is Python _citation_sources: the body without its citation sections, the
// `sources` entries they hold (the title on the first resource of a block only) and the reason
// they do not migrate. With no citation section the body comes back unchanged and the entries are
// empty; with a reason the body and the entries are empty.
func citationSources(body string) (string, []yamlpatch.Value, string) {
	lines, heads := pytext.SplitLines(body, true), catalogue.IterHeadings(body)
	drop := make([]bool, len(lines))
	var entries []yamlpatch.Value
	cut := false
	for k, h := range heads {
		if !citationHeadings[pytext.Casefold(h.Text)] {
			continue
		}
		later, end := heads[k+1:], len(lines)
		for _, n := range later {
			if n.Level <= h.Level {
				end = n.Line
				break
			}
		}
		for _, n := range later {
			if h.Line < n.Line && n.Line < end {
				return "", nil, "citation section " + pytext.ReprStr(h.Text) + " holds a sub-heading"
			}
		}
		blocks, reason := citationBlocks(lines[h.Line+1 : end])
		if reason != "" {
			return "", nil, "citation section " + pytext.ReprStr(h.Text) + ": " + reason
		}
		if len(blocks) == 0 {
			return "", nil, "citation section " + pytext.ReprStr(h.Text) + " holds no block"
		}
		for _, block := range blocks {
			found := citationResources(block)
			if len(found) == 0 {
				return "", nil, "citation section " + pytext.ReprStr(h.Text) +
					": block without a resource: " + block
			}
			entries = append(entries, yamlpatch.Map("resource", yamlpatch.Str(found[0]), "title", yamlpatch.Str(block)))
			for _, r := range found[1:] {
				entries = append(entries, yamlpatch.Map("resource", yamlpatch.Str(r)))
			}
		}
		for i := h.Line; i < end; i++ {
			drop[i] = true
		}
		cut = true
	}
	if !cut {
		return body, nil, ""
	}
	var kept strings.Builder
	for i, line := range lines {
		if !drop[i] {
			kept.WriteString(line)
		}
	}
	return kept.String(), entries, ""
}
