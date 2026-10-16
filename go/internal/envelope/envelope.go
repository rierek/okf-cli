// Package envelope is the one output path of every command that answers `--json`: the ordered
// JSON object, the Python-compatible encoder, the one-envelope runner and the call note. A
// command answers with exactly one envelope {command, ok, data, warnings, error} on stdout; its
// handler returns `data` and prints nothing in that mode, and a classified failure is an
// *okferr.Error whose optional result becomes `data`.
package envelope

import (
	"errors"
	"fmt"
	"os"
	"runtime/debug"

	"nas/volume1/data/git/okf-tools/go/internal/okferr"
)

// warnings are the notes of the running envelope call; nil in text mode.
var warnings *[]string

// Note is the one call-note path. message is the note text without the `note: ` prefix: a stderr
// line in text mode, an entry of the envelope's `warnings` while an envelope call runs.
func Note(message string) {
	if warnings == nil {
		fmt.Fprintln(os.Stderr, "note: "+message)
		return
	}
	*warnings = append(*warnings, message)
}

// Run runs call, prints the one envelope line to stdout and returns the exit code. command is the
// command as typed, a verb included (`find`, `ctx show`). A classified error becomes the envelope's
// error with its result as data. Any other error, or a panic, becomes an internal error whose text
// also goes to stderr, as the Python traceback did. The `error` object is {kind, code, message};
// the message falls back to the kind when empty.
func Run(command string, call func() (any, error)) int {
	notes := []string{}
	warnings = &notes
	defer func() { warnings = nil }()

	var data any
	var failure *okferr.Error
	func() {
		defer func() {
			if r := recover(); r != nil {
				fmt.Fprintf(os.Stderr, "panic: %v\n%s", r, debug.Stack())
				failure = okferr.Newf(okferr.Internal, "panic: %v", r)
			}
		}()
		var err error
		if data, err = call(); err == nil {
			return
		}
		if !errors.As(err, &failure) {
			fmt.Fprintf(os.Stderr, "%T: %v\n", err, err)
			failure = okferr.Newf(okferr.Internal, "%T: %v", err, err)
		}
		data = failure.Result
	}()

	document, err := render(command, data, notes, failure)
	if err != nil { // data that JSON cannot hold
		fmt.Fprintln(os.Stderr, err)
		failure = okferr.New(okferr.Internal, err.Error())
		document, _ = render(command, nil, notes, failure)
	}
	fmt.Fprintln(os.Stdout, document)
	if failure != nil {
		return failure.Code()
	}
	return 0
}

func render(command string, data any, notes []string, failure *okferr.Error) (string, error) {
	var errObj any
	if failure != nil {
		message := failure.Message
		if message == "" {
			message = string(failure.Kind)
		}
		errObj = O("kind", string(failure.Kind), "code", failure.Code(), "message", message)
	}
	out, err := Marshal(O("command", command, "ok", failure == nil, "data", data, "warnings", notes, "error", errObj))
	return string(out), err
}
