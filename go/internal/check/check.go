// Package check is the conformance scan of the okf binary and the command that records a
// verification (Python okf.check, okf.spec_check and okf.verify): the rule registry, the engine, the
// finding report and the commands `check` and `verify`.
//
// The registry holds the rules in the order the engine runs them: Python RULES, with each rule's ID,
// severity, scope and OKF-version gate. The other command packages build on what this one exports
// instead of copying it: Finding, FindingOf and ReportFindings (ctx check), RunChecks and Rules,
// FilenameForbiddenChars and ForbiddenFilenameChars (the new-filename guard of rename and
// archive), MaskCodeSpans and Unmask, XMLTagChainRE, IsIgnorableChain and FindXMLLikeTags
// (fix-crosslinks and fix-xml-tags).
package check

import (
	"path/filepath"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/cli"
	"nas/volume1/data/git/okf-tools/go/internal/complete"
	"nas/volume1/data/git/okf-tools/go/internal/okferr"
)

// Register attaches `check` and `verify` with their completers.
func Register(app *cli.App) {
	app.Attach("check", cli.Spec{
		Args: []cli.Arg{
			{Dest: "target", Nargs: cli.Optional, Help: "<bundle> or <bundle>/<subdir> (default: whole catalogue)"},
			{Flags: []string{"--strict"}, Action: cli.StoreTrue,
				Help: "count warnings toward the exit code; each finding keeps its severity"},
			{Flags: []string{"--ignore"}, Action: cli.Append, Metavar: []string{"PATTERN"},
				Help: "suppress rules: an exact rule ID, or a prefix ending in `*` (kc/*, okf/link/*); " +
					"repeatable, added to .okf.toml ignore_rules; suppressed findings neither print nor count"},
			cli.JSON(),
			{Flags: []string{"--types"}, Help: "explicit TYPES.md path (overrides .okf.toml types_source)"},
		},
		Handler: runCheck,
	})
	complete.Attach([]string{"check"}, "target", complete.Scopes)
	complete.Attach([]string{"check"}, "types", complete.Files)

	app.Attach("verify", cli.Spec{
		Args: []cli.Arg{
			{Dest: "concept", Help: "<bundle>/<concept-id> of the concept"},
			{Flags: []string{"--by"}, Required: true, Metavar: []string{"ACTOR"},
				Help: "who verified it: `human:<id>`, `process:<id>` or `<producer>/<version>`"},
			cli.JSON(),
		},
		Handler: runVerify,
	})
	complete.Attach([]string{"verify"}, "concept", complete.Concepts)
}

// runCheck is Python cmd_check: the target gate, the suppression set, the engine run and the report.
func runCheck(root string, a *cli.Args) (any, error) {
	target := a.String("target")
	if target != "" && !catalogue.RealFS.IsDir(catalogue.Join(root, filepath.Clean(target))) {
		// Without this a typo'd or renamed bundle scanned nothing and exited 0, a clean bill of
		// health for a directory that does not exist.
		return nil, okferr.Newf(okferr.NotFound, "not a directory: %s", target)
	}
	config, err := catalogue.LoadConfig(root)
	if err != nil {
		return nil, err
	}
	patterns := IgnorePatterns(config, a.Strings("ignore"))
	var types *string
	if a.Has("types") {
		t := a.String("types")
		types = &t
	}
	all, err := RunChecks(root, target, types)
	if err != nil {
		return nil, err
	}
	kept := all[:0]
	for _, f := range all {
		if !IsSuppressed(f.Rule, patterns) {
			kept = append(kept, f)
		}
	}
	return ReportFindings(kept, a.Bool("strict"), a.JSON)
}
