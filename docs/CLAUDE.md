# /docs — okf-tools Knowledge (OKF)

This `/docs` folder is OKF-structured project knowledge, driven by the `/okf-p` skill.

## Zones (Docs-Standard, `/tools/CLAUDE.md`)
- **`okf-tools-okf/`** — the OKF bundle. Strict: every non-reserved `.md` has YAML
  frontmatter with a non-empty `type`. Written only via `/okf-p ingest` (never by hand).
- **`okf-tools-okf-inbox/`** — git-ignored staging for `/okf-p ingest` sources.
- **`_free-notes/`** — freeform, git-ignored, no rules. Scratch, drafts, dumps.
- **`plans/<beans-id>-<slug>/`** — mandatory home for plan-skills (writing-plans).
- **`docs-index-map.md`** — docs-root Map of Content, loaded by ce-start (Awareness).

## Type + config authority
Valid `type` values and all tooling config: see **`.okf.toml`** →
central `TYPES.md` at `/Users/erik/Obsidian/Knowledge-Catalogue/TYPES.md`. Do not add a local TYPES.md.

## Working here
- Knowledge → the bundle (`/okf-p ingest`). Work-state → **beans** (`beans list --ready`;
  no `ROADMAP.md`, beans supersedet). Status/hand-over → `SSTD.md` (`/sstd` format, pointer).
- `GLOSSARY.md` (domain terms) is maintained via the `ce-glossary` skill.
- Conformance: `/okf-p audit` (wraps `okf-cli check`). Must be `OK — 0 violations`.
- This is a plain git repo — normal Read/Write/Edit/git. Not the Obsidian Vault.

## Repo-Kontext
`okf-tools` bündelt die komplette OKF-Tool-Kette in einem Repo, aus
`~/Obsidian/Knowledge-Catalogue` extrahiert (2026-07-18, Git-Historie via
`git filter-repo` + Merge erhalten). Drei Tech-Stacks, je eigener Unterordner:

| Unterordner | Inhalt | Stack |
|---|---|---|
| `cli/` | `okf-cli.py`, `test_okf_cli.py` — Kern-Substanz | Python |
| `mcp/` | `okf_mcp.py` — dünner subprocess-Wrapper um `cli/okf-cli.py` | Python |
| `plugin/` | Skeleton, Zweck noch offen | TypeScript/Obsidian-Plugin-API (geplant) |

Allgemeines Wissen über das OKF-System selbst bleibt bewusst im KC-Bundle
`okf-meta-wiki` (nicht hier — Konzeptwissen, nicht Projekt-Substanz).

**Worktree-Weiche:** main-direkt erlaubt (Solo, ein Repo für alle drei Komponenten).
