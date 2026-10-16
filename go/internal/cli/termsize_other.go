//go:build !(linux || darwin)

package cli

// stdoutColumns is unknown here: only $COLUMNS and the default of 80 apply.
func stdoutColumns() int { return 0 }
