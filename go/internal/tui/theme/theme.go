// Copied from lif internal/tui/theme/theme.go at commit 2056715, adapted: the palette lives in
// this package, no status/type/priority colours.

// Package theme holds the Catppuccin palette and the styles derived from it.
package theme

import (
	"regexp"

	"github.com/charmbracelet/lipgloss"
)

// Palette colours. Apply fills them from a flavour; init starts with mocha so a process that never
// calls Apply still has colours.
var (
	Rosewater lipgloss.Color
	Flamingo  lipgloss.Color
	Pink      lipgloss.Color
	Mauve     lipgloss.Color // accent
	Red       lipgloss.Color
	Maroon    lipgloss.Color
	Peach     lipgloss.Color
	Yellow    lipgloss.Color
	Green     lipgloss.Color
	Teal      lipgloss.Color
	Sky       lipgloss.Color
	Sapphire  lipgloss.Color
	Blue      lipgloss.Color
	Lavender  lipgloss.Color

	Text    lipgloss.Color
	Subtext lipgloss.Color
	Overlay lipgloss.Color // input and field border
	Surface lipgloss.Color
	Base    lipgloss.Color // app and body background
)

// Hint is the colour of hints, labels, shortcuts and placeholders. It is fixed and does not follow
// the flavour.
const Hint = lipgloss.Color("#7c7c7c")

// Styles built from the palette above; rebuildStyles refreshes them.
var (
	Header = lipgloss.NewStyle()
	Accent = lipgloss.NewStyle()
	// BindingKey and BindingDesc render the key and the description of a key hint.
	BindingKey  = lipgloss.NewStyle()
	BindingDesc = lipgloss.NewStyle()
	Dim         = lipgloss.NewStyle()
	// Muted is the style of hints, sub-labels and placeholders.
	Muted = lipgloss.NewStyle()
	// Chevron is the structural marker of the header.
	Chevron = lipgloss.NewStyle()
)

func init() { Apply(palettes["mocha"]) }

// Apply puts the palette p in force and rebuilds every style derived from it. A user accent
// (SetAccent) does not survive: call SetAccent afterwards.
func Apply(p Palette) {
	for c, tone := range map[*lipgloss.Color]string{
		&Rosewater: "rosewater", &Flamingo: "flamingo", &Pink: "pink", &Mauve: "mauve",
		&Red: "red", &Maroon: "maroon", &Peach: "peach", &Yellow: "yellow",
		&Green: "green", &Teal: "teal", &Sky: "sky", &Sapphire: "sapphire",
		&Blue: "blue", &Lavender: "lavender", &Text: "text", &Subtext: "subtext0",
		&Overlay: "overlay1", &Surface: "surface1", &Base: "base",
	} {
		*c = lipgloss.Color(p.Hex(tone))
	}
	rebuildStyles()
	lipgloss.SetHasDarkBackground(p.Name != "latte")
}

func rebuildStyles() {
	Header = lipgloss.NewStyle().Bold(true).Foreground(Mauve)
	Accent = lipgloss.NewStyle().Foreground(Lavender)
	BindingKey = lipgloss.NewStyle().Foreground(Teal)
	BindingDesc = lipgloss.NewStyle().Foreground(Subtext)
	Dim = lipgloss.NewStyle().Foreground(Overlay)
	Muted = lipgloss.NewStyle().Foreground(Hint)
	Chevron = lipgloss.NewStyle().Foreground(Peach)
}

// HexColor matches a #rrggbb accent.
var HexColor = regexp.MustCompile(`^#[0-9a-fA-F]{6}$`)

// SetAccent overrides the accent style (cursor, header) with a user colour. Anything but #rrggbb
// is a no-op: the built-in accent stays.
func SetAccent(hex string) {
	if !HexColor.MatchString(hex) {
		return
	}
	c := lipgloss.Color(hex)
	Accent = lipgloss.NewStyle().Foreground(c)
	Header = lipgloss.NewStyle().Bold(true).Foreground(c)
}
