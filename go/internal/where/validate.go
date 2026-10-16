package where

import (
	"slices"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/okferr"
	"nas/volume1/data/git/okf-tools/go/internal/spec"
)

// tiers are the trust tiers a `tier` comparison names (OKF §5.3).
var tiers = []string{"unverified", "machine-confirmed", "human-reviewed"}

func isOrdering(op string) bool { return op == "<" || op == "<=" || op == ">" || op == ">=" }

// validate is Python _validate: semantic misuse of a field is invalid_input, like a syntax error.
// The first misuse in expression order is reported.
func validate(n node) error {
	switch n := n.(type) {
	case andNode:
		if err := validate(n.left); err != nil {
			return err
		}
		return validate(n.right)
	case orNode:
		if err := validate(n.left); err != nil {
			return err
		}
		return validate(n.right)
	case notNode:
		return validate(n.operand)
	case compareNode:
		return validateLeaf(n.field, n.op, []string{n.value})
	case inNode:
		return validateLeaf(n.field, "in", n.values)
	}
	panic("where: unknown expression node")
}

func validateLeaf(field, op string, values []string) error {
	if field == "archived" && (isOrdering(op) || op == "~" || !allIn(values, "true", "false")) {
		return okferr.New(okferr.InvalidInput, "--where: archived takes = != or in, with true or false")
	}
	if field == "tag" && isOrdering(op) {
		return okferr.Newf(okferr.InvalidInput, "--where: tag takes no ordering operator, got %s", op)
	}
	if field == "tier" || field == "stale" {
		allowed := tiers
		if field == "stale" {
			allowed = []string{"true", "false"}
		}
		if isOrdering(op) || op == "~" || !allIn(values, allowed...) {
			return okferr.Newf(okferr.InvalidInput, "--where: %s takes = != or in, with %s", field, strings.Join(allowed, " or "))
		}
	}
	if isInstantField(field) && (op == "~" || slices.ContainsFunc(values, func(v string) bool {
		_, ok := spec.ParseOkfDatetimeText(v)
		return !ok
	})) {
		return okferr.Newf(okferr.InvalidInput, "--where: %s compares instants: = != < <= > >= or in, with an "+
			"ISO 8601 datetime and an explicit offset, e.g. 2026-09-23T00:00:00Z "+
			"(quote a value that holds +)", field)
	}
	return nil
}

// allIn reports whether every value is one of allowed.
func allIn(values []string, allowed ...string) bool {
	return !slices.ContainsFunc(values, func(v string) bool { return !slices.Contains(allowed, v) })
}
