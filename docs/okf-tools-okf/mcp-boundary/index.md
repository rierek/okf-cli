# mcp-boundary

Durable findings about the CLI↔MCP seam — what `mcp/okf_mcp.py` may hand a
consumer, and which CLI output shapes survive that hand-off.

## Contents

<!-- okf:index -->
* [MCP output budget and the shape of index --json](/okf-tools-okf/mcp-boundary/mcp-output-budget-and-index-json-shape.md) - Catalogue-wide `index --json` returns a bundle summary (counts, not concept lists) in parity with the text branch, and run_okf caps every MCP result at MAX_OUTPUT_CHARS with an actionable error instead of returning a payload no consumer accepts.
<!-- /okf:index -->
