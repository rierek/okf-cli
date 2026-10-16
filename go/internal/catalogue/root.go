package catalogue

import (
	"errors"
	"fmt"
	"os"
	"os/user"
	"path/filepath"
	"strings"
	"syscall"

	"github.com/BurntSushi/toml"

	"nas/volume1/data/git/okf-tools/go/internal/okferr"
	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

// RegistryFormats are the values of the `registry_format` configuration key.
var RegistryFormats = []string{"table", "block"}

// ExpandUser is Python os.path.expanduser: a leading `~` or `~/` becomes the home directory
// ($HOME, else the account's), `~name` the home of that account; anything else is unchanged.
func ExpandUser(path string) string {
	if !strings.HasPrefix(path, "~") {
		return path
	}
	name, rest, _ := strings.Cut(path[1:], "/")
	home := ""
	if name == "" {
		home = os.Getenv("HOME")
		if home == "" {
			if u, err := user.Current(); err == nil {
				home = u.HomeDir
			}
		}
	} else if u, err := user.Lookup(name); err == nil {
		home = u.HomeDir
	}
	if home == "" {
		return path
	}
	home = strings.TrimRight(home, "/")
	if rest == "" && !strings.Contains(path, "/") {
		return home
	}
	return home + "/" + rest
}

// Getwd is Python os.getcwd: the physical working directory (Go's os.Getwd would answer with the
// logical $PWD when that names the same directory).
func Getwd() (string, error) { return syscall.Getwd() }

// Abspath is Python os.path.abspath: the path joined to the working directory and normalised
// lexically.
func Abspath(path string) (string, error) {
	if filepath.IsAbs(path) {
		return filepath.Clean(path), nil
	}
	wd, err := Getwd()
	if err != nil {
		return "", err
	}
	return filepath.Join(wd, path), nil
}

// UserConfigPath is $XDG_CONFIG_HOME/okf/config.toml; an unset or relative XDG_CONFIG_HOME means
// ~/.config.
func UserConfigPath() string {
	base := os.Getenv("XDG_CONFIG_HOME")
	if !filepath.IsAbs(base) {
		base = filepath.Join(ExpandUser("~"), ".config")
	}
	return filepath.Join(base, "okf", "config.toml")
}

// ConfiguredRoot is `root` of the user config: the catalogue used when no marker sits above the
// working directory. "" when the file or the key is absent.
func ConfiguredRoot() (string, error) {
	p := UserConfigPath()
	if !isFile(p) {
		return "", nil
	}
	table, err := ReadTOML(p)
	if err != nil {
		return "", err
	}
	raw, ok := table["root"]
	if !ok {
		return "", nil
	}
	root, isStr := raw.(string)
	if !isStr || !filepath.IsAbs(ExpandUser(root)) {
		return "", okferr.Newf(okferr.InvalidInput, "ERROR: %s: root must be an absolute path or start with ~/", p)
	}
	root = ExpandUser(root)
	if !isDir(root) {
		return "", okferr.Newf(okferr.NotFound, "ERROR: root %s from %s does not exist", root, p)
	}
	return root, nil
}

// HasMarker reports whether dir carries a catalogue marker: `.okf.toml`, or SPEC.md together with
// TYPES.md. An explicit --root without one gets the dispatch note.
func HasMarker(dir string) bool {
	return isFile(filepath.Join(dir, ".okf.toml")) ||
		(isFile(filepath.Join(dir, "SPEC.md")) && isFile(filepath.Join(dir, "TYPES.md")))
}

// CatalogueRoot resolves the catalogue root (Python catalogue_root).
//
// useGlobal (--global) takes the `root` of the user config whatever sits above the working
// directory: none configured is not_found, together with an explicit root invalid_input. An
// explicit --root otherwise wins (`~` expanded, then made absolute, even when it does not exist;
// the caller validates that). Absent --root, the working directory is walked upward for a
// catalogue marker in the candidate directory or in its `docs/` child (the workspace and repo
// layout puts the catalogue in `<hull>/docs`); with no marker anywhere the `root` of the user
// config is used. The result is "" when nothing is found.
func CatalogueRoot(explicit string, useGlobal bool) (string, error) {
	if useGlobal {
		if explicit != "" {
			return "", okferr.New(okferr.InvalidInput, "ERROR: --global and --root exclude each other")
		}
		root, err := ConfiguredRoot()
		if err != nil {
			return "", err
		}
		if root == "" {
			return "", okferr.Newf(okferr.NotFound, "ERROR: --global needs a `root` in %s", UserConfigPath())
		}
		return root, nil
	}
	if explicit != "" {
		return Abspath(ExpandUser(explicit))
	}
	d, err := Getwd()
	if err != nil {
		return "", err
	}
	for {
		if HasMarker(d) {
			return d, nil
		}
		if docs := filepath.Join(d, "docs"); HasMarker(docs) {
			return docs, nil
		}
		parent := filepath.Dir(d)
		if parent == d {
			return ConfiguredRoot()
		}
		d = parent
	}
}

// ReadTOML parses a TOML file into its table. Invalid TOML is an invalid_input error naming the
// file and the reason (the wording and positions are the Go parser's).
func ReadTOML(path string) (map[string]any, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var table map[string]any
	if _, err := toml.Decode(string(b), &table); err != nil {
		reason := err.Error()
		var perr toml.ParseError
		if errors.As(err, &perr) {
			reason = fmt.Sprintf("%s (at line %d, column %d)", perr.Message, perr.Position.Line, perr.Position.Col)
		}
		return nil, okferr.Newf(okferr.InvalidInput, "ERROR: %s is not valid TOML: %s", path, reason)
	}
	if table == nil {
		table = map[string]any{}
	}
	return table, nil
}

// LoadConfig is Python load_okf_config: the parsed table of <root>/.okf.toml, empty when the file
// is absent. A leading `~` of `kc_root` and `types_source` is expanded; `registry_format` must be
// "table" or "block". Values are as the TOML decoder yields them (string, int64, float64, bool,
// time.Time, []any, map[string]any).
func LoadConfig(root string) (map[string]any, error) {
	p := filepath.Join(root, ".okf.toml")
	if !isFile(p) {
		return map[string]any{}, nil
	}
	data, err := ReadTOML(p)
	if err != nil {
		return nil, err
	}
	for _, k := range []string{"kc_root", "types_source"} {
		if s, ok := data[k].(string); ok {
			data[k] = ExpandUser(s)
		}
	}
	if v, ok := data["registry_format"]; ok {
		if s, isStr := v.(string); !isStr || (s != RegistryFormats[0] && s != RegistryFormats[1]) {
			return nil, okferr.Newf(okferr.InvalidInput,
				`ERROR: %s: registry_format must be "table" or "block", got %s`, p, pytext.Repr(v))
		}
	}
	return data, nil
}

// ConfigStrings returns the list of strings under key in a config table, or nil when the key is
// absent or not a list; non-string items are skipped.
func ConfigStrings(config map[string]any, key string) []string {
	list, _ := config[key].([]any)
	var out []string
	for _, item := range list {
		if s, ok := item.(string); ok {
			out = append(out, s)
		}
	}
	return out
}

func isFile(path string) bool {
	info, err := os.Stat(path)
	return err == nil && info.Mode().IsRegular()
}

func isDir(path string) bool {
	info, err := os.Stat(path)
	return err == nil && info.IsDir()
}
