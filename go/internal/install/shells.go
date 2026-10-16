package install

import (
	"os"
	"os/exec"
	"strconv"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/complete"
	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

// shellPaths are the files the shells read and the completion files okf places.
type shellPaths struct {
	zshRC, zshComp, bashRC, bashComp, fishDir, fishConf, fishComp string
	zshRCs, bashRCs                                               []string
}

func (c *ctx) shellPaths() shellPaths {
	data := orDefault(c.env["XDG_DATA_HOME"], c.path(".local", "share"))
	conf := pyJoin(orDefault(c.env["XDG_CONFIG_HOME"], c.path(".config")), "fish")
	bashRC := c.path(".bashrc")
	if c.goos == "darwin" { // terminals start login shells, which never read .bashrc
		bashRC = c.path(".bash_profile")
		for _, n := range []string{".bash_profile", ".bash_login", ".profile"} {
			if isfile(c.path(n)) {
				bashRC = c.path(n)
				break
			}
		}
	}
	zshRC := pyJoin(orDefault(c.env["ZDOTDIR"], c.home), ".zshrc")
	zshRCs := []string{zshRC}
	if home := c.path(".zshrc"); home != zshRC { // uninstall looks everywhere a block may have gone
		zshRCs = append(zshRCs, home)
	}
	var bashRCs []string
	for _, n := range []string{".bashrc", ".bash_profile", ".bash_login", ".profile"} {
		bashRCs = append(bashRCs, c.path(n))
	}
	return shellPaths{
		zshRC: zshRC, zshRCs: zshRCs, zshComp: c.path(".zsh", "completions", "_okf"),
		bashRC: bashRC, bashRCs: bashRCs, bashComp: pyJoin(data, "bash-completion", "completions", "okf"),
		fishDir: conf, fishConf: pyJoin(conf, "conf.d", "okf.fish"), fishComp: pyJoin(conf, "completions", "okf.fish"),
	}
}

func (p shellPaths) comp(sh string) string {
	switch sh {
	case "zsh":
		return p.zshComp
	case "bash":
		return p.bashComp
	}
	return p.fishComp
}

func (p shellPaths) rc(sh string) string {
	if sh == "zsh" {
		return p.zshRC
	}
	return p.bashRC
}

func (p shellPaths) rcs(sh string) []string {
	if sh == "zsh" {
		return p.zshRCs
	}
	return p.bashRCs
}

// wrapperStep places ~/.local/bin/okf for a source tree whose okf is not on PATH yet. It
// returns the step and whether ~/.local/bin must be on PATH.
func wrapperStep(c *ctx, un bool) (*step, bool) {
	dest := c.path(".local", "bin", "okf")
	text := wrapHead + "exec " + pyQuote(c.exe) + " \"$@\"\n"
	what := c.short(dest) + " (runs " + c.short(c.exe) + ")"
	cur, err := readText(dest)
	ours := err == nil && strings.HasPrefix(cur.or(""), wrapHead)

	t := func(cur opt) (opt, error) {
		if cur.Ok && !strings.HasPrefix(cur.S, wrapHead) {
			if un {
				return none, skip(c.short(dest) + " is not okf's; left alone")
			}
			return none, unsafe(c.short(dest) + " exists and is not okf's; move it away, then re-run")
		}
		if un {
			return none, nil
		}
		return some(text), nil
	}
	place := func() (*step, bool) {
		s := fileStep(c, "shell", "PATH", dest, t, what, "", false, 0o755)
		return s, s.status != "blocked" // a wrapper that could not be placed needs no PATH line
	}
	if un || ours {
		return place()
	}
	if found := c.which("okf"); found != "" {
		return newStep("shell", "PATH", "skip", "okf is already on PATH: "+c.short(found), nil), false
	}
	if !c.sourceTree() { // pipx/uv put their own console script in a bin directory; that is not ours to touch
		return newStep("shell", "PATH", "skip", "okf is not on PATH; run `pipx ensurepath` (or add its bin directory to PATH)", nil), false
	}
	return place() // a foreign file in the way comes back BLOCKED
}

// ownedFile is the transform of a file okf owns outright: its managed header says so.
func ownedFile(content func() string, un bool, where string) transform {
	return func(old opt) (opt, error) {
		if old.Ok && pytext.Strip(old.S) != "" && !strings.HasPrefix(old.S, managed+"\n") {
			if un {
				return none, skip(where + " is not okf's; left alone")
			}
			return none, unsafe(where + " exists and is not okf's; move it away, then re-run")
		}
		if un {
			return none, nil
		}
		return some(content()), nil
	}
}

// completionStep places the completion script of a shell. zsh's is a file the autoloader reads
// (first line `#compdef okf`), bash and fish get theirs behind the managed header.
func completionStep(c *ctx, sh string, p shellPaths, un bool) *step {
	subject := sh + " completion"
	script, _ := complete.Script(sh)
	if sh == "zsh" {
		return zshStep(c, subject, p.zshComp, script, un)
	}
	path := p.comp(sh)
	return fileStep(c, "shell", subject, path, ownedFile(func() string { return managed + "\n" + script }, un, c.short(path)),
		c.short(path), "", false, 0)
}

// zshStep is the step for ~/.zsh/completions/_okf: a file with the script text. A symlink to
// cli/_okf (what the Python install makes from a source tree) and an older copy are okf's own and
// get replaced; anything else is foreign.
func zshStep(c *ctx, subject, dest, script string, un bool) *step {
	state := "absent"
	switch {
	case islink(dest):
		target, _ := os.Readlink(dest)
		state = "foreign"
		if strings.HasSuffix(strings.TrimRight(target, "/"), "cli/_okf") || mine(dest) {
			state = "stale"
		}
	case lexists(dest):
		state = "foreign"
		if cur, err := readText(dest); err == nil && cur.Ok && cur.S == script {
			state = "ok"
		} else if mine(dest) {
			state = "stale"
		}
	}
	what := c.short(dest)
	if un {
		switch state {
		case "absent":
			return newStep("shell", subject, "ok", "", nil)
		case "foreign":
			return newStep("shell", subject, "skip", c.short(dest)+" is not okf's; left alone", nil)
		}
		return newStep("shell", subject, "remove", what, func() error {
			if err := clear(dest); err != nil {
				return err
			}
			prune(c, pyDirname(dest))
			return nil
		})
	}
	switch state {
	case "ok":
		return newStep("shell", subject, "ok", what, nil)
	case "foreign":
		return newStep("shell", subject, "blocked", c.short(dest)+" exists and is not okf's; move it away, then re-run", nil)
	}
	status := "update"
	if state == "absent" {
		status = "create"
	}
	return newStep("shell", subject, status, what, func() error { return putText(dest, script, 0o644) })
}

// putText writes text at dest atomically through a temporary sibling, replacing whatever is there.
func putText(dest, text string, mode os.FileMode) error {
	if err := os.MkdirAll(pyDirname(dest), 0o777); err != nil {
		return osError(err)
	}
	tmp := pyJoin(pyDirname(dest), ".okf-cli.tmp."+pyBasename(dest))
	if err := clear(tmp); err != nil {
		return err
	}
	if err := os.WriteFile(tmp, []byte(text), 0o666); err != nil {
		return osError(err)
	}
	if err := os.Chmod(tmp, mode); err != nil {
		return osError(err)
	}
	if err := clear(dest); err != nil {
		return err
	}
	return osError(os.Rename(tmp, dest))
}

// homeVar writes a path under HOME as "$HOME/..." for an rc file, any other path shell-quoted.
func homeVar(c *ctx, path string) string {
	if strings.HasPrefix(path, c.home+"/") {
		return `"$HOME` + path[len(c.home):] + `"`
	}
	return pyQuote(path)
}

var reCompinit = pytext.Regexp(`\bcompinit\b`)

// rcBody is the lines our rc block holds; rest is the rc without our block, so what the user
// already configures is not added twice.
func rcBody(c *ctx, sh string, rest []string, p shellPaths, needsPath, comp bool) []string {
	var body []string
	if needsPath && !mentions(rest, ".local/bin") {
		body = append(body, `case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) export PATH="$HOME/.local/bin:$PATH" ;; esac`)
	}
	switch {
	case comp && sh == "zsh":
		fpath := mentions(rest, ".zsh/completions")
		compinit := false
		for _, l := range rest {
			if !strings.HasPrefix(pytext.Lstrip(l), "#") && reCompinit.MatchString(l) {
				compinit = true
				break
			}
		}
		if !fpath {
			body = append(body, `fpath=("$HOME/.zsh/completions" $fpath)`)
		}
		switch {
		case !compinit:
			body = append(body, "autoload -Uz compinit && compinit")
		case !fpath: // compinit may have run already: register without waiting for it
			body = append(body, "autoload -Uz _okf", "(( $+functions[compdef] )) && compdef _okf okf")
		}
	case comp:
		r := homeVar(c, p.bashComp)
		body = append(body, "if [ -r "+r+" ]; then . "+r+"; fi")
	}
	return body
}

// rcStep is the step for one rc file (or fish's conf.d file); nil when nothing is wanted and
// nothing is there.
func rcStep(c *ctx, sh string, p shellPaths, un, needsPath, comp bool, path string) *step {
	var s *step
	if sh == "fish" {
		path = p.fishConf
		t := ownedFile(func() string {
			return managed + "\nif not contains -- $HOME/.local/bin $PATH\n    set -gx PATH $HOME/.local/bin $PATH\nend\n"
		}, un || !needsPath, c.short(path))
		s = fileStep(c, "shell", "fish PATH", path, t, c.short(path), "", false, 0)
	} else {
		if path == "" {
			path = p.rc(sh)
		}
		t := func(old opt) (opt, error) {
			text := old.or("")
			lines, err := linesOf(strings.ReplaceAll(text, "\r", "")) // enough to decide whether anything is to be done
			if err != nil {
				return none, err
			}
			var body []string
			if !un {
				rest, err := dropBlock(lines)
				if err != nil {
					return none, err
				}
				body = rcBody(c, sh, rest, p, needsPath, comp)
			}
			span, err := findBlock(lines)
			if err != nil {
				return none, err
			}
			if len(body) == 0 && span == nil {
				return old, nil
			}
			if strings.Contains(text, "\r") {
				return none, unsafe("the file uses CRLF line endings")
			}
			if len(body) == 0 {
				rest, err := dropBlock(lines)
				if err != nil {
					return none, err
				}
				if out := join(rest); out != "" {
					return some(out), nil
				}
				return none, nil
			}
			block := append([]string{begin, managed}, body...)
			put, err := putBlock(lines, append(block, end), -1)
			if err != nil {
				return none, err
			}
			return some(join(put)), nil
		}
		manual := "add to " + c.short(path) + " by hand:\n" +
			strings.Join(append(append([]string{begin}, rcBody(c, sh, nil, p, needsPath, comp)...), end), "\n")
		s = fileStep(c, "shell", sh+" rc", path, t, c.short(path)+" (managed block)", manual, true, 0)
	}
	if s.status == "ok" && !lexists(path) {
		return nil // nothing wanted, nothing there
	}
	return s
}

func shellSteps(c *ctx, ss []string, un bool) []*step {
	if len(ss) == 0 {
		return nil
	}
	p := c.shellPaths()
	wrapper, needsPath := wrapperStep(c, un)
	steps := []*step{wrapper}
	for _, sh := range ss {
		comp := completionStep(c, sh, p, un)
		active := comp.status == "create" || comp.status == "update" || comp.status == "ok"
		rcs := []string{""}
		if un && sh != "fish" {
			rcs = nil
			for _, x := range p.rcs(sh) {
				if lexists(x) {
					rcs = append(rcs, x)
				}
			}
		}
		steps = append(steps, comp)
		for _, x := range rcs {
			if s := rcStep(c, sh, p, un, needsPath, active, x); s != nil {
				steps = append(steps, s)
			}
		}
	}
	return steps
}

// loginShell is the passwd entry's shell: SHELL is set by login(1) and by bash, not by zsh;
// without it (cron, env -i, sudo) the passwd entry is the login shell.
func loginShell() string {
	uid := strconv.Itoa(os.Getuid())
	if b, err := os.ReadFile("/etc/passwd"); err == nil {
		for _, line := range strings.Split(string(b), "\n") {
			if f := strings.Split(line, ":"); len(f) >= 7 && f[2] == uid {
				return f[6]
			}
		}
	}
	for _, q := range [][]string{{"/usr/bin/getent", "passwd", uid}, {"/usr/bin/dscacheutil", "-q", "user", "-a", "uid", uid}} {
		out, err := exec.Command(q[0], q[1:]...).Output()
		if err != nil {
			continue
		}
		if strings.HasSuffix(q[0], "getent") {
			if f := strings.Split(strings.TrimSpace(string(out)), ":"); len(f) >= 7 {
				return f[6]
			}
			continue
		}
		for _, line := range strings.Split(string(out), "\n") {
			if v, ok := strings.CutPrefix(line, "shell:"); ok {
				return strings.TrimSpace(v)
			}
		}
	}
	return ""
}
