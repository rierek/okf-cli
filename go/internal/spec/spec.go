// Package spec is the OKF v0.2 helper layer (Python okf.spec): the actor and datetime parsers, the
// readers of `verified`, the trust tier, the staleness test and the one UTC clock that check,
// the derived output, the filters and `verify` share.
//
// A frontmatter is the root mapping node of package frontmatter, nil when the file has none. A
// value Python saw as a typed scalar is decided by frontmatter.Tag, with two exceptions: an
// explicit `!!str` tag (ruamel loads a TaggedScalar, no str) and whether an unquoted scalar is a
// timestamp (decided as ruamel decides it, see ParseOkfDatetime). A function whose Python argument
// is a str or a frontmatter value comes twice: the plain name takes the frontmatter value (a
// *yaml.Node), the Text name a Go string.
package spec

import (
	"go.yaml.in/yaml/v3"

	"nas/volume1/data/git/okf-tools/go/internal/frontmatter"
)

// isStr reports whether Python loads the value n as a str: a scalar the YAML package tags !!str,
// but not one with an explicit `!!str` tag, which ruamel keeps as a TaggedScalar.
func isStr(n *yaml.Node) bool {
	n = frontmatter.Deref(n)
	return frontmatter.IsString(n) && n.Style&yaml.TaggedStyle == 0
}
