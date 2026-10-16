package envelope

import (
	"bytes"
	"fmt"
	"math"
	"reflect"
	"sort"
	"strconv"
	"unicode/utf8"

	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

// Field is one key and value of an Obj.
type Field struct {
	Key   string
	Value any
}

// Obj is an ordered JSON object: the keys come out in insertion order, as a Python dict's do.
// Use it for every `data` object whose key order is part of the output; a plain map[string]any
// is encoded with its keys sorted.
type Obj []Field

// O builds an Obj from alternating keys and values: O("path", p, "title", t). It panics on an odd
// count or a key that is not a string.
func O(kv ...any) Obj {
	if len(kv)%2 != 0 {
		panic("envelope.O: odd number of arguments")
	}
	o := make(Obj, 0, len(kv)/2)
	for i := 0; i < len(kv); i += 2 {
		key, ok := kv[i].(string)
		if !ok {
			panic(fmt.Sprintf("envelope.O: key %v is not a string", kv[i]))
		}
		o = append(o, Field{key, kv[i+1]})
	}
	return o
}

// Set stores a value under key: an existing key keeps its position (Python dict assignment), a new
// key is appended.
func (o *Obj) Set(key string, value any) {
	for i := range *o {
		if (*o)[i].Key == key {
			(*o)[i].Value = value
			return
		}
	}
	*o = append(*o, Field{key, value})
}

// Get returns the value stored under key.
func (o Obj) Get(key string) (any, bool) {
	for _, f := range o {
		if f.Key == key {
			return f.Value, true
		}
	}
	return nil, false
}

// Marshal encodes v as Python json.dumps(v, ensure_ascii=False) does: separators `, ` and `: `, no
// HTML escaping, non-ASCII text written as is (U+2028 and U+2029 included), floats as Python repr
// (NaN, Infinity and -Infinity for the specials). v is nil, bool, string, any integer or float
// type, Obj, map[string]any (keys sorted), or a slice or array of those; anything else is an
// error.
func Marshal(v any) ([]byte, error) {
	var buf bytes.Buffer
	if err := encode(&buf, reflect.ValueOf(v)); err != nil {
		return nil, err
	}
	return buf.Bytes(), nil
}

var objType = reflect.TypeOf(Obj(nil))

func encode(buf *bytes.Buffer, v reflect.Value) error {
	if !v.IsValid() {
		buf.WriteString("null")
		return nil
	}
	if v.Type() == objType {
		return encodeObj(buf, v.Interface().(Obj))
	}
	switch v.Kind() {
	case reflect.Interface, reflect.Pointer:
		if v.IsNil() {
			buf.WriteString("null")
			return nil
		}
		return encode(buf, v.Elem())
	case reflect.Bool:
		buf.WriteString(strconv.FormatBool(v.Bool()))
	case reflect.String:
		writeString(buf, v.String())
	case reflect.Int, reflect.Int8, reflect.Int16, reflect.Int32, reflect.Int64:
		buf.WriteString(strconv.FormatInt(v.Int(), 10))
	case reflect.Uint, reflect.Uint8, reflect.Uint16, reflect.Uint32, reflect.Uint64:
		buf.WriteString(strconv.FormatUint(v.Uint(), 10))
	case reflect.Float32, reflect.Float64:
		buf.WriteString(floatText(v.Float()))
	case reflect.Slice, reflect.Array:
		if v.Kind() == reflect.Slice && v.IsNil() {
			buf.WriteString("[]")
			return nil
		}
		buf.WriteByte('[')
		for i := range v.Len() {
			if i > 0 {
				buf.WriteString(", ")
			}
			if err := encode(buf, v.Index(i)); err != nil {
				return err
			}
		}
		buf.WriteByte(']')
	case reflect.Map:
		if v.Type().Key().Kind() != reflect.String {
			return fmt.Errorf("envelope: map key type %s is not a string", v.Type().Key())
		}
		keys := make([]string, 0, v.Len())
		for _, k := range v.MapKeys() {
			keys = append(keys, k.String())
		}
		sort.Strings(keys)
		buf.WriteByte('{')
		for i, k := range keys {
			if i > 0 {
				buf.WriteString(", ")
			}
			writeString(buf, k)
			buf.WriteString(": ")
			if err := encode(buf, v.MapIndex(reflect.ValueOf(k).Convert(v.Type().Key()))); err != nil {
				return err
			}
		}
		buf.WriteByte('}')
	default:
		return fmt.Errorf("envelope: cannot encode %s as JSON", v.Type())
	}
	return nil
}

func encodeObj(buf *bytes.Buffer, o Obj) error {
	buf.WriteByte('{')
	for i, f := range o {
		if i > 0 {
			buf.WriteString(", ")
		}
		writeString(buf, f.Key)
		buf.WriteString(": ")
		if err := encode(buf, reflect.ValueOf(f.Value)); err != nil {
			return err
		}
	}
	buf.WriteByte('}')
	return nil
}

// floatText is json.dumps of a float: Python repr, except that the specials are JSON-style words.
func floatText(f float64) string {
	switch {
	case math.IsNaN(f):
		return "NaN"
	case math.IsInf(f, 1):
		return "Infinity"
	case math.IsInf(f, -1):
		return "-Infinity"
	}
	return pytext.ReprFloat(f)
}

const hexDigits = "0123456789abcdef"

// writeString writes s as a JSON string the way Python's encoder does with ensure_ascii off:
// only the quote, the backslash and the control characters below U+0020 are escaped.
func writeString(buf *bytes.Buffer, s string) {
	buf.WriteByte('"')
	for i := 0; i < len(s); {
		c := s[i]
		if c >= utf8.RuneSelf {
			_, size := utf8.DecodeRuneInString(s[i:])
			buf.WriteString(s[i : i+size])
			i += size
			continue
		}
		switch c {
		case '"':
			buf.WriteString(`\"`)
		case '\\':
			buf.WriteString(`\\`)
		case '\n':
			buf.WriteString(`\n`)
		case '\r':
			buf.WriteString(`\r`)
		case '\t':
			buf.WriteString(`\t`)
		case '\b':
			buf.WriteString(`\b`)
		case '\f':
			buf.WriteString(`\f`)
		default:
			if c < 0x20 {
				buf.WriteString(`\u00`)
				buf.WriteByte(hexDigits[c>>4])
				buf.WriteByte(hexDigits[c&0xf])
			} else {
				buf.WriteByte(c)
			}
		}
		i++
	}
	buf.WriteByte('"')
}
