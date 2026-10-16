// Package stdio is the standard output of the process and what happens when it cannot be written.
// A command prints its text through Printf, Println, Print or Writer, never to os.Stdout itself.
//
// The first write that fails is kept and every later write is dropped; the command runs on to its
// end. Python behaves so: its stdout is buffered, a failed write surfaces when the buffer is flushed,
// and `main` decides then. Exit is that decision:
//
//   - EPIPE: the reader of the pipe is gone (`okf read x | head -1`). That is no failure of okf;
//     Python catches the BrokenPipeError and exits 0, so the status is the one of the command.
//   - any other error (a full disk, /dev/full, an I/O error): the output is lost. The message goes to
//     stderr and the status is 120, the one CPython ends with when the flush of stdout fails at exit.
//
// A closed stdout is not reported: since Go 1.22 the runtime opens /dev/null on a closed descriptor
// 0, 1 or 2 before main runs, so the write succeeds, and that descriptor cannot be told from an
// inherited /dev/null (a daemon, a child started with ignored stdio).
package stdio

import (
	"errors"
	"fmt"
	"io"
	"io/fs"
	"os"
	"syscall"
)

// failed is the first error of a write to stdout.
var failed error

// Writer is stdout for code that takes an io.Writer. A Write never fails: a failure is kept for Exit.
var Writer io.Writer = writer{}

type writer struct{}

func (writer) Write(p []byte) (int, error) {
	if failed == nil {
		_, failed = os.Stdout.Write(p)
	}
	return len(p), nil
}

// Printf is fmt.Printf for stdout.
func Printf(format string, a ...any) { fmt.Fprintf(Writer, format, a...) }

// Println is fmt.Println for stdout.
func Println(a ...any) { fmt.Fprintln(Writer, a...) }

// Print is fmt.Print for stdout.
func Print(a ...any) { fmt.Fprint(Writer, a...) }

// Init is the first call of main. The os package ends the process with SIGPIPE when a write to the
// descriptor 1 or 2 fails with EPIPE, and only for those two numbers; a write to another descriptor
// returns the error. os.Stdout and os.Stderr therefore become files on duplicates of 1 and 2, the
// same open files under other numbers (a child process inherits them as its 1 and 2).
func Init() {
	os.Stdout = duplicate(1, os.Stdout, "/dev/stdout")
	os.Stderr = duplicate(2, os.Stderr, "/dev/stderr")
}

func duplicate(fd int, original *os.File, name string) *os.File {
	dup, err := syscall.Dup(fd)
	if err != nil {
		return original
	}
	syscall.CloseOnExec(dup)
	return os.NewFile(uintptr(dup), name)
}

// Exit is the exit status of the process once the command ended with code: code, unless the output
// was lost, then 120 after one line on stderr.
func Exit(code int) int {
	if failed == nil || errors.Is(failed, syscall.EPIPE) {
		return code
	}
	reason := failed
	var pathErr *fs.PathError
	if errors.As(failed, &pathErr) {
		reason = pathErr.Err
	}
	fmt.Fprintf(os.Stderr, "ERROR: cannot write to stdout: %v\n", reason)
	return 120
}
