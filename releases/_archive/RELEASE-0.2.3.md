# okf-cli 0.2.3

Release 0.2.3 is a hotfix on 0.2.1. The number 0.2.2 is not used.

## Why

The MCP tool call `root="~/Obsidian/Knowledge-Catalogue"` failed with `not_found: root not found: <cwd>/~/Obsidian/Knowledge-Catalogue`. `catalogue_root()` did not expand `~`. Besides, the central Knowledge-Catalogue could only be reached by its absolute path. Inside a project with its own catalogue (a `docs/` child with `SPEC.md` and `TYPES.md`), the user config root never applied.

## What changed

- `okf --root '~/x'` and the MCP parameter `root` expand a leading `~`.
- New switch `okf --global` (MCP: `use_global=true` on every tool): use the `root` of `~/.config/okf/config.toml`, even when a catalogue lies above cwd. No configured root: `not_found` (exit 3). Together with `--root`: `invalid_input` (exit 2).
- The two catalogue modes are described in the server header, `SKILL.md` and the README.
- Version `0.2.3` in `pyproject.toml`.

## Deploy steps after PO approval

1. In `repo/` on `main`: `git merge --no-ff milestone/0.2.x`, check `git diff --quiet milestone/0.2.x HEAD`, run `just test`, then `git push origin main`.
2. Tag the merge commit: `git tag -a rel-0-2-3 -m "okf-cli 0.2.3" && git push origin rel-0-2-3`, then watch the run and verify the provenance with `slsa-verifier`.
3. Restart the agent sessions: the MCP server and the skill links point to `repo/` and pick up the new code.
