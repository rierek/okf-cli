package tui

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"slices"
	"strings"
	"time"

	keybind "github.com/charmbracelet/bubbles/key"
	tea "github.com/charmbracelet/bubbletea"

	"nas/volume1/data/git/okf-tools/go/internal/tui/clip"
	"nas/volume1/data/git/okf-tools/go/internal/tui/theme"
)

// The hand-off (SPEC D13, D14, US 6): ctrl+s sends the export of the buffer to an agent pane, y
// copies it. Both keys work on the search screen and the buffer screen, outside an overlay; the
// text box captures ctrl+s first (it saves there). ctrl+s also works inside the query field,
// where it types nothing. An empty buffer sends and copies nothing.
//
// herdr is called as a subprocess, off the UI loop, with the export as one argv element (no
// shell). Its CLI answers `{"id":…,"result":…}` or `{"id":…,"error":{"code","message"}}`, the
// error with exit status 0.

// copyToClipboard writes the text to the clipboard; tests replace it.
var copyToClipboard = clip.Copy

// noAgentTitle is the toast when the export went to the clipboard for lack of an agent.
const noAgentTitle = "no agent found – copied to clipboard"

// herdrAgent is the part of a `herdr agent list` entry and of `herdr pane get`'s pane the
// hand-off reads. A pane that runs no agent has an empty Agent.
type herdrAgent struct {
	Agent     string `json:"agent"`
	Status    string `json:"agent_status"`
	Pane      string `json:"pane_id"`
	Workspace string `json:"workspace_id"`
	Cwd       string `json:"cwd"`
	Title     string `json:"terminal_title_stripped"`
}

// blocked agents wait at an approval or question dialog: text sent there could answer it.
func (a herdrAgent) blocked() bool { return a.Status == "blocked" }

// agentPicker is the state of overlayAgents.
type agentPicker struct {
	agents []herdrAgent // current workspace first
	cursor int
}

// handoffPickMsg opens the picker: the pane under the popup runs no (sendable) agent.
type handoffPickMsg struct{ agents []herdrAgent }

// handoffSentMsg answers a send: the text is in the target pane and the target is focused.
type handoffSentMsg struct{ err error }

// copiedMsg answers a clipboard copy; title is the toast of a success.
type copiedMsg struct {
	title string
	err   error
}

// herdrCall runs `herdr args...` and returns the result of its JSON answer. A failed process and
// an error answer are errors; an answer that is not JSON counts as success when the exit status
// is 0.
func herdrCall(args ...string) (json.RawMessage, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	out, err := exec.CommandContext(ctx, "herdr", args...).Output()
	if err != nil {
		var ee *exec.ExitError
		if errors.As(err, &ee) && len(ee.Stderr) > 0 {
			err = fmt.Errorf("%w: %s", err, strings.TrimSpace(string(ee.Stderr)))
		}
		return nil, fmt.Errorf("herdr %s: %w", strings.Join(args[:min(len(args), 2)], " "), err)
	}
	var answer struct {
		Result json.RawMessage `json:"result"`
		Error  *struct {
			Code    string `json:"code"`
			Message string `json:"message"`
		} `json:"error"`
	}
	if json.Unmarshal(out, &answer) == nil && answer.Error != nil {
		return nil, fmt.Errorf("herdr %s: %s", strings.Join(args[:min(len(args), 2)], " "), answer.Error.Message)
	}
	return answer.Result, nil
}

// sendToPane writes text into the pane without Enter and focuses it. The trailing newline of the
// export stays out: it could submit the text.
func sendToPane(pane, text string) tea.Msg {
	if _, err := herdrCall("pane", "send-text", pane, strings.TrimRight(text, "\n")); err != nil {
		return handoffSentMsg{err}
	}
	_, err := herdrCall("agent", "focus", pane)
	return handoffSentMsg{err}
}

// copyExport copies text to the clipboard.
func copyExport(text, title string) tea.Msg {
	return copiedMsg{title: title, err: copyToClipboard(text)}
}

// resolveHandoff decides the target of ctrl+s (SPEC D14): the pane under the popup when it runs a
// sendable agent, else the picker of the agents herdr lists, else the clipboard. The pane under
// the popup is HERDR_ACTIVE_PANE_ID; a TUI in a plain herdr pane has only HERDR_PANE_ID, its own
// pane, which runs no agent. Without either variable the TUI runs outside herdr.
func resolveHandoff(text string) tea.Msg {
	pane := os.Getenv("HERDR_ACTIVE_PANE_ID")
	if pane == "" {
		pane = os.Getenv("HERDR_PANE_ID")
	}
	if pane == "" {
		return copyExport(text, noAgentTitle)
	}
	var workspace string
	if res, err := herdrCall("pane", "get", pane); err == nil {
		var got struct {
			Pane herdrAgent `json:"pane"`
		}
		if json.Unmarshal(res, &got) == nil {
			workspace = got.Pane.Workspace
			if got.Pane.Agent != "" && !got.Pane.blocked() {
				return sendToPane(pane, text)
			}
		}
	}
	res, err := herdrCall("agent", "list")
	var list struct {
		Agents []herdrAgent `json:"agents"`
	}
	if err != nil || json.Unmarshal(res, &list) != nil || len(list.Agents) == 0 {
		return copyExport(text, noAgentTitle)
	}
	slices.SortStableFunc(list.Agents, func(a, b herdrAgent) int {
		return boolRank(b.Workspace == workspace) - boolRank(a.Workspace == workspace)
	})
	return handoffPickMsg{list.Agents}
}

func boolRank(b bool) int {
	if b {
		return 1
	}
	return 0
}

// send is ctrl+s: it resolves the target off the UI loop. An empty buffer only shows a toast; a
// second press while the first is resolving is ignored.
func (m model) send() (tea.Model, tea.Cmd) {
	if len(m.buf.entries) == 0 {
		return m.showToast(toastWarn, "Buffer is empty", "Nothing to send.", false)
	}
	if m.handoffBusy {
		return m, nil
	}
	m.handoffBusy = true
	text := exportText(m.buf.Entries())
	return m, func() tea.Msg { return resolveHandoff(text) }
}

// copyBuffer is y: it copies the export to the clipboard and stays open.
func (m model) copyBuffer() (tea.Model, tea.Cmd) {
	n := len(m.buf.entries)
	if n == 0 {
		return m.showToast(toastWarn, "Buffer is empty", "Nothing to copy.", false)
	}
	text := exportText(m.buf.Entries())
	title := fmt.Sprintf("copied %d %s to clipboard", n, plural(n, "entry", "entries"))
	return m, func() tea.Msg { return copyExport(text, title) }
}

func plural(n int, one, many string) string {
	if n == 1 {
		return one
	}
	return many
}

// handleHandoffPick opens the picker with the cursor on the first agent that is not blocked.
func (m model) handleHandoffPick(msg handoffPickMsg) (tea.Model, tea.Cmd) {
	m.handoffBusy = false
	cursor := slices.IndexFunc(msg.agents, func(a herdrAgent) bool { return !a.blocked() })
	m.agents = agentPicker{agents: msg.agents, cursor: max(cursor, 0)}
	m.overlay = overlayAgents
	return m, nil
}

// handleHandoffSent quits after a send; a failure shows a toast and the TUI stays open.
func (m model) handleHandoffSent(msg handoffSentMsg) (tea.Model, tea.Cmd) {
	m.handoffBusy = false
	if msg.err != nil {
		return m.showToast(toastError, "Hand-off failed", msg.err.Error(), true)
	}
	return m, tea.Quit
}

// handleCopied shows the toast of a finished copy.
func (m model) handleCopied(msg copiedMsg) (tea.Model, tea.Cmd) {
	m.handoffBusy = false
	if msg.err != nil {
		return m.showToast(toastError, "Copy to clipboard failed", msg.err.Error(), true)
	}
	return m.showToast(toastInfo, msg.title, "", false)
}

// keyAgents handles input while the agent picker is open (full capture). enter on a blocked
// agent sends nothing.
func (m model) keyAgents(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	p := m.agents
	switch {
	case keybind.Matches(msg, keys.Back):
		m.overlay = overlayNone
	case keybind.Matches(msg, keys.Up):
		m.agents.cursor = max(p.cursor-1, 0)
	case keybind.Matches(msg, keys.Down):
		m.agents.cursor = min(p.cursor+1, len(p.agents)-1)
	case keybind.Matches(msg, keys.Run):
		a := p.agents[p.cursor]
		if a.blocked() {
			return m.showToast(toastWarn, "Agent is blocked", "It waits at a dialog: pick another agent.", false)
		}
		m.overlay = overlayNone
		m.handoffBusy = true
		text := exportText(m.buf.Entries())
		return m, func() tea.Msg { return sendToPane(a.Pane, text) }
	}
	return m, nil
}

// agentsBox renders the picker: agent, status, title and directory per row; blocked agents grey.
func (m model) agentsBox() string {
	p := m.agents
	w := clampModalWidth(100, m.width)
	room := w - 4 // padding and the cursor column
	rows := make([]string, len(p.agents))
	for i, a := range p.agents {
		line := a.Agent + "  " + a.Status + "  " + a.Title + "  " + tildePath(a.Cwd)
		cursor, text := "  ", truncate(line, room)
		if i == p.cursor {
			cursor = theme.Accent.Render("▸ ")
		}
		switch {
		case a.blocked():
			text = theme.Dim.Render(text)
		case i == p.cursor:
			text = theme.Header.Render(text)
		}
		rows[i] = cursor + text
	}
	visible := max(min(len(rows), m.height-8), 1)
	hint := theme.Muted.Render("↑/↓ choose · enter send · esc cancel")
	body := hint + "\n" + strings.Join(windowAround(rows, visible, p.cursor), "\n")
	return modalPanel("Send to agent", body, "", w, theme.Mauve)
}
