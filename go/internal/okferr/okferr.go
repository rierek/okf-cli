// Package okferr is the one classified failure every okf command ends with: a kind, a message
// and an optional result, mapped to a fixed exit code at the entry point (Python okf.errors).
package okferr

import (
	"errors"
	"fmt"
)

// Kind is the class of a failure; its exit code is fixed by Code.
type Kind string

const (
	Internal      Kind = "internal"
	InvalidInput  Kind = "invalid_input"
	NotFound      Kind = "not_found"
	NonConformant Kind = "non_conformant"
	Drift         Kind = "drift"
)

// Code is the process exit code of a kind: internal 1, invalid_input 2, not_found 3,
// non_conformant 4, drift 5. An unknown kind exits 1.
func (k Kind) Code() int {
	switch k {
	case InvalidInput:
		return 2
	case NotFound:
		return 3
	case NonConformant:
		return 4
	case Drift:
		return 5
	}
	return 1
}

// Error is a classified failure. Message is printed to stderr in text mode and becomes the
// envelope's error message in --json mode; Result, when set, becomes the envelope's data.
type Error struct {
	Kind    Kind
	Message string
	Result  any
}

func (e *Error) Error() string { return e.Message }

// Code is the exit code of the error's kind.
func (e *Error) Code() int { return e.Kind.Code() }

// New returns a classified error without a result.
func New(kind Kind, message string) *Error { return &Error{Kind: kind, Message: message} }

// Newf is New with a formatted message.
func Newf(kind Kind, format string, args ...any) *Error {
	return &Error{Kind: kind, Message: fmt.Sprintf(format, args...)}
}

// WithResult returns a classified error that carries the data an envelope reports next to the
// failure (Python OkfError(kind, message, result)).
func WithResult(kind Kind, message string, result any) *Error {
	return &Error{Kind: kind, Message: message, Result: result}
}

// As returns the classified error inside err, or an internal error carrying err's text when err
// is not classified. A nil err gives nil.
func As(err error) *Error {
	if err == nil {
		return nil
	}
	var e *Error
	if errors.As(err, &e) {
		return e
	}
	return &Error{Kind: Internal, Message: err.Error()}
}
