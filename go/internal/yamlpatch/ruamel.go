package yamlpatch

import (
	"regexp"
	"strings"
	"unicode/utf8"
)

// ruamelResolvers is the implicit resolver table of ruamel.yaml 0.19.1 for YAML 1.2, the reader and writer
// of the Python CLI (okf.catalogue.YAML_RT). ruamel gives a plain scalar the type of the first pattern of
// its table that matches, trying only the patterns listed for the first character of the scalar; a scalar
// that matches none is a string. The patterns are those of ruamel with the whitespace of their verbose
// form removed. yaml.v3 resolves differently (it has no `=` type, takes only a time zone of the form
// +01:00, reads 2026-13-45 as a string where ruamel fails on it, ...), so a plain string that passes the
// yaml.v3 probe of the self-check can still read back as another type or not at all through ruamel.
var ruamelResolvers = []struct {
	tag, first string
	re         *regexp.Regexp
}{
	{"null", "Nn~", regexp.MustCompile(`^(?:~|null|Null|NULL|)$`)},
	{"yaml", "!&*", regexp.MustCompile(`^(?:!|&|\*)$`)},
	{"float", "+-.0123456789", regexp.MustCompile(`^(?:[-+]?(?:[0-9][0-9_]*)\.[0-9_]*(?:[eE][-+]?[0-9]+)?|[-+]?(?:[0-9][0-9_]*)(?:[eE][-+]?[0-9]+)|[-+]?\.[0-9_]+(?:[eE][-+][0-9]+)?|[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN))$`)},
	{"int", "+-0123456789", regexp.MustCompile(`^(?:[-+]?0b[0-1_]+|[-+]?0o?[0-7_]+|[-+]?[0-9_]+|[-+]?0x[0-9a-fA-F_]+)$`)},
	{"timestamp", "0123456789", regexp.MustCompile(`^(?:[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]|[0-9][0-9][0-9][0-9]-[0-9][0-9]?-[0-9][0-9]?(?:[Tt]|[ \t]+)[0-9][0-9]?:[0-9][0-9]:[0-9][0-9](?:\.[0-9]*)?(?:[ \t]*(?:Z|[-+][0-9][0-9]?(?::[0-9][0-9])?))?)$`)},
	{"merge", "<", regexp.MustCompile(`^(?:<<)$`)},
	{"value", "=", regexp.MustCompile(`^(?:=)$`)},
	{"bool", "FTft", regexp.MustCompile(`^(?:true|True|TRUE|false|False|FALSE)$`)},
}

// resolvesToOtherType reports whether ruamel's reader gives the plain scalar s another type than string
// (null, boolean, number, timestamp, a tag of its own) or fails to construct it. Such a string is written
// quoted (ruamel's writer quotes exactly these).
func resolvesToOtherType(s string) bool {
	r, _ := utf8.DecodeRuneInString(s)
	for _, e := range ruamelResolvers {
		if strings.ContainsRune(e.first, r) && e.re.MatchString(s) {
			return true
		}
	}
	return false
}
