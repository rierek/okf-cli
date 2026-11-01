# Collect hits in the session buffer, add a note, review the buffer, hand it to an agent pane.
Sleep 600ms
Type "okf tui"
Enter
Sleep 1500ms
Type "recipe"
Enter
Sleep 2s
Space
Sleep 900ms
Type "j"
Sleep 600ms
Space
Sleep 900ms
Type "n"
Sleep 1s
Type "Check the rollback step first"
Sleep 1s
Screenshot note
Ctrl+S
Sleep 1500ms
Type "b"
Sleep 2s
Screenshot buffer
Type "j"
Sleep 1500ms
Ctrl+S
Sleep 2s
Screenshot picker
Enter
Sleep 2s
Type "cat ../sent.md"
Enter
Sleep 3s
