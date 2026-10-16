package cli

// UsageError is an argument error: no command, an unknown command, an unknown option, a missing
// or invalid argument, an ambiguous abbreviation and so on. Text is the complete message of
// Python's parser.error: the usage of the parser that failed (it begins with "usage: okf")
// and its "okf <command>: error: ..." line. The caller prints Text to stderr as it is and exits 2.
type UsageError struct{ Text string }

// Error is Text, so the value reads as the message it carries.
func (e *UsageError) Error() string { return e.Text }

// HelpOutput is a -h/--help request. It is no failure: the caller prints Text to stdout as it is
// and exits 0. It travels in the error result of Parse because the parse ends there.
type HelpOutput struct{ Text string }

// Error is Text; a help request is no failure, see the type.
func (h *HelpOutput) Error() string { return h.Text }

// argError is argparse's ArgumentError: a message about one argument (act) or, when act is nil,
// about the whole command line. The parser that meets it turns it into a UsageError.
type argError struct {
	act *action
	msg string
}

func (e *argError) Error() string {
	if e.act != nil {
		if name := e.act.name(); name != "" {
			return "argument " + name + ": " + e.msg
		}
	}
	return e.msg
}
