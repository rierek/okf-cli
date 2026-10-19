package find

// findEpilog is the text after the options of `okf find --help` (Python _FIND_EPILOG): the rank and
// score lines and the filters section, line breaks kept (argparse RawDescriptionHelpFormatter).
const findEpilog = "rank / score lines:\n" +
	"  Every hit's headline number is `rank: N` — its 1-based position in the\n" +
	"  delivered list. It is the one scale comparable across a mixed-arm result,\n" +
	"  because it IS the list order, and it claims nothing about the two arms'\n" +
	"  raw scores being on one scale (D12: fuse_conditional hands the ranking to\n" +
	"  whichever arm owns it, it never blends the two by score). Those raw,\n" +
	"  non-comparable values stay out of the default output and show only with\n" +
	"  --breakdown, one `score:` line per hit naming which arm produced it:\n" +
	"    a/100        the FTS5/BM25 lexical arm, relative to this run's own top\n" +
	"                 hit.\n" +
	"    a/(6 * n)    the substring fallback used when no FTS index is available:\n" +
	"                 per query term 3 for a title hit, 2 for a tag hit, 1 for a\n" +
	"                 body hit, capped at one per field per term — so the maximum\n" +
	"                 is 6 * number of terms.\n" +
	"    cosine X.XX  the semantic arm's raw cosine similarity — printed on its\n" +
	"                 own line, not folded into an a/100 fraction, because that\n" +
	"                 shape would invite comparing it against a lexical score\n" +
	"                 (D12, same rule as above).\n" +
	"  `provenance:` names the arm that produced the line. Degradations (index\n" +
	"  absent or stale, embedding backend unavailable) are announced on stderr,\n" +
	"  one note per degraded arm.\n" +
	"\n" +
	"filters:\n" +
	"  --where EXPR selects the concepts the answer may hold, whichever arm owns\n" +
	"  the ranking: the lexical, substring and semantic arms all apply it before\n" +
	"  the result is cut to --limit. Without `archived` in the expression,\n" +
	"  archived concepts are hidden; the semantic arm never covers them.\n"
