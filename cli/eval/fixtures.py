#!/usr/bin/env python3
"""cli/eval/fixtures.py — seed/teardown hidden golden fixtures S1-S4 into the
real OKF Knowledge Catalogue (Task 2 of docs/okf-revision/PLAN.md, D11).

Fixtures are `_`-prefixed fake concept files seeded into REAL bundles so they
compete with the ~1783 live concepts for ranking during the eval (Modus A).
Each scenario isolates one retrieval property (PLAN.md Task 2 placement
table):

    S1 — token in Title + one H2 + Body, correct bundle (ceiling/sanity)
    S2 — same as S1 but in the WRONG bundle (location-sensitivity)
    S3 — correct bundle, generic title, no matching tags, token body-only
         (field-weighting + semantic gap)
    S4 — correct bundle, type/tag frontmatter wrong/missing (metadata- vs
         structure-retrieval — findable only via index-walk / body)

Ownership is tracked by FILENAME PREFIX (FIXTURE_PREFIX), not by remembering
which bundle a fixture landed in — teardown() walks every real bundle and
removes anything it owns, so it stays idempotent even after a partial seed
or if bundle selection drifts between runs.

Usage:
    python3 fixtures.py --root <catalogue> --seed
    python3 fixtures.py --root <catalogue> --teardown
"""
import argparse
import collections
import importlib.util
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_CLI_PATH = os.path.join(_HERE, "..", "okf-cli.py")
_spec = importlib.util.spec_from_file_location("okf_cli", _CLI_PATH)
okf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(okf)

# Rare token unlikely to collide with real content — the shared "secret" the
# golden queries (Task 3) search for.
SEED_TOKEN = "zqxeval"

# Every fixture file this module ever writes starts with this prefix, so
# teardown() can find and remove them without tracking bundle placement.
FIXTURE_PREFIX = "_okfeval-"

Fixture = collections.namedtuple(
    "Fixture",
    ["sz", "rel_path", "title", "type", "tags", "body", "correct_bundle"],
)


# Pinned fixture bundle pair (D-sgkn-01, D-sgkn-02, OKFT-sgkn): explicit,
# not derived from list_bundles() alphabetical order. Matches the bundle
# segment cli/eval/golden.json's expected_path / s4-index-walk query.bundle
# fields already hardcode — golden.json's literals are checked against
# these two constants by cli/test_eval_runner.py's
# GoldenBundleConsistencyTest, so the two files cannot drift silently.
# Changing either constant without updating golden.json (or vice versa)
# fails that guard immediately.
CORRECT_BUNDLE = "knowledge-management"
WRONG_BUNDLE = "testing-quality"


def _pick_bundles(root):
    """Return the pinned (correct_bundle, wrong_bundle) pair, after
    validating both are real (non-symlink) bundles under root.

    Previously derived positionally from list_bundles() alphabetical
    order ("first two non-symlink bundles") — silently wrong whenever a
    new, earlier-sorting bundle joined the catalogue (OKFT-sgkn: `aca-okf`
    started sorting before `agent-memory`, seeding S1 into the wrong
    bundle while golden.json kept expecting `agent-memory`). Pinning by
    name removes the coupling to catalogue sort order entirely."""
    real = {
        b for b in okf.list_bundles(root)
        if not os.path.islink(os.path.join(root, b))
    }
    missing = [b for b in (CORRECT_BUNDLE, WRONG_BUNDLE) if b not in real]
    if missing:
        raise RuntimeError(
            "fixtures.py pin ({!r}, {!r}) invalid under {}: {} not found "
            "as a real (non-symlink) bundle".format(
                CORRECT_BUNDLE, WRONG_BUNDLE, root, ", ".join(missing)
            )
        )
    return CORRECT_BUNDLE, WRONG_BUNDLE


def _fixture_spec(root):
    """Build the four Fixture records against the current catalogue state."""
    correct, wrong = _pick_bundles(root)
    return [
        Fixture(
            sz="S1",
            rel_path="{}/{}s1.md".format(correct, FIXTURE_PREFIX),
            title="Zqxeval Sanity Concept",
            type="Concept",
            tags=["eval-fixture"],
            body=(
                "## Zqxeval Overview\n\n"
                "This concept exists purely to validate zqxeval retrieval "
                "as a sanity ceiling: the token zqxeval sits in the title, "
                "one heading, and this body paragraph.\n"
            ),
            correct_bundle=True,
        ),
        Fixture(
            sz="S2",
            rel_path="{}/{}s2.md".format(wrong, FIXTURE_PREFIX),
            title="Zqxeval Sanity Concept (S2)",
            type="Concept",
            tags=["eval-fixture"],
            body=(
                "## Zqxeval Overview\n\n"
                "Same placement as S1 — zqxeval in title, heading, and body "
                "— but seeded into the wrong bundle on purpose, to isolate "
                "location-sensitivity: find is location-blind, list --scope "
                "is not.\n"
            ),
            correct_bundle=False,
        ),
        Fixture(
            sz="S3",
            rel_path="{}/{}s3.md".format(correct, FIXTURE_PREFIX),
            title="Generic Fixture Concept",
            type="Concept",
            tags=[],
            body=(
                "## Notes\n\n"
                "A generic concept with a generic title and no matching "
                "tags. zqxeval appears only here, in body prose, to isolate "
                "field-weighting and the keyword-vs-semantic gap.\n"
            ),
            correct_bundle=True,
        ),
        Fixture(
            sz="S4",
            rel_path="{}/{}s4.md".format(correct, FIXTURE_PREFIX),
            title="Zqxeval Metadata-Gap Concept",
            type="",
            tags=[],
            body=(
                "## Zqxeval Metadata Gap\n\n"
                "zqxeval appears in title and body, but frontmatter type/tag "
                "are missing on purpose, so this concept is findable only "
                "via index-walk or body search, never via list(type, tag).\n"
            ),
            correct_bundle=True,
        ),
    ]


def _render(fx):
    lines = ["---", 'title: "{}"'.format(fx.title)]
    if fx.type:
        lines.append("type: {}".format(fx.type))
    lines.append("tags: [{}]".format(", ".join(fx.tags)))
    lines.append(
        "description: hidden eval fixture ({}) — owned by cli/eval/fixtures.py, "
        "do not curate".format(fx.sz)
    )
    lines.append("---")
    header = "\n".join(lines) + "\n\n"
    return header + "# {}\n\n{}".format(fx.title, fx.body)


def seed(root):
    """Write exactly one .md per fixture (S1-S4). Returns the abs paths
    written.

    Pre-cleans any stray FIXTURE_PREFIX files first (I09, P12 prelude):
    an aborted prior run must never leave residue that a fresh run would
    count as live fixtures. teardown() is idempotent, so this is safe."""
    teardown(root)
    written = []
    for fx in _fixture_spec(root):
        ap = os.path.join(root, fx.rel_path.replace("/", os.sep))
        os.makedirs(os.path.dirname(ap), exist_ok=True)
        with open(ap, "w", encoding="utf-8") as f:
            f.write(_render(fx))
        written.append(ap)
    return written


def teardown(root):
    """Remove every fixture file this module owns (FIXTURE_PREFIX), across
    every real (non-symlink) bundle. Idempotent — safe to call after a
    partial seed or with nothing seeded at all."""
    removed = []
    for b in okf.list_bundles(root):
        bp = os.path.join(root, b)
        if os.path.islink(bp):
            continue
        for dirpath, dirnames, filenames in os.walk(bp):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for fn in filenames:
                if fn.startswith(FIXTURE_PREFIX) and fn.endswith(".md"):
                    ap = os.path.join(dirpath, fn)
                    os.remove(ap)
                    removed.append(ap)
    return removed


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", required=True, help="catalogue root")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--seed", action="store_true", help="seed S1-S4 fixtures")
    g.add_argument("--teardown", action="store_true", help="remove S1-S4 fixtures")
    args = p.parse_args(argv)
    root = os.path.abspath(os.path.expanduser(args.root))
    paths = seed(root) if args.seed else teardown(root)
    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
