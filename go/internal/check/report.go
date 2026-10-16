package check

import (
	"fmt"
	"slices"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/envelope"
	"nas/volume1/data/git/okf-tools/go/internal/okferr"
	"nas/volume1/data/git/okf-tools/go/internal/pytext"
	"nas/volume1/data/git/okf-tools/go/internal/stdio"
)

// Finding is one violation of one rule: the rule ID, the severity the registry gives that rule, the
// catalogue-relative path and the message, in that order (the order of the JSON fields too).
type Finding struct {
	Rule, Severity, Path, Message string
}

// FindingOf is Python finding_of: the Finding for ruleID with the severity of the registry. An ID
// no rule registers is a programming error and panics; a severity is never defaulted.
func FindingOf(ruleID, path, message string) Finding {
	for i := range rules {
		if rules[i].ID == ruleID {
			return Finding{ruleID, rules[i].Severity, path, message}
		}
	}
	panic("check: no rule " + pytext.ReprStr(ruleID) + " is registered")
}

// ReportFindings is Python report_findings, the one place that decides what counts: a finding
// counts when its severity is error, or when strict is set; strict never changes a severity.
// Errors come before warnings, each group by path, ties in input order, so the order does not
// depend on the walk of the file system.
//
// In text mode the report is written to stdout and the data is nil; in JSON mode the data is
// {"findings": [...]} and nothing is written. When any finding counts the error is the
// non_conformant class, carrying the data in JSON mode: the report is out before the error, so it
// is never lost to the exit.
func ReportFindings(findings []Finding, strict, asJSON bool) (any, error) {
	counting := 0
	for _, f := range findings {
		if strict || f.Severity == SeverityError {
			counting++
		}
	}
	ordered := slices.Clone(findings)
	slices.SortStableFunc(ordered, func(a, b Finding) int {
		if ea, eb := a.Severity == SeverityError, b.Severity == SeverityError; ea != eb {
			if ea {
				return -1
			}
			return 1
		}
		return strings.Compare(a.Path, b.Path)
	})
	if asJSON {
		rows := make([]envelope.Obj, len(ordered))
		for i, f := range ordered {
			rows[i] = envelope.O("rule", f.Rule, "severity", f.Severity, "path", f.Path, "message", f.Message)
		}
		result := envelope.O("findings", rows)
		if counting > 0 {
			return nil, okferr.WithResult(okferr.NonConformant, "", result)
		}
		return result, nil
	}
	var sb strings.Builder
	for _, f := range ordered {
		fmt.Fprintf(&sb, "%-9s%-20s %s  (%s)\n", strings.ToUpper(f.Severity), f.Rule, f.Path, f.Message)
	}
	if counting > 0 {
		fmt.Fprintf(&sb, "%d VIOLATIONS\n", counting)
	} else {
		sb.WriteString("OK — 0 violations\n")
	}
	stdio.Print(sb.String())
	if counting > 0 {
		return nil, okferr.New(okferr.NonConformant, "")
	}
	return nil, nil
}

// IgnorePatterns is Python ignore_patterns: the suppression set, every --ignore pattern plus the
// `ignore_rules` array of the `.okf.toml` table config. A value that is not an array of strings is
// announced as a call note and contributes nothing: the safe direction is more findings, never
// fewer.
func IgnorePatterns(config map[string]any, flagPatterns []string) []string {
	patterns := slices.Clone(flagPatterns)
	v, ok := config["ignore_rules"]
	if !ok {
		return patterns
	}
	if list, isList := v.([]any); isList {
		var strs []string
		for _, x := range list {
			s, isStr := x.(string)
			if !isStr {
				strs = nil
				isList = false
				break
			}
			strs = append(strs, s)
		}
		if isList {
			return append(patterns, strs...)
		}
	}
	envelope.Note("ignore_rules must be an array of rule-ID patterns; got " + pytext.Repr(v) +
		" — it suppresses no rule")
	return patterns
}

// IsSuppressed is Python is_suppressed. `*` is the only metacharacter and only as the last
// character: that pattern matches every ID that starts with the text before it; any other pattern
// matches only the identical ID.
func IsSuppressed(ruleID string, patterns []string) bool {
	for _, p := range patterns {
		if prefix, star := strings.CutSuffix(p, "*"); star {
			if strings.HasPrefix(ruleID, prefix) {
				return true
			}
		} else if ruleID == p {
			return true
		}
	}
	return false
}
