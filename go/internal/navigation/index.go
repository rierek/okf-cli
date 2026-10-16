package navigation

import (
	"io"
	"sort"
	"strconv"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/cli"
	"nas/volume1/data/git/okf-tools/go/internal/envelope"
	"nas/volume1/data/git/okf-tools/go/internal/frontmatter"
	"nas/volume1/data/git/okf-tools/go/internal/pytext"
	"nas/volume1/data/git/okf-tools/go/internal/spec"
)

func indexArgs() []cli.Arg {
	return []cli.Arg{
		{Dest: "bundle", Nargs: cli.Optional, Help: "bundle to print (default: the whole catalogue TOC)"},
		{Flags: []string{"--full"}, Action: cli.StoreTrue,
			Help: "catalogue TOC: print the structured per-bundle block " +
				"(description, concept count, directories, types, tags) " +
				"instead of the default one-line name+description " +
				"listing; with a bundle arg: print the structured " +
				"bundle summary instead of the raw index.md"},
		cli.JSON(),
	}
}

// bundleDescription is Python bundle_description: the intro paragraph of a bundle's entry file
// (INDEX-MAP.md, else index.md).
func bundleDescription(bp string) (string, error) {
	for _, fn := range []string{"INDEX-MAP.md", "index.md"} {
		if fp := catalogue.Join(bp, fn); catalogue.RealFS.IsFile(fp) {
			_, desc, err := catalogue.IndexH1AndDesc(fp, catalogue.RealFS)
			return desc, err
		}
	}
	return "", nil
}

// bundleTopDirs is Python bundle_top_dirs: the immediate subdirectories of a bundle, sorted,
// without hidden directories and assets/.
func bundleTopDirs(bp string) ([]string, error) {
	names, err := catalogue.RealFS.ListDir(bp)
	if err != nil {
		return nil, err
	}
	dirs := []string{}
	for _, n := range names {
		if catalogue.RealFS.IsDir(catalogue.Join(bp, n)) && !strings.HasPrefix(n, ".") && n != "assets" {
			dirs = append(dirs, n)
		}
	}
	sort.Strings(dirs)
	return dirs, nil
}

// bundleTypesAndTags is Python bundle_types_and_tags: the sorted types and tags used across a
// bundle's concepts.
func bundleTypesAndTags(bp string) (types, tags []string, err error) {
	typeSet, tagSet := map[string]bool{}, map[string]bool{}
	for _, ap := range catalogue.IterConcepts(bp, true) {
		text, err := catalogue.ReadFile(ap)
		if err != nil {
			return nil, nil, err
		}
		data := frontmatter.Read(text).Data()
		if t := frontmatter.Text(data, "type", ""); t != "" {
			typeSet[t] = true
		}
		for _, tag := range frontmatter.Tags(data) {
			tagSet[tag] = true
		}
	}
	for t := range typeSet {
		types = append(types, t)
	}
	for t := range tagSet {
		tags = append(tags, t)
	}
	sort.Strings(types)
	sort.Strings(tags)
	return types, tags, nil
}

func conceptCount(bp string) int {
	n := 0
	for range catalogue.IterConcepts(bp, true) {
		n++
	}
	return n
}

// renderBundleLine is Python render_bundle_line: name and concept count, prime's compact form.
func renderBundleLine(root, b string) string {
	return b + " (" + strconv.Itoa(conceptCount(catalogue.Join(root, b))) + " concepts)"
}

// renderBundleCompact is Python render_bundle_compact: name and one-line description, the
// catalogue-wide default of `index`.
func renderBundleCompact(root, b string) (string, error) {
	desc, err := bundleDescription(catalogue.Join(root, b))
	return b + ": " + pytext.Collapse(desc), err
}

// renderBundleBlock is Python render_bundle_block.
func renderBundleBlock(root, b string, full bool) (string, error) {
	bp := catalogue.Join(root, b)
	desc, err := bundleDescription(bp)
	if err != nil {
		return "", err
	}
	lines := []string{"bundle: " + b, "description: " + pytext.Collapse(desc), "concepts: " + strconv.Itoa(conceptCount(bp))}
	dirs, err := bundleTopDirs(bp)
	if err != nil {
		return "", err
	}
	if len(dirs) > 0 {
		lines = append(lines, "directories:")
		for _, d := range dirs {
			lines = append(lines, "- "+d)
		}
	}
	if full {
		types, tags, err := bundleTypesAndTags(bp)
		if err != nil {
			return "", err
		}
		lines = append(lines, "types: "+strings.Join(types, ", "), "tags: "+strings.Join(tags, ", "))
	}
	return strings.Join(lines, "\n"), nil
}

// bundleSummaryJSON is Python _bundle_summary_json: compact by default, concept count and
// directories only with full.
func bundleSummaryJSON(root, b string, full bool) (envelope.Obj, error) {
	bp := catalogue.Join(root, b)
	desc, err := bundleDescription(bp)
	if err != nil {
		return nil, err
	}
	summary := envelope.O("bundle", b, "description", pytext.Collapse(desc))
	if full {
		dirs, err := bundleTopDirs(bp)
		if err != nil {
			return nil, err
		}
		summary.Set("concepts", conceptCount(bp))
		summary.Set("directories", dirs)
	}
	return summary, nil
}

// conceptsJSON is Python _concepts_json: every concept under bp, sorted by concept id.
func conceptsJSON(bp string) ([]envelope.Obj, error) {
	now := spec.Utcnow()
	entries := sortedConcepts(bp)
	concepts := make([]envelope.Obj, 0, len(entries))
	for _, e := range entries {
		meta, fm, err := catalogue.MetaAndFm(e.ap, catalogue.RealFS)
		if err != nil {
			return nil, err
		}
		tier, stale := spec.TrustFields(fm, now)
		concepts = append(concepts, envelope.O("id", e.cid, "title", meta.Title, "type", meta.Type,
			"description", meta.Description, "tier", tier, "stale", stale))
	}
	return concepts, nil
}

// runIndex is Python cmd_index.
func runIndex(root string, a *cli.Args) (any, error) {
	bundle, full := a.String("bundle"), a.Bool("full")
	if bundle != "" {
		if err := catalogue.RequireBundleDir(root, bundle); err != nil {
			return nil, err
		}
	}
	bundles, err := catalogue.ListBundles(root)
	if err != nil {
		return nil, err
	}
	if a.JSON {
		if bundle != "" {
			concepts, err := conceptsJSON(catalogue.Join(root, bundle))
			if err != nil {
				return nil, err
			}
			return envelope.O("bundle", bundle, "concepts", concepts), nil
		}
		summaries := make([]envelope.Obj, len(bundles))
		for i, b := range bundles {
			if summaries[i], err = bundleSummaryJSON(root, b, full); err != nil {
				return nil, err
			}
		}
		return envelope.O("bundles", summaries), nil
	}
	w := newOut()
	defer w.Flush()
	if bundle != "" {
		return nil, printBundle(w, root, bundle, full)
	}
	// catalogue TOC: compact by default (name + one-line description); --full restores the
	// structured per-bundle block
	for _, b := range bundles {
		if !full {
			line, err := renderBundleCompact(root, b)
			if err != nil {
				return nil, err
			}
			printf(w, "%s\n", line)
			continue
		}
		block, err := renderBundleBlock(root, b, true)
		if err != nil {
			return nil, err
		}
		printf(w, "%s\n-----\n", block)
	}
	return nil, nil
}

// printBundle prints one bundle: the structured block with full, else its entry file, else a
// listing synthesised from its concepts.
func printBundle(w io.Writer, root, bundle string, full bool) error {
	bp := catalogue.Join(root, bundle)
	if full {
		block, err := renderBundleBlock(root, bundle, true)
		printf(w, "%s\n", block)
		return err
	}
	for _, fn := range []string{"INDEX-MAP.md", "index.md"} {
		if p := catalogue.Join(bp, fn); catalogue.RealFS.IsFile(p) {
			text, err := catalogue.ReadFile(p)
			printf(w, "%s\n", text)
			return err
		}
	}
	printf(w, "# %s\n\n", bundle)
	for _, e := range sortedConcepts(bp) {
		meta, err := catalogue.MetaOf(e.ap, catalogue.RealFS)
		if err != nil {
			return err
		}
		desc := ""
		if meta.Description != "" {
			desc = " - " + meta.Description
		}
		printf(w, "* [%s](%s.md) [%s]%s\n", meta.Title, e.cid, meta.Type, desc)
	}
	return nil
}
