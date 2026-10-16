package spec

import (
	"time"
	"unicode/utf8"
)

// fromISO is CPython 3.14 datetime.fromisoformat (Modules/_datetimemodule.c), reduced to what
// parse_okf_datetime keeps of it: the aware result. ok is false for a string the C code refuses,
// a value out of range and a naive result (no offset). The code follows the C functions step by
// step, quirks included, and reads past the end as the C code does: a NUL.
//
// The zone of the result is a whole number of seconds. An offset with microseconds
// (`+00:00:00.5`) moves the instant exactly but leaves the zone at its whole seconds, and an
// offset of zero seconds is UTC whatever its microseconds, as in CPython.
func fromISO(s string) (time.Time, bool) {
	b, ok := isoBytes(s)
	if !ok {
		return time.Time{}, false
	}
	sc := isoScan{b: b}
	n := len(b)
	sep := sc.separator(n)
	if sep < 0 {
		return time.Time{}, false
	}
	year, month, day, rv := sc.parseDate(sep)
	var t isoTime
	if rv == 0 && n > sep {
		start := sep // skip the separator, a character of one to four bytes
		switch lead := b[start]; {
		case lead&0x80 == 0:
			start++
		case lead&0xf0 == 0xe0:
			start += 3
		case lead&0xf0 == 0xf0:
			start += 4
		default:
			start += 2
		}
		t, rv = sc.parseTime(start)
	}
	if rv != 1 { // failed, or no offset: naive
		return time.Time{}, false
	}
	if t.hour == 24 && month <= 12 {
		if dim := daysInMonth(year, month); day <= dim {
			if t.minute != 0 || t.second != 0 || t.micro != 0 {
				return time.Time{}, false
			}
			t.hour = 0 // midnight of the next day
			if day++; day > dim {
				day = 1
				if month++; month > 12 {
					month = 1
					year++
				}
			}
		}
	}
	if !validDate(year, month, day) || t.hour > 23 || t.minute > 59 || t.second > 59 {
		return time.Time{}, false
	}
	local := time.Date(year, time.Month(month), day, t.hour, t.minute, t.second, t.micro*1000, time.UTC)
	if t.offset == 0 {
		return local, true
	}
	offset := time.Duration(t.offset)*time.Second + time.Duration(t.offsetMicro)*time.Microsecond
	if offset <= -24*time.Hour || offset >= 24*time.Hour {
		return time.Time{}, false
	}
	return local.Add(-offset).In(time.FixedZone("", t.offset)), true
}

// isoBytes is the UTF-8 text CPython's fromisoformat works on. A string shorter than seven
// characters is refused. A byte that is no UTF-8 is a lone surrogate in Python (a command-line
// argument decoded with surrogateescape); one is allowed where the separator can stand (character
// 7, 8 or 10), is read as `T`, and any other is refused.
func isoBytes(s string) ([]byte, bool) {
	if utf8.RuneCountInString(s) < 7 {
		return nil, false
	}
	b := []byte(s)
	if utf8.ValidString(s) {
		return b, true
	}
	lone, loneAt := 0, 0
	for i, char := 0, 0; i < len(s); char++ {
		r, size := utf8.DecodeRuneInString(s[i:])
		if r == utf8.RuneError && size == 1 {
			if char != 7 && char != 8 && char != 10 {
				return nil, false
			}
			lone, loneAt = lone+1, i
		}
		i += size
	}
	if lone != 1 {
		return nil, false
	}
	b[loneAt] = 'T'
	return b, true
}

// isoTime is the time of day and the offset fromisoformat read: offset is in seconds and
// offsetMicro its microseconds, both already signed.
type isoTime struct {
	hour, minute, second, micro int
	offset, offsetMicro         int
}

// isoScan reads the UTF-8 bytes of an ISO string; at(i) is the byte at i, NUL past the end.
type isoScan struct{ b []byte }

func (s *isoScan) at(i int) byte {
	if i >= 0 && i < len(s.b) {
		return s.b[i]
	}
	return 0
}

func isDigit(c byte) bool { return c >= '0' && c <= '9' }

// digits is parse_digits: exactly n ASCII digits at *p, which moves past them (and past the bad
// character on failure).
func (s *isoScan) digits(p *int, n int) (int, bool) {
	v := 0
	for range n {
		c := s.at(*p)
		*p++
		if !isDigit(c) {
			return 0, false
		}
		v = v*10 + int(c-'0')
	}
	return v, true
}

// separator is _find_isoformat_datetime_separator: the byte index of the character between date
// and time, n being the byte length (at least 7). Any character may stand there, so the date
// format is told from the shape of its first characters; -1 is a string with no valid date.
func (s *isoScan) separator(n int) int {
	if n == 7 {
		return 7
	}
	if s.at(4) == '-' {
		if s.at(5) != 'W' {
			return 10 // YYYY-MM-DD
		}
		if n > 8 && s.at(8) == '-' { // YYYY-Www-D, or YYYY-Www- and a time
			if n == 9 {
				return -1
			}
			if n > 10 && isDigit(s.at(10)) {
				return 8
			}
			return 10
		}
		return 8 // YYYY-Www
	}
	if s.at(4) == 'W' { // YYYYWww or YYYYWwwD: the digits that follow tell the two apart
		idx := 7
		for idx < n && isDigit(s.at(idx)) {
			idx++
		}
		if idx < 9 {
			return idx
		}
		if idx%2 == 0 {
			return 7
		}
		return 8
	}
	return 8 // YYYYMMDD
}

// parseDate is parse_isoformat_date over the first sep bytes: YYYY-MM-DD, YYYYMMDD, YYYY-Www[-D]
// and YYYYWww[D]. rv is 0 on success, negative on failure.
func (s *isoScan) parseDate(sep int) (year, month, day, rv int) {
	p := 0
	year, ok := s.digits(&p, 4)
	if !ok {
		return 0, 0, 0, -1
	}
	uses := s.at(p) == '-'
	if uses {
		p++
	}
	if s.at(p) == 'W' {
		p++
		week, ok := s.digits(&p, 2)
		if !ok {
			return 0, 0, 0, -3
		}
		weekday := 1
		if p < sep {
			if uses {
				c := s.at(p)
				p++
				if c != '-' {
					return 0, 0, 0, -2
				}
			}
			if weekday, ok = s.digits(&p, 1); !ok {
				return 0, 0, 0, -4
			}
		}
		year, month, day, ok = isoToYMD(year, week, weekday)
		if !ok {
			return 0, 0, 0, -3
		}
		return year, month, day, 0
	}
	month, ok = s.digits(&p, 2)
	if !ok {
		return 0, 0, 0, -1
	}
	if uses {
		c := s.at(p)
		p++
		if c != '-' {
			return 0, 0, 0, -2
		}
	}
	day, ok = s.digits(&p, 2)
	if !ok {
		return 0, 0, 0, -1
	}
	return year, month, day, 0
}

// parseTime is parse_isoformat_time from byte start to the end: HH[:?MM[:?SS[{.,}f]]] and an
// offset, `Z` or `±HH[:?MM[:?SS[{.,}f]]]`. rv is 1 with an offset, 0 without, negative on failure.
func (s *isoScan) parseTime(start int) (t isoTime, rv int) {
	end := len(s.b)
	zone := start // the first Z, + or -, else end
	for {
		if c := s.at(zone); c == 'Z' || c == '+' || c == '-' {
			break
		}
		if zone++; zone >= end {
			break
		}
	}
	fields, micro, rv := s.parseFields(start, zone)
	t.hour, t.minute, t.second, t.micro = fields[0], fields[1], fields[2], micro
	switch {
	case rv < 0:
		return t, rv
	case zone == end:
		if rv == 1 { // text after the time, and no offset
			return t, -5
		}
		return t, 0
	case s.at(zone) == 'Z':
		if s.at(zone+1) != 0 {
			return t, -5
		}
		return t, 1
	}
	sign := 1
	if s.at(zone) == '-' {
		sign = -1
	}
	off, offMicro, rv := s.parseFields(zone+1, end)
	t.offset = sign * (off[0]*3600 + off[1]*60 + off[2])
	t.offsetMicro = sign * offMicro
	if rv != 0 {
		return t, -5
	}
	return t, 1
}

// parseFields is parse_hh_mm_ss_ff over [start, end): HH[:?MM[:?SS[{.,}fff[fff]]]] with the
// colons all there or all absent. rv is 1 when text remains after the fields, 0 when they end the
// string, negative on failure. A fraction of fewer than six digits is padded, one of more is cut.
func (s *isoScan) parseFields(start, end int) (v [3]int, micro, rv int) {
	p := start
	hasSep := true
loop:
	for i := range 3 {
		var ok bool
		if v[i], ok = s.digits(&p, 2); !ok {
			return v, 0, -3
		}
		c := s.at(p)
		p++
		if i == 0 {
			hasSep = c == ':'
		}
		switch {
		case p >= end:
			return v, 0, b2i(c != 0)
		case hasSep && c == ':':
			if i == 2 {
				return v, 0, -4
			}
		case c == '.' || c == ',':
			if i < 2 {
				return v, 0, -3
			}
			break loop
		case !hasSep:
			p--
		default:
			return v, 0, -4
		}
	}
	remains := min(end-p, 6)
	micro, ok := s.digits(&p, remains)
	if !ok {
		return v, 0, -3
	}
	if remains < 6 {
		micro *= [...]int{100000, 10000, 1000, 100, 10}[remains-1]
	}
	for isDigit(s.at(p)) {
		p++ // the digits beyond the sixth
	}
	return v, micro, b2i(s.at(p) != 0)
}

func b2i(b bool) int {
	if b {
		return 1
	}
	return 0
}

// isoToYMD is iso_to_ymd: the date of an ISO year, week (1-53) and weekday (1 Monday to 7
// Sunday). The date may fall in year 10000, which validDate refuses.
func isoToYMD(year, week, weekday int) (y, m, d int, ok bool) {
	if year < 1 || year > 9999 {
		return 0, 0, 0, false
	}
	if week <= 0 || week >= 53 {
		if week != 53 {
			return 0, 0, 0, false
		}
		first := (int(time.Date(year, time.January, 1, 0, 0, 0, 0, time.UTC).Weekday()) + 6) % 7 // Monday is 0
		if first != 3 && (first != 2 || !isLeap(year)) {
			return 0, 0, 0, false
		}
	}
	if weekday <= 0 || weekday >= 8 {
		return 0, 0, 0, false
	}
	jan4 := time.Date(year, time.January, 4, 0, 0, 0, 0, time.UTC) // week 1 is the week with January 4th
	monday := jan4.AddDate(0, 0, -((int(jan4.Weekday()) + 6) % 7))
	date := monday.AddDate(0, 0, (week-1)*7+weekday-1)
	return date.Year(), int(date.Month()), date.Day(), true
}

func isLeap(year int) bool { return year%4 == 0 && (year%100 != 0 || year%400 == 0) }

// daysInMonth is days_in_month of the C code, month 0 included: fromisoformat's `24:00` rule can
// reach it, and it has no days.
func daysInMonth(year, month int) int {
	if month == 2 && isLeap(year) {
		return 29
	}
	return [...]int{0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31}[month]
}

// validDate is check_date_args.
func validDate(year, month, day int) bool {
	return year >= 1 && year <= 9999 && month >= 1 && month <= 12 && day >= 1 && day <= daysInMonth(year, month)
}
