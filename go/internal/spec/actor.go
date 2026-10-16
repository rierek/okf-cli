package spec

import (
	"strings"

	"go.yaml.in/yaml/v3"

	"nas/volume1/data/git/okf-tools/go/internal/frontmatter"
	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

// ParseActorText is Python parse_actor for a str value (OKF §7): ("producer",
// "<producer>/<version>"), ("human", "<id>") or ("process", "<id>") with every part non-empty,
// else ok is false. A value with leading or trailing whitespace is no actor; the id of `human:`
// and `process:` is returned as written.
func ParseActorText(value string) (kind, text string, ok bool) {
	if value != pytext.Strip(value) {
		return "", "", false
	}
	if k, ident, found := strings.Cut(value, ":"); found && (k == "human" || k == "process") {
		if pytext.Strip(ident) == "" {
			return "", "", false
		}
		return k, ident, true
	}
	if producer, version, found := strings.Cut(value, "/"); found && pytext.Strip(producer) != "" && pytext.Strip(version) != "" {
		return "producer", value, true
	}
	return "", "", false
}

// ParseActor is ParseActorText for a frontmatter value: anything that is not a string is no actor.
func ParseActor(n *yaml.Node) (kind, text string, ok bool) {
	if !isStr(n) {
		return "", "", false
	}
	return ParseActorText(frontmatter.ScalarText(n))
}
