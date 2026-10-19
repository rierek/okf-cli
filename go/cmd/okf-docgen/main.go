// Command okf-docgen writes the command reference of the docs site from the okf command tree: one
// Markdown page per visible command and per verb, plus _command-tree.md. Usage: okf-docgen <output-dir>.
//
// Hand-written files in the output directory stay. A supplement _supplements/_okf_<name>.md (verb:
// _okf_<name>_<verb>.md) is merged into its page before the usage block.
package main

import (
	"fmt"
	"io"
	"os"
	"path/filepath"
	"slices"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/cli"
	"nas/volume1/data/git/okf-tools/go/internal/commands"
)

// groups is the order of the purposes in okf --help (cli.groupOrder).
var groups = []string{"navigation", "search", "tags", "maintenance"}

const treeFile = "_command-tree.md"

func main() {
	if len(os.Args) != 2 {
		fmt.Fprintln(os.Stderr, "usage: okf-docgen <output-dir>")
		os.Exit(2)
	}
	if err := generate(os.Args[1]); err != nil {
		fmt.Fprintln(os.Stderr, "okf-docgen:", err)
		os.Exit(1)
	}
}

// generate replaces every okf*.md page and the tree file in out.
func generate(out string) error {
	// A fixed width makes the wrapping of the help text the same on every machine.
	if err := os.Setenv("COLUMNS", "100"); err != nil {
		return err
	}
	app := cli.NewApp()
	commands.Register(app)
	if err := os.MkdirAll(out, 0o755); err != nil {
		return err
	}
	stale, err := filepath.Glob(filepath.Join(out, "okf*.md"))
	if err != nil {
		return err
	}
	for _, p := range append(stale, filepath.Join(out, treeFile)) {
		if err := os.Remove(p); err != nil && !os.IsNotExist(err) {
			return err
		}
	}
	var visible []cli.Entry
	for _, e := range app.Directory() {
		if e.Hidden {
			continue
		}
		if !slices.Contains(groups, e.Group) {
			return fmt.Errorf("command %q has group %q, which okf-docgen does not know", e.Name, e.Group)
		}
		visible = append(visible, e)
	}
	for _, e := range visible {
		if err := writePage(out, app, e.Name, "", e.Summary); err != nil {
			return err
		}
		for _, v := range app.Verbs(e.Name) {
			if err := writePage(out, app, e.Name, v.Name, v.Help); err != nil {
				return err
			}
		}
	}
	return writeFile(filepath.Join(out, treeFile), func(w io.Writer) error { return writeTree(w, app, visible) })
}

// writePage writes okf-<command>[-<verb>].md: supplement, then the usage block with the help text.
func writePage(out string, app *cli.App, command, verb, summary string) error {
	words := []string{command}
	if verb != "" {
		words = append(words, verb)
	}
	supplement, err := os.ReadFile(filepath.Join(out, "_supplements", "_okf_"+strings.Join(words, "_")+".md"))
	if err != nil && !os.IsNotExist(err) {
		return err
	}
	return writeFile(filepath.Join(out, pageName(words)+".md"), func(w io.Writer) error {
		fmt.Fprintf(w, "---\ntitle: %s\ndescription: %s\n---\n\n", yamlQuote("okf "+strings.Join(words, " ")), yamlQuote(summary))
		if text := strings.TrimSpace(string(supplement)); text != "" {
			fmt.Fprintf(w, "%s\n\n", text)
		}
		// The help is argparse layout: a fenced block keeps its columns and its "# ..." lines out of the headings.
		_, err := fmt.Fprintf(w, "## Usage\n\n```text\n%s\n```\n", strings.TrimRight(app.CommandHelp(words...), "\n"))
		return err
	})
}

// writeTree writes one section per group, in the order of okf --help, with the verbs nested under their command.
func writeTree(w io.Writer, app *cli.App, visible []cli.Entry) error {
	for _, g := range groups {
		fmt.Fprintf(w, "### %s\n\n", g)
		for _, e := range visible {
			if e.Group != g {
				continue
			}
			fmt.Fprintf(w, "- [okf %s](./%s/): %s\n", e.Name, pageName([]string{e.Name}), e.Summary)
			for _, v := range app.Verbs(e.Name) {
				fmt.Fprintf(w, "  - [okf %s %s](./%s/): %s\n", e.Name, v.Name, pageName([]string{e.Name, v.Name}), v.Help)
			}
		}
		if _, err := fmt.Fprintln(w); err != nil {
			return err
		}
	}
	return nil
}

func pageName(words []string) string { return "okf-" + strings.Join(words, "-") }

// yamlQuote returns s as a double-quoted YAML scalar.
func yamlQuote(s string) string {
	return `"` + strings.NewReplacer(`\`, `\\`, `"`, `\"`).Replace(s) + `"`
}

func writeFile(path string, fill func(io.Writer) error) (err error) {
	f, err := os.Create(path)
	if err != nil {
		return err
	}
	defer func() {
		if cerr := f.Close(); err == nil {
			err = cerr
		}
	}()
	return fill(f)
}
