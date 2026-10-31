package tui

import (
	"fmt"
	"os"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/tui/theme"
)

// Settings are the `[tui]` keys of the okf user config (~/.config/okf/config.toml):
//
//	[tui]
//	editor = "nvim"       # editor command; empty: $VISUAL, then $EDITOR, then vi
//	theme  = "mocha"      # latte, frappe, macchiato or mocha
//	accent = "#cba6f7"    # #rrggbb; empty: the built-in accent
type Settings struct {
	Editor string
	Theme  string
	Accent string
}

// defaultSettings are the settings of a user config without a [tui] section.
func defaultSettings() Settings { return Settings{Theme: "mocha"} }

// LoadSettings reads the `[tui]` section of the user config. A missing file or section gives the
// defaults. An unreadable file, a section of the wrong type, a key of the wrong type or an
// unknown theme or accent gives the defaults and an error that names the config path; the TUI
// shows it as a sticky error toast, so the user sees it inside a popup, which a failed start would
// close at once.
func LoadSettings() (Settings, error) {
	path := catalogue.UserConfigPath()
	if info, err := os.Stat(path); err != nil || info.IsDir() {
		return defaultSettings(), nil
	}
	table, err := catalogue.ReadTOML(path)
	if err != nil {
		return defaultSettings(), err
	}
	raw, ok := table["tui"]
	if !ok {
		return defaultSettings(), nil
	}
	section, ok := raw.(map[string]any)
	if !ok {
		return defaultSettings(), fmt.Errorf("%s: [tui] must be a table", path)
	}
	s := defaultSettings()
	for _, k := range []struct {
		key  string
		into *string
	}{{"editor", &s.Editor}, {"theme", &s.Theme}, {"accent", &s.Accent}} {
		v, present := section[k.key]
		if !present {
			continue
		}
		str, isStr := v.(string)
		if !isStr {
			return defaultSettings(), fmt.Errorf("%s: [tui] %s must be a string", path, k.key)
		}
		*k.into = str
	}
	if s.Theme == "" {
		s.Theme = defaultSettings().Theme
	}
	if _, ok := theme.ByName(s.Theme); !ok {
		return defaultSettings(), fmt.Errorf("%s: [tui] theme %q is unknown (use %s)",
			path, s.Theme, strings.Join(theme.Names, ", "))
	}
	if s.Accent != "" && !theme.HexColor.MatchString(s.Accent) {
		return defaultSettings(), fmt.Errorf("%s: [tui] accent %q must be #rrggbb", path, s.Accent)
	}
	return s, nil
}

// apply puts the theme and the accent in force. The theme is process wide and must be in force
// before anything renders.
func (s Settings) apply() {
	p, _ := theme.ByName(s.Theme)
	theme.Apply(p)
	theme.SetAccent(s.Accent)
}
