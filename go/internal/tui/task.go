package tui

import (
	"strings"

	tea "github.com/charmbracelet/bubbletea"

	"nas/volume1/data/git/okf-tools/go/internal/find"
)

// taskCaller names the task box in the editor's textEditedMsg.
const taskCaller = "task"

// maxStderrToast bounds the stderr text of a failed tracker command in the toast, in runes.
const maxStderrToast = 400

// taskDoneMsg is the answer of a tracker run. A failed run carries retry, which puts the box back
// with the text the user wrote.
type taskDoneMsg struct {
	task  maintenanceTask
	note  string
	err   error
	retry func(model) (model, tea.Cmd)
}

// openTask opens the task box on hit h. The maintenance task never enters the session buffer and
// changes nothing else of the screen: root, query, list, focus and buffer stay as they are. When
// the tracker is missing or invalid the box does not open; a sticky toast names the problem and
// the config path instead.
func (m model) openTask(h find.Hit) (model, tea.Cmd) {
	tr, err := loadTracker()
	if err != nil {
		return m.showToast(toastError, "No task saved: the tracker is not configured", err.Error(), true)
	}
	task := maintenanceTask{Path: h.Abs, Ref: h.Path, Root: m.root}
	return m.openTaskBox("Task on "+truncate(h.Title, max(m.textWidth()-12, 1)), "", tr, task)
}

// openTaskBox opens the text box of a task. The first line of the text is the title, the rest the
// body. Saving records the task off the UI loop; a failure brings the box back with the same text
// (see handleTaskDone). The closure holds values only: the tracker and the task of the hit.
func (m model) openTaskBox(boxTitle, initial string, tr tracker, task maintenanceTask) (model, tea.Cmd) {
	return m.openText(taskCaller, boxTitle, initial, func(m model, text string) (model, tea.Cmd) {
		retry := func(m model) (model, tea.Cmd) { return m.openTaskBox(boxTitle, text, tr, task) }
		title, body, _ := strings.Cut(text, "\n")
		if title = strings.TrimSpace(title); title == "" {
			m, toast := m.showToast(toastWarn, "A task needs a title", "The first line of the text is the title.", false)
			m, box := retry(m)
			return m, tea.Batch(toast, box)
		}
		t := task
		t.Title, t.Body = title, strings.TrimSpace(body)
		return m, func() tea.Msg {
			note, err := tr.record(t)
			return taskDoneMsg{task: t, note: note, err: err, retry: retry}
		}
	})
}

// handleTaskDone shows the result. Success: an info toast, nothing else changes. Failure: an error
// toast with the tracker's message (stderr of a command) and the box back with the same text.
func (m model) handleTaskDone(msg taskDoneMsg) (model, tea.Cmd) {
	if msg.err == nil {
		context := msg.note
		if context == "" {
			context = msg.task.Title + " (" + msg.task.Ref + ")"
		}
		return m.showToast(toastInfo, "Task recorded", context, false)
	}
	reason := []rune(msg.err.Error())
	if len(reason) > maxStderrToast {
		reason = append(reason[:maxStderrToast], '…')
	}
	m, toast := m.showToast(toastError, "Task not saved", string(reason), true)
	m, box := msg.retry(m)
	return m, tea.Batch(toast, box)
}
