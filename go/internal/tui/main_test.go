package tui

import (
	"flag"
	"os"
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"github.com/muesli/termenv"
)

// update rewrites the golden frames: go test ./internal/tui -update
var update = flag.Bool("update", false, "rewrite the golden files in testdata")

// Golden frames are rendered at a fixed size and colour profile (no colour escapes), so they do
// not depend on the terminal that runs the tests.
const (
	goldenWidth  = 100
	goldenHeight = 30
	testRoot     = "/srv/catalogue"
)

func TestMain(m *testing.M) {
	// The user config and the TUI state file of the developer must not leak into a test.
	home, err := os.MkdirTemp("", "okf-tui-test")
	if err != nil {
		panic(err)
	}
	os.Setenv("HOME", home)
	os.Setenv("XDG_CONFIG_HOME", home+"/.config")
	os.Setenv("XDG_STATE_HOME", home+"/.local/state")
	lipgloss.SetColorProfile(termenv.Ascii)
	defaultSettings().apply()
	code := m.Run()
	os.RemoveAll(home)
	os.Exit(code)
}

// key builds the key message of a key name or of typed text.
func key(s string) tea.KeyMsg {
	switch s {
	case "esc":
		return tea.KeyMsg{Type: tea.KeyEsc}
	case "tab":
		return tea.KeyMsg{Type: tea.KeyTab}
	case "shift+tab":
		return tea.KeyMsg{Type: tea.KeyShiftTab}
	case "enter":
		return tea.KeyMsg{Type: tea.KeyEnter}
	case "ctrl+c":
		return tea.KeyMsg{Type: tea.KeyCtrlC}
	case "ctrl+k":
		return tea.KeyMsg{Type: tea.KeyCtrlK}
	case "f1":
		return tea.KeyMsg{Type: tea.KeyF1}
	}
	return tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune(s)}
}

// press sends the keys one after the other and returns the model and the command of the last key.
func press(m model, names ...string) (model, tea.Cmd) {
	var cmd tea.Cmd
	for _, n := range names {
		var next tea.Model
		next, cmd = m.Update(key(n))
		m = next.(model)
	}
	return m, cmd
}

// quits reports whether cmd ends the program.
func quits(cmd tea.Cmd) bool {
	if cmd == nil {
		return false
	}
	_, ok := cmd().(tea.QuitMsg)
	return ok
}

// sized is the start model at the golden size.
func sized(t *testing.T, settingsErr error) model {
	t.Helper()
	m := newModel(testRoot, defaultSettings(), settingsErr)
	next, _ := m.Update(tea.WindowSizeMsg{Width: goldenWidth, Height: goldenHeight})
	return next.(model)
}

// writeConfig makes content the user config of the test.
func writeConfig(t *testing.T, content string) string {
	t.Helper()
	dir := t.TempDir()
	t.Setenv("XDG_CONFIG_HOME", dir)
	path := dir + "/okf/config.toml"
	if err := os.MkdirAll(dir+"/okf", 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}
	return path
}

// assertGolden compares the view with testdata/<name>.golden, which -update rewrites. It also
// checks that the frame fills the terminal exactly.
func assertGolden(t *testing.T, name string, m model) {
	t.Helper()
	out := m.View()
	if h := lipgloss.Height(out); h != m.height {
		t.Errorf("view height = %d, want the terminal height %d", h, m.height)
	}
	for i, line := range strings.Split(out, "\n") {
		if w := lipgloss.Width(line); w > m.width {
			t.Errorf("line %d is %d cells wide, want at most %d: %q", i, w, m.width, line)
		}
	}
	path := "testdata/" + name + ".golden"
	if *update {
		if err := os.MkdirAll("testdata", 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(path, []byte(out), 0o644); err != nil {
			t.Fatal(err)
		}
		return
	}
	want, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("golden missing, rewrite with -update: %v", err)
	}
	if out != string(want) {
		t.Errorf("view differs from %s (rewrite with -update).\n--- got ---\n%s\n--- want ---\n%s", path, out, want)
	}
}
