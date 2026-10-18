---
title: "Tag hygiene"
description: "Tags only help while the vocabulary stays small and controlled. Register tags in TAGS.md, validate them and block unregistered tags in CI."
date: 2026-10-18
tags: [tags, okf, knowledge-management]
---

**Tags only help while their number stays small and under control.** Register each tag, validate the catalogue, and let CI refuse tags nobody approved.

## The problem

Tags grow wild: `auth`, `authn`, `authentication`, `Auth`. Search fragments, and a filter returns random hits.

## The rules

- Keep tags few and give them on purpose.
- Register every tag in `TAGS.md`, each with a description.
- A description has at most 150 characters, one line and no `|`. `okf tags --register` refuses anything else.

```text
okf tags --register operations "Running and operating services"
```

## Check

`okf tags --validate` reports tags that are not in the registry and exits with a non-zero code, so a script can act on it. Test for non-zero rather than for one value: the exit code and the help text disagree today ([irxe], see [Known limitations](/known-limitations/)).

## A CI gate

Let CI run `okf tags --validate` and fail on non-zero. A new, unregistered tag then blocks the merge. Whoever wants the tag adds it to `TAGS.md`, and the review shows that change on purpose.

## Clean up

| Command | Does |
|---|---|
| [`okf merge-tags`](/reference/commands/okf-merge-tags/) | Merge duplicates and synonyms into one tag. |
| [`okf remove-tags`](/reference/commands/okf-remove-tags/) | Remove a tag. |
| [`okf normalize-tags`](/reference/commands/okf-normalize-tags/) | Unify the spelling and list form. |

All three change many files at once. They print a diff first and write only with `--apply`. Read the diff, apply, then commit.

```text
okf merge-tags --into operations ops
okf merge-tags --into operations ops --apply
```

## In short

- A small, registered vocabulary.
- A CI gate keeps it clean.
- The tools repair what accumulated before.

See also [Tags and registry](/features/tags-and-registry/).
