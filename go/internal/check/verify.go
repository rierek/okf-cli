package check

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/cli"
	"nas/volume1/data/git/okf-tools/go/internal/diffs"
	"nas/volume1/data/git/okf-tools/go/internal/envelope"
	"nas/volume1/data/git/okf-tools/go/internal/frontmatter"
	"nas/volume1/data/git/okf-tools/go/internal/okferr"
	"nas/volume1/data/git/okf-tools/go/internal/pytext"
	"nas/volume1/data/git/okf-tools/go/internal/spec"
	"nas/volume1/data/git/okf-tools/go/internal/yamlpatch"
)

// runVerify is Python cmd_verify: `verify` appends one `{by, at}` entry to the `verified` key of a
// concept (OKF §5.2). It is the one command that writes `verified`; nothing calls it for the caller.
// The write goes through the line-patch writer, so every other key, comment, quoting style and the
// body stay as they were; a frontmatter the writer declines is refused with no write.
func runVerify(root string, a *cli.Args) (any, error) {
	by, concept := a.String("by"), a.String("concept")
	if _, _, ok := spec.ParseActorText(by); !ok {
		return nil, okferr.Newf(okferr.InvalidInput, "--by %s is not `<producer>/<version>`, `human:<id>` or "+
			"`process:<id>`", pytext.ReprStr(by))
	}
	ap, err := catalogue.ResolveConcept(root, concept)
	if err != nil {
		return nil, err
	}
	if catalogue.IsReserved(filepath.Base(ap)) {
		return nil, okferr.Newf(okferr.InvalidInput, "%s is a reserved file; verify takes a concept", concept)
	}
	stored, err := os.ReadFile(ap)
	if err != nil {
		return nil, err
	}
	// The decisions of Python read the decoded text (undecodable bytes replaced, line endings
	// translated); the patch is made on the stored bytes, so the file keeps its line endings.
	doc := frontmatter.Read(catalogue.DecodeText(stored))
	if doc.Head != "" && doc.Root == nil {
		return nil, okferr.Newf(okferr.InvalidInput, "frontmatter does not parse: %s", doc.Err)
	}
	at := spec.Utcnow().Format("2006-01-02T15:04:05Z")
	if frontmatter.Has(doc.Root, "verified") && !spec.VerifiedIsWellFormed(doc.Root) {
		return nil, okferr.New(okferr.InvalidInput, "`verified` is neither a mapping nor a list of mappings; "+
			"fix it by hand before verifying")
	}
	// The `at` is written as the plain timestamp the spec shows, not as a quoted string.
	patched, err := yamlpatch.Apply(string(stored),
		yamlpatch.AppendItem("verified", yamlpatch.Map("by", yamlpatch.Str(by), "at", yamlpatch.Plain(at))))
	if err != nil {
		return nil, err
	}
	if err := diffs.WriteFileVerbatim(ap, patched); err != nil {
		return nil, err
	}
	rel, err := filepath.Rel(root, ap)
	if err != nil {
		rel = ap
	}
	path := strings.TrimSuffix(filepath.ToSlash(rel), ".md")
	if a.JSON {
		return envelope.O("path", path, "entry", envelope.O("by", by, "at", at)), nil
	}
	_, err = fmt.Printf("verified %s by %s at %s\n", path, by, at)
	return nil, err
}
