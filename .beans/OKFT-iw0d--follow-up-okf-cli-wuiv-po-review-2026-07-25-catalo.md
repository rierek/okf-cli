---
# OKFT-iw0d
title: 'Follow-up OKFT-wuiv PO-Review 2026-07-25: catalogue gap'
status: todo
type: feature
priority: normal
created_at: 2026-07-25T22:34:27Z
updated_at: 2026-07-25T22:34:27Z
parent: OKFT-wuiv
---

## Nebenbefund (PO-Review 2026-07-25, Runde 2/Q03-Gegenprobe)

No OKF concept in the Knowledge-Catalogue covers "serving Excalidraw mockups as HTML via tailscale serve" end-to-end. Two adjacent concepts each cover half:

- `dev-wiki/testsystem-vite-tailscale/serve-excalidraw-drafts.md` — mockup diagrams via tailscale serve, but as PNG + .excalidraw JSON, not HTML.
- `dev-wiki/testsystem-vite-tailscale/serve-dev-server-to-tailnet.md` — generic HTML-via-tailscale pattern (Vite/Storybook dev server), not mockup-specific.

Neither is a search/retrieval problem (confirmed live: find "mockup tailscale" genuinely has nothing to surface -- no third concept exists). This is a real content gap, not a bug.

## Task

Author a new SOP concept in dev-wiki/testsystem-vite-tailscale/ (or extend serve-excalidraw-drafts.md) covering the HTML-rendering path for mockups (not just PNG/raw-JSON) served via tailscale serve, cross-linked to both adjacent concepts. Route via /okf-p ingest, never hand-written.

Source: PO-review live counter-test, 2026-07-25/26.
