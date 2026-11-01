# Record a maintenance task about a hit in the tracker, without leaving the TUI.
Sleep 600ms
Type "okf tui"
Enter
Sleep 1500ms
Type "runbook"
Enter
Sleep 2s
Type "t"
Sleep 1s
Type "Review the deploy runbook"
Enter
Type "The rollback step is outdated."
Sleep 1s
Screenshot box
Ctrl+S
Sleep 2s
Screenshot saved
Type "q"
Sleep 1s
Type "y"
Sleep 1s
Type "cat ../tasks.md"
Enter
Sleep 3s
