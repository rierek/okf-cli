package install

import (
	"regexp"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

// The three edit strategies of the MCP file fallback. Edits never guess: anything unusual is an
// unsafeErr (the step is BLOCKED, the file stays as it was).

// --- JSON --------------------------------------------------------------------

// loadJSON is load_json: the object of a text, {} for a blank or missing file.
func loadJSON(text opt, what string) (*jobj, error) {
	if !text.Ok || strings.TrimFunc(text.S, pytext.IsSpace) == "" {
		return newObj(), nil
	}
	doc, err := parseJSON(text.S)
	if err != nil {
		return nil, unsafe(what + " is not plain JSON (" + err.Error() + "); comments and trailing commas cannot be edited safely")
	}
	o, ok := doc.(*jobj)
	if !ok {
		return nil, unsafe(what + " does not hold a JSON object")
	}
	return o, nil
}

// indentOf is the file's own indentation: the leading blanks of its first indented line, else two spaces.
func indentOf(old opt) string {
	for _, line := range splitLines(old.S) {
		n := 0
		for n < len(line) && (line[n] == ' ' || line[n] == '\t') {
			n++
		}
		if n == 0 || n == len(line) {
			continue
		}
		if r := []rune(line[n:])[0]; !pytext.IsSpace(r) {
			return line[:n]
		}
	}
	return "  "
}

func dumpJSON(doc *jobj, old opt) string {
	ind := indentOf(old)
	return dumps(doc, &ind, false) + "\n"
}

// entryState is entry_state: absent, foreign (not okf's), differs or ok against the identity.
func entryState(entry any, ident *jobj) string {
	if entry == nil {
		return "absent"
	}
	if !containsScript(entry) {
		return "foreign"
	}
	e, ok := entry.(*jobj)
	if !ok {
		return "foreign"
	}
	for _, k := range ident.keys {
		v, _ := e.get(k)
		if !equalsWant(v, wantOf(ident.m[k])) {
			return "differs"
		}
	}
	return "ok"
}

// wantOf turns an identity value (string or list of strings) into what equalsWant compares.
func wantOf(v any) any {
	list, ok := v.([]any)
	if !ok {
		return v
	}
	out := make([]string, len(list))
	for i, e := range list {
		out[i] = e.(string)
	}
	return out
}

// jsonEdit is json_edit: a key-scoped merge of doc[container]["okf"]; foreign keys and the file's
// indentation survive.
func jsonEdit(container string, entry, ident *jobj, un bool, what string, newDoc *jobj) transform {
	return func(old opt) (opt, error) {
		doc, err := loadJSON(old, what)
		if err != nil {
			return none, err
		}
		if doc.size() == 0 && newDoc != nil {
			doc = copyObj(newDoc)
		}
		var servers *jobj
		if v, present := doc.get(container); present {
			s, ok := v.(*jobj)
			if !ok {
				return none, unsafe(what + ": " + container + " is not an object")
			}
			servers = s
		}
		var cur any
		if servers != nil {
			cur, _ = servers.get("okf")
		}
		state := entryState(cur, ident)
		if un {
			switch state {
			case "foreign":
				return none, skip(what + ": the okf entry is not okf's own; left alone")
			case "absent":
				return old, nil
			}
			servers.del("okf")
			if servers.size() == 0 {
				doc.del(container)
			}
			if onlySchema(doc) {
				return none, nil
			}
			return some(dumpJSON(doc, old)), nil
		}
		switch state {
		case "foreign":
			return none, unsafe(what + ": " + container + ".okf exists and is not okf's own; remove it, then re-run")
		case "ok":
			return old, nil
		case "differs":
			for _, k := range ident.keys {
				cur.(*jobj).set(k, ident.m[k])
			}
		default:
			if servers == nil {
				servers = newObj()
				doc.set(container, servers)
			}
			servers.set("okf", copyObj(entry))
		}
		return some(dumpJSON(doc, old)), nil
	}
}

func onlySchema(doc *jobj) bool {
	for _, k := range doc.keys {
		if k != "$schema" {
			return false
		}
	}
	return true
}

func copyObj(o *jobj) *jobj {
	c := newObj()
	for _, k := range o.keys {
		c.set(k, o.m[k])
	}
	return c
}

// --- TOML --------------------------------------------------------------------

// tomlEntry is toml_entry: mcp_servers.okf of a text, nil when absent or when the text is no TOML.
func tomlEntry(text string) (any, bool) {
	data, err := parseTOML(text)
	if err != nil {
		return nil, false
	}
	return tomlOkf(data), true
}

func tomlOkf(data map[string]any) any {
	servers, _ := data["mcp_servers"].(map[string]any)
	return fromTOML(servers["okf"])
}

// fromTOML maps a decoded TOML value onto the JSON model entryState reads.
func fromTOML(v any) any {
	switch x := v.(type) {
	case map[string]any:
		o := newObj()
		for k, e := range x {
			o.set(k, fromTOML(e))
		}
		return o
	case []any:
		out := make([]any, len(x))
		for i, e := range x {
			out[i] = fromTOML(e)
		}
		return out
	case []map[string]any:
		out := make([]any, len(x))
		for i, e := range x {
			out[i] = fromTOML(e)
		}
		return out
	case string, bool, nil:
		return x
	}
	return jnum("0") // numbers and dates: never part of okf's identity
}

func identOf(args []string) *jobj {
	return obj("command", "uv", "args", strList(args...))
}

// tomlEdit is toml_edit: Codex config.toml without the `codex` CLI. One marker block, text only
// (the parser of tomlparse.go validates, it never writes: the file carries the user's comments).
func tomlEdit(args []string, un bool) (transform, []string) {
	ident := identOf(args)
	quoted := make([]string, len(args))
	for i, a := range args {
		quoted[i] = dumps(a, nil, false)
	}
	body := []string{"[mcp_servers.okf]", `command = "uv"`, "args = [" + strings.Join(quoted, ", ") + "]",
		"startup_timeout_sec = 30"} // uv resolves `mcp` on its first start
	block := append(append([]string{begin}, body...), end)
	t := func(old opt) (opt, error) {
		lines, err := linesOf(old.or(""))
		if err != nil {
			return none, err
		}
		span, err := findBlock(lines)
		if err != nil {
			return none, err
		}
		entry, _ := tomlEntry(old.or(""))
		state := entryState(entry, ident)
		if un {
			if span != nil {
				rest, err := dropBlock(lines)
				if err != nil {
					return none, err
				}
				if text := join(rest); text != "" {
					return some(text), nil
				}
				return none, nil
			}
			switch state {
			case "ok", "differs":
				return none, skip("registered by `codex mcp add`, not by this installer; remove it with `codex mcp remove okf`")
			case "foreign":
				return none, skip("[mcp_servers.okf] is not okf's own; left alone")
			}
			return old, nil
		}
		if span == nil && state != "absent" {
			if state == "ok" {
				return old, nil
			}
			return none, unsafe("config.toml already has an [mcp_servers.okf] table that is not up to date or not okf's own; edit or remove it, then re-run")
		}
		put, err := putBlock(lines, block, -1)
		if err != nil {
			return none, err
		}
		next := join(put)
		data, err := parseTOML(next)
		if err != nil {
			return none, unsafe("config.toml would not be valid TOML (" + err.Error() + "); add the block by hand")
		}
		if entryState(tomlOkf(data), ident) != "ok" {
			return none, unsafe("config.toml would not register okf as expected; add the block by hand")
		}
		return some(next), nil
	}
	return t, body
}

// --- YAML --------------------------------------------------------------------

var (
	reTop    = pytext.Regexp(`^["']?mcp_servers["']?\s*:`)
	rePlain  = pytext.Regexp(`^mcp_servers:[ \t]*(#.*)?$`)
	reList   = regexp.MustCompile(`^-( |$)`)
	reAnchor = pytext.Regexp(`(^|[\s:\[{,])[&*][\w-]+|<<:`)
)

func indentLen(l string) int { return len([]rune(l)) - len([]rune(pytext.Lstrip(l))) }

func blank(l string) bool { return pytext.Strip(l) == "" }

func isComment(l string) bool { return strings.HasPrefix(pytext.Lstrip(l), "#") }

// yamlEdit is yaml_edit: Hermes config.yaml, text edits only, never a whole-file rewrite.
// Anything unusual is an unsafeErr.
func yamlEdit(args []string, un bool) (transform, []string) {
	quoted := make([]string, len(args))
	for i, a := range args {
		quoted[i] = dumps(a, nil, false)
	}
	flow := "[" + strings.Join(quoted, ", ") + "]"
	child := func(ind string) []string {
		return []string{ind + begin, ind + "okf:", ind + `  command: "uv"`, ind + "  args: " + flow, ind + end}
	}
	whole := []string{begin, "mcp_servers:", "  okf:", `    command: "uv"`, "    args: " + flow, end}

	goEdit := func(old opt) (opt, error) {
		lines, err := linesOf(old.or(""))
		if err != nil {
			return none, err
		}
		span, err := findBlock(lines)
		if err != nil {
			return none, err
		}
		fromBlock := func(l []string, e error) (opt, error) {
			if e != nil {
				return none, e
			}
			return some(join(l)), nil
		}
		if un && span != nil {
			rest, err := dropBlock(lines)
			if err != nil {
				return none, err
			}
			if text := join(rest); text != "" {
				return some(text), nil
			}
			return none, nil
		}
		if span != nil { // ours: regenerate in place, in the shape it was written
			s := span[0]
			ind := lines[s][:len(lines[s])-len(pytext.Lstrip(lines[s]))]
			if pytext.Strip(lines[s+1]) == "mcp_servers:" {
				return fromBlock(putBlock(lines, whole, -1))
			}
			return fromBlock(putBlock(lines, child(ind), -1))
		}
		var tops []int
		for i, l := range lines {
			if reTop.MatchString(l) {
				tops = append(tops, i)
			}
		}
		if len(tops) == 0 {
			if un {
				return old, nil
			}
			return fromBlock(putBlock(lines, whole, -1))
		}
		if len(tops) > 1 {
			return none, unsafe("config.yaml has more than one top-level mcp_servers key")
		}
		k := tops[0]
		if !rePlain.MatchString(lines[k]) {
			return none, unsafe("mcp_servers in config.yaml is not a plain block mapping")
		}
		stop := len(lines)
		for i := k + 1; i < len(lines); i++ {
			if lines[i] != "" && !pytext.IsSpace([]rune(lines[i])[0]) && lines[i][0] != '#' {
				stop = i
				break
			}
		}
		if stop == k+1 && stop < len(lines) && reList.MatchString(lines[stop]) {
			return none, unsafe("mcp_servers in config.yaml is a list")
		}
		for _, l := range lines[k:stop] {
			if reAnchor.MatchString(l) {
				return none, unsafe("mcp_servers in config.yaml uses YAML anchors or aliases")
			}
		}
		ci := "  "
		for _, l := range lines[k+1 : stop] {
			if !blank(l) && !isComment(l) {
				ci = l[:len(l)-len(pytext.Lstrip(l))]
				break
			}
		}
		for i := k + 1; i < stop; i++ {
			if !okfKey(lines[i], ci) {
				continue
			}
			j := i + 1
			for j < stop && (blank(lines[j]) || indentLen(lines[j]) > len([]rune(ci))) {
				j++
			}
			for blank(lines[j-1]) {
				j--
			}
			if !strings.Contains(strings.Join(lines[i:j], "\n"), scriptName) {
				return none, unsafe("config.yaml already has an mcp_servers.okf entry that is not okf's own")
			}
			if un { // Hermes rewrites config.yaml on `hermes config set` and drops our markers
				rest := append(append([]string{}, lines[:i]...), lines[j:]...)
				left := false
				for _, l := range rest[k+1 : stop-(j-i)] {
					if !blank(l) && !isComment(l) {
						left = true
						break
					}
				}
				if !left {
					rest = append(append([]string{}, rest[:k]...), rest[stop-(j-i):]...)
				}
				if text := join(rest); text != "" {
					return some(text), nil
				}
				return none, nil
			}
			out := append(append([]string{}, lines[:i]...), child(ci)...)
			return some(join(append(out, lines[j:]...))), nil
		}
		if un {
			return old, nil
		}
		return fromBlock(putBlock(lines, child(ci), k))
	}
	t := func(old opt) (opt, error) {
		next, err := goEdit(old)
		if _, ok := err.(*unsafeErr); ok && un {
			return old, nil // nothing of ours to find in a shape we cannot read
		}
		return next, err
	}
	return t, whole
}

// okfKey is re.match(re.escape(ci) + r"okf[ \t]*:", line).
func okfKey(line, ci string) bool {
	rest, ok := strings.CutPrefix(line, ci)
	if !ok {
		return false
	}
	rest, ok = strings.CutPrefix(rest, "okf")
	if !ok {
		return false
	}
	return strings.HasPrefix(strings.TrimLeft(rest, " \t"), ":")
}
