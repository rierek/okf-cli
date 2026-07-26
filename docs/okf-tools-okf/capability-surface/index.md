# capability-surface

Durable decisions and findings from the capability-surface plan
(`docs/okf-cli-capability-surface/PLAN.md`, epic `okf-cli-5uog`). The plan
itself stays a file — only its decision and finding passages are concepts here.

## Contents

<!-- okf:index -->
* [Capability-surface plan — decisions (D01-D04)](/okf-tools-okf/capability-surface/capability-surface-decisions.md) - argparse becomes the single source of truth for okf-cli's command surface; both a flat and a grouped view render from it; MCP gains build-index, prime and info.
* [find's documented score formula went stale after the FTS arm shipped](/okf-tools-okf/capability-surface/find-score-formula-drift.md) - The deleted docstring's "achieved/max = 6 * number of terms" score explanation only ever described the substring fallback; since the FTS arm shipped, find reports a 0..100 relative scale — the carried-forward prose had to be corrected, not copied.
<!-- /okf:index -->
