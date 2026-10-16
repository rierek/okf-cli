package install

import (
	"bytes"
	"context"
	"errors"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"syscall"
	"time"

	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

const (
	scriptName = "okf_mcp.py" // an MCP entry that names this script is okf's own
	begin      = "# >>> okf-cli >>>"
	end        = "# <<< okf-cli <<<"
	managed    = "# managed by `okf install`; undo with `okf install --uninstall --apply`"
	wrapHead   = "#!/bin/sh\n" + managed + "\n"
)

var (
	harnesses = []string{"claude", "omp", "codex", "opencode", "kimi", "openclaw", "hermes"}
	shells    = []string{"zsh", "bash", "fish"}
	// harnesses that read ~/.agents/skills: one shared install covers all of them
	sharedReaders = []string{"codex", "opencode", "kimi", "omp", "openclaw"}
)

// ctx is everything install reads from the machine (Python Ctx).
type ctx struct {
	env     map[string]string
	home    string
	pkgRoot string // the nearest ancestor of the executable holding skills/okf and mcp/okf_mcp.py
	exe     string // the executable, symlinks resolved, a Homebrew Cellar path mapped to opt
	goos    string
	timeout time.Duration
}

func (c *ctx) envGet(k string) string { return c.env[k] }

// sourceTree is a checkout (or unpacked sdist), not an installed package: its files stay where
// they are, so a symlink follows `git pull`; an installed package's may move.
func (c *ctx) sourceTree() bool { return isfile(pyJoin(c.pkgRoot, "pyproject.toml")) }

func (c *ctx) path(parts ...string) string { return pyJoin(append([]string{c.home}, parts...)...) }

// which is shutil.which(name, path=env PATH): the first executable regular file on PATH.
func (c *ctx) which(name string) string {
	path, ok := c.env["PATH"]
	if !ok {
		path = "/bin:/usr/bin"
	}
	if path == "" {
		return ""
	}
	for _, dir := range strings.Split(path, ":") {
		fn := pyJoin(dir, name)
		if exists(fn) && syscall.Access(fn, 1) == nil && !isdir(fn) {
			return fn
		}
	}
	return ""
}

// short is the path with HOME written as `~`.
func (c *ctx) short(p string) string {
	h := c.home
	if p == h || strings.HasPrefix(p, h+"/") {
		return "~" + p[len(h):]
	}
	return p
}

func (c *ctx) environ() []string {
	out := make([]string, 0, len(c.env))
	for k, v := range c.env {
		out = append(out, k+"="+v)
	}
	return out
}

// run starts a harness CLI with stdin /dev/null and the install timeout; a non-zero exit, a
// timeout or a start failure is a failedErr with the text of the Python exception.
func (c *ctx) run(argv []string) error {
	path := c.which(argv[0])
	if path == "" {
		path = argv[0]
	}
	cx, cancel := context.WithTimeout(context.Background(), c.timeout)
	defer cancel()
	cmd := exec.CommandContext(cx, path)
	cmd.Args = argv
	cmd.Env = c.environ()
	var out, errb bytes.Buffer
	cmd.Stdout, cmd.Stderr = &out, &errb
	cmd.WaitDelay = time.Second
	err := cmd.Run()
	if cx.Err() != nil && errors.Is(cx.Err(), context.DeadlineExceeded) {
		return &failedErr{shlexJoin(argv) + ": Command '" + pytext.Repr(strs(argv)) + "' timed out after " +
			strconv.Itoa(int(c.timeout/time.Second)) + " seconds"}
	}
	var exitErr *exec.ExitError
	switch {
	case err == nil:
		return nil
	case errors.As(err, &exitErr):
		code := exitErr.ExitCode()
		if ws, ok := exitErr.Sys().(syscall.WaitStatus); ok && ws.Signaled() {
			code = -int(ws.Signal())
		}
		text := universalNewlines(errb.String())
		if text == "" {
			text = universalNewlines(out.String())
		}
		text = pytext.Strip(text)
		if r := []rune(text); len(r) > 300 {
			text = string(r[:300])
		}
		return &failedErr{shlexJoin(argv) + " exited " + strconv.Itoa(code) + ": " + text}
	}
	oe := osError(err)
	return &failedErr{shlexJoin(argv) + ": " + oe.Error()}
}

func universalNewlines(s string) string {
	return strings.ReplaceAll(strings.ReplaceAll(s, "\r\n", "\n"), "\r", "\n")
}

func strs(a []string) []any {
	out := make([]any, len(a))
	for i, s := range a {
		out[i] = s
	}
	return out
}

// newCtx reads the machine: the environment, HOME, the executable and its package root.
func newCtx(goos string) *ctx {
	c := &ctx{env: map[string]string{}, goos: goos, timeout: 30 * time.Second}
	for _, kv := range os.Environ() {
		if k, v, ok := strings.Cut(kv, "="); ok {
			c.env[k] = v
		}
	}
	home := c.env["HOME"]
	if home == "" {
		home, _ = os.UserHomeDir()
	}
	c.home = abspath(home)
	c.exe, c.pkgRoot = locate()
	return c
}

// locate resolves the executable (symlinks followed, a Cellar path mapped to the stable opt
// symlink) and its package root: the nearest ancestor directory that holds skills/okf/SKILL.md
// and mcp/okf_mcp.py. An executable outside any package gets its parent directory as root, where
// the skill and the MCP script are then reported missing.
func locate() (exe, root string) {
	self, err := os.Executable()
	if err != nil {
		self = os.Args[0]
	}
	exe = brewOptPath(realpath(self))
	for d := pyDirname(exe); ; d = pyDirname(d) {
		if isfile(pyJoin(d, "skills", "okf", "SKILL.md")) && isfile(pyJoin(d, "mcp", scriptName)) {
			return exe, d
		}
		if d == "/" || d == "" || d == "." {
			break
		}
	}
	return exe, pyDirname(pyDirname(exe))
}

// brewOptPath: Homebrew installs to <prefix>/Cellar/<formula>/<version>, which `brew upgrade`
// deletes; the symlink <prefix>/opt/<formula> stays. Config files must name that one.
func brewOptPath(path string) string {
	const marker = "/Cellar/"
	for from := len(path); ; {
		i := strings.LastIndex(path[:from], marker)
		if i < 0 {
			return path
		}
		from = i
		formula, rest, _ := strings.Cut(path[i+len(marker):], "/")
		version, _, _ := strings.Cut(rest, "/")
		if formula == "" || version == "" {
			continue
		}
		prefix := path[:i]
		cellar := path[:i+len(marker)+len(formula)+1+len(version)]
		opt := pyJoin(prefix, "opt", formula)
		if isdir(opt) {
			a, errA := os.Stat(opt)
			b, errB := os.Stat(cellar)
			if errA == nil && errB == nil && os.SameFile(a, b) {
				return opt + path[len(cellar):]
			}
		}
		return path
	}
}
