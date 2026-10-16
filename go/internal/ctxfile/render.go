package ctxfile

import (
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/frontmatter"
	"nas/volume1/data/git/okf-tools/go/internal/yamlpatch"
)

// ctxBody is the body of a ctx file that Python render_ctx builds: an empty line, the H1, the
// table with one row per entry, every line ended by a newline.
func ctxBody(slug string, entries []CtxEntry) string {
	var b strings.Builder
	b.WriteString("\n# " + slug + "\n\n| pos | mode | path | comment |\n|---|---|---|---|\n")
	for _, e := range entries {
		cell := "[" + pySplitextRoot(pyBasename(e.Path)) + "](/" + e.Path + ")"
		if strings.HasPrefix(e.Path, "~") || strings.HasPrefix(e.Path, "/") {
			cell = "`" + e.Path + "`"
		}
		// re.sub(r"\r?\n", " ", comment): a line break becomes one space, a lone \r stays
		comment := strings.ReplaceAll(strings.ReplaceAll(e.Comment, "\r\n", " "), "\n", " ")
		comment = strings.ReplaceAll(comment, "|", `\|`)
		b.WriteString("| " + posText(e) + " | " + e.Mode + " | " + cell + " | " + comment + " |\n")
	}
	return b.String()
}

// RenderCtx is Python render_ctx: the full text of a ctx file. existing is the text of the file it
// replaces. Its frontmatter keeps every other key, comment and quoting style; `type` is set only
// when it is not Context and `description` only when it is missing or differs from the given
// text. Without existing text, or when that has no frontmatter, the old text is dropped and a new
// block is written.
//
// Deviation (D02): an existing frontmatter that does not parse is not replaced by a new block, as
// Python does; the error of the writer is returned and no text. So is the rejection of a
// frontmatter the writer cannot patch.
func RenderCtx(slug, description string, entries []CtxEntry, existing *string) (string, error) {
	// the body starts with the newline that ends the closing delimiter line
	body := "\n" + ctxBody(slug, entries)
	if existing != nil {
		if doc := frontmatter.Read(*existing); doc.Head != "" {
			var edits []yamlpatch.Edit
			if frontmatter.Text(doc.Data(), "type", "") != CtxType {
				edits = append(edits, yamlpatch.SetValue("type", yamlpatch.Str(CtxType)))
			}
			if !frontmatter.Has(doc.Data(), "description") ||
				frontmatter.Text(doc.Data(), "description", "") != description {
				edits = append(edits, yamlpatch.SetValue("description", yamlpatch.Str(description)))
			}
			return yamlpatch.Apply(*existing, append(edits, yamlpatch.SetBody(body))...)
		}
	}
	return yamlpatch.Apply("",
		yamlpatch.NewKey("type", yamlpatch.Str(CtxType)),
		yamlpatch.NewKey("description", yamlpatch.Str(description)),
		yamlpatch.SetBody(body))
}

// CtxText is Python ctx_text: the full text that save_ctx writes for c over the file text existing
// (nil: a new file). The required entries come first, numbered 1..n in their order; every other
// entry is a reference entry without a position. c is not changed.
func CtxText(c Ctx, existing *string) (string, error) {
	var required, rest []CtxEntry
	for _, e := range c.Entries {
		if e.Mode == "pflicht" {
			n := len(required) + 1
			e.Pos = &n
			required = append(required, e)
		} else {
			e.Pos = nil
			rest = append(rest, e)
		}
	}
	return RenderCtx(c.Slug, c.Description, append(required, rest...), existing)
}
