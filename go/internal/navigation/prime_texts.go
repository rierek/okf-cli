// The guide texts of `prime`: cli/okf/prime.py, byte for byte.

package navigation

// primeIntro is _PRIME_INTRO.
const primeIntro = "# OKF Knowledge Catalogue — agent onboarding\n" +
	"\n" +
	"The catalogue is a read-mostly, LLM-facing knowledge store, separate from any\n" +
	"Obsidian vault it may be opened in. It holds thematic *bundles*; a bundle is a\n" +
	"folder of Markdown *concepts*, each with YAML frontmatter carrying a non-empty\n" +
	"`type`. A concept-id is its path below the bundle, minus `.md`. The store is a\n" +
	"plain git repo — ordinary file tools and git apply.\n" +
	"\n" +
	"Every invocation needs `--root <catalogue>`; without it the CLI searches cwd and\n" +
	"its ancestors for a catalogue marker and fails if it finds none. It never falls\n" +
	"back to its own script directory.\n" +
	"\n" +
	"## Retrieve — by command, not by blind grep\n" +
	"\n" +
	"Progressive disclosure: widen only when the cheaper step left the question open.\n" +
	"\n" +
	"  1. find \"<query>\"             ranked search across all bundles; narrow it with\n" +
	"                                --where \"type = Runbook and path ~ <bundle>/\"\n" +
	"  2. index [<bundle>]           what bundles and directories exist\n" +
	"  3. toc <bundle>[/<concept>]   headings before bodies — the cheapest way to\n" +
	"                                decide whether a page is worth reading. A bare\n" +
	"                                <bundle> or <bundle>/<subdir> resolves to its\n" +
	"                                index.md, so the names listed below are the\n" +
	"                                argument, verbatim.\n" +
	"  4. read <bundle>/<concept>    the page itself. `read --section \"<heading>\"`\n" +
	"                                prints one section; `read --follow N` adds the\n" +
	"                                pages it links to (`--inbound`: also those\n" +
	"                                linking to it)\n" +
	"  5. refs / wikilinks           follow the graph out of a page\n" +
	"\n" +
	"Reach for `toc` before `read`: a concept can run long, and its headings usually\n" +
	"settle the question or name the section to read. Concepts cross-link in\n" +
	"Markdown — following a link beats re-running a search, and a large bundle's\n" +
	"`index.md` is the map its concepts hang from.\n" +
	"\n" +
	"## Write — through the ce-okf skill, never by hand\n" +
	"\n" +
	"Concepts are not hand-authored. The `ce-okf` skill routes a source to a bundle,\n" +
	"applies frontmatter and re-indexes. `index.md` listings are marker-managed and\n" +
	"generated (`reindex`) — never edit between the `<!-- okf:... -->` markers. Tag\n" +
	"edits go through `merge-tags` / `remove-tags`, not a search-and-replace. A\n" +
	"commit is allowed only once `check` reports zero violations.\n"

// primeIntroCompact is _PRIME_INTRO_COMPACT.
const primeIntroCompact = "# OKF Knowledge Catalogue — agent onboarding\n" +
	"\n" +
	"The catalogue is a read-mostly, LLM-facing knowledge store, separate from any\n" +
	"Obsidian vault it may be opened in. It holds thematic *bundles*; a bundle is a\n" +
	"folder of Markdown *concepts*, each with YAML frontmatter carrying a non-empty\n" +
	"`type`. A concept-id is its path below the bundle, minus `.md`. The store is a\n" +
	"plain git repo — ordinary file tools and git apply.\n" +
	"\n" +
	"## Retrieve — by command, not by blind grep\n" +
	"\n" +
	"Progressive disclosure: widen only when the cheaper step left the question open.\n" +
	"\n" +
	"  1. find \"<query>\"             ranked search across all bundles; narrow it with\n" +
	"                                --where \"type = Runbook and path ~ <bundle>/\"\n" +
	"  2. index [<bundle>]           what bundles and directories exist\n" +
	"  3. toc <bundle>[/<concept>]   headings before bodies — the cheapest way to\n" +
	"                                decide whether a page is worth reading. A bare\n" +
	"                                <bundle> or <bundle>/<subdir> resolves to its\n" +
	"                                index.md, so the names listed below are the\n" +
	"                                argument, verbatim.\n" +
	"  4. read <bundle>/<concept>    the page itself. `read --section \"<heading>\"`\n" +
	"                                prints one section; `read --follow N` adds the\n" +
	"                                pages it links to (`--inbound`: also those\n" +
	"                                linking to it)\n" +
	"  5. refs / wikilinks           follow the graph out of a page\n" +
	"\n" +
	"## Write — through the ce-okf skill, never by hand\n" +
	"\n" +
	"Concepts are not hand-authored: `ce-okf` routes a source to a bundle, applies\n" +
	"frontmatter and re-indexes. `index.md` listings are marker-managed and\n" +
	"generated — never edit between the `<!-- okf:... -->` markers. A commit is\n" +
	"allowed only once `check` reports zero violations.\n"

// findScalesCompact is _FIND_SCALES_COMPACT.
const findScalesCompact = "Each result line's headline number is `rank: N` — its 1-based position in\n" +
	"the delivered list, the one scale comparable across a mixed-arm result\n" +
	"because it IS the list order (D12: handover, never blend by score). The\n" +
	"arm's own raw value is not in that column; pass `--breakdown` to see it,\n" +
	"per hit: `score: a/b` for a lexical hit (a/100 is the FTS5/BM25 arm,\n" +
	"relative to this run's own top hit; a/(6 * n) is the substring fallback\n" +
	"used when no FTS index is available, over n query terms), `score: cosine\n" +
	"X.XX` for a semantic hit — its own scale, never the same column as a\n" +
	"lexical a/b. `provenance:` names the arm that produced the line.\n" +
	"Degradations are announced on stderr.\n"
