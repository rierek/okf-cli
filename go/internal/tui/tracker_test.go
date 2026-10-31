package tui

import (
	"os"
	"path/filepath"
	"regexp"
	"slices"
	"strings"
	"testing"
	"time"

	tea "github.com/charmbracelet/bubbletea"
)

// trackerRig is a model on the fixture with a fake tracker command. The command script writes the
// NUL-separated task variables and its own arguments to envFile; a fake `sh` on PATH writes the
// arguments the program gave `sh` to argvFile, then runs the real shell.
type trackerRig struct {
	m                 model
	dir, envFile      string
	argvFile, command string
}

// newTrackerRig configures a `command` tracker whose script runs body after it logged the task.
// The command string has blanks at both ends and inside, so a trim or a re-quote shows.
func newTrackerRig(t *testing.T, body string) trackerRig {
	t.Helper()
	dir := t.TempDir()
	r := trackerRig{dir: dir, envFile: filepath.Join(dir, "env"), argvFile: filepath.Join(dir, "argv")}
	script := fakeEditor(t, `printf '%s\0' "$OKF_TASK_TITLE" "$OKF_TASK_BODY" "$OKF_TASK_PATH" "$OKF_TASK_REF" "$OKF_TASK_ROOT" "$@" > `+r.envFile+"\n"+body)
	r.command = " " + script + `  "$OKF_TASK_TITLE"  "$OKF_TASK_BODY" `
	fakeSh := filepath.Join(dir, "bin", "sh")
	if err := os.MkdirAll(filepath.Dir(fakeSh), 0o755); err != nil {
		t.Fatal(err)
	}
	shim := "#!/bin/sh\nprintf '%s\\0' \"$@\" > " + r.argvFile + "\nexec /bin/sh \"$@\"\n"
	if err := os.WriteFile(fakeSh, []byte(shim), 0o755); err != nil {
		t.Fatal(err)
	}
	t.Setenv("PATH", filepath.Dir(fakeSh)+string(os.PathListSeparator)+os.Getenv("PATH"))
	writeConfig(t, "[tui.tracker]\nkind = \"command\"\ncommand = '"+r.command+"'\n")
	r.m = searchedOnFixture(t, "unused")
	return r
}

// nulFields reads a file of NUL-terminated fields.
func nulFields(t *testing.T, path string) []string {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	return strings.Split(strings.TrimSuffix(string(data), "\x00"), "\x00")
}

// writeTask opens the task box on the focused hit and puts text in it.
func writeTask(t *testing.T, m model, text string) model {
	t.Helper()
	m, _ = press(m, "t")
	if m.overlay != overlayText || m.text.caller != taskCaller {
		t.Fatalf("t opened no task box (overlay %v)", m.overlay)
	}
	m.text.area.SetValue(text)
	return m
}

// answer runs the command the save returned and feeds its answer back.
func answer(t *testing.T, m model, cmd tea.Cmd) model {
	t.Helper()
	if cmd == nil {
		t.Fatal("saving the task started no command")
	}
	msg, ok := cmd().(taskDoneMsg)
	if !ok {
		t.Fatalf("the save command answered %T, want taskDoneMsg", cmd())
	}
	return feed(m, msg)
}

// sameScreen checks that root, query, list, focus and buffer did not change.
func sameScreen(t *testing.T, before, after model) {
	t.Helper()
	paths := func(m model) []string {
		var out []string
		for _, h := range m.search.hits {
			out = append(out, h.Abs)
		}
		return out
	}
	if before.root != after.root || before.query.Value() != after.query.Value() || before.focus != after.focus ||
		before.screen != after.screen || !slices.Equal(paths(before), paths(after)) ||
		before.search.focused().Abs != after.search.focused().Abs || !slices.Equal(titles(before), titles(after)) {
		t.Errorf("the screen changed: root %q→%q, query %q→%q, focus %v→%v, focused %s→%s",
			before.root, after.root, before.query.Value(), after.query.Value(), before.focus, after.focus,
			before.search.focused().Abs, after.search.focused().Abs)
	}
}

// Criteria 1, 2, 4 and 7: the task reaches the command in OKF_TASK_* variables; the command string
// run by `sh -c` is the configured one byte for byte, although title and body are hostile; a toast
// shows the first stdout line; nothing else of the screen changes and the buffer stays empty.
func TestCommandTrackerGetsTaskInEnvironment(t *testing.T) {
	r := newTrackerRig(t, "echo 'filed as T-1'\necho second line")
	pwned := filepath.Join(r.dir, "PWNED")
	title := `fix "deploy" $(touch ` + pwned + `); 'x' ` + "`touch " + pwned + "`" + ` | & > <`
	body := "why: $HOME; touch " + pwned + "\n\n  indented \\ line"
	m := r.m
	before := m
	hit := *m.search.focused()

	m = writeTask(t, m, title+"\n"+body)
	m, cmd := pressKey(m, tea.KeyCtrlS)
	if m.overlay != overlayNone {
		t.Fatalf("overlay %v after ctrl+s, want the box closed", m.overlay)
	}
	m = answer(t, m, cmd)

	env := nulFields(t, r.envFile)
	want := []string{title, body, hit.Abs, hit.Path, m.root, title, body}
	if !slices.Equal(env, want) {
		t.Errorf("task variables and arguments:\n got %q\nwant %q", env, want)
	}
	if !filepath.IsAbs(env[2]) || !strings.Contains(env[3], "/") {
		t.Errorf("OKF_TASK_PATH %q must be absolute and OKF_TASK_REF %q `<bundle>/<id>`", env[2], env[3])
	}
	if argv := nulFields(t, r.argvFile); !slices.Equal(argv, []string{"-c", r.command}) {
		t.Errorf("sh got %q, want [-c %q]", argv, r.command)
	}
	if _, err := os.Stat(pwned); err == nil {
		t.Error("task text was executed by the shell")
	}
	if m.toast == nil || m.toast.kind != toastInfo || m.toast.context != "filed as T-1" {
		t.Errorf("toast = %+v, want an info toast with the first stdout line", m.toast)
	}
	sameScreen(t, before, m)
	if len(m.buf.Entries()) != 0 {
		t.Errorf("the buffer holds %v, a task must not enter it", titles(m))
	}
}

// Criterion 5: a failing command shows its stderr in an error toast and the box comes back with
// the same text; saving again after the cause is gone records the task.
func TestCommandFailureKeepsPromptForRetry(t *testing.T) {
	r := newTrackerRig(t, "")
	gate := filepath.Join(r.dir, "down")
	script := fakeEditor(t, `if [ -e `+gate+` ]; then echo 'tracker down: try later' >&2; exit 1; fi
echo recorded`)
	writeConfig(t, "[tui.tracker]\nkind = \"command\"\ncommand = '"+script+"'\n")
	if err := os.WriteFile(gate, nil, 0o644); err != nil {
		t.Fatal(err)
	}
	text := "title line\nbody line"
	m := writeTask(t, r.m, text)
	m, cmd := pressKey(m, tea.KeyCtrlS)
	m = answer(t, m, cmd)

	if m.toast == nil || m.toast.kind != toastError || !strings.Contains(m.toast.context, "tracker down: try later") {
		t.Errorf("toast = %+v, want an error toast with the stderr", m.toast)
	}
	if m.overlay != overlayText || m.text.area.Value() != text {
		t.Fatalf("overlay %v, text %q: want the box back with %q", m.overlay, m.text.area.Value(), text)
	}
	if err := os.Remove(gate); err != nil {
		t.Fatal(err)
	}
	m, cmd = pressKey(m, tea.KeyCtrlS)
	m = answer(t, m, cmd)
	if m.overlay != overlayNone || m.toast == nil || m.toast.kind != toastInfo || m.toast.context != "recorded" {
		t.Errorf("retry: overlay %v, toast %+v, want the task recorded", m.overlay, m.toast)
	}
}

// Criterion 3: a `file` tracker appends one Obsidian-Tasks line with the hit reference and the
// absolute path, body lines indented; `~` expands; a missing file and folder are created; a file
// without a final newline keeps its last line.
func TestFileTrackerAppendsTaskLine(t *testing.T) {
	home := t.TempDir()
	t.Setenv("HOME", home)
	writeConfig(t, "[tui.tracker]\nkind = \"file\"\nfile = \"~/vault/Tasks/okf.md\"\n")
	m := searchedOnFixture(t, "unused")
	before := m
	hit := *m.search.focused()
	file := filepath.Join(home, "vault", "Tasks", "okf.md")

	m = writeTask(t, m, "Check deploy steps\nfirst detail\n\nsecond detail")
	m, cmd := pressKey(m, tea.KeyCtrlS)
	m = answer(t, m, cmd)
	if m.toast == nil || m.toast.kind != toastInfo || !strings.Contains(m.toast.context, file) {
		t.Errorf("toast = %+v, want an info toast naming %s", m.toast, file)
	}
	sameScreen(t, before, m)
	if len(m.buf.Entries()) != 0 {
		t.Errorf("the buffer holds %v, a task must not enter it", titles(m))
	}

	link := "[" + hit.Path + "](" + hit.Abs + ")"
	date := ` ➕ \d{4}-\d{2}-\d{2}`
	first := regexp.MustCompile(`^- \[ \] Check deploy steps ` + regexp.QuoteMeta(link) + date + `\n  first detail\n  second detail\n$`)
	data, err := os.ReadFile(file)
	if err != nil || !first.Match(data) {
		t.Fatalf("file (%v):\n%s\nwant a task line with %s and the two body lines indented", err, data, link)
	}

	if err := os.WriteFile(file, []byte("- [ ] older"), 0o644); err != nil { // no final newline
		t.Fatal(err)
	}
	m = writeTask(t, m, "Second task")
	m, cmd = pressKey(m, tea.KeyCtrlS)
	answer(t, m, cmd)
	data, _ = os.ReadFile(file)
	second := regexp.MustCompile(`^- \[ \] older\n- \[ \] Second task ` + regexp.QuoteMeta(link) + date + `\n$`)
	if !second.Match(data) {
		t.Errorf("file:\n%s\nwant the older line kept and one task line appended", data)
	}
}

// A path with a blank or a parenthesis goes in angle brackets, so the Markdown link holds.
func TestTaskLineLinkTarget(t *testing.T) {
	day := time.Date(2026, 10, 31, 0, 0, 0, 0, time.UTC)
	got := taskLine(maintenanceTask{Title: "T", Body: "a\n\n b ", Path: "/x y/z.md", Ref: "b/z"}, day)
	if want := "- [ ] T [b/z](</x y/z.md>) ➕ 2026-10-31\n  a\n   b\n"; got != want {
		t.Errorf("taskLine = %q, want %q", got, want)
	}
}

// Criterion 6: a missing or invalid tracker opens no box, saves nothing and names the problem and
// the config path.
func TestTrackerProblemNamesPathInsteadOfSaving(t *testing.T) {
	cases := []struct{ name, config, problem string }{
		{"no config file", "", "no config file"},
		{"no tracker table", "[tui]\ntheme = \"mocha\"\n", "no [tui.tracker] table"},
		{"tracker not a table", "[tui]\ntracker = \"lif\"\n", "must be a table"},
		{"no kind", "[tui.tracker]\ncommand = \"true\"\n", "needs a string key `kind`"},
		{"unknown kind", "[tui.tracker]\nkind = \"jira\"\n", `kind "jira" is unknown`},
		{"empty command", "[tui.tracker]\nkind = \"command\"\ncommand = \"  \"\n", "needs a non-empty string key `command`"},
		{"command of wrong type", "[tui.tracker]\nkind = \"command\"\ncommand = 3\n", "needs a non-empty string key `command`"},
		{"empty file", "[tui.tracker]\nkind = \"file\"\n", "needs a non-empty string key `file`"},
		{"relative file", "[tui.tracker]\nkind = \"file\"\nfile = \"tasks.md\"\n", "must be an absolute path or start with ~"},
		{"broken toml", "[tui.tracker\nkind = 1\n", ""},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			var path string
			if c.name == "no config file" {
				t.Setenv("XDG_CONFIG_HOME", t.TempDir())
				path = filepath.Join(os.Getenv("XDG_CONFIG_HOME"), "okf", "config.toml")
			} else {
				path = writeConfig(t, c.config)
			}
			m := searchedOnFixture(t, "unused")
			before := m
			m, cmd := press(m, "t")
			if m.overlay != overlayNone || cmd != nil {
				t.Fatalf("overlay %v, cmd %v: a broken tracker must open no box and run nothing", m.overlay, cmd != nil)
			}
			if m.toast == nil || m.toast.kind != toastError || !m.toast.sticky ||
				!strings.Contains(m.toast.context, path) || !strings.Contains(m.toast.context, c.problem) {
				t.Errorf("toast = %+v, want an error toast with %q and the path %s", m.toast, c.problem, path)
			}
			sameScreen(t, before, m)
		})
	}
}

// An empty text has no title: the task is refused with a toast, nothing runs and the box stays.
func TestTaskWithoutTitleIsRefused(t *testing.T) {
	r := newTrackerRig(t, "echo ran")
	m := writeTask(t, r.m, "  \n ")
	m, _ = pressKey(m, tea.KeyCtrlS)
	if m.toast == nil || m.toast.kind != toastWarn || m.overlay != overlayText {
		t.Errorf("toast %+v, overlay %v: want a warning and the box open", m.toast, m.overlay)
	}
	if _, err := os.Stat(r.envFile); err == nil {
		t.Error("the command ran for a task without a title")
	}
}

// commandModel is a model on the fixture whose tracker command is a script that runs body.
func commandModel(t *testing.T, body string) model {
	t.Helper()
	writeConfig(t, "[tui.tracker]\nkind = \"command\"\ncommand = '"+fakeEditor(t, body)+"'\n")
	return searchedOnFixture(t, "unused")
}

// saveTask writes text in the task box and saves; the returned message is the tracker's answer.
func saveTask(t *testing.T, m model, text string) (model, taskDoneMsg) {
	t.Helper()
	m = writeTask(t, m, text)
	m, cmd := pressKey(m, tea.KeyCtrlS)
	msg, ok := cmd().(taskDoneMsg)
	if !ok {
		t.Fatalf("the save command answered %T, want taskDoneMsg", cmd())
	}
	return m, msg
}

// Criterion 5: a command that fails without stderr shows its exit status; a long stderr is cut to
// 400 characters; a command without stdout gives the title and the reference in the toast.
func TestTaskToastTexts(t *testing.T) {
	t.Run("exit status without stderr", func(t *testing.T) {
		m, msg := saveTask(t, commandModel(t, "exit 3"), "title")
		m = feed(m, msg)
		if m.toast == nil || m.toast.kind != toastError || !strings.Contains(m.toast.context, "exit status 3") {
			t.Errorf("toast = %+v, want the exit status", m.toast)
		}
	})
	t.Run("long stderr is cut", func(t *testing.T) {
		m, msg := saveTask(t, commandModel(t, "head -c 600 /dev/zero | tr '\\0' x >&2; exit 1"), "title")
		m = feed(m, msg)
		if got := []rune(m.toast.context); len(got) != maxStderrToast+1 || got[len(got)-1] != '…' {
			t.Errorf("toast context has %d runes, want %d and a final …", len(got), maxStderrToast+1)
		}
	})
	t.Run("silent success", func(t *testing.T) {
		m := commandModel(t, "exit 0")
		hit := *m.search.focused()
		m, msg := saveTask(t, m, "silent title")
		m = feed(m, msg)
		if want := "silent title (" + hit.Path + ")"; m.toast == nil || m.toast.kind != toastInfo || m.toast.context != want {
			t.Errorf("toast = %+v, want context %q", m.toast, want)
		}
	})
}

// A late failure never replaces another overlay: a note box, the help and a second task box keep
// their state, and the sticky error toast names the failed task.
func TestLateTaskFailureKeepsOtherOverlay(t *testing.T) {
	m, failed := saveTask(t, commandModel(t, "echo nope >&2; exit 1"), "first task")

	note, _ := press(m, "n", "my note")
	if got := feed(note, failed); got.overlay != overlayText || got.text.caller != noteCaller || got.text.area.Value() != "my note" {
		t.Errorf("note box: overlay %v, caller %q, text %q: want it untouched", got.overlay, got.text.caller, got.text.area.Value())
	} else if got.toast == nil || got.toast.kind != toastError || !strings.Contains(got.toast.title, "first task") ||
		!strings.Contains(got.toast.context, "nope") {
		t.Errorf("toast = %+v, want an error toast naming the task and stderr", got.toast)
	}

	second := writeTask(t, m, "second task")
	if got := feed(second, failed); got.overlay != overlayText || got.text.area.Value() != "second task" {
		t.Errorf("second task box: overlay %v, text %q: want it untouched", got.overlay, got.text.area.Value())
	}

	help, _ := press(m, "?")
	if got := feed(help, failed); got.overlay != overlayHelp {
		t.Errorf("overlay %v, want the help kept", got.overlay)
	}

	if got := feed(m, failed); got.overlay != overlayText || got.text.area.Value() != "first task" {
		t.Errorf("no other overlay: overlay %v, text %q: want the task box back", got.overlay, got.text.area.Value())
	}
}

// A body line that looks like a task does not become a second task.
func TestTaskLineEscapesBodyCheckbox(t *testing.T) {
	day := time.Date(2026, 10, 31, 0, 0, 0, 0, time.UTC)
	got := taskLine(maintenanceTask{Title: "T", Body: "- [ ] sub\n  * [x] done\n1. [ ] num\n- [link](x) plain\ntext [ ] mid", Path: "/p.md", Ref: "b/z"}, day)
	want := "- [ ] T [b/z](/p.md) ➕ 2026-10-31\n" +
		"  - \\[ ] sub\n" + "    * \\[x] done\n" + "  1. \\[ ] num\n" + "  - [link](x) plain\n" + "  text [ ] mid\n"
	if got != want {
		t.Errorf("taskLine:\n%s\nwant:\n%s", got, want)
	}
}
