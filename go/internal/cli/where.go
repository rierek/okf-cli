package cli

// WhereArg is the --where option of every filter command (Python _add_filters): find, list,
// recent and the tag verbs call it and nothing else, so the filter language, its help and its
// errors exist once.
func WhereArg() Arg {
	return Arg{
		Flags:   []string{"--where"},
		Metavar: []string{"EXPR"},
		Help: "select concepts by an expression: `field op value` with op one of = != < <= > >= " +
			"~ (contains), or `field in (a, b)`; combine with and, or, not and parentheses. " +
			"Fields: type, tag, path (<bundle>/<concept-id>), archived (true or false), tier " +
			"(unverified, machine-confirmed or human-reviewed), stale (true or false), status " +
			"(an absent status is stable) and any frontmatter key (nested: a.b; through lists: " +
			"verified.by, sources.resource). Timestamp keys (generated.at, verified.at, " +
			"stale_after, usage_window.from/to, sources.last_modified, sources.usage_window.from/to) " +
			"compare as instants and take an ISO 8601 value with an explicit offset: " +
			"stale_after < 2026-10-01T00:00:00Z. Archived concepts are hidden unless the expression " +
			"names `archived`. Quote a value holding spaces, + or other characters: 'a b'. " +
			"Example: (type = Runbook and tag != draft) and path ~ home-lab/",
	}
}
