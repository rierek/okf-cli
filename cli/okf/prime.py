"""The prime command: the one-shot agent onboarding. Holds the guide texts, the live
catalogue state and the parser block. okf.parser imports this module, so the two
parser helpers prime renders from are imported inside the functions that call them."""

import os

from okf.catalogue import ctx_slugs, iter_concepts, list_bundles, load_tags
from okf.fts import _fts_db_path
from okf.index import render_bundle_block, render_bundle_line
from okf.output import _add_output
from okf.parser_support import _sub, subcommand_parsers
from okf.semantic import _tagvec_db_path, semantic_coverage


_PRIME_INTRO = """\
# OKF Knowledge Catalogue — agent onboarding

The catalogue is a read-mostly, LLM-facing knowledge store, separate from any
Obsidian vault it may be opened in. It holds thematic *bundles*; a bundle is a
folder of Markdown *concepts*, each with YAML frontmatter carrying a non-empty
`type`. A concept-id is its path below the bundle, minus `.md`. The store is a
plain git repo — ordinary file tools and git apply.

Every invocation needs `--root <catalogue>`; without it the CLI searches cwd and
its ancestors for a catalogue marker and fails if it finds none. It never falls
back to its own script directory.

## Retrieve — by command, not by blind grep

Progressive disclosure: widen only when the cheaper step left the question open.

  1. find "<query>"             ranked search across all bundles; narrow it with
                                --where "type = Runbook and path ~ <bundle>/"
  2. index [<bundle>]           what bundles and directories exist
  3. toc <bundle>[/<concept>]   headings before bodies — the cheapest way to
                                decide whether a page is worth reading. A bare
                                <bundle> or <bundle>/<subdir> resolves to its
                                index.md, so the names listed below are the
                                argument, verbatim.
  4. read <bundle>/<concept>    the page itself
  5. refs / wikilinks           follow the graph out of a page

Reach for `toc` before `read`: a concept can run long, and its headings usually
settle the question or name the section to read. Concepts cross-link in
Markdown — following a link beats re-running a search, and a large bundle's
`index.md` is the map its concepts hang from.

## Write — through the ce-okf skill, never by hand

Concepts are not hand-authored. The `ce-okf` skill routes a source to a bundle,
applies frontmatter and re-indexes. `index.md` listings are marker-managed and
generated (`reindex`) — never edit between the `<!-- okf:... -->` markers. Tag
edits go through `merge-tags` / `remove-tags`, not a search-and-replace. A
commit is allowed only once `check` reports zero violations.
"""


_PRIME_INTRO_COMPACT = """\
# OKF Knowledge Catalogue — agent onboarding

The catalogue is a read-mostly, LLM-facing knowledge store, separate from any
Obsidian vault it may be opened in. It holds thematic *bundles*; a bundle is a
folder of Markdown *concepts*, each with YAML frontmatter carrying a non-empty
`type`. A concept-id is its path below the bundle, minus `.md`. The store is a
plain git repo — ordinary file tools and git apply.

## Retrieve — by command, not by blind grep

Progressive disclosure: widen only when the cheaper step left the question open.

  1. find "<query>"             ranked search across all bundles; narrow it with
                                --where "type = Runbook and path ~ <bundle>/"
  2. index [<bundle>]           what bundles and directories exist
  3. toc <bundle>[/<concept>]   headings before bodies — the cheapest way to
                                decide whether a page is worth reading. A bare
                                <bundle> or <bundle>/<subdir> resolves to its
                                index.md, so the names listed below are the
                                argument, verbatim.
  4. read <bundle>/<concept>    the page itself
  5. refs / wikilinks           follow the graph out of a page

## Write — through the ce-okf skill, never by hand

Concepts are not hand-authored: `ce-okf` routes a source to a bundle, applies
frontmatter and re-indexes. `index.md` listings are marker-managed and
generated — never edit between the `<!-- okf:... -->` markers. A commit is
allowed only once `check` reports zero violations.
"""

_FIND_SCALES_COMPACT = """\
Each result line's headline number is `rank: N` — its 1-based position in
the delivered list, the one scale comparable across a mixed-arm result
because it IS the list order (D12: handover, never blend by score). The
arm's own raw value is not in that column; pass `--breakdown` to see it,
per hit: `score: a/b` for a lexical hit (a/100 is the FTS5/BM25 arm,
relative to this run's own top hit; a/(6 * n) is the substring fallback
used when no FTS index is available, over n query terms), `score: cosine
X.XX` for a semantic hit — its own scale, never the same column as a
lexical a/b. `provenance:` names the arm that produced the line.
Degradations are announced on stderr.
"""


def render_find_compact():
    """`find`'s options for the compact guide. The signature comes from the
    parser, so a flag registered later cannot go missing here — only the score
    scales are prose, because they are the one thing an agent cannot recover by
    trying the command. Everything else is one `find --help` away."""
    from okf.parser import build_parser
    usage = subcommand_parsers(build_parser())["find"].format_usage().strip()
    return "## find — the entry point\n\n{}\n\n{}\nFull flag semantics: `find --help`.".format(
        usage, _FIND_SCALES_COMPACT)


def _semantic_coverage_line(root, paths, thorough=False):
    """The onboarding statement about the semantic arm's reach. The lexical
    index announces its absence and its staleness; before this, an incomplete
    `concept_emb` said nothing at all, and the arm simply did not see the
    concepts it lacked (Modus-B, 2026-08-10: 4.4 % of the live catalogue).

    `thorough=False` (prime's default) reports presence only: semantic_coverage()
    now does a real content-hash pass and costs ~2.2s over the live catalogue,
    too slow for a call on every session start. Presence-only is an honest
    "don't know", not a diluted count — the one counting method lives in
    semantic_coverage() and only runs when `thorough=True` (`prime
    --check-semantic`)."""
    db = _tagvec_db_path(root)
    if not os.path.isfile(db):
        return ("semantic index: absent — `find` runs its lexical arm only")
    if not thorough:
        return ("semantic index: present — staleness not checked by default "
                 "(costs ~2s on a large catalogue); run `prime --check-semantic` "
                 "for an exact count")
    cov = semantic_coverage(root, paths)
    if cov is None:
        return ("semantic index: absent — `find` runs its lexical arm only")
    embedded, total = cov
    if embedded >= total:
        return ("semantic index: complete — all {} concept(s) embedded".format(total))
    return ("semantic index: partial — {} of {} concept(s) embedded; the rest is "
            "invisible to the semantic arm (rebuild: cli/embeddings/"
            "build_tagvec.py --target concepts)".format(embedded, total))


def render_catalogue_state(root, thorough=False):
    """The live half of the onboarding: facts read off this catalogue rather
    than asserted in prose, so they cannot go stale. Retrieval quality depends
    on the FTS index being there, and a write attempt depends on whether the
    tag vocabulary is closed — an agent needs both before its first call."""
    bundles = list_bundles(root)
    paths = ["{}/{}".format(b, cid) for b in bundles
             for cid, _ap in iter_concepts(os.path.join(root, b))]
    lines = ["## This catalogue", "",
             "root: {}".format(root),
             "bundles: {} · concepts: {}".format(len(bundles), len(paths))]
    if os.path.isfile(_fts_db_path(root)):
        lines.append("fts index: present — `find` runs its lexical arm")
    else:
        lines.append("fts index: absent — `find` degrades to a substring scan; "
                     "run `build-index`")
    lines.append(_semantic_coverage_line(root, paths, thorough=thorough))
    registered = load_tags(root)
    if registered is None:
        lines.append("tag vocabulary: open — no TAGS.md, any tag passes")
    else:
        lines.append("tag vocabulary: closed — {} tags in TAGS.md; check a new one with "
                     "`tags --validate`, adopt it with `tags --register`".format(len(registered)))
    slugs = ctx_slugs(root)
    if slugs:
        lines.append("ctx bundles: {} — {} — `ctx show <slug>` lists one".format(
            len(slugs), " · ".join(slugs)))
    docs = [d for d in ("README.md", "SPEC.md", "TYPES.md", "PROPERTIES.md", "TAGS.md")
            if os.path.isfile(os.path.join(root, d))]
    if docs:
        lines.append("root docs: {}".format(" · ".join(docs)))
    return "\n".join(lines)


def cmd_prime(root, args):
    """One-shot agent onboarding: guide, command directory, catalogue state and
    bundle TOC in a single call. The guide used to be <root>/CLAUDE.md, which
    made prime empty the moment that file was removed (okf-cli-3hjr); it is now
    the CLI's own, and its command section is generated from the parser.

    --compact is the session-start rendering (okf-cli, 2026-08-05): a recipe
    that primes on every session pays this guide against the SSTD, the roadmap
    and the git log. It keeps every command, every find flag and the live
    state, and drops the prose that is one call away."""
    from okf.parser import build_parser, command_overview
    if args.compact:
        guide, commands, find = (_PRIME_INTRO_COMPACT, command_overview(width=10 ** 6),
                                 render_find_compact())
    else:
        guide, commands = _PRIME_INTRO, command_overview()
        find = "## find — the entry point, in full\n\n{}".format(
            subcommand_parsers(build_parser())["find"].format_help().strip())
    state = render_catalogue_state(root, thorough=getattr(args, "check_semantic", False))
    bundles = [render_bundle_line(root, b) if args.compact
               else render_bundle_block(root, b, full=args.full) for b in list_bundles(root)]
    if getattr(args, "json", False):
        return {"guide": guide, "commands": commands, "find": find, "state": state,
                "bundles": bundles}
    print(guide)
    print(commands)
    print()
    print(find)
    print()
    print(state)
    print()
    print("## Bundles\n")
    print("The catalogue TOC, as `index` renders it. Each name is a path: "
          "`toc <bundle>`,\n`index <bundle>`, `--where \"path ~ <bundle>/\"` on find and "
          "list.\n")
    if args.compact:
        for line in bundles:
            print("- " + line)
        print("(`prime` without --compact inlines each bundle's description and "
              "directories)")
    else:
        for block in bundles:
            print(block)
            print("-----")
        if not args.full:
            print("(types+tags per bundle: `prime --full`; name+count only: "
                  "`prime --compact`)")


def add_prime_parser(sub):
    pp = _sub(sub, "prime", "navigation",
              "one-shot agent onboarding: usage guide, command directory, "
              "catalogue state and bundle TOC")
    pp.add_argument("--full", action="store_true",
                     help="add types+tags to each bundle block")
    pp.add_argument("--compact", action="store_true",
                     help="list bundles as name+count one-liners instead of the "
                          "`index` blocks (description+directories)")
    pp.add_argument("--check-semantic", action="store_true",
                     help="run the exact content-hash semantic coverage check "
                          "(~2s on a large catalogue) instead of reporting only "
                          "whether the semantic index is present")
    _add_output(pp)


COMMANDS = {"prime": (cmd_prime, add_prime_parser)}
