package cli

// directory is the command directory: every command of the okf binary with its group, its
// one-line summary and its flags, one entry per line. Group and summary of the 33 Python commands
// equal their registration (_sub in cli/okf/*.py); okf.install.CATALOGUE_FREE is the
// catalogue-free set. A command that exists only in Go is one more line, in any position:
// NewApp sorts the entries. Hidden keeps a command callable but out of the overview, the
// usage line, the command list and the invalid-choice message.
var directory = []Entry{
	{Name: "archive", Group: "maintenance", Summary: "move a concept into _archive/<bundle>/, or back with --restore (dry-run default)"},
	{Name: "build-index", Group: "search", Summary: "(re)build the FTS5 lexical search index at <root>/.fts/fts.sqlite (local only, no network)"},
	{Name: "build-semantic-index", Group: "search", Summary: "fill <root>/.tagvec/tag_vectors.sqlite's concept_emb table for every concept still missing a voyage-3-large embedding (NETWORK, requires VOYAGE_API_KEY)"},
	{Name: "check", Group: "maintenance", Summary: "conformance scan: §9 hard rules + local invariants"},
	{Name: "ctx", Group: "navigation", Summary: "context bundles: curated, ordered reading lists per topic (`ctx` lists them, `ctx <slug>` shows one)"},
	{Name: "find", Group: "search", Summary: "hybrid ranked search: lexical FTS5/BM25 arm plus semantic arm"},
	{Name: "fix-crosslinks", Group: "maintenance", Summary: "rewrite links to catalogue-root-absolute form (/bundle/subdir/concept.md)"},
	{Name: "fix-xml-tags", Group: "maintenance", Summary: "wrap `<tag>`/`<tag>.<tag2>` placeholders in inline code"},
	{Name: "index", Group: "navigation", Summary: "catalogue TOC (bundle names + one-line descriptions), or one bundle's index.md"},
	{Name: "info", Group: "navigation", Summary: "print catalogue schema docs (TYPES.md + PROPERTIES.md)"},
	{Name: "install", Group: "maintenance", Summary: "register okf, its agent skill, MCP server and shell completion with this machine's agents and shells (dry-run default; needs no catalogue)", CatalogueFree: true},
	{Name: "list", Group: "navigation", Summary: "list the complete, unranked set of concepts a required --where expression selects"},
	{Name: "merge-tags", Group: "tags", Summary: "merge/rename one or more tags into a target tag across concept frontmatter"},
	{Name: "migrate", Group: "maintenance", Summary: "migrate frontmatter to OKF 0.2: `timestamp` to `generated` (git), `status` per D37 (dry-run default)"},
	{Name: "normalize-tags", Group: "tags", Summary: "convert inline `tags: [...]` fields to YAML block-list form (local convention)"},
	{Name: "prime", Group: "navigation", Summary: "one-shot agent onboarding: usage guide, command directory, catalogue state and bundle TOC"},
	{Name: "read", Group: "navigation", Summary: "print one concept page"},
	{Name: "recent", Group: "navigation", Summary: "list the most recently created concepts, newest first"},
	{Name: "refs", Group: "search", Summary: "list inbound and outbound markdown links of a file"},
	{Name: "registry", Group: "maintenance", Summary: "reformat registry entries of TAGS.md or TYPES.md (table or block form); prose stays"},
	{Name: "reindex", Group: "maintenance", Summary: "(re)generate marker-bounded index listings: index.md one level, index-map.md the whole subtree"},
	{Name: "remove-tags", Group: "tags", Summary: "remove one or more tags from concept frontmatter (no merge target)"},
	{Name: "rename", Group: "maintenance", Summary: "move a concept + rewrite every inbound/outbound link + reindex (dry-run default)"},
	{Name: "rewrite-path", Group: "maintenance", Summary: "literal path-string rewrite across text files"},
	{Name: "sync-export", Group: "navigation", Summary: "print a canonical block's payload for materialisation elsewhere"},
	{Name: "sync-insert", Group: "maintenance", Summary: "materialise a canonical block inside a consumer concept (dry-run default)"},
	{Name: "sync-status", Group: "maintenance", Summary: "drift report for every materialised canon block"},
	{Name: "sync-update", Group: "maintenance", Summary: "re-materialise outdated consumer blocks from their canon owner (dry-run default)"},
	{Name: "tags", Group: "tags", Summary: "list all tags with usage counts, or fuzzy-search candidate tags"},
	{Name: "toc", Group: "navigation", Summary: "print a concept's headings (default: h2 only)"},
	{Name: "verify", Group: "maintenance", Summary: "record that a concept was checked against its sources"},
	{Name: "visualize", Group: "navigation", Summary: "write a viz.html concept graph for a bundle (embeds every concept body; needs network for cytoscape/marked)"},
	{Name: "wikilinks", Group: "maintenance", Summary: "report Obsidian wikilinks ([[…]]) and whether each resolves to a concept"},
}
