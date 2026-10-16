package spec

import (
	"os"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/frontmatter"
)

// DeclaredOkfVersion is Python declared_okf_version: the `okf_version` string in the frontmatter
// of `<bundleRoot>/index.md` (OKF §12), the file found case-insensitively in directory order as
// os.listdir lists it. ok is false when there is no index.md, no frontmatter, no such key, an
// unreadable directory or file, or a value that is not a YAML string: an unquoted `0.2` loads as
// a float and declares nothing.
func DeclaredOkfVersion(bundleRoot string) (version string, ok bool) {
	dir, err := os.Open(bundleRoot)
	if err != nil {
		return "", false
	}
	defer dir.Close()
	names, err := dir.Readdirnames(-1)
	if err != nil {
		return "", false
	}
	name, found := catalogue.FindReservedName(names, "index.md")
	if !found {
		return "", false
	}
	text, err := catalogue.ReadFile(catalogue.Join(bundleRoot, name))
	if err != nil {
		return "", false
	}
	value := frontmatter.Lookup(frontmatter.Read(text).Root, "okf_version")
	if !isStr(value) {
		return "", false
	}
	return frontmatter.ScalarText(value), true
}
