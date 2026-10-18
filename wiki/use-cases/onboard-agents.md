---
title: "Onboard Agents"
description: "Give a fresh agent session the catalogue map and the right pages in one call."
---

## Purpose

Show onboarding an agent to a catalogue end to end.

## Audience

A user who starts agent sessions against a knowledge catalogue.

## Visual elements

Steps; code blocks with `okf prime` and `okf ctx` output.

## Search terms

onboard AI agent to knowledge base; okf prime; Claude Code context; MCP knowledge base

## Required sections

### Result sentence

- Bold sentence: an agent starts with the map of your catalogue and the pages that matter. Source: FACTS §okf prime.

### Set it up

- Install okf and run `okf install --apply` for the agent of choice. Source: FACTS §Topic: install; FACTS §Topic: MCP server and `OKF_BIN`.

### Work through it

- `okf prime` prints guide, command directory and bundle TOC. Source: FACTS §okf prime.
- `okf ctx <slug>` hands the agent the pages of one topic in reading order. Source: FACTS §okf ctx show.
- The agent calls `okf_find` and `okf_read` through MCP or `okf find` and `okf read` in the shell. Source: FACTS §Topic: MCP server and `OKF_BIN`; FACTS §okf read.

### What you get

- An agent that finds and reads sections without blind grep. Source: FACTS §okf read.

### Limits

- The `prime` state text names `build_tagvec.py`. [erpf]. Source: FACTS §Defect list h.

### Reference

- Links to Agent onboarding, Context bundles, `okf prime`, `okf read`. Source: FACTS §Section index of commands.
