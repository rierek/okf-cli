// The TUI state file: what the TUI remembers between sessions. It is not the user config
// (~/.config/okf/config.toml, which the user writes) and not part of any catalogue. Pattern from
// lif internal/tui/config/state.go at commit 2056715, adapted: JSON under $XDG_STATE_HOME.

package tui

import (
	"encoding/json"
	"errors"
	"io/fs"
	"os"
	"path/filepath"
	"slices"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
)

// maxRememberedRoots caps the list of roots used before, most recent first.
const maxRememberedRoots = 20

// tuiState is the content of the state file.
type tuiState struct {
	Roots []string `json:"roots"` // roots used in earlier sessions, most recent first
}

// statePath is $XDG_STATE_HOME/okf/tui.json; an unset or relative XDG_STATE_HOME means
// ~/.local/state.
func statePath() string {
	base := os.Getenv("XDG_STATE_HOME")
	if !filepath.IsAbs(base) {
		base = filepath.Join(catalogue.ExpandUser("~"), ".local", "state")
	}
	return filepath.Join(base, "okf", "tui.json")
}

// loadState reads the state file. A missing file is the empty state; an unreadable or corrupt one
// is an error that names the path.
func loadState() (tuiState, error) {
	path := statePath()
	data, err := os.ReadFile(path)
	if errors.Is(err, fs.ErrNotExist) {
		return tuiState{}, nil
	}
	if err != nil {
		return tuiState{}, err
	}
	var s tuiState
	if err := json.Unmarshal(data, &s); err != nil {
		return tuiState{}, errors.New(path + ": " + err.Error())
	}
	return s, nil
}

// rememberRoot puts root at the front of the roots used before.
func rememberRoot(root string) error {
	s, err := loadState()
	if err != nil {
		return err
	}
	s.Roots = slices.DeleteFunc(s.Roots, func(r string) bool { return r == root })
	s.Roots = append([]string{root}, s.Roots...)
	if len(s.Roots) > maxRememberedRoots {
		s.Roots = s.Roots[:maxRememberedRoots]
	}
	path := statePath()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	data, err := json.MarshalIndent(s, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, data, 0o644)
}
