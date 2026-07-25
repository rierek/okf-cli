# REFERENCES — okf-cli + okf-mcp Reifegraderhöhung

## Code
- CLI (20 Verben, 85 KB, dependency-free): `/Users/erik/Obsidian/tools/okf-tools/cli/okf-cli.py`
  - `cmd_find` Ranking: `:538-574` · Verb-Registrierung: `:1884-1976` · Root-Resolution: `:72-73`, `:1983-1984`
- MCP-Server (FastMCP, 9 Tools): `/Users/erik/Obsidian/tools/okf-tools/mcp/okf_mcp.py` (`:119-120` init, `:47` OKF_CLI-Override)
- CLI-Wrapper (Bash): `/Users/erik/.local/bin/okf-cli`
- Test-Suite (22 Klassen/98 Methoden, nur Python-Funktion-Ebene): `/Users/erik/Obsidian/tools/okf-tools/cli/test_okf_cli.py`

## Daten / Katalog
- Catalogue-Root: `/Users/erik/Obsidian/Knowledge-Catalogue/` (22 Bundles)
- Schema: `TYPES.md` · `PROPERTIES.md` · `TAGS.md` · `SPEC.md` (Root)
- Verwaiste Embeddings: `/Users/erik/Obsidian/Knowledge-Catalogue/.tagvec/tag_vectors.sqlite` (1277 Zeilen, bge-m3 + voyage-3-large; toter Code, Herkunfts-Skript außerhalb Repo)

## MCP-Registrierung
- `/Users/erik/.claude.json` → `mcpServers.okf` (stdio, `uv run --with mcp .../okf_mcp.py`)

## Kanonische Doku (stale, aber Referenz — D07)
- `/Users/erik/Obsidian/Knowledge-Catalogue/okf-meta-wiki/okf-cli-mcp-overview.md` (228 Z., Stand 2026-07-12; listet 18 statt 20 Verben)

## Session-Sammlung (dieser Ordner)
- `00-synthesis.yaml` · `01-storage` · `02-verbs` · `03-mcp-config` · `04-skills` · `05-cli-docs` · `06-retrieval-quality` · `07-tests-and-usage` .yaml
- `DECISIONS.md` · `QUESTIONS.md` · `TASKS.md` · `DESIGN.md`
