package spec

import (
	"regexp"
	"strconv"
	"time"

	"go.yaml.in/yaml/v3"
)

// timestampRE is the scalar shape ruamel resolves to !!timestamp and constructs a datetime from
// (resolver and constructor patterns of ruamel.yaml 0.19 joined, a time of day required: a bare
// date is a date, which has no offset). Groups: year, month, day, hour, minute, second, fraction,
// zone, zone sign, zone hour, zone minute.
var timestampRE = regexp.MustCompile(`^([0-9]{4})-([0-9]{1,2})-([0-9]{1,2})(?:[Tt]|[ \t]+)` +
	`([0-9]{1,2}):([0-9]{2}):([0-9]{2})(?:\.([0-9]*))?` +
	`(?:[ \t]*(Z|([-+])([0-9]{1,2})(?::([0-9]{2}))?))?$`)

// quoted is every style of a scalar that ruamel does not resolve: a quoted or block scalar is a
// str.
const quoted = yaml.DoubleQuotedStyle | yaml.SingleQuotedStyle | yaml.LiteralStyle | yaml.FoldedStyle

// yamlTimestamp is the datetime ruamel builds from the text of a scalar it resolves, or is told
// by a `!!timestamp` tag, to be a timestamp. loaded is false when the text has not the shape of a
// timestamp: ruamel then keeps an unquoted scalar a str, and the caller reads it as one. When
// loaded, ok is false for a datetime without an offset and for one the Python loader refuses
// (month 13, hour 24, an offset of a day or more): a file Python could not read at all.
//
// The fraction is rounded at the sixth digit, half up, as ruamel does. An offset has no
// microseconds.
func yamlTimestamp(text string) (t time.Time, ok, loaded bool) {
	m := timestampRE.FindStringSubmatch(text)
	if m == nil {
		return t, false, false
	}
	if m[8] == "" { // no zone: naive
		return t, false, true
	}
	num := func(s string) int { v, _ := strconv.Atoi(s); return v }
	year, month, day := num(m[1]), num(m[2]), num(m[3])
	hour, minute, second := num(m[4]), num(m[5]), num(m[6])
	micro, carry := 0, false
	if fraction := m[7]; fraction != "" {
		micro = num((fraction + "000000")[:6])
		if len(fraction) > 6 && fraction[6] > '4' {
			micro++
		}
		if micro > 999999 { // rounded up to the next second
			micro, carry = 0, true
		}
	}
	offset := 0
	if m[9] != "" {
		offset = num(m[10])*3600 + num(m[11])*60
		if m[9] == "-" {
			offset = -offset
		}
	}
	if !validDate(year, month, day) || hour > 23 || minute > 59 || second > 59 || offset <= -86400 || offset >= 86400 {
		return t, false, true
	}
	t = time.Date(year, time.Month(month), day, hour, minute, second, micro*1000, time.UTC).
		Add(-time.Duration(offset) * time.Second)
	if carry {
		t = t.Add(time.Second)
	}
	if offset == 0 {
		return t, true, true
	}
	return t.In(time.FixedZone("", offset)), true, true
}
