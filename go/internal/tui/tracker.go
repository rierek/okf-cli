package tui

import (
	"bytes"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
)

// maintenanceTask is one task the user records on a hit.
type maintenanceTask struct {
	Title string // one line
	Body  string // the rest of the text, may be empty
	Path  string // absolute path of the hit's file
	Ref   string // `<bundle>/<id>`, the hit reference
	Root  string // the active root
}

// tracker records a maintenance task and returns a short note for the success toast. Two kinds
// exist (`[tui.tracker]` of the user config): a command and a file. Tracker-specific code does not
// belong here; a tracker is a command line.
type tracker interface {
	record(maintenanceTask) (note string, err error)
}

// loadTracker reads the `[tui.tracker]` table of the user config. Every problem comes back as an
// error that names the config path and the fault; the caller shows it instead of saving.
func loadTracker() (tracker, error) {
	path := catalogue.UserConfigPath()
	fail := func(format string, args ...any) (tracker, error) {
		return nil, fmt.Errorf("%s: [tui.tracker] %s", path, fmt.Sprintf(format, args...))
	}
	if info, err := os.Stat(path); err != nil || info.IsDir() {
		return nil, fmt.Errorf("%s: no config file, so no [tui.tracker]; add one with kind = \"command\" or kind = \"file\"", path)
	}
	table, err := catalogue.ReadTOML(path)
	if err != nil {
		return nil, err
	}
	tui, _ := table["tui"].(map[string]any)
	raw, present := tui["tracker"]
	if !present {
		return nil, fmt.Errorf("%s: no [tui.tracker] table; add one with kind = \"command\" or kind = \"file\"", path)
	}
	section, ok := raw.(map[string]any)
	if !ok {
		return fail("must be a table")
	}
	str := func(key string) string {
		v, _ := section[key].(string)
		return v
	}
	kind := str("kind")
	switch kind {
	case "command":
		command := str("command")
		if strings.TrimSpace(command) == "" {
			return fail("kind \"command\" needs a non-empty string key `command`")
		}
		return commandTracker{command: command}, nil
	case "file":
		file := strings.TrimSpace(str("file"))
		if file == "" {
			return fail("kind \"file\" needs a non-empty string key `file`")
		}
		if file = catalogue.ExpandUser(file); !filepath.IsAbs(file) {
			return fail("file %q must be an absolute path or start with ~", file)
		}
		return fileTracker{file: file}, nil
	case "":
		return fail("needs a string key `kind`: \"command\" or \"file\"")
	}
	return fail("kind %q is unknown (use \"command\" or \"file\")", kind)
}

// commandTracker runs `sh -c <command>`. The task reaches the command in OKF_TASK_* environment
// variables only: the command string is passed on as configured, so task text never meets the
// shell's parser. Quote the variables in the command (`"$OKF_TASK_TITLE"`).
type commandTracker struct{ command string }

// taskEnv is the environment of a command: the parent's, plus the task.
func taskEnv(t maintenanceTask) []string {
	return append(os.Environ(),
		"OKF_TASK_TITLE="+t.Title,
		"OKF_TASK_BODY="+t.Body,
		"OKF_TASK_PATH="+t.Path,
		"OKF_TASK_REF="+t.Ref,
		"OKF_TASK_ROOT="+t.Root,
	)
}

// record runs the command. The note is the first line of stdout; a non-zero exit gives an error
// that carries stderr (the exit status when stderr is empty).
// ponytail: no timeout; a command that hangs leaves the box closed and no answer. Add a context
// deadline when a tracker command turns out to hang.
func (c commandTracker) record(t maintenanceTask) (string, error) {
	cmd := exec.Command("sh", "-c", c.command)
	cmd.Env = taskEnv(t)
	var stdout, stderr bytes.Buffer
	cmd.Stdout, cmd.Stderr = &stdout, &stderr
	if err := cmd.Run(); err != nil {
		if msg := strings.TrimSpace(stderr.String()); msg != "" {
			return "", fmt.Errorf("%s", msg)
		}
		return "", err
	}
	first, _, _ := strings.Cut(strings.TrimSpace(stdout.String()), "\n")
	return strings.TrimSpace(first), nil
}

// fileTracker appends an Obsidian Tasks line to file.
type fileTracker struct{ file string }

// taskLine is the Obsidian Tasks entry of t: `- [ ] <title> [<ref>](<path>) ➕ <date>`, then the
// body as indented lines. Blank body lines are dropped: a blank line would end the list item.
// A path with a space or a parenthesis goes in `<...>`, which Markdown links accept.
func taskLine(t maintenanceTask, day time.Time) string {
	target := t.Path
	if strings.ContainsAny(target, " ()") {
		target = "<" + target + ">"
	}
	var b strings.Builder
	fmt.Fprintf(&b, "- [ ] %s [%s](%s) ➕ %s\n", t.Title, t.Ref, target, day.Format("2006-01-02"))
	for _, line := range strings.Split(t.Body, "\n") {
		if line = strings.TrimRight(line, " \t\r"); line != "" {
			b.WriteString("  " + line + "\n")
		}
	}
	return b.String()
}

// record appends the task line and creates the file (and its folder) when absent. A file that
// does not end in a newline gets one first.
func (f fileTracker) record(t maintenanceTask) (string, error) {
	if err := os.MkdirAll(filepath.Dir(f.file), 0o755); err != nil {
		return "", err
	}
	out, err := os.OpenFile(f.file, os.O_RDWR|os.O_APPEND|os.O_CREATE, 0o644)
	if err != nil {
		return "", err
	}
	defer out.Close()
	line := taskLine(t, time.Now())
	if info, err := out.Stat(); err == nil && info.Size() > 0 {
		last := make([]byte, 1)
		if _, err := out.ReadAt(last, info.Size()-1); err == nil && last[0] != '\n' {
			line = "\n" + line
		}
	}
	if _, err := out.WriteString(line); err != nil {
		return "", err
	}
	return "appended to " + f.file, out.Close()
}
