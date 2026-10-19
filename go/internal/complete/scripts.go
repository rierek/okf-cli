package complete

import (
	_ "embed"
	"fmt"
)

// The shell code that makes a shell call `okf` with the completion environment.
//
// okf.bash and okf.fish are argcomplete 3.7.2 shellcode(["okf"], shell=...) as the Python
// install writes it (pin: packaging/homebrew/okf-cli.rb). okf.zsh is a copy of cli/_okf:
// go:embed cannot reach outside the module. `just go-completion-scripts` rewrites the three
// files, `just go-completion-scripts --check` compares them with their sources.
var (
	//go:embed okf.zsh
	zshScript string
	//go:embed okf.bash
	bashScript string
	//go:embed okf.fish
	fishScript string
)

// Script is the completion code of a shell, "zsh", "bash" or "fish", without any managed header.
func Script(shell string) (string, error) {
	switch shell {
	case "zsh":
		return zshScript, nil
	case "bash":
		return bashScript, nil
	case "fish":
		return fishScript, nil
	}
	return "", fmt.Errorf("complete: no completion script for shell %q", shell)
}
