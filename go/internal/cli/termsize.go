package cli

import "os"

// terminalColumns is shutil.get_terminal_size().columns: $COLUMNS when it is a positive integer,
// else the width of the terminal on stdout, else 80.
func terminalColumns() int {
	if n, ok := parseInt(os.Getenv("COLUMNS")); ok && n > 0 {
		return n
	}
	if n := stdoutColumns(); n > 0 {
		return n
	}
	return 80
}
