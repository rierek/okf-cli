package check

import (
	"path/filepath"
	"time"

	"go.yaml.in/yaml/v3"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/ctxfile"
	"nas/volume1/data/git/okf-tools/go/internal/envelope"
	"nas/volume1/data/git/okf-tools/go/internal/frontmatter"
	"nas/volume1/data/git/okf-tools/go/internal/history"
	"nas/volume1/data/git/okf-tools/go/internal/pytext"
	"nas/volume1/data/git/okf-tools/go/internal/spec"
	"nas/volume1/data/git/okf-tools/go/internal/wikisync"
)

// runState is what one run shares between its files: the registries, the lazily built indexes, the
// clock and the git history handle.
type runState struct {
	typesSet, tagsSet map[string]bool // nil: the registry file is missing
	wlChecked         map[string]bool
	wlIndex           wikisync.BasenameIndex
	canonIndex        func() (wikisync.CanonIndex, error)
	now               time.Time
	history           *history.History
}

// fileCtx is the context every file rule reads (Python gather_file_context): one concept file of
// one bundle, read and split once.
type fileCtx struct {
	root, bundle, ap, rel, fn string
	text, body                string
	fm                        *yaml.Node // the root mapping, nil without readable frontmatter
	fmError                   string
	hasFM                     bool
	isReserved                bool
	run                       *runState

	ctxFindings []ctxfile.CtxFinding
	ctxLoaded   bool
	sync        []syncRecord
	syncLoaded  bool
}

// bundleCtx is what a bundle rule reads: the bundle label and the directory scanned.
type bundleCtx struct{ root, bundle, bp string }

func gatherFileContext(root, bundle, ap string, run *runState) (*fileCtx, error) {
	text, err := catalogue.ReadFile(ap)
	if err != nil {
		return nil, err
	}
	doc := frontmatter.Read(text)
	rel, err := filepath.Rel(root, ap)
	if err != nil {
		rel = ap
	}
	fn := filepath.Base(ap)
	return &fileCtx{
		root: root, bundle: bundle, ap: ap, rel: filepath.ToSlash(rel), fn: fn,
		text: text, body: doc.Body, fm: doc.Data(), fmError: doc.Err, hasFM: doc.Data() != nil,
		isReserved: catalogue.IsReserved(fn), run: run,
	}, nil
}

// RunChecks is Python run_checks: every rule of the registry over target (a bundle or
// `<bundle>/<subdir>`, "" for the whole catalogue). typesSource overrides the TYPES.md of the
// root; absent (nil) it falls back to the `types_source` key of `.okf.toml`, then to
// `<root>/TYPES.md`. The findings come in engine order: per bundle, per file in walk order with the
// rules in registry order, then the bundle rules; each severity is the one of its rule.
//
// The engine builds the canon index and the wikilink basename index only when a file or bundle in
// scope needs them: an unconfigured catalogue, or a scan of a bundle that did not opt in, pays
// nothing. A reason the drift check could not run is announced once as a call note.
func RunChecks(root, target string, typesSource *string) ([]Finding, error) {
	scopes, err := catalogue.ResolveScopes(root, target, false, false)
	if err != nil {
		return nil, err
	}
	config, err := catalogue.LoadConfig(root)
	if err != nil {
		return nil, err
	}
	source := ""
	if typesSource != nil {
		source = *typesSource
	} else if s, ok := config["types_source"].(string); ok {
		source = s
	}
	run := &runState{now: spec.Utcnow()}
	if run.typesSet, err = catalogue.LoadTypes(root, source); err != nil {
		return nil, err
	}
	if run.tagsSet, err = catalogue.LoadTags(root, ""); err != nil {
		return nil, err
	}
	// The basename index costs a full catalogue walk, so it is built only when a bundle in THIS RUN'S
	// scope has opted in.
	inScope := map[string]bool{}
	for _, sc := range scopes {
		inScope[pytext.Lower(sc.Bundle)] = true
	}
	run.wlChecked = map[string]bool{}
	for b := range wikisync.CheckedBundles(config, root) {
		if inScope[b] {
			run.wlChecked[b] = true
		}
	}
	if len(run.wlChecked) > 0 {
		if run.wlIndex, err = wikisync.BuildBasenameIndex(root); err != nil {
			return nil, err
		}
	}
	var canon wikisync.CanonIndex // the canon index is another full walk: built on first use
	run.canonIndex = func() (wikisync.CanonIndex, error) {
		if canon == nil {
			idx, err := wikisync.BuildCanonIndex(root)
			if err != nil {
				return nil, err
			}
			canon = idx
		}
		return canon, nil
	}
	run.history = history.New(root)
	findings, err := runScopes(root, scopes, run)
	_ = run.history.Close() // ends the git processes; their error changes no finding
	if err != nil {
		return nil, err
	}
	for _, reason := range run.history.Notes() {
		envelope.Note("drift check skipped: " + reason)
	}
	return findings, nil
}

func runScopes(root string, scopes []catalogue.Scope, run *runState) ([]Finding, error) {
	var findings []Finding
	for _, sc := range scopes {
		// The version gate reads the bundle-ROOT index.md, never an index.md under a scoped path,
		// once per bundle; an empty bundle name is a target outside the catalogue and has no root.
		version, declared := "", false
		if sc.Bundle != "" {
			version, declared = spec.DeclaredOkfVersion(catalogue.Join(root, sc.Bundle))
		}
		gated := func(r *Rule) bool { return r.OkfVersion == "" || (declared && r.OkfVersion == version) }
		for ap := range catalogue.IterAllMd(sc.Path, true) {
			c, err := gatherFileContext(root, sc.Bundle, ap, run)
			if err != nil {
				return nil, err
			}
			for i := range rules {
				r := &rules[i]
				if r.Scope != ScopeFile || !gated(r) {
					continue
				}
				if r.OkfVersion != "" && c.isReserved {
					continue // a gated entry never sees a reserved file
				}
				msgs, err := r.file(c)
				if err != nil {
					return nil, err
				}
				for _, m := range msgs {
					findings = append(findings, Finding{r.ID, r.Severity, c.rel, m})
				}
			}
		}
		for i := range rules {
			r := &rules[i]
			if r.Scope != ScopeBundle || !gated(r) {
				continue
			}
			found, err := r.bundle(&bundleCtx{root, sc.Bundle, sc.Path})
			if err != nil {
				return nil, err
			}
			for _, pm := range found {
				findings = append(findings, Finding{r.ID, r.Severity, pm.path, pm.message})
			}
		}
	}
	return findings, nil
}
