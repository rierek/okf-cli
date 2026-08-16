---
# okf-cli-fcrc
title: Merge both spec branches after the peer chain lands
status: todo
type: task
priority: high
created_at: 2026-08-09T20:44:56Z
updated_at: 2026-08-09T20:44:56Z
parent: okf-cli-03o1
---

Two branches wait for merge. Neither goes to `main` without the peer's green light, and the rule runs both ways.

`fix/b01-b02-bundle-validation` @ `b5a9f1d`, base `3310656`, suite 559 green. Adds `require_bundle_dir(root, bundle)` below `is_bundle_dir` in `cli/okf-cli.py` and calls it from `cmd_index` and `cmd_visualize`. It checks `os.path.isdir` and deliberately NOT `is_bundle_dir()`, so `_archive/` paths still pass. Test class `BundleArgumentIsValidated` in `cli/test_okf_cli.py`. This is the only branch that touches `cli/` and the only one needing a real rebase.

`docs/rust-rewrite-spec` @ `aeb4058`, base `main @ a73a60e`, docs only.

The peer anchored `b5a9f1d` — helper name, test name, and the existence-not-eligibility property — as a prelude in its leaf `okf-cli-fu7o`, which touches `cmd_index`.

Peer session realises milestone `okf-cli-wuiv` in the main workdir directly on `main`. It reports at the end of its chain with the final `main` state.
