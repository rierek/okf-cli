---
type: Runbook
title: Deploy
description: "How to deploy: build, ship, verify"
tags:
  - ops
  - deploy
generated:
  by: human:golden
  at: 2026-01-02T10:00:00Z
verified:
  - by: human:golden
    at: 2026-01-03T10:00:00Z
sources:
  - resource: https://example.org/deploy-docs
stale_after: 2099-01-01T00:00:00Z
---

# Deploy

## Steps

1. Run `deploy <env>` with the target.
2. Wait for the `<env>.<region>` health check.
3. Fetch `https://old-host.example.org/status`.

## Links

Back to [getting started](../getting-started.md).
Compare [setup](setup.md) and the [rule](/kc-gov/ownership.md).
