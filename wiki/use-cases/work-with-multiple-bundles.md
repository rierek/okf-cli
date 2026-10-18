---
title: "Work with multiple bundles"
description: "Point okf at different catalogues with --root, --global or a config file."
---

## Purpose

Show how one binary serves several catalogues.

## Audience

A user with a private catalogue, project catalogues and shared bundles.

## Visual elements

Code blocks with two roots side by side; Mermaid of root resolution order.

## Search terms

multiple knowledge bases CLI; okf --root; catalogue config; Obsidian vault CLI

## Required sections

### Result sentence

- Bold sentence: one binary, any number of catalogues, chosen per call. Source: FACTS §Topic: config files and root resolution.

### Set it up

- Root resolution: `--root`, then the nearest catalogue above the working directory, then `~/.config/okf/config.toml`; `--global` uses the config root. Source: FACTS §Topic: config files and root resolution.

### Work through it

- Run the same command against two roots: `okf --root A find x`, `okf --root B find x`. Source: FACTS §Topic: config files and root resolution.
- Catalogue-wide commands work across all bundles of one root. Source: FACTS §Topic: catalogue, bundle, concept and type model.

### What you get

- One command set across every catalogue. Source: FACTS §Topic: config files and root resolution.

### Limits

- `--root` and `--global` go before the command and exclude each other. Source: FACTS §Topic: config files and root resolution.

### Reference

- Links to Configuration and Concepts. Source: FACTS §Section index of commands.
