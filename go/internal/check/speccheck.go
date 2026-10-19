package check

import (
	"fmt"

	"go.yaml.in/yaml/v3"

	"nas/volume1/data/git/okf-tools/go/internal/frontmatter"
	"nas/volume1/data/git/okf-tools/go/internal/pytext"
	"nas/volume1/data/git/okf-tools/go/internal/spec"
)

// The 11 OKF v0.2 rules (Python okf.spec_check). Each is registered with the gate OkfV02: the engine
// runs it only on non-reserved files of a bundle that declares v0.2. Each reads the frontmatter
// mapping of the file context and returns messages.

var statuses = []string{"draft", "stable", "deprecated"}

// isPyStr reports whether Python loads n as a str: a string scalar without an explicit `!!str` tag
// (ruamel keeps a TaggedScalar for that). It is the predicate of the spec package, which keeps
// it private.
func isPyStr(n *yaml.Node) bool {
	n = frontmatter.Deref(n)
	return frontmatter.IsString(n) && n.Style&yaml.TaggedStyle == 0
}

// sourcesOf is the `sources` value when it is a list, else nothing (the shape rule reports the rest).
func sourcesOf(c *fileCtx) []*yaml.Node {
	if !c.hasFM {
		return nil
	}
	return frontmatter.Elems(frontmatter.Lookup(c.fm, "sources"))
}

func windowOK(window *yaml.Node) bool {
	return frontmatter.IsMap(window) && frontmatter.Has(window, "from") && frontmatter.Has(window, "to")
}

// checkSourcesShape (OKF §5.1): `sources` is a list of mappings.
func checkSourcesShape(c *fileCtx) []string {
	if !c.hasFM || !frontmatter.Has(c.fm, "sources") {
		return nil
	}
	sources := frontmatter.Lookup(c.fm, "sources")
	if !frontmatter.IsSeq(sources) {
		return []string{"`sources` is not a list of mappings"}
	}
	var out []string
	for i, entry := range frontmatter.Elems(sources) {
		if !frontmatter.IsMap(entry) {
			out = append(out, fmt.Sprintf("`sources[%d]` is not a mapping", i))
		}
	}
	return out
}

// checkSourceResource (OKF §5.1): every `sources` entry has a non-empty `resource`, the field the
// spec marks REQUIRED.
func checkSourceResource(c *fileCtx) []string {
	var out []string
	for i, entry := range sourcesOf(c) {
		if !frontmatter.IsMap(entry) {
			continue
		}
		resource := frontmatter.Lookup(entry, "resource")
		if !(isPyStr(resource) && pytext.Strip(frontmatter.ScalarText(resource)) != "") {
			out = append(out, fmt.Sprintf("`sources[%d]` has no non-empty `resource`", i))
		}
	}
	return out
}

// checkUsageWindow (OKF §5.1): a shared or per-entry `usage_window` is a mapping with `from` and `to`.
func checkUsageWindow(c *fileCtx) []string {
	if !c.hasFM {
		return nil
	}
	var out []string
	if frontmatter.Has(c.fm, "usage_window") && !windowOK(frontmatter.Lookup(c.fm, "usage_window")) {
		out = append(out, "`usage_window` is not a mapping with `from` and `to`")
	}
	for i, entry := range sourcesOf(c) {
		if frontmatter.IsMap(entry) && frontmatter.Has(entry, "usage_window") &&
			!windowOK(frontmatter.Lookup(entry, "usage_window")) {
			out = append(out, fmt.Sprintf("`sources[%d].usage_window` is not a mapping with `from` and `to`", i))
		}
	}
	return out
}

// checkGenerated (OKF §5.2): `generated` is a mapping with a non-empty `by`.
func checkGenerated(c *fileCtx) []string {
	if !c.hasFM || !frontmatter.Has(c.fm, "generated") {
		return nil
	}
	generated := frontmatter.Lookup(c.fm, "generated")
	if !frontmatter.IsMap(generated) {
		return []string{"`generated` is not a mapping"}
	}
	if spec.Filled(frontmatter.Lookup(generated, "by")) {
		return nil
	}
	return []string{"`generated` has no non-empty `by`"}
}

// checkVerified (OKF §5.2): `verified` is a mapping or a list of mappings, each with a non-empty `by`
// and `at`.
func checkVerified(c *fileCtx) []string {
	if !c.hasFM || !frontmatter.Has(c.fm, "verified") {
		return nil
	}
	entries, _ := spec.VerifiedEntries(c.fm)
	var out []string
	if !spec.VerifiedIsWellFormed(c.fm) {
		out = append(out, "`verified` is neither a mapping nor a list of mappings")
	}
	for i, entry := range entries {
		if !frontmatter.IsMap(entry) {
			continue
		}
		for _, key := range []string{"by", "at"} {
			if !spec.Filled(frontmatter.Lookup(entry, key)) {
				out = append(out, fmt.Sprintf("`verified[%d]` has no non-empty `%s`", i, key))
			}
		}
	}
	return out
}

// checkStatus (OKF §5.4): `status` is draft, stable or deprecated; an absent `status` is stable.
func checkStatus(c *fileCtx) []string {
	if !c.hasFM || !frontmatter.Has(c.fm, "status") {
		return nil
	}
	value := frontmatter.Lookup(c.fm, "status")
	text := frontmatter.ScalarText(value)
	if isPyStr(value) {
		for _, s := range statuses {
			if text == s {
				return nil
			}
		}
	}
	return []string{fmt.Sprintf("`status` is `%s`, not draft, stable or deprecated", text)}
}

// checkStaleAfter (OKF §5.5): a `stale_after` that is an instant at or before the run's `now` has passed.
func checkStaleAfter(c *fileCtx) []string {
	if !c.hasFM || !spec.IsStale(c.fm, c.run.now) {
		return nil
	}
	return []string{fmt.Sprintf("`stale_after` %s has passed", frontmatter.ScalarText(frontmatter.Lookup(c.fm, "stale_after")))}
}

// labelled is a frontmatter value with the label the messages name it by.
type labelled struct {
	label string
	value *yaml.Node
}

// actorFields are `generated.by` and every `verified[].by` that says something; a blank one is a
// Trust finding already.
func actorFields(fm *yaml.Node) []labelled {
	var pairs []labelled
	if generated := frontmatter.Lookup(fm, "generated"); frontmatter.IsMap(generated) {
		pairs = append(pairs, labelled{"generated.by", frontmatter.Lookup(generated, "by")})
	}
	entries, _ := spec.VerifiedEntries(fm)
	for i, entry := range entries {
		if frontmatter.IsMap(entry) {
			pairs = append(pairs, labelled{fmt.Sprintf("verified[%d].by", i), frontmatter.Lookup(entry, "by")})
		}
	}
	out := pairs[:0]
	for _, p := range pairs {
		if spec.Filled(p.value) {
			out = append(out, p)
		}
	}
	return out
}

func windowFields(label string, window *yaml.Node) []labelled {
	if !frontmatter.IsMap(window) {
		return nil
	}
	var out []labelled
	for _, key := range []string{"from", "to"} {
		if v := frontmatter.Lookup(window, key); v != nil {
			out = append(out, labelled{label + "." + key, v})
		}
	}
	return out
}

// timestampFields are every timestamp-valued v0.2 key that is present. A blank `verified[].at` is
// left to the Trust rule, which reports the missing field once.
func timestampFields(fm *yaml.Node) []labelled {
	var pairs []labelled
	if generated := frontmatter.Lookup(fm, "generated"); frontmatter.IsMap(generated) {
		if at := frontmatter.Lookup(generated, "at"); at != nil {
			pairs = append(pairs, labelled{"generated.at", at})
		}
	}
	entries, _ := spec.VerifiedEntries(fm)
	for i, entry := range entries {
		if frontmatter.IsMap(entry) && spec.Filled(frontmatter.Lookup(entry, "at")) {
			pairs = append(pairs, labelled{fmt.Sprintf("verified[%d].at", i), frontmatter.Lookup(entry, "at")})
		}
	}
	if v := frontmatter.Lookup(fm, "stale_after"); v != nil {
		pairs = append(pairs, labelled{"stale_after", v})
	}
	pairs = append(pairs, windowFields("usage_window", frontmatter.Lookup(fm, "usage_window"))...)
	for i, entry := range frontmatter.Elems(frontmatter.Lookup(fm, "sources")) {
		if !frontmatter.IsMap(entry) {
			continue
		}
		if v := frontmatter.Lookup(entry, "last_modified"); v != nil {
			pairs = append(pairs, labelled{fmt.Sprintf("sources[%d].last_modified", i), v})
		}
		pairs = append(pairs, windowFields(fmt.Sprintf("sources[%d].usage_window", i), frontmatter.Lookup(entry, "usage_window"))...)
	}
	return pairs
}

// checkActor (OKF §7): `generated.by` and `verified[].by` follow the actor convention.
func checkActor(c *fileCtx) []string {
	if !c.hasFM {
		return nil
	}
	var out []string
	for _, p := range actorFields(c.fm) {
		if _, _, ok := spec.ParseActor(p.value); !ok {
			out = append(out, fmt.Sprintf("`%s` is `%s`, not `<producer>/<version>`, `human:<id>` or `process:<id>`",
				p.label, frontmatter.ScalarText(p.value)))
		}
	}
	return out
}

// checkTimestamp (OKF §7): every timestamp-valued key is an ISO 8601 datetime with an explicit UTC
// offset, whether the loader left it a string or resolved it to a datetime.
func checkTimestamp(c *fileCtx) []string {
	if !c.hasFM {
		return nil
	}
	var out []string
	for _, p := range timestampFields(c.fm) {
		if _, ok := spec.ParseOkfDatetime(p.value); !ok {
			out = append(out, fmt.Sprintf("`%s` is `%s`, not an ISO 8601 datetime with an explicit UTC offset",
				p.label, frontmatter.ScalarText(p.value)))
		}
	}
	return out
}

// computationType is the `type` whose `runtime` is required (OKF §10.2).
const computationType = "Attested Computation"

// checkRuntime (OKF §10.2): an Attested Computation names its `runtime`; no other field of the type
// is required.
func checkRuntime(c *fileCtx) []string {
	if !c.hasFM || typeOf(c) != computationType || spec.Filled(frontmatter.Lookup(c.fm, "runtime")) {
		return nil
	}
	return []string{"`" + computationType + "` has no non-empty `runtime`"}
}

// checkDrift (OKF §5.2 with D45): the body changed in a commit after `generated.at` that did not
// touch `generated.at` itself, so the provenance may no longer describe the body. Nothing is written.
func checkDrift(c *fileCtx) ([]string, error) {
	if !c.hasFM {
		return nil, nil
	}
	generated := frontmatter.Lookup(c.fm, "generated")
	if !frontmatter.IsMap(generated) {
		return nil, nil
	}
	at, ok := spec.ParseOkfDatetime(frontmatter.Lookup(generated, "at"))
	if !ok {
		return nil, nil // no generated.at, or one the Format rule reports: nothing to compare
	}
	commit, err := c.run.history.LastBodyCommit(c.ap, true)
	if err != nil || commit == nil || !commit.Time.After(at) {
		return nil, err
	}
	return []string{fmt.Sprintf("body changed on %s without a new `generated.at` (%s)",
		spec.Isoformat(commit.Time), frontmatter.ScalarText(frontmatter.Lookup(generated, "at")))}, nil
}
