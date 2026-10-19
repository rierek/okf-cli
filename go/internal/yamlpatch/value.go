package yamlpatch

import (
	"fmt"
	"unicode/utf8"

	"go.yaml.in/yaml/v3"
)

// Value is what an edit writes: a string scalar, a typed plain scalar, an ordered mapping or a
// list. New mappings and lists are always written in block style.
type Value interface{ isValue() }

type (
	strValue   struct{ s string }
	plainValue struct{ s string }
	mapValue   struct {
		keys []string
		vals []Value
	}
	listValue struct{ items []Value }
)

func (strValue) isValue()   {}
func (plainValue) isValue() {}
func (mapValue) isValue()   {}
func (listValue) isValue()  {}

// Str is a string scalar. It is written plain when its plain form reads back as the same string,
// single-quoted otherwise, and double-quoted only when it holds a line break or a character that
// single quotes cannot carry (see quote.go).
func Str(s string) Value { return strValue{s} }

// Plain is a typed scalar written unquoted exactly as given, such as the timestamp of a `verified`
// entry. It must be one line, hold no leading or trailing space and read back as one plain scalar.
func Plain(s string) Value { return plainValue{s} }

// Map is an ordered mapping: Map("by", Str(actor), "at", Plain(timestamp)). The arguments are
// alternating string keys and Values; anything else is a programming error and panics.
func Map(kv ...any) Value {
	if len(kv)%2 != 0 {
		panic("yamlpatch.Map: odd number of arguments")
	}
	m := mapValue{}
	for i := 0; i < len(kv); i += 2 {
		k, ok := kv[i].(string)
		if !ok {
			panic(fmt.Sprintf("yamlpatch.Map: key %d is %T, not a string", i/2, kv[i]))
		}
		v, ok := kv[i+1].(Value)
		if !ok {
			panic(fmt.Sprintf("yamlpatch.Map: value of key %q is %T, not a Value", k, kv[i+1]))
		}
		m.keys = append(m.keys, k)
		m.vals = append(m.vals, v)
	}
	return m
}

// List is an ordered list of Values.
func List(items ...Value) Value { return listValue{append([]Value(nil), items...)} }

// validate refuses a Value the writer cannot write; it never inspects what the target file holds.
func validate(v Value) error {
	switch x := v.(type) {
	case strValue:
		if !utf8.ValidString(x.s) {
			return reject("a new string is not valid UTF-8")
		}
	case plainValue:
		if x.s == "" || !utf8.ValidString(x.s) || !printableLine(x.s) || x.s != trimSpaces(x.s) {
			return reject("%q is not a writable plain scalar", x.s)
		}
	case mapValue:
		seen := map[string]bool{}
		for i, k := range x.keys {
			if seen[k] {
				return reject("a new mapping holds the key %q twice", k)
			}
			seen[k] = true
			if !utf8.ValidString(k) || k == "" {
				return reject("a new mapping holds an invalid key")
			}
			if err := validate(x.vals[i]); err != nil {
				return err
			}
		}
	case listValue:
		for _, item := range x.items {
			if _, nested := item.(listValue); nested {
				return reject("a list inside a list is not supported")
			}
			if err := validate(item); err != nil {
				return err
			}
		}
	default:
		return reject("unknown value type %T", v)
	}
	return nil
}

// datumOf is the data a Value stands for, the intended side of the self-check.
func datumOf(v Value) *datum {
	switch x := v.(type) {
	case strValue:
		return &datum{kind: yaml.ScalarNode, tag: "!!str", text: x.s}
	case plainValue:
		return &datum{kind: yaml.ScalarNode, text: x.s, anyTag: true, needPlain: true}
	case mapValue:
		d := &datum{kind: yaml.MappingNode, tag: "!!map"}
		for i, k := range x.keys {
			d.kids = append(d.kids, &datum{kind: yaml.ScalarNode, tag: "!!str", text: k}, datumOf(x.vals[i]))
		}
		return d
	default:
		d := &datum{kind: yaml.SequenceNode, tag: "!!seq"}
		for _, item := range v.(listValue).items {
			d.kids = append(d.kids, datumOf(item))
		}
		return d
	}
}
