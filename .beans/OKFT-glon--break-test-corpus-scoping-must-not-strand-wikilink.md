---
# OKFT-glon
title: 'Break-test: corpus scoping must not strand wikilinks'
status: todo
type: task
priority: high
created_at: 2026-08-13T11:07:31Z
updated_at: 2026-08-13T11:07:31Z
parent: OKFT-wmbu
blocked_by:
    - OKFT-n8xz
---

Proof obligation for the corpus/resolution split, per lean-stack-okf/guard-form-vs-mechanismus: a guard nobody deliberately tried to break is a hypothesis.

Procedure: add a wikilink from a topic-folder file to a bundle concept and one in the reverse direction, run okf-cli check on the bundle, and quote the observed output. Assert that no new unresolved entries appear. Roll the manipulation back afterwards.

A passing run without this probe does not close the task.
