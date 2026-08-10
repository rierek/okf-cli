---
# OKFT-gm5k
title: Resolver ignores Unicode normalisation (NFC/NFD)
status: todo
type: bug
priority: low
created_at: 2026-08-05T09:11:16Z
updated_at: 2026-08-05T09:11:16Z
---

Confirmed 2026-08-05 during review round 5 of the wikilink-awareness topic. Deferred on purpose, not overlooked — see `docs/wikilink-awareness/SPEC.md`, C09 and Q07.

## Symptom

`build_concept_basename_index` keys on the filename bytes the filesystem hands over; a wikilink carries whatever form the author typed. `lower()` folds case but does not normalise, so the two keys never meet across normalisation forms.

Measured on a scratch tree, APFS:

```
file on disk:      Qualität.md   (NFD, 9 codepoints)
[[Qualität]] NFC:  ('unresolved', [])
[[Qualität]] NFD:  ('resolved', ['/a/Qualität.md'])
```

## Why it matters

Two consequences, and the second is the one that costs data:

1. `wikilinks` reports a false unresolved for a target that is sitting right there.
2. `rename` does not find the link, so it is left pointing at the old name while the run reports success — the silent-orphan class D06 exists to close, reached along a second axis.

## Why it is not urgent

Zero live exposure: 2422 index keys in the catalogue, not one non-ASCII basename. The portable-filename convention is what buys that. ASCII has no canonical decomposition, so the defect cannot fire while the convention holds.

Trigger to pick this up: the first concept basename carrying a character WITH a canonical decomposition. Umlauts and accents qualify; ß does not (no NFD form) — a first attempt to reproduce with `Straße` failed for exactly that reason.

Detector, runnable any time:

```
python3 -c "
import types,os
SRC='cli/okf-cli.py'
m=types.ModuleType('o'); m.__file__=os.path.abspath(SRC)
exec(compile(open(SRC,encoding='utf-8').read(),SRC,'exec'),m.__dict__)
idx=m.build_concept_basename_index(os.path.expanduser('~/Obsidian/Knowledge-Catalogue'))
print(len([k for k in idx if any(ord(c)>127 for c in k)]))
"
```

## Scope of the fix

Five key-deriving sites: `build_concept_basename_index`, `resolve_wikilink` (twice — the basename lookup and the path-tail compare), and `plan_wikilink_rewrites`' own `old_key`/`new_key` derivation.

Two hard requirements:

- Add the mutant to `docs/wikilink-awareness/mutants.py` FIRST — drop the normalisation, expect SURVIVED — so the new test is proven non-vacuous before the fix lands. That harness stands at 39/39 killed; a test that cannot fail would be the first hole in it.
- Normalisation and case folding are separate axes and only one of them is Obsidian's. D06 requires `[[STRASSE]]` to stay unresolved against `Straße.md`, because Obsidian folds with JavaScript `toLowerCase()`. Reaching for `casefold()` while normalising breaks that.

## Not verified

Which normalisation form Obsidian and Finder produce when creating files, and which form Obsidian holds link text in. That decides how likely a divergence is in practice and is the first thing to measure if this becomes real.
