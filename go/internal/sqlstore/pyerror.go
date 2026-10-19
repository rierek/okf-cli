package sqlstore

import (
	"errors"
	"strings"

	"modernc.org/sqlite"
)

// PyError describes a driver error the way Python's sqlite3 raises it: the name of the exception
// class and its message, for the notes that print `type(exc).__name__` and `exc`. ok is false when
// err is not a driver error (IsDatabaseError). The class follows the primary result code as
// CPython maps it. The message is sqlite3_errmsg(); the driver wraps it as
// `<sqlite3_errstr>: <message> (<code>)`, or `<sqlite3_errstr> (<code>)` when the two are equal,
// with ` (SQLITE_BUSY)` appended for a locked database. No sqlite3_errstr text contains a colon,
// so the first ": " ends the wrapper.
func PyError(err error) (class, message string, ok bool) {
	var e *sqlite.Error
	if !errors.As(err, &e) {
		return "", "", false
	}
	message = strings.TrimSuffix(e.Error(), " (SQLITE_BUSY)")
	if i := strings.LastIndex(message, " ("); i >= 0 {
		message = message[:i]
	}
	if i := strings.Index(message, ": "); i >= 0 {
		message = message[i+2:]
	}
	return pyClass(e.Code() & 0xff), message, true
}

// pyClass is CPython's mapping of a primary SQLite result code to an exception class of the
// sqlite3 module (Modules/_sqlite/util.c). SQLITE_NOMEM raises MemoryError there.
func pyClass(code int) string {
	switch code {
	case 2, 12: // SQLITE_INTERNAL, SQLITE_NOTFOUND
		return "InternalError"
	case 7: // SQLITE_NOMEM
		return "MemoryError"
	case 1, 3, 4, 5, 6, 8, 9, 10, 13, 14, 15, 16, 17: // ERROR PERM ABORT BUSY LOCKED READONLY INTERRUPT IOERR FULL CANTOPEN PROTOCOL EMPTY SCHEMA
		return "OperationalError"
	case 18: // SQLITE_TOOBIG
		return "DataError"
	case 19, 20: // SQLITE_CONSTRAINT, SQLITE_MISMATCH
		return "IntegrityError"
	case 21, 25: // SQLITE_MISUSE, SQLITE_RANGE
		return "InterfaceError"
	}
	return "DatabaseError" // SQLITE_CORRUPT, SQLITE_NOTADB and every other code
}
