---
title: "First steps"
description: "Point okf at a catalogue and run the first commands: index, find, read, check."
---

## Purpose

Walk a new user from a catalogue on disk to a first search, a read of one concept and a conformance check.

## Audience

A user who installed okf and has, or wants to try, a catalogue; the golden fixture catalogue works as a sandbox.

## Required sections

### Result sentence

- Bold sentence: after the steps you found and read a concept and ran a check. Source: FACTS §okf find; FACTS §okf read; FACTS §okf check.

### Numbered steps

- 1. Point okf at a catalogue: `--root`, or the nearest catalogue above the working directory, or `--global`. Source: FACTS §Topic: config files and root resolution.
- 2. `okf index` lists the bundles. Source: FACTS §okf index.
- 3. `okf build-index`, then `okf find <query>`: ranked results; without the index it falls back to a substring scan with a note. Source: FACTS §okf build-index; FACTS §okf find; FACTS §Topic: index and search artefacts.
- 4. `okf read <concept>` prints one concept page. Source: FACTS §okf read.
- 5. `okf check` scans the catalogue against the format rules. Source: FACTS §okf check.

### Where options go

- `--root` and `--global` go before the command: `okf --root /path find git`. Source: FACTS §Topic: config files and root resolution; FACTS §okf find.

### Result

- The reader ends with a working catalogue root, an index and one real output of each command. Source: FACTS §okf index; FACTS §okf find; FACTS §okf read; FACTS §okf check.

### Reference

- Links to the pages of the commands used. Source: FACTS §Section index of commands.
