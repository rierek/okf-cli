package tui

import (
	"errors"
	"strings"
	"testing"

	"github.com/charmbracelet/lipgloss"
	"github.com/muesli/termenv"

	"nas/volume1/data/git/okf-tools/go/internal/tui/theme"
)

// US 1: the TUI starts on the search screen, root in the header, query field focused.
func TestStartScreen(t *testing.T) {
	m := sized(t, nil)
	if m.focus != focusQuery || !m.query.Focused() {
		t.Fatalf("focus = %v, query focused = %v; want the query field focused", m.focus, m.query.Focused())
	}
	out := m.View()
	for _, want := range []string{"> " + testRoot + ": Search", "/ query"} {
		if !strings.Contains(out, want) {
			t.Errorf("start view lacks %q:\n%s", want, out)
		}
	}
	assertGolden(t, "start", m)
}

// Inside the query field the letter keys type: q neither quits nor asks, ? does not open the help.
func TestQueryFieldTypesLetterKeys(t *testing.T) {
	m, cmd := press(sized(t, nil), "q", "?", "j")
	if m.overlay != overlayNone || quits(cmd) {
		t.Fatalf("overlay = %v, quits = %v; want typing only", m.overlay, quits(cmd))
	}
	if got := m.query.Value(); got != "q?j" {
		t.Errorf("query = %q, want %q", got, "q?j")
	}
}

// esc leaves the field, / and tab come back; tab and shift+tab cycle the whole ring, and walk the
// fields of the filter bar on their way through it.
func TestFocusRing(t *testing.T) {
	m, _ := press(sized(t, nil), "esc")
	if m.focus != focusList || m.query.Focused() {
		t.Fatalf("after esc: focus = %v, query focused = %v; want the list focused", m.focus, m.query.Focused())
	}
	m, _ = press(m, "/")
	if m.focus != focusQuery || !m.query.Focused() {
		t.Fatalf("after /: focus = %v; want the query field", m.focus)
	}
	m, _ = press(m, "tab")
	if m.focus != focusFilter || m.filters.field != fieldRoot {
		t.Fatalf("after tab: focus = %v, field = %v; want the first field of the filter bar", m.focus, m.filters.field)
	}
	for f := fieldBundle; f < filterFieldCount; f++ {
		if m, _ = press(m, "tab"); m.focus != focusFilter || m.filters.field != f {
			t.Fatalf("tab inside the bar: focus = %v, field = %v; want field %v", m.focus, m.filters.field, f)
		}
	}
	m, _ = press(m, "tab")
	if m.focus != focusList {
		t.Fatalf("tab behind the last field: focus = %v; want the list", m.focus)
	}
	m, _ = press(m, "tab")
	if m.focus != focusQuery {
		t.Fatalf("tab wraps: focus = %v; want the query field", m.focus)
	}
	m, _ = press(m, "shift+tab")
	if m.focus != focusList {
		t.Fatalf("shift+tab wraps back: focus = %v; want the list", m.focus)
	}
	m, _ = press(m, "shift+tab")
	if m.focus != focusFilter || m.filters.field != filterFieldCount-1 {
		t.Fatalf("shift+tab into the bar: focus = %v, field = %v; want its last field", m.focus, m.filters.field)
	}
}

// The help overlay lists every binding of the key map, and opens with ? outside the field and with
// f1 inside it.
func TestHelpOverlayIsGeneratedFromKeyMap(t *testing.T) {
	m, _ := press(sized(t, nil), "esc", "?")
	if m.overlay != overlayHelp {
		t.Fatalf("overlay = %v after ?, want the help", m.overlay)
	}
	m.height = 60 // tall enough to show every row
	out := m.View()
	for _, g := range keys.helpGroups() {
		if !strings.Contains(out, g.title) {
			t.Errorf("help lacks group %q", g.title)
		}
		for _, b := range g.bindings {
			h := b.Help()
			if !strings.Contains(out, h.Key) || !strings.Contains(out, h.Desc) {
				t.Errorf("help lacks binding %q %q", h.Key, h.Desc)
			}
		}
	}
	golden, _ := press(sized(t, nil), "esc", "?")
	assertGolden(t, "help", golden)

	if in, _ := press(sized(t, nil), "f1"); in.overlay != overlayHelp {
		t.Errorf("f1 inside the query field: overlay = %v, want the help", in.overlay)
	}
}

// The help closes with esc, ? and q; q there closes the help and does not ask to quit.
func TestHelpCloses(t *testing.T) {
	for _, closer := range []string{"esc", "?", "q"} {
		m, cmd := press(sized(t, nil), "esc", "?", closer)
		if m.overlay != overlayNone || quits(cmd) {
			t.Errorf("%s: overlay = %v, quits = %v; want the help closed", closer, m.overlay, quits(cmd))
		}
	}
}

// The help searches its entries and scrolls.
func TestHelpSearch(t *testing.T) {
	m, _ := press(sized(t, nil), "esc", "?", "/", "q", "u", "i", "t", "enter")
	out := m.View()
	if !strings.Contains(out, "quit now") || strings.Contains(out, "next focus") {
		t.Errorf("help search for quit keeps the wrong rows:\n%s", out)
	}
	m, _ = press(m, "esc")
	if m.overlay != overlayHelp || m.help.query != "" {
		t.Errorf("esc clears the search first: overlay = %v, query = %q", m.overlay, m.help.query)
	}
}

// US 1: q asks before it quits; enter and y confirm, esc and n cancel.
func TestQuitAsksForConfirmation(t *testing.T) {
	m, cmd := press(sized(t, nil), "esc", "q")
	if m.overlay != overlayConfirm || quits(cmd) {
		t.Fatalf("after q: overlay = %v, quits = %v; want the dialog and no exit", m.overlay, quits(cmd))
	}
	assertGolden(t, "quit", m)
	for _, no := range []string{"esc", "n"} {
		cancelled, cmd := press(m, no)
		if cancelled.overlay != overlayNone || quits(cmd) {
			t.Errorf("%s: overlay = %v, quits = %v; want the dialog closed, no exit", no, cancelled.overlay, quits(cmd))
		}
	}
	for _, yes := range []string{"enter", "y"} {
		if _, cmd := press(m, yes); !quits(cmd) {
			t.Errorf("%s did not quit", yes)
		}
	}
}

// ctrl+c quits at once: from the start screen and from an open dialog, without asking.
func TestCtrlCQuitsWithoutDialog(t *testing.T) {
	m, cmd := press(sized(t, nil), "ctrl+c")
	if !quits(cmd) || m.overlay != overlayNone {
		t.Errorf("start: quits = %v, overlay = %v", quits(cmd), m.overlay)
	}
	if _, cmd := press(sized(t, nil), "esc", "q", "ctrl+c"); !quits(cmd) {
		t.Error("ctrl+c inside the quit dialog did not quit")
	}
	if _, cmd := press(sized(t, nil), "esc", "?", "ctrl+c"); !quits(cmd) {
		t.Error("ctrl+c inside the help did not quit")
	}
}

// One overlay at a time: an open overlay swallows the keys of the others.
func TestOneOverlayAtATime(t *testing.T) {
	m, _ := press(sized(t, nil), "esc", "q", "?")
	if m.overlay != overlayConfirm {
		t.Errorf("? inside the dialog: overlay = %v, want the dialog to stay", m.overlay)
	}
	m, _ = press(sized(t, nil), "esc", "?", "n")
	if m.overlay != overlayHelp {
		t.Errorf("n inside the help: overlay = %v, want the help to stay", m.overlay)
	}
}

// A destructive dialog has the red border and title; the plain one does not.
func TestDestructiveConfirmIsRed(t *testing.T) {
	lipgloss.SetColorProfile(termenv.TrueColor)
	defer lipgloss.SetColorProfile(termenv.Ascii)
	red := "38;2;243;139;168" // mocha red #f38ba8

	m := sized(t, nil)
	plain := m.openConfirm(confirmDialog{title: "Move?", body: "ok?", yes: "move"})
	if strings.Contains(plain.confirmBox(), red) {
		t.Error("plain dialog carries the red colour")
	}
	danger := m.openConfirm(confirmDialog{title: "Clear?", body: "gone", yes: "clear", destructive: true})
	if !strings.Contains(danger.confirmBox(), red) {
		t.Error("destructive dialog lacks the red colour")
	}
}

// An invalid [tui] section shows as a sticky error toast naming the config path; esc dismisses it
// outside the field, and its footer hint appears with it.
func TestInvalidSettingsToast(t *testing.T) {
	path := writeConfig(t, "[tui]\ntheme = \"neon\"\n")
	_, err := LoadSettings()
	m := sized(t, err)
	if m.toast == nil || !m.toast.sticky || m.toast.kind != toastError {
		t.Fatalf("toast = %+v, want a sticky error toast", m.toast)
	}
	if !strings.Contains(m.toast.context, path) {
		t.Errorf("toast context does not name the config path %s: %q", path, m.toast.context)
	}
	assertGolden(t, "toast_settings", sized(t, errors.New(`/home/u/.config/okf/config.toml: [tui] theme "neon" is unknown (use latte, frappe, macchiato, mocha)`)))

	if in, _ := press(m, "esc"); in.toast == nil {
		t.Error("the first esc leaves the field and keeps the toast")
	}
	m, _ = press(m, "esc", "esc")
	if m.toast != nil {
		t.Error("esc outside the field did not dismiss the sticky toast")
	}
}

// A toast expires with its own generation only.
func TestToastExpiry(t *testing.T) {
	m := sized(t, nil)
	m, cmd := m.showToast(toastInfo, "done", "", false)
	if cmd == nil || m.toast == nil {
		t.Fatal("a plain toast sets a timer")
	}
	stale, _ := m.handleToastExpired(toastExpiredMsg{seq: m.toast.seq - 1})
	if stale.(model).toast == nil {
		t.Error("an expired older generation cleared the newer toast")
	}
	gone, _ := m.handleToastExpired(toastExpiredMsg{seq: m.toast.seq})
	if gone.(model).toast != nil {
		t.Error("the expiry of the current generation did not clear the toast")
	}
}

// A sticky toast that replaces a plain one in place (within the debounce window) inherits its
// generation, so the timer of the plain toast must not clear it.
func TestStickyToastOutlivesTheTimerItInherits(t *testing.T) {
	m := sized(t, nil)
	m, _ = m.showToast(toastInfo, "working", "", false)
	seq := m.toast.seq
	m, _ = m.showToast(toastError, "failed", "", true)
	if m.toast.seq != seq {
		t.Fatalf("seq = %d, want the debounced replacement to keep %d", m.toast.seq, seq)
	}
	next, _ := m.handleToastExpired(toastExpiredMsg{seq: seq})
	if next.(model).toast == nil {
		t.Error("the timer of the replaced plain toast cleared the sticky toast")
	}
}

func TestLoadSettings(t *testing.T) {
	t.Run("absent file gives defaults", func(t *testing.T) {
		t.Setenv("XDG_CONFIG_HOME", t.TempDir())
		got, err := LoadSettings()
		if err != nil || got != defaultSettings() {
			t.Errorf("got %+v, %v; want the defaults", got, err)
		}
	})
	t.Run("valid section", func(t *testing.T) {
		writeConfig(t, "root = \"/x\"\n[tui]\neditor = \"nvim\"\ntheme = \"Latte\"\naccent = \"#112233\"\n")
		got, err := LoadSettings()
		want := Settings{Editor: "nvim", Theme: "Latte", Accent: "#112233"}
		if err != nil || got != want {
			t.Errorf("got %+v, %v; want %+v", got, err, want)
		}
	})
	for name, content := range map[string]string{
		"unknown theme":     "[tui]\ntheme = \"neon\"\n",
		"bad accent":        "[tui]\naccent = \"red\"\n",
		"editor not text":   "[tui]\neditor = 3\n",
		"section not table": "tui = \"x\"\n",
		"broken toml":       "[tui\n",
	} {
		t.Run(name, func(t *testing.T) {
			path := writeConfig(t, content)
			got, err := LoadSettings()
			if err == nil || !strings.Contains(err.Error(), path) {
				t.Fatalf("err = %v, want an error naming %s", err, path)
			}
			if got != defaultSettings() {
				t.Errorf("got %+v, want the defaults next to the error", got)
			}
		})
	}
}

// The theme and the accent of the settings come into force.
func TestSettingsApply(t *testing.T) {
	defer defaultSettings().apply()
	Settings{Theme: "latte", Accent: "#112233"}.apply()
	if theme.Base != "#eff1f5" {
		t.Errorf("Base = %s, want latte base #eff1f5", theme.Base)
	}
	if got := theme.Accent.GetForeground(); got != lipgloss.Color("#112233") {
		t.Errorf("accent = %v, want #112233", got)
	}
}
