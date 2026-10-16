//go:build linux || darwin

package cli

import (
	"syscall"
	"unsafe"
)

// stdoutColumns is the width of the terminal on stdout (ioctl TIOCGWINSZ), 0 when stdout is no
// terminal.
func stdoutColumns() int {
	var size struct{ rows, columns, x, y uint16 }
	_, _, errno := syscall.Syscall(syscall.SYS_IOCTL, uintptr(syscall.Stdout), syscall.TIOCGWINSZ, uintptr(unsafe.Pointer(&size)))
	if errno != 0 {
		return 0
	}
	return int(size.columns)
}
