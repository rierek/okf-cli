// Copied from lif internal/tui/editor.go at commit 2056715, adapted: editorBinary, prepareEditor,
// readEditorResult and editInEditor, with the setting passed in instead of a package variable, a
// caller identifier on the text result and a second use that opens a file in place.

package tui

import (
	"os"
	"os/exec"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
)

// editorCommand is the editor command to launch: the TUI setting `editor`, then $VISUAL, then
// $EDITOR, then `vi`. A value may carry arguments (`code --wait`); it splits on whitespace.
func editorCommand(setting string) []string {
	if ed := strings.TrimSpace(setting); ed != "" {
		return strings.Fields(ed)
	}
	for _, name := range []string{"VISUAL", "EDITOR"} {
		if ed := strings.TrimSpace(os.Getenv(name)); ed != "" {
			return strings.Fields(ed)
		}
	}
	return []string{"vi"}
}

// editorExec is the editor of the setting, opened on path.
func editorExec(setting, path string) *exec.Cmd {
	bin := editorCommand(setting)
	return exec.Command(bin[0], append(bin[1:], path)...)
}

// fileEditedMsg reports that the editor opened by openInEditor on path has exited; err is its
// failure, nil for a clean exit.
type fileEditedMsg struct {
	path string
	err  error
}

// openInEditor suspends the program into the editor on path. The program resumes with a
// fileEditedMsg.
func (m model) openInEditor(path string) tea.Cmd {
	return tea.ExecProcess(editorExec(m.settings.Editor, path), func(err error) tea.Msg {
		return fileEditedMsg{path: path, err: err}
	})
}

// textEditedMsg is the answer of editText: the edited text, or err when the editor could not run,
// exited with an error or its temp file could not be read. caller is the identifier editText was
// given, so the one handler of the asker can tell its answer from another asker's.
type textEditedMsg struct {
	caller string
	text   string
	err    error
}

// editText suspends the program into the editor on a temp file holding initial. The temp file is
// removed when the editor exits. The program resumes with a textEditedMsg carrying caller.
func (m model) editText(caller, initial string) tea.Cmd {
	fail := func(err error) tea.Cmd {
		return func() tea.Msg { return textEditedMsg{caller: caller, err: err} }
	}
	f, err := os.CreateTemp("", "okf-tui-*.md")
	if err != nil {
		return fail(err)
	}
	path := f.Name()
	_, err = f.WriteString(initial)
	if cerr := f.Close(); err == nil {
		err = cerr
	}
	if err != nil {
		os.Remove(path)
		return fail(err)
	}
	return tea.ExecProcess(editorExec(m.settings.Editor, path), func(runErr error) tea.Msg {
		defer os.Remove(path)
		if runErr != nil {
			return textEditedMsg{caller: caller, err: runErr}
		}
		data, err := os.ReadFile(path)
		return textEditedMsg{caller: caller, text: string(data), err: err}
	})
}
