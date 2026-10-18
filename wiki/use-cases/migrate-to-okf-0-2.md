---
title: "Migrate to OKF 0.2"
description: "Bring a catalogue to the OKF v0.2 frontmatter with okf migrate."
---

## Purpose

Show a migration from `timestamp` to `generated` and the status rules.

## Audience

A catalogue owner on an older frontmatter shape.

## Required sections

### Result sentence

- Bold sentence: problem and solution in one sentence. Source: FACTS §okf migrate.

### Set it up

- Commit the catalogue; run `okf migrate` as a dry run. Source: FACTS §okf migrate.

### Work through it

- Read the plan, `--apply`, then `okf check`. Source: FACTS §okf migrate; FACTS §okf check.
- A file the line patcher cannot patch ends the whole run with exit 2 and `<path>: <reason>`; fix it by hand and rerun. Source: FACTS §okf migrate; FACTS Nicht bestimmbar part 2 (D-09).

### What you get

- A catalogue that passes the v0.2 rules. Source: FACTS §okf check.

### Limits

- Exit codes of `migrate` beyond the observed ones are not verified. TODO: verify

### Reference

- Links to `migrate`, `check`, Troubleshooting. Source: FACTS §Section index of commands.
