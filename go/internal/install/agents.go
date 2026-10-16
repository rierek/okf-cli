package install

import (
	"os"
	"slices"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

// harnessDir is the directory a coding agent keeps its own files in.
func (c *ctx) harnessDir(h string) string {
	e := c.env
	switch h {
	case "claude":
		return orDefault(e["CLAUDE_CONFIG_DIR"], c.path(".claude"))
	case "omp":
		if d := e["PI_CODING_AGENT_DIR"]; d != "" {
			return d
		}
		return c.path(orDefault(e["PI_CONFIG_DIR"], ".omp"), "agent")
	case "codex":
		return orDefault(e["CODEX_HOME"], c.path(".codex"))
	case "opencode":
		return pyJoin(orDefault(e["XDG_CONFIG_HOME"], c.path(".config")), "opencode")
	case "kimi":
		return orDefault(e["KIMI_CODE_HOME"], c.path(".kimi-code"))
	case "openclaw":
		return orDefault(e["OPENCLAW_STATE_DIR"], c.path(".openclaw"))
	}
	return orDefault(e["HERMES_HOME"], c.path(".hermes"))
}

func orDefault(v, def string) string {
	if v != "" {
		return v
	}
	return def
}

// --- skills ------------------------------------------------------------------

func skillSteps(c *ctx, hs []string, un bool) []*step {
	src := pyJoin(c.pkgRoot, "skills", "okf")
	copy := !c.sourceTree()
	var steps []*step
	own := func(subject, dest string, copy bool, note string) {
		steps = append(steps, putStep(c, "skills", subject, src, dest, copy, un, note))
	}
	if slices.Contains(hs, "claude") {
		own("claude", pyJoin(c.harnessDir("claude"), "skills", "okf"), copy, "")
	}
	if slices.Contains(hs, "hermes") { // follows symlinks, but logs a security warning for a skill resolving outside ~/.hermes/skills
		own("hermes", pyJoin(c.harnessDir("hermes"), "skills", "okf"), true, "")
	}
	customOpenclaw := slices.Contains(hs, "openclaw") && c.env["OPENCLAW_STATE_DIR"] != ""
	if customOpenclaw { // a custom state dir drops ~/.agents/skills from the session skill index
		own("openclaw", pyJoin(c.harnessDir("openclaw"), "skills", "okf"), true, "")
	}
	var readers []string
	for _, h := range sharedReaders {
		if slices.Contains(hs, h) && !(h == "openclaw" && customOpenclaw) {
			readers = append(readers, h)
		}
	}
	shared := c.path(".agents", "skills", "okf")
	switch {
	case len(readers) > 0 && (!un || len(hs) == len(harnesses)):
		own("shared", shared, copy, "read by "+strings.Join(readers, ", "))
	case len(readers) > 0: // a subset uninstall keeps what the others read
		steps = append(steps, newStep("skills", "shared", "skip", "kept: other agents still read "+c.short(shared), nil))
	}
	if !un {
		for _, h := range readers {
			steps = append(steps, newStep("skills", h, "skip", "covered by the shared "+c.short(shared), nil))
		}
	}
	return steps
}

// --- MCP ---------------------------------------------------------------------

// cliStep is the registration through the harness's own CLI; state comes from reading its config.
func cliStep(c *ctx, subject, state string, add, rm []string, un bool) *step {
	if un {
		switch state {
		case "ok", "differs":
			return newStep("mcp", subject, "remove", "run: "+shlexJoin(rm), func() error { return c.run(rm) })
		case "foreign":
			return newStep("mcp", subject, "skip", "the okf server is not okf's own; left alone", nil)
		}
		return newStep("mcp", subject, "ok", "", nil)
	}
	switch state {
	case "ok":
		return newStep("mcp", subject, "ok", "registered", nil)
	case "foreign":
		return newStep("mcp", subject, "blocked",
			"an `okf` MCP server that is not okf's own exists; remove it ("+shlexJoin(rm)+"), then re-run", nil)
	case "differs":
		return newStep("mcp", subject, "update", "run: "+shlexJoin(rm)+" && "+shlexJoin(add), func() error {
			if err := c.run(rm); err != nil {
				return err
			}
			return c.run(add)
		})
	}
	return newStep("mcp", subject, "create", "run: "+shlexJoin(add), func() error { return c.run(add) })
}

// jsonState is the state of container.okf in a JSON config; unknown when it cannot be read.
func jsonState(path, container string, ident *jobj) string {
	text, err := readText(realpath(path))
	if err != nil {
		return "unknown"
	}
	doc, err := loadJSON(text, path)
	if err != nil {
		return "unknown"
	}
	var entry any
	if v, _ := doc.get(container); v != nil {
		if servers, ok := v.(*jobj); ok {
			entry, _ = servers.get("okf")
		}
	}
	return entryState(entry, ident)
}

func jsonStep(c *ctx, h, path, container string, entry, ident *jobj, un bool, newDoc *jobj, mode os.FileMode) *step {
	what := container + ".okf in " + c.short(path)
	two := "  "
	manual := "add this to " + c.short(path) + " by hand:\n" + dumps(obj(container, obj("okf", entry)), &two, true)
	return fileStep(c, "mcp", h, path, jsonEdit(container, entry, ident, un, c.short(path), newDoc), what, manual, true, mode)
}

func claudeEntry(args []string) (entry, ident *jobj) {
	ident = identOf(args)
	entry = obj("type", "stdio", "command", "uv", "args", strList(args...), "env", newObj())
	return entry, ident
}

func mcpClaude(c *ctx, un bool, args []string) *step {
	cfg := c.path(".claude.json")
	if base := c.env["CLAUDE_CONFIG_DIR"]; base != "" {
		cfg = pyJoin(base, ".claude.json")
	}
	entry, ident := claudeEntry(args)
	add := append([]string{"claude", "mcp", "add", "--scope", "user", "--transport", "stdio", "okf", "--", "uv"}, args...)
	if c.which("claude") == "" { // fallback: key-scoped merge (0600 on creation: credentials live there)
		return jsonStep(c, "claude", cfg, "mcpServers", entry, ident, un, nil, 0o600)
	}
	return cliStep(c, "claude", jsonState(cfg, "mcpServers", ident), add,
		[]string{"claude", "mcp", "remove", "okf", "--scope", "user"}, un)
}

func mcpCodex(c *ctx, un bool, args []string) *step {
	cfg := pyJoin(c.harnessDir("codex"), "config.toml")
	add := append([]string{"codex", "mcp", "add", "okf", "--", "uv"}, args...)
	text, err := readText(realpath(cfg))
	if err != nil {
		return newStep("mcp", "codex", "blocked", c.short(cfg)+": "+err.Error(), nil)
	}
	hasBlock := false
	for _, l := range splitLines(text.or("")) {
		if pytext.Strip(l) == begin {
			hasBlock = true
			break
		}
	}
	if hasBlock || c.which("codex") == "" { // a block we wrote stays ours; no CLI: fall back to the block
		t, body := tomlEdit(args, un)
		return fileStep(c, "mcp", "codex", cfg, t, "[mcp_servers.okf] in "+c.short(cfg),
			"add this to "+c.short(cfg)+" by hand:\n"+strings.Join(body, "\n"), true, 0)
	}
	entry, _ := tomlEntry(text.or(""))
	return cliStep(c, "codex", entryState(entry, identOf(args)), add, []string{"codex", "mcp", "remove", "okf"}, un)
}

func mcpOpenclaw(c *ctx, un bool, args []string) *step {
	cfg := pyJoin(c.harnessDir("openclaw"), "openclaw.json") // JSON5: read the text, never write it
	add := []string{"openclaw", "mcp", "set", "okf", dumps(obj("command", "uv", "args", strList(args...)), nil, true)}
	rm := []string{"openclaw", "mcp", "unset", "okf"}
	text, err := readText(realpath(cfg))
	if err != nil {
		return newStep("mcp", "openclaw", "blocked", c.short(cfg)+": "+err.Error(), nil)
	}
	body := text.or("")
	if c.which("openclaw") == "" {
		if un {
			status := "ok"
			if strings.Contains(body, scriptName) {
				status = "skip"
			}
			return newStep("mcp", "openclaw", status, "the openclaw CLI is not on PATH; run by hand: "+shlexJoin(rm), nil)
		}
		return newStep("mcp", "openclaw", "blocked", "the openclaw CLI is not on PATH; run by hand:\n"+shlexJoin(add), nil)
	}
	state := "absent"
	if strings.Contains(body, scriptName) {
		state = "differs"
		if strings.Contains(body, args[len(args)-1]) {
			state = "ok"
		}
	}
	return cliStep(c, "openclaw", state, add, rm, un)
}

func mcpHermes(c *ctx, un bool, args []string) *step {
	cfg := pyJoin(c.harnessDir("hermes"), "config.yaml")
	t, whole := yamlEdit(args, un)
	return fileStep(c, "mcp", "hermes", cfg, t, "mcp_servers.okf in "+c.short(cfg),
		"add this to "+c.short(cfg)+" by hand:\n"+strings.Join(whole[1:len(whole)-1], "\n"), true, 0)
}

func opencodeConfig(c *ctx) string {
	if v := c.env["OPENCODE_CONFIG"]; v != "" { // the user named their config file
		return v
	}
	base := c.harnessDir("opencode")
	for _, name := range []string{"opencode.json", "opencode.jsonc"} {
		if isfile(pyJoin(base, name)) {
			return pyJoin(base, name)
		}
	}
	return pyJoin(base, "opencode.json")
}

func mcpSteps(c *ctx, hs []string, un bool) []*step {
	script := pyJoin(c.pkgRoot, "mcp", scriptName)
	args := []string{"run", "--with", "mcp<2", script}
	ident := identOf(args)
	var steps []*step
	for _, h := range hs {
		switch {
		case !un && c.which("uv") == "":
			steps = append(steps, newStep("mcp", h, "blocked", "uv is not on PATH; install it (https://docs.astral.sh/uv/), then re-run", nil))
		case !un && !isfile(script):
			steps = append(steps, newStep("mcp", h, "blocked", "MCP server script not found: "+c.short(script), nil))
		default:
			steps = append(steps, mcpHandler(c, h, un, args, ident))
		}
	}
	return steps
}

func mcpHandler(c *ctx, h string, un bool, args []string, ident *jobj) *step {
	switch h {
	case "claude":
		return mcpClaude(c, un, args)
	case "codex":
		return mcpCodex(c, un, args)
	case "openclaw":
		return mcpOpenclaw(c, un, args)
	case "hermes":
		return mcpHermes(c, un, args)
	case "omp":
		entry, id := claudeEntry(args)
		return jsonStep(c, "omp", pyJoin(c.harnessDir("omp"), "mcp.json"), "mcpServers", entry, id, un, nil, 0)
	case "kimi":
		return jsonStep(c, "kimi", pyJoin(c.harnessDir("kimi"), "mcp.json"), "mcpServers", copyObj(ident), ident, un, nil, 0)
	}
	command := strList(append([]string{"uv"}, args...)...)
	entry := obj("type", "local", "command", command, "enabled", true, "timeout", jnum("30000"))
	return jsonStep(c, "opencode", opencodeConfig(c), "mcp", entry, obj("command", command), un,
		obj("$schema", "https://opencode.ai/config.json"), 0)
}
