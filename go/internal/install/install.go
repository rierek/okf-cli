// Package install is the `install` command: it puts okf, its agent skill, its MCP server and TAB
// completion where this machine's coding agents and shells look for them. It is the Go port of
// cli/okf_install.py and behaves the same, step for step and byte for byte.
//
// `install` builds a plan (a list of steps) from what is on disk and changes nothing; `--apply`
// performs it; `--uninstall` plans or performs the reverse. Edits never guess: rc files, TOML and
// YAML get one marker-bounded block, JSON gets a key-scoped merge, every write is atomic and
// keeps a one-time `<file>.okf-cli.bak` of a file that existed. A config that cannot be edited
// safely turns its step into BLOCKED and prints the manual edit instead.
//
// Two things differ from the Python installer on purpose: the PATH wrapper starts this binary
// (not `uv run --script cli/okf-cli.py`), and the completion files hold the scripts of
// go/internal/complete (not argcomplete's).
package install

import (
	"fmt"
	"runtime"
	"slices"
	"strconv"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/cli"
	"nas/volume1/data/git/okf-tools/go/internal/envelope"
	"nas/volume1/data/git/okf-tools/go/internal/okferr"
	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

// Register attaches the `install` command.
func Register(app *cli.App) {
	app.Attach("install", cli.Spec{
		Args: []cli.Arg{
			{Flags: []string{"--apply"}, Action: cli.StoreTrue,
				Help: "perform the plan (default: print the plan, change nothing)"},
			{Flags: []string{"--uninstall"}, Action: cli.StoreTrue,
				Help: "plan, or with --apply perform, the removal of everything install created"},
			{Flags: []string{"--only"}, Metavar: []string{"NAMES"},
				Help: "comma-separated subset: claude, omp, codex, opencode, kimi, openclaw, hermes " +
					"(agents), zsh, bash, fish (shells). Default: install for every agent and " +
					"shell found on this machine; uninstall covers all of them"},
			cli.JSON(),
		},
		Handler: func(_ string, a *cli.Args) (any, error) { return run(newCtx(runtime.GOOS), a) },
	})
}

func shellDetected(c *ctx, sh string, login string) bool {
	p := c.shellPaths()
	switch sh {
	case "zsh":
		return isfile(p.zshRC) || login == "zsh"
	case "bash":
		return isfile(c.path(".bashrc")) || isfile(c.path(".bash_profile")) || login == "bash"
	}
	return isdir(p.fishDir) || login == "fish"
}

// selectTargets is `select`: the harnesses and shells to act on, and the skip steps of what is
// not detected. Install without --only auto-detects; --only names are taken as given; uninstall
// without --only considers all.
func selectTargets(c *ctx, only []string, un bool) (hs, ss []string, notes []*step) {
	if only != nil || un {
		for _, h := range harnesses {
			if only == nil || slices.Contains(only, h) {
				hs = append(hs, h)
			}
		}
		for _, s := range shells {
			if only == nil || slices.Contains(only, s) {
				ss = append(ss, s)
			}
		}
		return hs, ss, nil
	}
	for _, h := range harnesses {
		d := c.harnessDir(h)
		if c.which(h) != "" || isdir(d) {
			hs = append(hs, h)
		} else {
			notes = append(notes, newStep("detect", h, "skip", "not detected (no `"+h+"` on PATH, no "+c.short(d)+")", nil))
		}
	}
	login := c.env["SHELL"]
	if login == "" {
		login = loginShell()
	}
	login = pyBasename(login)
	for _, s := range shells {
		if shellDetected(c, s, login) {
			ss = append(ss, s)
		} else {
			notes = append(notes, newStep("detect", s, "skip", "not detected (no rc file or config directory, not the login shell)", nil))
		}
	}
	return hs, ss, notes
}

func plan(c *ctx, only []string, un bool) []*step {
	hs, ss, steps := selectTargets(c, only, un)
	steps = append(steps, skillSteps(c, hs, un)...)
	steps = append(steps, mcpSteps(c, hs, un)...)
	return append(steps, shellSteps(c, ss, un)...)
}

// execute performs every planned change; a step ends done, skipped, blocked or failed.
func execute(steps []*step) {
	for _, s := range steps {
		if !isChange(s.status) {
			continue
		}
		switch err := s.apply().(type) {
		case nil:
			s.done = true
		case *skipErr:
			s.status, s.detail = "skip", err.Error()
		case *unsafeErr:
			s.status, s.detail = "blocked", err.Error()
		default:
			s.status, s.detail = "failed", err.Error()
		}
	}
}

var planVerb = map[string]string{"create": "create", "update": "update", "remove": "remove", "ok": "unchanged",
	"skip": "skip", "blocked": "BLOCKED", "failed": "FAILED"}
var doneVerb = map[string]string{"create": "created", "update": "updated", "remove": "removed", "ok": "unchanged",
	"skip": "skip", "blocked": "BLOCKED", "failed": "FAILED"}

// report is the --json data: one entry per step.
func report(c *ctx, steps []*step, apply, un bool) envelope.Obj {
	list := make([]envelope.Obj, len(steps))
	for i, s := range steps {
		list[i] = envelope.O("group", s.group, "subject", s.subject, "status", s.status, "done", s.done, "detail", s.detail)
	}
	return envelope.O("apply", apply, "uninstall", un, "source", c.pkgRoot, "source_tree", c.sourceTree(), "steps", list)
}

func pad(s string, width int) string {
	if n := len([]rune(s)); n < width {
		return s + strings.Repeat(" ", width-n)
	}
	return s
}

func render(c *ctx, steps []*step, apply, un bool) {
	head := "okf install"
	if un {
		head += " --uninstall"
	}
	if apply {
		head += " - applied"
	} else {
		head += " - PLAN only, nothing is changed (add --apply to perform it)"
	}
	fmt.Println(head)
	kind := "installed package, skills are copied"
	if c.sourceTree() {
		kind = "source tree, skills are linked"
	}
	fmt.Printf("source: %s (%s)\n", c.short(c.pkgRoot), kind)
	group := ""
	width := 8
	for _, s := range steps {
		width = max(width, len([]rune(s.subject)))
	}
	width += 2
	for _, s := range steps {
		if un && s.status == "ok" {
			continue
		}
		if s.group != group {
			group = s.group
			fmt.Println("\n" + group)
		}
		verbs := planVerb
		if s.done {
			verbs = doneVerb
		}
		lines := strings.Split(s.detail, "\n")
		fmt.Println(pytext.Rstrip("  " + pad(verbs[s.status], 10) + pad(s.subject, width) + lines[0]))
		for _, line := range lines[1:] {
			fmt.Println(strings.Repeat(" ", 12+width) + line)
		}
	}
	changes, bad, done := 0, 0, 0
	for _, s := range steps {
		if isChange(s.status) || s.done {
			changes++
		}
		if s.status == "blocked" || s.status == "failed" {
			bad++
		}
		if s.done {
			done++
		}
	}
	fmt.Println()
	if bad > 0 {
		fmt.Printf("%d step(s) blocked or failed: read the marked lines above\n", bad)
	}
	switch {
	case apply && done > 0:
		fmt.Printf("done: %d step(s) changed. Open a new shell and restart your agents to pick it up.\n", done)
	case changes > 0:
		fmt.Printf("%d step(s) planned. Run again with --apply to perform them.\n", changes)
	case bad == 0:
		verb := "do"
		if un {
			verb = "remove"
		}
		fmt.Printf("nothing to %s: already up to date\n", verb)
	}
}

// run is Python okf_install.run plus cmd_install: the plan, the text report or the --json
// report, and the exit class (a blocked or failed step is an internal error carrying the report).
func run(c *ctx, a *cli.Args) (any, error) {
	if c.goos == "windows" {
		return nil, okferr.New(okferr.Internal, "ERROR: okf install supports macOS and Linux only")
	}
	var only []string
	if a.Value("only") != nil {
		only = []string{}
		for _, n := range strings.Split(a.String("only"), ",") {
			if n = pytext.Strip(n); n != "" {
				only = append(only, n)
			}
		}
		var unknown []string
		for _, n := range only {
			if !slices.Contains(harnesses, n) && !slices.Contains(shells, n) {
				unknown = append(unknown, n)
			}
		}
		if len(unknown) > 0 || len(only) == 0 {
			names := strings.Join(unknown, ", ")
			if names == "" {
				names = "(none given)"
			}
			return nil, okferr.Newf(okferr.InvalidInput, "install: unknown --only name(s): %s; valid: %s",
				names, strings.Join(append(slices.Clone(harnesses), shells...), ", "))
		}
	}
	apply, un := a.Bool("apply"), a.Bool("uninstall")
	steps := plan(c, only, un)
	if apply {
		execute(steps)
	}
	code := 0
	for _, s := range steps {
		if s.status == "blocked" || s.status == "failed" {
			code = 1
		}
	}
	if !a.JSON {
		render(c, steps, apply, un)
	}
	data := report(c, steps, apply, un)
	if code != 0 {
		return nil, okferr.WithResult(okferr.Internal, "install failed with exit code "+strconv.Itoa(code), data)
	}
	return data, nil
}
