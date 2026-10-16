// Package ctxfile is the ctx file model: one curated, ordered reading list per topic, stored as
// _ctx/<slug>.md, a frontmatter block (type Context, a description) over a markdown table of
// entries (Python okf.catalogue, the ctx section). It parses, renders and checks a ctx file and
// resolves the paths its entries name; the commands that edit a ctx build on it.
//
// The directory (catalogue.CtxDir), the slug listing (catalogue.CtxSlugs) and the file path
// (catalogue.Join of root, CtxDir and <slug>.md) belong to package catalogue.
package ctxfile

import (
	"regexp"
	"slices"
)

// CtxType is the frontmatter type of a ctx file.
const CtxType = "Context"

// CtxModes are the modes of an entry: pflicht (required reading, numbered 1..n in table order)
// and nachschlag (reference, no position).
var CtxModes = []string{"pflicht", "nachschlag"}

// CtxVerbs are the ctx subcommands, sorted. None of them can be a slug.
var CtxVerbs = []string{"add", "check", "create", "drop", "edit", "inbound", "list", "move",
	"outbound", "read", "remove", "rename", "show", "toc"}

// CtxReservedSlugs are the slugs no ctx can take: the verbs and the reserved file names (index,
// log, readme, index-map), sorted.
var CtxReservedSlugs = []string{"add", "check", "create", "drop", "edit", "inbound", "index",
	"index-map", "list", "log", "move", "outbound", "read", "readme", "remove", "rename", "show",
	"toc"}

// CtxSlugRE is Python CTX_SLUG_RE, `^[a-z0-9][a-z0-9-]*$` matched with re.match: lower-case
// letters, digits and hyphens, starting with a letter or digit. Python's `$` also matches before
// one final newline, so the pattern here allows it (Go's `$` does not).
var CtxSlugRE = regexp.MustCompile(`^[a-z0-9][a-z0-9-]*\n?$`)

// CtxEntry is one row of the table of a ctx file. A nil Pos is the `-` of a reference entry.
type CtxEntry struct {
	Pos     *int   `json:"pos"`
	Mode    string `json:"mode"`
	Path    string `json:"path"`
	Comment string `json:"comment"`
}

// Ctx is the content of a ctx file as a writer hands it over: the slug, the description and the
// entries in table order.
type Ctx struct {
	Slug        string
	Description string
	Entries     []CtxEntry
}

// LoadedCtx is a ctx file as LoadCtx reads it. Problems lists the rows that could not be read and
// are not in Entries.
type LoadedCtx struct {
	Slug        string     `json:"slug"`
	Description string     `json:"description"`
	Entries     []CtxEntry `json:"entries"`
	Problems    []string   `json:"problems"`
}

// CtxMembership is one entry of one ctx: the slug of the ctx and the entry.
type CtxMembership struct {
	Slug  string
	Entry CtxEntry
}

// CtxFinding is one problem of a ctx file: the id of the `kc/ctx/*` sub-rule that reports it and
// the message. The severity is the check registry's, not decided here.
type CtxFinding struct {
	Rule    string
	Message string
}

// CtxSlugProblem is Python ctx_slug_problem: why a slug cannot name a ctx, "" for a valid slug.
func CtxSlugProblem(slug string) string {
	if !CtxSlugRE.MatchString(slug) {
		return "use lowercase letters, digits and hyphens"
	}
	if slices.Contains(CtxReservedSlugs, slug) {
		return `"` + slug + `" is a reserved name`
	}
	return ""
}
