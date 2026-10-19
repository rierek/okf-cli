package check

import "slices"

// The severities and scopes of a rule, and the OKF version the spec rules are gated to.
const (
	SeverityError   = "error"
	SeverityWarning = "warning"

	// ScopeFile rules run once per concept file, ScopeBundle rules once per scanned bundle.
	ScopeFile   = "file"
	ScopeBundle = "bundle"

	// OkfV02 gates the OKF v0.2 rules: they run only on non-reserved files of a bundle whose
	// root index.md declares `okf_version: "0.2"`.
	OkfV02 = "0.2"
)

// Rule is one entry of the registry: its stable ID (`okf/<area>/<name>` for an OKF spec rule,
// `kc/<area>/<name>` for a local catalogue invariant), its severity, its scope and the OKF
// version it is gated to ("" for a rule that runs on every bundle).
type Rule struct {
	ID         string
	Severity   string
	Scope      string
	OkfVersion string

	file   func(*fileCtx) ([]string, error)
	bundle func(*bundleCtx) ([]pathMessage, error)
}

// pathMessage is one finding of a bundle rule: the path it names and the message.
type pathMessage struct{ path, message string }

func fileRule(id, severity, version string, f func(*fileCtx) []string) Rule {
	return Rule{ID: id, Severity: severity, Scope: ScopeFile, OkfVersion: version,
		file: func(c *fileCtx) ([]string, error) { return f(c), nil }}
}

func fileRuleErr(id, severity, version string, f func(*fileCtx) ([]string, error)) Rule {
	return Rule{ID: id, Severity: severity, Scope: ScopeFile, OkfVersion: version, file: f}
}

func bundleRule(id, severity string, f func(*bundleCtx) ([]pathMessage, error)) Rule {
	return Rule{ID: id, Severity: severity, Scope: ScopeBundle, bundle: f}
}

// rules is the registry, in the order the engine runs it: Python RULES, 40 entries.
var rules = []Rule{
	fileRule("okf/frontmatter/parseable", SeverityError, "", checkFrontmatterParseable),
	fileRule("okf/frontmatter/type-nonempty", SeverityError, "", checkTypeNonempty),
	fileRule("okf/type/reserved-no-type", SeverityError, "", checkReservedNoType),
	fileRule("kc/name/filename-chars", SeverityError, "", checkFilenameChars),
	fileRule("kc/type/registered", SeverityWarning, "", checkTypeRegistered),
	fileRule("kc/tag/registered", SeverityWarning, "", checkTagRegistered),
	fileRule("kc/frontmatter/english-keys", SeverityWarning, "", checkEnglishKeys),
	fileRule("kc/link/crosslink-format", SeverityWarning, "", checkCrosslinkFormat),
	fileRule("kc/supersede/resolves", SeverityError, "", checkSupersededByResolves),
	fileRule("kc/supersede/scope", SeverityWarning, "", checkSupersededByScope),
	fileRule("kc/frontmatter/tags-block-form", SeverityWarning, "", checkTagsBlockForm),
	fileRule("kc/markup/xml-like-tags", SeverityWarning, "", checkXMLLikeTags),
	fileRuleErr("kc/link/wikilink-resolvable", SeverityWarning, "", checkWikilinkResolvableRule),
	fileRuleErr("kc/sync/block", SeverityError, "", checkSyncIntegrity),
	fileRuleErr("kc/sync/stale", SeverityWarning, "", checkSyncStale),
	fileRule("kc/sync/canon-block", SeverityError, "", checkCanonBlocks),
	ctxRule("kc/ctx/type", SeverityError),
	ctxRule("kc/ctx/slug", SeverityError),
	ctxRule("kc/ctx/row-format", SeverityError),
	ctxRule("kc/ctx/mode", SeverityError),
	ctxRule("kc/ctx/required-positions", SeverityError),
	ctxRule("kc/ctx/reference-position", SeverityError),
	ctxRule("kc/ctx/duplicate-entry", SeverityError),
	ctxRule("kc/ctx/dead-entry", SeverityError),
	ctxRule("kc/ctx/empty-description", SeverityWarning),
	ctxRule("kc/ctx/archived-entry", SeverityWarning),
	ctxRule("kc/ctx/stale-entry", SeverityWarning),
	bundleRule("kc/asset/placement", SeverityError, checkAssetPlacementRule),
	bundleRule("kc/asset/entry-file-description", SeverityWarning, checkEntryFileDescriptionRule),
	fileRule("okf/provenance/sources-shape", SeverityError, OkfV02, checkSourcesShape),
	fileRule("okf/provenance/source-resource", SeverityError, OkfV02, checkSourceResource),
	fileRule("okf/provenance/usage-window", SeverityError, OkfV02, checkUsageWindow),
	fileRule("okf/trust/generated", SeverityError, OkfV02, checkGenerated),
	fileRule("okf/trust/verified", SeverityError, OkfV02, checkVerified),
	fileRule("okf/lifecycle/status", SeverityError, OkfV02, checkStatus),
	fileRule("okf/lifecycle/stale-after", SeverityWarning, OkfV02, checkStaleAfter),
	fileRule("okf/format/actor", SeverityError, OkfV02, checkActor),
	fileRule("okf/format/timestamp", SeverityError, OkfV02, checkTimestamp),
	fileRule("okf/computation/runtime", SeverityError, OkfV02, checkRuntime),
	fileRuleErr("okf/trust/drift", SeverityWarning, OkfV02, checkDrift),
}

// Rules is the registry in engine order: every rule of the check with its ID, severity, scope and
// OKF-version gate. The slice is a copy.
func Rules() []Rule { return slices.Clone(rules) }
