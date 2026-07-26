---
# okf-cli-iksi
title: Follow-up capability surface 2026-07-26
status: todo
type: epic
priority: normal
created_at: 2026-07-26T15:09:34Z
updated_at: 2026-07-26T16:43:14Z
parent: okf-cli-wuiv
---

Follow-up epic for findings raised during the PO review of okf-cli-5uog on 2026-07-26. Holds side findings (NB) and rejects that no existing leaf covers.



## Requirements

**R-01 — An MCP consumer receives the degradation notes the CLI emits.** The CLI announces a degraded run on stderr (lexical index absent or stale, embedding backend unavailable). Those notes exist to make the caller act; the MCP wrapper discards them on a successful run, so the audience that most needs them never sees one. Source: PO review of okf-cli-5uog, 2026-07-26, side finding.

**R-02 — The conformance gate covers every option the CLI exposes, including the top-level parser's own.** The gate shipped by okf-cli-80nb iterates the subcommand parsers only. The epic's claim is that an undocumented option cannot merge; as built, that holds for the 21 subcommands and not for the top level. Source: ce-specs-reviewer during the okf-cli-80nb review, 2026-07-26, confirmed by mutation.

## Shared context for both leaves

**Repo:** `/Users/erik/Obsidian/tools/okf-tools`, branch `main`, main-direct (repo Worktree-Weiche: solo).

**Test baseline, measured live on 2026-07-26 after the predecessor epic landed:** `python3 -m unittest discover -s cli -p "test_*.py"` gives `Ran 279 tests` with exactly `failures=19, errors=2`. All 19F/2E are pre-existing in the crosslink suites. A leaf is done only when the count is still exactly 19F/2E plus its own new tests, all green. The suite prints stdout noise, so `tail` hides the summary — use `| grep -E "^(Ran |OK|FAILED)"`.

**Constraints binding both leaves:**

- Standard library only, no install, no external CLI framework. This is the CLI's defining constraint.
- Artifact language English: commit subjects and bodies, bean titles and bodies, code comments, docstrings. Chat with the PO stays German.
- Commits: `<type>(<scope>): <subject>`, subject max 50 characters, no `Co-Authored-By` trailer. Explicit paths in `git add`, never `-A`. Note that no `commit-msg` hook exists in `.git/hooks/` — the cap is discipline, not a guard.
- `~/Obsidian/Knowledge-Catalogue` is a separate git repo: read from it, never commit into it. Its `.fts/` is gitignored, so building an index there touches nothing versioned.
- No network in any test.

**Evidence discipline (LL-13, LL-17).** A claim of the form "verified" or "behaviour-preserving" is the one to check, not the one to skip. State the command executed and quote its observed output. Two further shapes carry the same risk and are just as unwatched: the mechanism claim ("done via X" — name the tool that actually produced the artefact) and the completeness claim ("the only change" — a quantifier that requires an enumeration).

**One lesson from the predecessor epic that applies directly here (LL-15).** Prose that becomes product text — help strings, docstrings, error messages — is a claim about the code, and its truth condition is the code. The defect this epic's R-01 fixes was created exactly this way: a docstring promised "degradations are announced on stderr" and nobody checked whether that channel reaches the reader. Verify any such text against the code before shipping it.
