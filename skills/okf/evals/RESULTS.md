# okf skill eval results

Reproduce everything: `just skill-eval` (= `python3 scripts/skill-eval.py`, defaults: haiku-4-5 as `small`, sonnet-5-5 as `large`, thinking `low`, ~$5 per full run; `--only <id-prefix,...>`, `--models name=id,...`, `--skill-dir <older skill export>` for before/after, `--materialise-only` to check the 38 fixtures without an agent).
Each scenario x model runs in its own tmpdir with a fake HOME, `okf-cli` as a wrapper to `cli/okf-cli.py`, the skill copied in without `evals/` (answer key out of reach), `omp -p --mode json --tools read,bash,edit,write,grep,glob`. Routing = reference files the agent opened (read tool or shell); outcome = programmatic checks on the final files, CLI state and transcript (schema: docstring of `scripts/skill-eval.py`). "SKILL.md opened" = agent read `skill://okf`. The harness tells the agent nobody can answer questions, so "ask the user" steps show up as stated assumptions.

## Latest run

<!-- results:begin -->
Run 2026-10-11 · thinking `low` · small = `claude-haiku-4-5`, large = `claude-sonnet-5-5` · 38 scenarios · routing = required references opened (R), outcome = programmatic checks (O)

| scenario | workflow | small R / O | large R / O | notes |
|---|---|---|---|---|
| retrieval-stale-index-superseded | retrieval | pass / pass | pass / pass |  |
| retrieval-negative-result | retrieval | pass / pass | pass / pass |  |
| retrieval-cli-fallback | retrieval | pass / FAIL | pass / pass | small: skill never loaded (SKILL.md not read); uses the python3 okf-cli.py form \| transcript_cmd /python3?\s+\S*okf-cli\.py/ absent (0 hit) |
| retrieval-autodetect-docs | retrieval | pass / pass | pass / pass |  |
| retrieval-filter-type-tag | retrieval | pass / pass | pass / pass |  |
| create-bundle-in-catalogue | create-bundle | pass / pass | pass / pass |  |
| create-bundle-new-catalogue | create-bundle | pass / pass | pass / pass |  |
| create-bundle-register-type | create-bundle | pass / pass | pass / pass |  |
| create-bundle-closed-tags | create-bundle | pass / pass | pass / pass |  |
| create-bundle-nested-dirs | create-bundle | pass / pass | pass / pass |  |
| write-new-with-source | write-concepts | pass / pass | pass / pass |  |
| write-update-existing | write-concepts | FAIL / FAIL | pass / pass | small: generated.at refreshed \| fm_not_contains cat/eng/architecture/order-service.md /at:\s*2025-01-01T00:00:00Z/; missing refs ['write-concepts.md'] |
| write-canon-insert | write-concepts | FAIL / FAIL | pass / pass | small: skill never loaded (SKILL.md not read); consumer copy made by sync-insert \| file_contains cat/eng/operations/restart-worker.md /<!-- okf:sync .*hash=/; sync-insert: preview before --apply \| cmd_order: /sync-insert\b.*--apply/ never ran; missing refs ['write-concepts.md'] |
| write-canon-update | write-concepts | FAIL / FAIL | pass / pass | small: skill never loaded (SKILL.md not read); cmd 'okf-cli --root cat sync-status' exit 1: 'malformed          eng/operations/restart-worker.md ?#?\nsync-status: 0 synced, 0 source-changed, 0 consumer-modified, 0 both-changed, 0 source-missing, 1 malformed\n'; uses sync-update \| transcript_cmd /sync-updat |
| write-human-author | write-concepts | pass / pass | pass / pass |  |
| write-supersede-decision | write-concepts | pass / pass | pass / pass |  |
| write-yaml-quoting | write-concepts | FAIL / pass | pass / pass | small: ; missing refs ['write-concepts.md'] |
| maintain-add-decision-and-rename | maintain-catalogue | FAIL / pass | pass / pass | small: ; missing refs ['maintain-catalogue.md'] |
| maintain-rename-directory | maintain-catalogue | pass / pass | pass / pass |  |
| maintain-merge-tags | maintain-catalogue | pass / pass | pass / pass |  |
| maintain-archive-obsolete | maintain-catalogue | pass / pass | pass / pass |  |
| maintain-health-routine | maintain-catalogue | pass / pass | pass / pass |  |
| maintain-stale-report | maintain-catalogue | FAIL / pass | FAIL / pass | small: ; missing refs ['maintain-catalogue.md']<br>large: ; missing refs ['maintain-catalogue.md'] |
| integrate-full | integrate-project-knowledge | pass / FAIL | pass / pass | small: code mention updated \| file_contains repo/src/app.py /docs/shop//; also-read missed ['write-concepts.md'] |
| integrate-move-one-file | integrate-project-knowledge | pass / pass | pass / pass |  |
| integrate-plan-only | integrate-project-knowledge | pass / pass | pass / pass |  |
| integrate-mount-in-catalogue | integrate-project-knowledge | pass / pass | pass / pass |  |
| integrate-add-knowledge-later | integrate-project-knowledge | pass / pass | pass / pass |  |
| ctx-create | context-bundles | pass / pass | pass / pass |  |
| ctx-read | context-bundles | FAIL / pass | pass / pass | small: ; missing refs ['context-bundles.md'] |
| ctx-dead-entry | context-bundles | FAIL / FAIL | pass / pass | small: positions renumbered \| file_contains cat/_ctx/onboarding.md /\\|\s*2\s*\\|\s*pflicht\s*\\|.*use-postgres/; missing refs ['context-bundles.md'] |
| ctx-reorder | context-bundles | pass / pass | pass / pass |  |
| ctx-which-contain | context-bundles | FAIL / pass | pass / pass | small: ; missing refs ['context-bundles.md'] |
| migrate-basic-citations | migrate-bundle-to-v0.2 | pass / FAIL | pass / pass | small: alice not assumed to be the writer \| fm_not_contains cat/finance/metrics/revenue.md /by:\s*[\"']?human:alice/; also-read missed ['write-concepts.md'] |
| migrate-adhoc-mapping | migrate-bundle-to-v0.2 | pass / pass | pass / pass |  |
| migrate-stale-after | migrate-bundle-to-v0.2 | pass / pass | pass / pass |  |
| migrate-no-invented-trust | migrate-bundle-to-v0.2 | pass / pass | pass / pass |  |
| migrate-citations-two-concepts | migrate-bundle-to-v0.2 | pass / pass | pass / pass |  |

| model | scenarios | SKILL.md opened | routing pass | outcome pass |
|---|---|---|---|---|
| small | 38 | 35/38 | 29/38 | 31/38 |
| large | 38 | 38/38 | 37/38 | 38/38 |
<!-- results:end -->

## Before / after (same 38 scenarios, same graders, one run each)

| model | text | SKILL.md opened | routing pass | outcome pass |
|---|---|---|---|---|
| small (haiku-4-5) | before (git HEAD skill) | 36/38 | 24/38 | 31/38 |
| small (haiku-4-5) | after | 35/38 | 29/38 | 31/38 |
| large (sonnet-5-5) | before | 38/38 | 32/38 | 33/38 |
| large (sonnet-5-5) | after | 38/38 | 37/38 | 38/38 |

The small model is noisy: three full runs on the changed text gave outcome 28, 29 and 30 of 38 (31 in the table after a grader fix; later runs also carry further text fixes), so its outcome rate is flat within noise; routing and the large model's outcome improved beyond it. A re-run of the nine failing small scenarios twice passed 7 of 9 in at least one run (flakes: stale-index retrieval, archive, add-decision, write-supersede, write-canon-update, integrate-full, integrate-add-later); `integrate-mount-in-catalogue` and `migrate-basic-citations` failed 3 of 3 for small before the last two text fixes (final run: mount passes, migrate-basic still fails).

Scenarios that flipped (large): `write-canon-insert`, `maintain-add-decision-and-rename` (no preview before `--apply`), `retrieval-stale-index-superseded` (no `prime`), `migrate-basic-citations` (assumed `human:alice`), plus routing misses for the ctx, tags, archive and canon scenarios. Flipped (small): `maintain-health-routine`, `maintain-archive-obsolete`, `write-human-author`, `write-supersede-decision`, `maintain-add-decision-and-rename`; regressed in the final run only by flakes where the agent skipped the reference (`ctx-dead-entry`, `write-canon-insert`, `write-canon-update`, `retrieval-cli-fallback`, `integrate-full`). `retrieval-autodetect-docs` failed for large in the first run only because of an over-strict grader (answer mentioned the 180-day rule as contrast); that check was removed.

## Skill text fixes (evidence in the table above)

1. `SKILL.md`, new paragraph after the intro and an unconditional sentence under "Route by intent": open the routed reference file before the first command of a workflow. Cause: both models answered write/maintain tasks from the CLI `--help` and missed previews, `generated`, `sources` keys and `--check` steps. Effect: routing 24 -> 29 (small), 32 -> 37 (large).
2. `SKILL.md` hard rule 5: never put `--apply` on the first run and never chain preview and `--apply` in one command (large skipped the preview in `write-canon-insert`, `maintain-archive-obsolete`, `maintain-add-decision-and-rename`). `write-concepts.md` section 7 repeats it for `sync-insert`. Effect: all three pass for large.
3. `SKILL.md` hard rule 11: every written concept carries `generated { by: <own agent id>, at: date -u }` and `sources` with `resource`; never `author`/`url` keys or an invented `human:<name>`; an old `author` key does not prove authorship. Cause: small wrote `author: human:erik` and `sources: - url:`. Effect: `write-human-author` passes.
4. `SKILL.md` first step 3: run `prime --compact` before the first `find`/`read`/`index` (large answered from `find` and `read` alone). Effect: `retrieval-stale-index-superseded` passes for large.
5. `SKILL.md` route table: new row for mounting a project bundle into a shared catalogue (integrate-project-knowledge.md, section 7); small had opened `maintain-catalogue.md` and made a relative symlink. Effect: `integrate-mount-in-catalogue` passes.
6. `migrate-bundle-to-v0.2.md` (`author` row and "Deciding values"): `author` alone is no proof; without an answer keep `author` and the old date keys, leave `generated` out, report the concept, never write `human:unknown` (small invented `human:unknown`; large assumed `human:alice`). Effect: large passes `migrate-basic-citations` and `migrate-no-invented-trust`.

## Helper script

`skills/okf/scripts/adopt-files.py` scripts the per-file steps 2 to 5 of `integrate-project-knowledge.md` section 5 (git mv, frontmatter, all markdown links including `../` forms, `rewrite-path` for code mentions, `fix-crosslinks`, `check`, leftover scan; preview by default). Evidence: in the first run the large model left `src/app.py` pointing at the old path and the small model moved files with plain writes, so the manual five-pass was not followed reliably. After the change the large model used the script in `integrate-full` and `integrate-move-one-file`; the small model never ran it (it does not open the section that names it) and missed the code mention in `integrate-full`.

## Unresolved

- `small` often opens `SKILL.md` but not the routed reference for tasks it believes it knows (`maintain-stale-report`, `ctx-read`, `ctx-which-contain`, canon and update scenarios) and then misses provenance or preview rules. Root cause: model compliance, not a wrong text; no stronger wording helped beyond the numbers above. `maintain-stale-report` also fails routing for large because the stale check is answerable from `find`/`read` (secondary routing noise, outcome passes).
- `migrate-basic-citations` fails for small in every run (assumes `human:alice` from the `author` key even after opening the reference).
- `integrate-full` for small: code mention `src/app.py` is not updated when it does not use the helper (outcome flake, 1 of 3 runs).
- `retrieval-cli-fallback` for small passed when it opened the skill and failed once when it never read it (no `okf-cli` on PATH, answered by grepping files).
- Single runs per cell; the table is a smoke signal, not a significance test. Results of the first full run (old text, older graders) are not kept.
