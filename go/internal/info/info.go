// Package info is the `info` command: it prints the catalogue's schema docs (TYPES.md and
// PROPERTIES.md) so an agent can load the type vocabulary and the property spec in one call.
package info

import (
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/cli"
	"nas/volume1/data/git/okf-tools/go/internal/envelope"
	"nas/volume1/data/git/okf-tools/go/internal/pytext"
	"nas/volume1/data/git/okf-tools/go/internal/stdio"
)

// Register attaches the `info` command.
func Register(app *cli.App) {
	app.Attach("info", cli.Spec{Args: []cli.Arg{cli.JSON()}, Handler: run})
}

// run is Python cmd_info: the two files in order, a missing file reads as null in the envelope and
// as `(missing: NAME)` in text.
func run(root string, a *cli.Args) (any, error) {
	names := []string{"TYPES.md", "PROPERTIES.md"}
	texts := make([]*string, len(names))
	for i, name := range names {
		path := catalogue.Join(root, name)
		if !catalogue.RealFS.IsFile(path) {
			continue
		}
		text, err := catalogue.ReadFile(path)
		if err != nil {
			return nil, err
		}
		texts[i] = &text
	}
	if a.JSON {
		files := make([]envelope.Obj, len(names))
		for i, name := range names {
			var text any
			if texts[i] != nil {
				text = *texts[i]
			}
			files[i] = envelope.O("name", name, "text", text)
		}
		return envelope.O("files", files), nil
	}
	for i, name := range names {
		stdio.Println("------")
		if texts[i] != nil {
			stdio.Println(*texts[i])
		} else {
			stdio.Printf("(missing: %s)\n", name)
		}
	}
	stdio.Println("------")
	return nil, nil
}

// TypeDef is one type of the catalogue's TYPES.md: its name and description.
type TypeDef struct{ Name, Description string }

// Types lists the types of the catalogue's TYPES.md in file order, read the way `info` reads the
// file. ok is false when TYPES.md is missing. The description of a block entry joins its lines.
func Types(root string) (defs []TypeDef, ok bool, err error) {
	path := catalogue.Join(root, "TYPES.md")
	if !catalogue.RealFS.IsFile(path) {
		return nil, false, nil
	}
	text, err := catalogue.ReadFile(path)
	if err != nil {
		return nil, true, err
	}
	lines := pytext.SplitLines(text, true)
	for _, e := range catalogue.ScanRegistry(lines).Entries {
		_, desc := e.Fields(lines)
		defs = append(defs, TypeDef{e.Value, strings.Join(desc, " ")})
	}
	return defs, true, nil
}
