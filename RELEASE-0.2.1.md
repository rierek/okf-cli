# okf-cli 0.2.1

Release 0.2.1 is a hotfix on 0.2.0. It changes no code of the command `okf`: the CLI, the MCP server and the skills are those of 0.2.0.

## Why

The GitHub release `rel-0-2-0` carries no wheel, no sdist and no provenance. The repository was private when the tag was pushed. The provenance job stopped at the privacy check, but its upload step still published an empty release. The repository setting "immutable releases" then forbids adding files to it. That release stays as it is. 0.2.1 is the first release with all files.

## What changed

- `release.yml` builds the wheel and the sdist, makes the SLSA provenance, creates the GitHub release as a draft, attaches the three files and publishes last. A published immutable release takes no further file.
- `release.yml` has a dry run: start the workflow by hand (`workflow_dispatch`). It builds, makes provenance, creates a draft release `dry-run-<sha>`, checks that exactly three files are attached and deletes the draft. It never publishes and never creates a tag.
- Version `0.2.1` in `pyproject.toml`.

## Verify the provenance

Download the wheel and `multiple.intoto.jsonl` from the release, then run `slsa-verifier verify-artifact okf_cli-0.2.1-py3-none-any.whl --provenance-path multiple.intoto.jsonl --source-uri github.com/xRiErOS/okf-cli --source-tag rel-0-2-1`.

## Deploy steps after PO approval

1. In `repo/` on `main`: `git merge --no-ff milestone/0.2.x`, check `git diff --quiet milestone/0.2.x HEAD`, run `just test`, then `git push origin main`.
2. Tag the merge commit: `git tag -a rel-0-2-1 -m "okf-cli 0.2.1" && git push origin rel-0-2-1`, then watch the run.
3. Nothing changes on the machines that already run 0.2.0: the command, the wrapper and the callers are the same.
