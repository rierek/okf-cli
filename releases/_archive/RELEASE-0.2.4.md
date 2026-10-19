# okf-cli 0.2.4

Release 0.2.4 is a hotfix on 0.2.3.

## Why

`okf` read `TAGS.md` and `TYPES.md` only as pipe tables. A file in block form (`### \`tag\``) gave an empty set: `check --strict` flagged every tag and `prime` showed 0 tags. `tags --register` re-rendered `TAGS.md` from a fixed header and a table and so deleted frontmatter, own prose and check sections.

## What changed

- Both registries are read in table form, block form or mixed. Lines in code fences never count.
- `tags --register` only inserts entries; every other byte stays. `.okf.toml` `registry_format = "table" | "block"` (default `table`) sets the form of new entries; any other value is `invalid_input` (exit 2).
- New command `okf registry convert TAGS.md|TYPES.md --to block|table [--apply]`: previews a diff, rewrites the entries in the target form, keeps the prose, refuses lossy conversions.
- README "Registry format". Version `0.2.4` in `pyproject.toml`.

## Deploy steps after PO approval

1. In `repo/` on `main`: `git merge --no-ff milestone/0.2.x`, check `git diff --quiet milestone/0.2.x HEAD`, run `just test`, then `git push origin main`.
2. Tag the merge commit: `git tag -a rel-0-2-4 -m "okf-cli 0.2.4" && git push origin rel-0-2-4`, then watch the run and verify the provenance with `slsa-verifier`.
3. Restart the agent sessions: the MCP server and the skill links point to `repo/` and pick up the new code.
