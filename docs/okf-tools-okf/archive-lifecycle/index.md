# archive-lifecycle

The okf-cli side of the catalogue archive: the topology and its two verbs, the precedence rule that keeps wikilinks resolving, and the retrieval dimension that keeps archived material invisible by default. Distilled from `docs/okf-archive-lifecycle/SPEC.md` (milestone `okf-cli-huow` and its follow-up epic, 2026-08-09/10) when that theme folder was cleared away after acceptance. The requirement table R-01…R-15 and the acceptance table A01–A16 live on in the git history from commit `1eea173`; what mattered beyond a one-time acceptance yardstick is here.

## Contents

<!-- okf:index -->
* [Active beats archived when a wikilink resolves, and the move simulation must agree](/okf-tools-okf/archive-lifecycle/active-beats-archived-in-wikilink-resolution.md) - Archiving a concept would strand every inbound ``[[x]]`` as unresolved, so the basename index includes _archive/ — but with a precedence rule, otherwise archive-then-recreate makes every such link ambiguous. The same rule has to run in the dry-run's index simulation.
* [include_archive is a field of FindFilters, and the index needs two staleness counters](/okf-tools-okf/archive-lifecycle/include-archive-as-a-retrieval-dimension.md) - The archive is invisible by default across every retrieval arm; the flag became the fourth field of the FindFilters value object rather than a fifth loose argument, the SQL exclusion needs ESCAPE because _ is a LIKE wildcard, and fts_meta needs separate active/archived counters or the move goes unnoticed.
* [The archive is a directory, and archive/restore are its only verbs](/okf-tools-okf/archive-lifecycle/archive-topology-and-verbs.md) - An archived concept lives at _archive/<bundle>/<cid>.md at catalogue level, never behind a frontmatter flag; archive and archive --restore each take one path and derive the other, guarded in both directions.
<!-- /okf:index -->
