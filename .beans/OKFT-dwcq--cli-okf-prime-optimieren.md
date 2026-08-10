---
# OKFT-dwcq
title: cli okf prime optimieren
status: completed
type: task
priority: high
created_at: 2026-07-18T12:33:14Z
updated_at: 2026-07-18T12:49:52Z
---

okf Prime erzeugt einen aufgeblähten input, der so nicht wirklich nützlich ist. Es braucht klare Tool-Informationen. Progressive Disclosure ist nicht eingehalten, da die bundle Informationen zu umfangreich sind

## Summary of Changes

Default `prime` bundle listing is jetzt kompakt (Name + Concept-Count) via
render_bundle_line. --full unveraendert (volle Bloecke: description+directories+
types+tags). Gemessen gegen ~/Obsidian/Knowledge-Catalogue (21 Bundles): default
268 -> 93 Zeilen (13.5KB -> 7.9KB, ~41% weniger). --full: 310 Zeilen/25KB, identisch
zu vorher. cmd_index unveraendert -- bleibt Stelle fuer volles Bundle-Browsing.
