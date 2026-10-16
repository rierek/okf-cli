package spec

import (
	"fmt"
	"time"

	"go.yaml.in/yaml/v3"

	"nas/volume1/data/git/okf-tools/go/internal/frontmatter"
)

// ParseOkfDatetimeText is Python parse_okf_datetime for a str: the timezone-aware time of an ISO
// 8601 datetime with an explicit UTC offset, read as CPython 3.14 datetime.fromisoformat reads it.
// ok is false for an offset-less datetime, a date alone or anything else, so a missing offset is
// never read as UTC.
//
// Compare the results as instants (Equal, Before, After), never with ==. The microseconds of the
// result are those of Python (a longer fraction is cut, not rounded); a string with invalid UTF-8
// is read as Python reads a command-line argument, each such byte a lone surrogate.
func ParseOkfDatetimeText(value string) (time.Time, bool) { return fromISO(value) }

// ParseOkfDatetime is Python parse_okf_datetime for a frontmatter value: the string of a `str`
// scalar read like ParseOkfDatetimeText, or the datetime the YAML loader resolves an unquoted
// timestamp to, which counts only when it carries an offset (`Z` or `±HH[:MM]`). A date, a number,
// a list and every other value gives ok false.
//
// Whether an unquoted scalar is a timestamp is decided from its text as ruamel decides it, not by
// the tag of the YAML package, which resolves other shapes (`2026-1-5T1:2:3Z`) and misses some
// (`2026-01-05 10:00:00 +02:00`).
func ParseOkfDatetime(n *yaml.Node) (time.Time, bool) {
	n = frontmatter.Deref(n)
	tagged := n != nil && n.Style&yaml.TaggedStyle != 0
	switch tag := frontmatter.Tag(n); {
	case tag == "!!timestamp" && tagged: // an explicit tag: built from any text of the shape
		t, ok, _ := yamlTimestamp(n.Value)
		return t, ok
	case tag == "!!str" && tagged: // an explicit tag: ruamel keeps a TaggedScalar, no str
		return time.Time{}, false
	case tag == "!!str" || tag == "!!timestamp":
		if n.Style&quoted == 0 {
			if t, ok, loaded := yamlTimestamp(n.Value); loaded {
				return t, ok
			}
		}
		return fromISO(n.Value)
	}
	return time.Time{}, false
}

// Utcnow is Python utcnow: the instant of a call, in UTC and at microsecond resolution, the one
// clock of every comparison with `stale_after`.
func Utcnow() time.Time { return time.Now().UTC().Truncate(time.Microsecond) }

// Isoformat is Python datetime.isoformat() of an aware datetime: `YYYY-MM-DDTHH:MM:SS[.ffffff]`
// and the offset as `+HH:MM[:SS]`, `+00:00` for UTC (never `Z`, which time.RFC3339 would write).
func Isoformat(t time.Time) string {
	s := t.Format("2006-01-02T15:04:05")
	if micro := t.Nanosecond() / 1000; micro != 0 {
		s += fmt.Sprintf(".%06d", micro)
	}
	_, offset := t.Zone()
	sign := '+'
	if offset < 0 {
		sign, offset = '-', -offset
	}
	s += fmt.Sprintf("%c%02d:%02d", sign, offset/3600, offset%3600/60)
	if seconds := offset % 60; seconds != 0 {
		s += fmt.Sprintf(":%02d", seconds)
	}
	return s
}
