// Package info is the `info` command: it prints the catalogue's schema docs (TYPES.md and
// PROPERTIES.md) so an agent can load the type vocabulary and the property spec in one call.
package info

import (
	"fmt"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/cli"
	"nas/volume1/data/git/okf-tools/go/internal/envelope"
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
		fmt.Println("------")
		if texts[i] != nil {
			fmt.Println(*texts[i])
		} else {
			fmt.Printf("(missing: %s)\n", name)
		}
	}
	fmt.Println("------")
	return nil, nil
}
