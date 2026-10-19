---
title: "About okf: Open Knowledge Format tooling"
description: "What okf is, where it comes from and how it relates to the Open Knowledge Format (OKF) specification."
---

## About okf, an Open Knowledge Format tool

**okf is a command line tool and MCP server for catalogues of Open Knowledge Format (OKF) v0.2 bundles.** It searches, navigates, validates and refactors markdown files with YAML frontmatter, for people and for AI agents. It is a single Go binary.

## Specification tool

:::note[Specification first]
okf exists to work with the OKF specification. okf follows the specification and is adapted when the specification changes. There is no release date and no release per specification version.
:::

## Origin

okf is a catalogue-aware fork inspired by Cole Medin's single-bundle `okf-cli.py`. A Go port replaced the Python run time. The Go binary needs no Python. The [Known limitations](/okf-cli/known-limitations/) page lists where the port differs from the Python original.

## The OKF format

The normative text is the [OKF specification](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md). [okf.md](https://okf.md/) is a community guide. For the terms okf uses, see the [glossary](/okf-cli/reference/glossary/). For a short tour of the model, see [Concepts](/okf-cli/overview/concepts/).

## Scope

okf leaves version control to git. Git gives clean diffs for markdown, a commit log per concept, and branches and pull requests for proposed changes. okf reads and writes the files and never commits.

## Where to go next

- [Install okf](/okf-cli/overview/installation/)
- [First steps](/okf-cli/overview/first-steps/)
- [Contribute](/okf-cli/contribute/)
