package cli

import (
	"math"
	"strconv"
	"strings"
	"unicode"

	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

// Type converts one command-line string into the value stored for an argument (argparse's
// type=). A non-empty message rejects the string: the usage error reads
// "argument --flag: <message>" (argparse.ArgumentTypeError). Accessors of Args expect the
// converted value to be an int for Int, a float64 for Float and a string for a nil Type.
type Type func(raw string) (value any, msg string)

// Int is type=int: Python's int(), so surrounding whitespace, a sign and digit groups
// separated by single underscores are accepted. A value beyond the range of int saturates.
func Int(raw string) (any, string) {
	n, ok := parseInt(raw)
	if !ok {
		return nil, "invalid int value: " + pytext.ReprStr(raw)
	}
	return n, ""
}

// Float is type=float: Python's float() for ASCII input (sign, digits with single underscores,
// a point, an exponent, inf, infinity and nan in any case).
func Float(raw string) (any, string) {
	f, ok := parseFloat(raw)
	if !ok {
		return nil, "invalid float value: " + pytext.ReprStr(raw)
	}
	return f, ""
}

func parseInt(raw string) (int, bool) {
	s := pytext.Strip(raw)
	neg := false
	if s != "" && (s[0] == '+' || s[0] == '-') {
		neg = s[0] == '-'
		s = s[1:]
	}
	var n uint64
	digits, afterDigit := 0, false
	for _, r := range s {
		if r == '_' {
			if !afterDigit {
				return 0, false
			}
			afterDigit = false
			continue
		}
		d, ok := digitValue(r)
		if !ok {
			return 0, false
		}
		if n > (math.MaxInt64-uint64(d))/10 {
			n = math.MaxInt64
		} else {
			n = n*10 + uint64(d)
		}
		digits++
		afterDigit = true
	}
	if digits == 0 || !afterDigit {
		return 0, false
	}
	if neg {
		return -int(n), true
	}
	return int(n), true
}

// digitValue is the value of a decimal digit of any script (Unicode category Nd): the digits of
// a script form runs of ten code points that start at zero.
func digitValue(r rune) (int, bool) {
	if !unicode.IsDigit(r) {
		return 0, false
	}
	start := r
	for unicode.IsDigit(start - 1) {
		start--
	}
	return int(r-start) % 10, true
}

func parseFloat(raw string) (float64, bool) {
	s := pytext.Strip(raw)
	i := 0
	if i < len(s) && (s[i] == '+' || s[i] == '-') {
		i++
	}
	switch strings.ToLower(s[i:]) {
	case "inf", "infinity", "nan":
		f, err := strconv.ParseFloat(s, 64)
		return f, err == nil
	}
	digits := func() (n int) {
		for i < len(s) {
			switch {
			case s[i] >= '0' && s[i] <= '9':
				n++
			case s[i] == '_' && n > 0 && i+1 < len(s) && s[i+1] >= '0' && s[i+1] <= '9':
			default:
				return n
			}
			i++
		}
		return n
	}
	whole, fraction := digits(), 0
	if i < len(s) && s[i] == '.' {
		i++
		fraction = digits()
	}
	if whole+fraction == 0 {
		return 0, false
	}
	if i < len(s) && (s[i] == 'e' || s[i] == 'E') {
		i++
		if i < len(s) && (s[i] == '+' || s[i] == '-') {
			i++
		}
		if digits() == 0 {
			return 0, false
		}
	}
	if i != len(s) {
		return 0, false
	}
	f, err := strconv.ParseFloat(strings.ReplaceAll(s, "_", ""), 64)
	return f, err == nil || math.IsInf(f, 0) // a range error is inf, as in Python
}
