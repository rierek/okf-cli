// Copied from lif internal/ui/theme.go at commit 2056715, adapted: only the tones the TUI uses,
// no CSS generation.

package theme

import "strings"

// Palette is one Catppuccin flavour: a lookup from tone name to hex value.
type Palette struct {
	Name   string
	Colors map[string]string
}

// Hex returns the hex value for a tone, or "" if this flavour does not define it.
func (p Palette) Hex(tone string) string { return p.Colors[tone] }

var palettes = map[string]Palette{
	"latte": {Name: "latte", Colors: map[string]string{
		"rosewater": "#dc8a78", "flamingo": "#dd7878", "pink": "#ea76cb",
		"mauve": "#8839ef", "red": "#d20f39", "maroon": "#e64553",
		"peach": "#fe640b", "yellow": "#df8e1d", "green": "#40a02b",
		"teal": "#179299", "sky": "#04a5e5", "sapphire": "#209fb5",
		"blue": "#1e66f5", "lavender": "#7287fd", "text": "#4c4f69",
		"subtext0": "#6c6f85", "overlay1": "#8c8fa1", "surface1": "#bcc0cc",
		"base": "#eff1f5",
	}},
	"frappe": {Name: "frappe", Colors: map[string]string{
		"rosewater": "#f2d5cf", "flamingo": "#eebebe", "pink": "#f4b8e4",
		"mauve": "#ca9ee6", "red": "#e78284", "maroon": "#ea999c",
		"peach": "#ef9f76", "yellow": "#e5c890", "green": "#a6d189",
		"teal": "#81c8be", "sky": "#99d1db", "sapphire": "#85c1dc",
		"blue": "#8caaee", "lavender": "#babbf1", "text": "#c6d0f5",
		"subtext0": "#a5adce", "overlay1": "#838ba7", "surface1": "#51576d",
		"base": "#303446",
	}},
	"macchiato": {Name: "macchiato", Colors: map[string]string{
		"rosewater": "#f4dbd6", "flamingo": "#f0c6c6", "pink": "#f5bde6",
		"mauve": "#c6a0f6", "red": "#ed8796", "maroon": "#ee99a0",
		"peach": "#f5a97f", "yellow": "#eed49f", "green": "#a6da95",
		"teal": "#8bd5ca", "sky": "#91d7e3", "sapphire": "#7dc4e4",
		"blue": "#8aadf4", "lavender": "#b7bdf8", "text": "#cad3f5",
		"subtext0": "#a5adcb", "overlay1": "#8087a2", "surface1": "#494d64",
		"base": "#24273a",
	}},
	"mocha": {Name: "mocha", Colors: map[string]string{
		"rosewater": "#f5e0dc", "flamingo": "#f2cdcd", "pink": "#f5c2e7",
		"mauve": "#cba6f7", "red": "#f38ba8", "maroon": "#eba0ac",
		"peach": "#fab387", "yellow": "#f9e2af", "green": "#a6e3a1",
		"teal": "#94e2d5", "sky": "#89dceb", "sapphire": "#74c7ec",
		"blue": "#89b4fa", "lavender": "#b4befe", "text": "#cdd6f4",
		"subtext0": "#a6adc8", "overlay1": "#7f849c", "surface1": "#45475a",
		"base": "#1e1e2e",
	}},
}

// Names are the bundled flavours, as `theme` in [tui] names them.
var Names = []string{"latte", "frappe", "macchiato", "mocha"}

// ByName looks up a flavour, case-insensitively.
func ByName(name string) (Palette, bool) {
	p, ok := palettes[strings.ToLower(name)]
	return p, ok
}
