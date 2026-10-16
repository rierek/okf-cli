package catalogue

import (
	"strings"
	"unicode/utf8"

	"go.yaml.in/yaml/v3"

	"nas/volume1/data/git/okf-tools/go/internal/frontmatter"
)

// Meta is the (type, title, description) of a concept file as strings. Title falls back to the
// file stem, Description to "".
type Meta struct {
	Type, Title, Description string
}

// stemOf is os.path.basename(ap)[:-3]: the base name without its last three characters, which
// are the `.md` of a concept file.
func stemOf(ap string) string {
	base := ap[strings.LastIndexByte(ap, '/')+1:]
	for n := 0; n < 3 && base != ""; n++ {
		_, size := utf8.DecodeLastRuneInString(base)
		base = base[:len(base)-size]
	}
	return base
}

// MetaAndFm is Python meta_and_fm: the metadata of one concept file and its frontmatter mapping
// (nil when the file has no readable frontmatter block), read through fs once.
func MetaAndFm(ap string, fs TreeView) (Meta, *yaml.Node, error) {
	text, err := fs.Read(ap)
	if err != nil {
		return Meta{}, nil, err
	}
	fm := frontmatter.Read(text).Data()
	typ, title, desc := frontmatter.Meta(fm, stemOf(ap))
	return Meta{typ, title, desc}, fm, nil
}

// MetaOf is Python meta_of: the metadata of one concept file, read through fs.
func MetaOf(ap string, fs TreeView) (Meta, error) {
	m, _, err := MetaAndFm(ap, fs)
	return m, err
}
