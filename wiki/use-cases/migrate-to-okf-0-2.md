---
title: "Migrate to OKF 0.2"
description: "Migrate a catalogue to OKF 0.2 frontmatter with okf migrate: timestamp to generated, status rules, dry run first. Open Knowledge Format upgrade."
---

# Migrate to OKF 0.2: `okf migrate`

**`okf migrate` turns `timestamp` into `generated` and maps old `status` values to the OKF 0.2 set, and it shows every change before it writes one.** The output below comes from okf 0.2.5 on a throwaway copy of the test catalogue.

## Set it up

1. Put the catalogue under git and commit. `migrate` reads author and time for `generated` from git history, so the migration also lands as one reviewable diff.
2. Optional: map author e-mail addresses to actors in `.okf.toml` under `[git_authors]`. See [Configuration](/okf-cli/reference/configuration/).
3. Run `okf migrate` without `--apply`. It is a dry run.

```text title="Dry run (first lines)"
$ okf --root <catalogue> migrate recipes
status mapping:
  active -> stable (1 concept(s))
  obsolete -> deprecated (1 concept(s))
  todo -> draft (1 concept(s))
--- a/recipes/bread.md
+++ b/recipes/bread.md
@@ -5,8 +5,10 @@
 tags:
   - food
   - bread
-timestamp: 2025-12-02T08:00:00Z
-status: todo
+generated:
+  by: human:golden
+  at: '2026-10-18T22:07:21+02:00'
+status: draft
 ---
 
 # Bread
```

The dry run exits 0 and leaves the files untouched.

## Work through it

1. Read the status mapping table. It counts the concepts for each old value.
2. Look for `unresolved` lines. A status value without a recorded decision is not changed:

   ```text title="Concept with no decision"
   $ okf --root <catalogue> migrate handbook
   status mapping:
     deprecated -> deprecated (1 concept(s))
     maybe-later -> (no decision) (1 concept(s))
     stable -> stable (1 concept(s))
   unresolved handbook/wiki-notes.md: no recorded decision for status value 'maybe-later'
   migrate: would migrate 0 file(s), 1 unresolved; dry-run: re-run with --apply
   ```

   Edit such a file by hand to `draft`, `stable` or `deprecated`.
3. Write the changes with `--apply`, then review `git diff`.
4. Run `okf check`. The rules `okf/trust/generated` and `okf/lifecycle/status` report what is still wrong:

   ```text title="Remaining findings after the run"
   $ okf --root <catalogue> check
   ERROR    okf/trust/generated  handbook/wiki-notes.md  (`generated` has no non-empty `by`)
   ERROR    okf/lifecycle/status handbook/wiki-notes.md  (`status` is `maybe-later`, not draft, stable or deprecated)
   ```

:::caution
`migrate` patches frontmatter line by line. A file it cannot patch ends the whole run with exit 2 and `<path>: <reason>`, and nothing is written, also in a dry run. Fix that file by hand and run again. See [known limitations](/okf-cli/known-limitations/).
:::

For scripts, `--json` prints the envelope with `data` = `{applied, files, unresolved, status_mapping}`.

## What you get

Files that carry `generated` (`by`, `at`) in place of `timestamp`, and `status` values from the set `draft`, `stable`, `deprecated`. A file you fixed by hand after an `unresolved` line passes the same two rules.

## Limits

- `migrate` exits 0 on success and 2 for a file the patcher refuses. A path that is not a directory exits 3.
- `okf check` can report findings unrelated to the migration. Read the rule names.

## Reference

- [`okf migrate`](/okf-cli/reference/commands/okf-migrate/)
- [`okf check`](/okf-cli/reference/commands/okf-check/)
- [Troubleshooting](/okf-cli/overview/troubleshooting/)
