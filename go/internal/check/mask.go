package check

import (
	"regexp"
	"strconv"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

// The code-span mask and the XML-like tag scanner: the scan helpers `fix-crosslinks` and
// `fix-xml-tags` (work package G) and the rule kc/markup/xml-like-tags share (Python
// _mask_code_spans, _unmask, XML_TAG_CHAIN_RE, _is_ignorable_chain, find_xml_like_tags).

var (
	inlineCodeRE = regexp.MustCompile("`[^`\\n]+`")
	placeholder  = regexp.MustCompile(`\x00([0-9]+)\x00`)

	// XMLTagChainRE matches an angle-bracket tag followed by `.`-separated tags or name segments
	// (`<info>.<other>`, `<tag>.<tag2>.go`).
	XMLTagChainRE = pytext.Regexp(`</?[A-Za-z][\w:-]*>(?:\.(?:</?[A-Za-z][\w:-]*>|[A-Za-z0-9_-]+))*`)

	autolinkRE = regexp.MustCompile(`^[A-Za-z][A-Za-z0-9+.-]*://`)
)

// safeHTMLTags are the tag names IsIgnorableChain reads as real HTML.
var safeHTMLTags = map[string]bool{"br": true, "hr": true, "sub": true, "sup": true, "kbd": true, "mark": true, "code": true, "wbr": true}

// MaskCodeSpans stashes what a pattern scan or a rewrite of a body must skip and returns the masked
// text with the stashed spans: first the materialised canon blocks (`okf:sync` spans), then fenced
// code blocks (three or more backticks or tildes), then inline code. Each span is replaced by
// `\x00<index>\x00`. The sync stash runs first and is not cosmetic: a materialised block is owned
// by its canon concept, so a scanner reading through the mask must neither report nor rewrite
// inside it. The frontmatter is split off by the caller.
func MaskCodeSpans(body string) (masked string, tokens []string) {
	stash := func(span string) string {
		tokens = append(tokens, span)
		return "\x00" + strconv.Itoa(len(tokens)-1) + "\x00"
	}
	body = catalogue.SyncSpanRE.ReplaceAllStringFunc(body, stash)
	body = maskFences(body, stash)
	body = inlineCodeRE.ReplaceAllStringFunc(body, stash)
	return body, tokens
}

// maskFences is re.sub(r"(`{3,}|~{3,})[\s\S]*?\1", stash, body) of Python: a run of three or more
// backticks (or tildes) opens a span that ends with the nearest later run of exactly the same text.
// A run with no such closing fence is tried with one character less (the group backtracks) down to
// three; a run that fails at every length cannot open a span from any later start in it either.
func maskFences(s string, stash func(string) string) string {
	var out strings.Builder
	last := 0
	for i := 0; i < len(s); {
		c := s[i]
		if c != '`' && c != '~' {
			i++
			continue
		}
		run := 1
		for i+run < len(s) && s[i+run] == c {
			run++
		}
		end := -1
		for k := run; k >= 3 && end < 0; k-- {
			fence := strings.Repeat(string(c), k)
			if at := strings.Index(s[i+k:], fence); at >= 0 {
				end = i + k + at + k
			}
		}
		if end < 0 {
			i += run
			continue
		}
		out.WriteString(s[last:i])
		out.WriteString(stash(s[i:end]))
		i, last = end, end
	}
	if last == 0 {
		return s
	}
	out.WriteString(s[last:])
	return out.String()
}

// Unmask restores every span MaskCodeSpans stashed, byte-identically. A stashed span can itself
// hold the placeholders of spans stashed before it (a fenced block around a sync span), so a
// restored span is unmasked in turn; it can only name an earlier span, which bounds the recursion
// even for a text that holds NUL-digit-NUL sequences of its own.
func Unmask(text string, tokens []string) string { return unmask(text, tokens, len(tokens)) }

// unmask expands the placeholders of text that name a span below limit.
func unmask(text string, tokens []string, limit int) string {
	if !strings.Contains(text, "\x00") {
		return text
	}
	return placeholder.ReplaceAllStringFunc(text, func(m string) string {
		i, err := strconv.Atoi(m[1 : len(m)-1])
		if err != nil || i >= limit {
			return m
		}
		return unmask(tokens[i], tokens, i)
	})
}

// IsIgnorableChain is Python _is_ignorable_chain: real HTML (`<br>`, `</br>`, ...) without a dot
// and markdown autolinks (`<https://...>`) are no violation; only placeholder-shaped chains are.
func IsIgnorableChain(chain string) bool {
	if !strings.Contains(chain, ".") && safeHTMLTags[pytext.Lower(strings.Trim(chain, "<>/"))] {
		return true
	}
	first, _, _ := strings.Cut(chain, ".")
	inner := ""
	if runes := []rune(first); len(runes) >= 2 { // Python first[1:-1]
		inner = strings.TrimLeft(string(runes[1:len(runes)-1]), "/")
	}
	return autolinkRE.MatchString(inner)
}

// FindXMLLikeTags is Python find_xml_like_tags: the angle-bracket placeholder chains of a body
// outside code spans, which Obsidian misreads as unclosed XML or HTML tags.
func FindXMLLikeTags(body string) []string {
	masked, _ := MaskCodeSpans(body)
	var hits []string
	for _, m := range XMLTagChainRE.FindAllString(masked, -1) {
		if !IsIgnorableChain(m) {
			hits = append(hits, m)
		}
	}
	return hits
}
