"""The conformance scan: the per-file, bundle-level, sync and canon rules, the
engine that runs them (`run_checks`), the crosslink and XML-like-tag repairs, and
the check, fix-crosslinks and fix-xml-tags commands."""

import json
from collections import namedtuple
import os
import re
import sys

from okf.errors import OkfError
from okf import sync, wikilinks
from okf.catalogue import (
    CANON_END, CROSSLINK_RE, CTX_DIR, FM_DELIM, RESERVED, SYNC_OPEN_LIT, SYNC_SPAN_RE, _dequote,
    _mask_managed_block, _split_managed_block, ctx_findings, extract_tags, index_h1_and_desc,
    iter_all_md, load_okf_config, load_tags, load_types, read_file, resolve_scopes,
    split_frontmatter, write_file,
)
from okf.parser_support import _complete_files, _complete_scopes, _sub
from okf.sync import classify_sync_block, parse_canon_blocks, parse_sync_blocks


# --- check: pluggable conformance scan (§9 hard rules + local invariants) ---

FILENAME_FORBIDDEN_CHARS = set('#^[]|\\:?*"<>%')
GERMAN_FM_KEYS = {"titel", "beschreibung", "typ", "stichworte", "datum", "zusammenfassung"}


def gather_file_context(root, bundle, ap):
    text = read_file(ap)
    fm, body = split_frontmatter(text)
    has_fm = text.startswith(FM_DELIM) and text.find("\n" + FM_DELIM, len(FM_DELIM)) != -1
    fn = os.path.basename(ap)
    return {
        "root": root, "bundle": bundle, "ap": ap,
        "rel": os.path.relpath(ap, root).replace(os.sep, "/"),
        "fn": fn, "text": text, "fm": fm, "body": body,
        "has_fm": has_fm, "is_reserved": fn.lower() in RESERVED,
    }


def check_fm_parseable(ctx):
    if ctx["is_reserved"]:
        return []
    return [] if ctx["has_fm"] else ["no parseable frontmatter"]


def check_type_nonempty(ctx):
    if ctx["is_reserved"] or not ctx["has_fm"]:
        return []
    return [] if ctx["fm"].get("type", "").strip() else ["missing/empty `type`"]


def check_reserved_no_type(ctx):
    if not ctx["is_reserved"] or not ctx["has_fm"]:
        return []
    return ["reserved file must not carry `type`"] if ctx["fm"].get("type", "").strip() else []


def check_filename_chars(ctx):
    if ctx["is_reserved"]:
        return []
    bad = FILENAME_FORBIDDEN_CHARS & set(ctx["fn"][:-3])
    return ["forbidden char(s) in filename: {}".format("".join(sorted(bad)))] if bad else []


def check_type_registered(ctx, types_set):
    if ctx["is_reserved"] or not ctx["has_fm"] or types_set is None:
        return []
    t = ctx["fm"].get("type", "").strip()
    return ["type `{}` not registered in TYPES.md".format(t)] if t and t not in types_set else []


def check_tag_registered(ctx, tags_set):
    """Closed-vocabulary gate: every frontmatter tag must be in TAGS.md.
    No-op when TAGS.md is absent (tags_set is None). Severity is warning, so it
    surfaces new tags without blocking; `check --strict` escalates to error.
    Keeps agents from exploding the tag vocabulary with creative one-offs — a tag
    only aggregates content if it is reused, not minted fresh each write."""
    if ctx["is_reserved"] or not ctx["has_fm"] or tags_set is None:
        return []
    return ["tag `{}` not registered in TAGS.md".format(t)
            for t in extract_tags(ctx["text"]) if t not in tags_set]


def check_english_keys(ctx):
    if ctx["is_reserved"] or not ctx["has_fm"]:
        return []
    hits = GERMAN_FM_KEYS & set(ctx["fm"].keys())
    return ["German frontmatter key(s): {}".format(", ".join(sorted(hits)))] if hits else []


def check_tags_block_form(ctx):
    """Local convention (this catalogue, not OKF spec): `tags` must be a YAML
    block-list, not inline `[a, b]`. Empty `[]` is fine (nothing to convert)."""
    if ctx["is_reserved"] or not ctx["has_fm"]:
        return []
    raw = ctx["fm"].get("tags", "").strip()
    if raw.startswith("[") and raw.endswith("]") and raw[1:-1].strip():
        return ["tags field uses inline form — local convention requires YAML block-list"]
    return []


def check_crosslink_format(ctx):
    """Cross-links must be catalogue-root-absolute (`/bundle/subdir/concept.md`,
    leading `/` = catalogue root = Obsidian vault root). Flags (a) relative links
    that resolve inconsistently and orphan in Obsidian, and (b) leading-`/` links
    that do not resolve to a real file from the catalogue root (legacy bundle-
    relative `/subdir/x.md` or typos — the phantom-orphan class).

    D-rx51-01 (OKFT-rx51): RESERVED files (index.md, log.md, readme.md,
    index-map.md) are scanned as a link source too — they routinely carry
    hand-authored prose alongside or instead of the managed
    `<!-- okf:index -->` block, and a crosslink an author writes there is a
    real crosslink. The managed block itself is masked out first so its
    generated links never trigger a warning; fix_crosslinks is untouched by
    this — it still never rewrites a RESERVED file."""
    # Symlinked external bundles keep the portable bundle-relative OKF form and are
    # audited in their own repo — the catalogue-root convention does not apply here.
    if os.path.islink(os.path.join(ctx["root"], ctx["bundle"])):
        return []
    relative, dangling = [], []
    scan_body, _ = _mask_code_spans(_mask_managed_block(ctx["body"]))
    # fenced/inline example links and the managed index block are not hand-authored links
    for m in re.finditer(r"\[[^\]]+\]\(([^)]+)\)", scan_body):
        tgt = m.group(1).split("#")[0].split("?")[0].strip()
        if not tgt.endswith(".md") or tgt.startswith(("http://", "https://", "mailto:")):
            continue
        if not tgt.startswith("/"):
            relative.append(tgt)
        elif not os.path.isfile(os.path.join(ctx["root"], tgt.lstrip("/"))):
            dangling.append(tgt)
    msgs = []
    if relative:
        msgs.append("non catalogue-absolute link(s) (use /bundle/…): {}".format(", ".join(relative)))
    if dangling:
        msgs.append("catalogue-absolute link(s) not resolving from root: {}".format(", ".join(dangling)))
    return msgs


def check_superseded_by_resolves(ctx):
    """D01 (OKFT-gpcx) — `superseded_by` is a pointer, and a pointer to
    nothing is the same violation class as a dead crosslink: ERROR, part of
    the `0 violations` commit gate. Same catalogue-root-absolute resolution
    check_crosslink_format uses (leading `/` = catalogue root)."""
    if ctx["is_reserved"] or not ctx["has_fm"]:
        return []
    sb = _dequote(ctx["fm"].get("superseded_by", "").strip())
    if not sb:
        return []
    if os.path.isfile(os.path.join(ctx["root"], sb.lstrip("/"))):
        return []
    return ["superseded_by target does not resolve: {}".format(sb)]


def check_superseded_by_scope(ctx):
    """D01 (OKFT-gpcx) — the scope guard: `superseded_by` is defined only for
    `type: Decision` concepts. A concept of another type carrying the field
    is not a hard failure (it may be an intentional early use or a schema
    typo an author can fix at leisure) — WARNING, not ERROR."""
    if ctx["is_reserved"] or not ctx["has_fm"]:
        return []
    sb = _dequote(ctx["fm"].get("superseded_by", "").strip())
    if not sb:
        return []
    t = ctx["fm"].get("type", "").strip()
    if t == "Decision":
        return []
    return ["superseded_by used on non-Decision concept (type={})".format(
        t or "<empty>")]


_TAG = r"</?[A-Za-z][\w:-]*>"
XML_TAG_CHAIN_RE = re.compile(r"{t}(?:\.(?:{t}|[A-Za-z0-9_-]+))*".format(t=_TAG))
SAFE_HTML_TAGS = {"br", "hr", "sub", "sup", "kbd", "mark", "code", "wbr"}
AUTOLINK_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")


def _sync_records(ctx, canon_index):
    """[(rec, status)] for one file, or [] without paying for the canon index.

    The early exit IS the performance contract of the two check entries: a
    catalogue with no materialised block must not trigger the catalogue walk
    build_canon_block_index costs."""
    if SYNC_OPEN_LIT not in ctx["body"]:
        return []
    canon = canon_index()
    return [(r, classify_sync_block(r, canon))
            for r in parse_sync_blocks(ctx["body"])]


def check_sync_integrity(ctx, canon_index):
    """Errors: a materialised canon block whose markers are broken, whose
    owner is gone, or whose payload was edited locally.

    `consumer-modified` is an error, not a warning: a consumer holding an
    edited copy of foreign Canon has silently become a second authority, which
    is precisely what this mechanism exists to prevent."""
    return ["sync block `{}` from {}: {}".format(
                rec["id"] or "?", rec["source"] or "?", status)
            for rec, status in _sync_records(ctx, canon_index)
            if status in ("malformed", "source-missing", "consumer-modified",
                          "both-changed")]


def check_sync_stale(ctx, canon_index):
    """Warning: the owner's block moved on while the local copy is untouched —
    mechanically repairable, so it never blocks."""
    return ["sync block `{}` from {} is outdated — run sync-update".format(
                rec["id"], rec["source"])
            for rec, status in _sync_records(ctx, canon_index)
            if status == "source-changed"]


def check_canon_blocks(ctx):
    """Owner-side integrity, index-free: an unterminated `okf:canon` marker,
    or one id declared twice in the same concept — which would make
    `(source, id)` addressing ambiguous for every consumer of it."""
    out, seen = [], set()
    for blk in parse_canon_blocks(ctx["body"]):
        if blk["payload"] is None:
            out.append("canon block `{}` has no closing {}".format(
                blk["id"], CANON_END))
        if blk["id"] in seen:
            out.append("canon block id `{}` declared twice".format(blk["id"]))
        seen.add(blk["id"])
    return out


def _mask_code_spans(body):
    """Stash materialised canon blocks, fenced code blocks and inline code so
    a pattern scan skips them.
    Frontmatter is already split off by the caller (ctx["body"]/split_frontmatter),
    so only sync blocks/fences/inline-code need masking here. Mirrors the
    Vault-side wrap-hex-tags.js mask/unmask convention for the same class of
    problem.

    The sync stash runs FIRST, and it is not cosmetic: a materialised canon
    block is owned by its canon concept, so every scanner reading through this
    mask must neither report nor rewrite inside it. _unmask restores the
    stashed text byte-identically, which is what keeps a rewriter (fix-
    crosslinks, fix-xml-tags) from turning a synced payload into a false
    `consumer-modified`."""
    tokens = []

    def stash(m):
        tokens.append(m.group(0))
        return "\x00{}\x00".format(len(tokens) - 1)

    body = SYNC_SPAN_RE.sub(stash, body)
    body = re.sub(r"(`{3,}|~{3,})[\s\S]*?\1", stash, body)
    body = re.sub(r"`[^`\n]+`", stash, body)
    return body, tokens


def _unmask(text, tokens):
    return re.sub(r"\x00(\d+)\x00", lambda m: tokens[int(m.group(1))], text)


def _is_ignorable_chain(chain):
    """Skip real HTML (`<br>`, `</br>`, ...) and markdown autolinks
    (`<https://...>`) — only placeholder-shaped chains are violations."""
    if "." not in chain and chain.strip("<>/").lower() in SAFE_HTML_TAGS:
        return True
    inner = chain.split(".", 1)[0][1:-1].lstrip("/")
    return bool(AUTOLINK_RE.match(inner))


def find_xml_like_tags(body):
    """Angle-bracket placeholder chains like `<info>.<other>` or `<tag>.<tag2>.go`
    outside code spans — Obsidian misreads these as unclosed XML/HTML tags."""
    masked, _ = _mask_code_spans(body)
    return [m for m in XML_TAG_CHAIN_RE.findall(masked) if not _is_ignorable_chain(m)]


def check_xml_like_tags(ctx):
    if ctx["is_reserved"]:
        return []
    hits = find_xml_like_tags(ctx["body"])
    return ["angle-bracket placeholder(s) not in code-fence: {}".format(", ".join(sorted(set(hits))))] if hits else []


def fix_xml_like_tags(root, target, dry_run=False):
    """Wrap angle-bracket placeholder chains in inline code across every
    non-reserved .md under `target` (bundle or bundle/subdir, or the whole
    catalogue when None). Returns [(rel, count), ...]."""
    touched = []
    for bundle, bp in resolve_scopes(root, target):
        for ap in iter_all_md(bp, prune_staging=False):
            if os.path.basename(ap).lower() in RESERVED:
                continue
            text = read_file(ap)
            _, body = split_frontmatter(text)
            head = text[:len(text) - len(body)]
            masked, tokens = _mask_code_spans(body)
            count = 0

            def repl(m):
                nonlocal count
                chain = m.group(0)
                if _is_ignorable_chain(chain):
                    return chain
                count += 1
                return "`" + chain + "`"

            new_masked = XML_TAG_CHAIN_RE.sub(repl, masked)
            new_body = _unmask(new_masked, tokens)
            if count:
                rel = os.path.relpath(ap, root).replace(os.sep, "/")
                touched.append((rel, count))
                if not dry_run:
                    write_file(ap, head + new_body)
    return touched


def cmd_fix_xml_tags(root, args):
    target = args.target
    if target:
        tp = os.path.join(root, target.rstrip("/"))
        if not os.path.isdir(tp):
            raise OkfError("not_found", "not a directory: {}".format(target))
    touched = fix_xml_like_tags(root, target, dry_run=args.check)
    verb = "would wrap" if args.check else "wrapped"
    for rel, n in touched:
        print("{:<12} {}  ({} chain(s))".format(verb, rel, n))
    print("fix-xml-tags: {} file(s) {}, {} chain(s) total".format(
        len(touched), verb, sum(n for _, n in touched)))


def check_asset_placement(bundle_path):
    """Non-md, non-hidden files that live outside <bundle>/assets/. Returns
    a list of paths relative to bundle_path."""
    bad = []
    for dirpath, dirnames, filenames in os.walk(bundle_path):
        dirnames[:] = [d for d in dirnames
                       if not d.startswith(".") and not d.startswith("_") and d != "assets"]
        for fn in filenames:
            if fn.endswith(".md") or fn.startswith("."):
                continue
            bad.append(os.path.relpath(os.path.join(dirpath, fn), bundle_path).replace(os.sep, "/"))
    return bad


def check_entry_file_description(bundle_path):
    """A bundle's entry file (INDEX-MAP.md preferred, else index.md) must carry
    an H1 + a real intro paragraph — `index --full` surfaces this as the
    bundle's `description`. Returns a list of violation messages (0..2)."""
    for fn in ("INDEX-MAP.md", "index.md"):
        fp = os.path.join(bundle_path, fn)
        if os.path.isfile(fp):
            h1, desc = index_h1_and_desc(fp)
            msgs = []
            if not h1:
                msgs.append("{} missing H1".format(fn))
            if not desc.strip():
                msgs.append("{} missing intro paragraph (used as bundle description)".format(fn))
            return msgs
    return ["no entry file (INDEX-MAP.md/index.md) found"]


def resolve_crosslink_target(root, bundle, cdir, tgt):
    """Absolute filesystem path a link target `tgt` (found in bundle/cdir) points
    at, then re-expressed as the canonical catalogue-root-absolute form
    (`/bundle/subdir/concept.md`, leading `/` = catalogue root = Obsidian vault
    root). Interpretations are tried in order so the same rewriter both migrates
    legacy links and stays idempotent:
      1. leading `/` as LEGACY bundle-root (`/subdir/x.md` -> bundle/subdir/x.md)
      2. leading `/` as already-catalogue-root (`/bundle/subdir/x.md`)
      3. relative to cdir within the bundle (`x.md`, `sub/x.md`, `../other/x.md`)
    Returns the canonical `/…` string only if the target file really exists (the
    safety anchor that leaves doc examples on non-existent paths untouched)."""
    if tgt.startswith("/"):
        p = tgt.lstrip("/")
        dest = os.path.join(root, bundle, p)            # legacy bundle-root
        if not os.path.isfile(dest):
            dest = os.path.join(root, p)                 # already catalogue-root
    else:
        dest = os.path.normpath(os.path.join(root, bundle, cdir, tgt))
        if not os.path.isfile(dest):
            # mis-depthed cross-bundle relative link (`../other-bundle/x.md` whose
            # `..` count never reaches the catalogue root): repoint from root iff
            # the `../`-stripped tail is a real file — no guessing beyond existence.
            tail = re.sub(r"^(?:\.\.?/)+", "", tgt)
            cand = os.path.join(root, tail)
            if os.path.isfile(cand):
                dest = cand
    if not os.path.isfile(dest):
        return None
    return "/" + os.path.relpath(dest, root).replace(os.sep, "/")


def rewrite_crosslinks_in_body(root, bundle, cdir, body):
    """Rewrite every resolvable markdown link to canonical catalogue-root-absolute
    form (`/bundle/subdir/concept.md`). Migrates legacy bundle-relative (`/sub/x`)
    and path-relative (`x`, `../other/x`) links alike; already-canonical links are
    left byte-identical (idempotent). Skips http(s)/mailto/anchor-only, and
    everything inside fenced or inline code — a link written between backticks
    is prose *about* link syntax, which Obsidian never resolves. Masking it
    keeps the OKF documentation bundles from reporting their own examples as
    unresolved, and stops a fenced example whose path happens to resolve from
    being silently rewritten. Mirrors check_crosslink_format, which masks the
    same spans. Returns (new_body, changed_count, unresolved_targets)."""
    changed = 0
    unresolved = []

    def repl(m):
        nonlocal changed
        label, target = m.group(1), m.group(2)
        raw_tgt, _, anchor = target.partition("#")
        raw_tgt = raw_tgt.strip()
        if not raw_tgt.endswith(".md") or raw_tgt.startswith(("http://", "https://", "mailto:")):
            return m.group(0)
        resolved = resolve_crosslink_target(root, bundle, cdir, raw_tgt)
        if resolved is None:
            unresolved.append(raw_tgt)
            return m.group(0)
        new_target = resolved + ("#" + anchor if anchor else "")
        if new_target == target:
            return m.group(0)                            # already canonical
        changed += 1
        return "[{}]({})".format(label, new_target)

    masked, tokens = _mask_code_spans(body)
    new_body = _unmask(CROSSLINK_RE.sub(repl, masked), tokens)
    return new_body, changed, unresolved


def fix_crosslinks(root, target, dry_run=False, include_reserved=False):
    """Rewrite crosslinks in every non-reserved .md under `target` (bundle or
    bundle/subdir, or the whole catalogue when None) to catalogue-root-absolute
    form. `include_reserved=True` (D-fxcr-01) additionally rewrites RESERVED
    files (index.md, log.md, readme.md, index-map.md), narrowed to the text
    outside the managed `<!-- okf:index -->` block via `_split_managed_block` —
    the block itself is never handed to the rewriter, so it stays
    byte-identical. Default (`include_reserved=False`) leaves RESERVED files
    untouched, unchanged from before this parameter existed. Returns
    (touched, unresolved): touched = [(rel, changed_count), ...],
    unresolved = [(rel, target), ...]."""
    touched, unresolved = [], []
    for bundle, bp in resolve_scopes(root, target):
        for ap in iter_all_md(bp, prune_staging=False):
            is_reserved = os.path.basename(ap).lower() in RESERVED
            if is_reserved and not include_reserved:
                continue
            text = read_file(ap)
            _, body = split_frontmatter(text)
            head = text[:len(text) - len(body)]
            cdir = os.path.dirname(os.path.relpath(ap, bp))
            rel = os.path.relpath(ap, root).replace(os.sep, "/")
            if is_reserved:
                before, block, after = _split_managed_block(body)
                new_before, changed_before, unres_before = rewrite_crosslinks_in_body(
                    root, bundle, cdir, before)
                new_after, changed_after, unres_after = rewrite_crosslinks_in_body(
                    root, bundle, cdir, after)
                new_body = new_before + block + new_after
                changed = changed_before + changed_after
                unres = unres_before + unres_after
            else:
                new_body, changed, unres = rewrite_crosslinks_in_body(root, bundle, cdir, body)
            for u in unres:
                unresolved.append((rel, u))
            if changed:
                touched.append((rel, changed))
                if not dry_run:
                    write_file(ap, head + new_body)
    return touched, unresolved


def cmd_fix_crosslinks(root, args):
    target = args.target
    if target:
        tp = os.path.join(root, target.rstrip("/"))
        if not os.path.isdir(tp):
            raise OkfError("not_found", "not a directory: {}".format(target))
    touched, unresolved = fix_crosslinks(root, target, dry_run=args.check,
                                          include_reserved=args.include_reserved)
    verb = "would rewrite" if args.check else "rewrote"
    for rel, n in touched:
        print("{:<14} {}  ({} link(s))".format(verb, rel, n))
    for rel, tgt in unresolved:
        print("unresolved     {}  -> {}".format(rel, tgt))
    print("fix-crosslinks: {} file(s) {}, {} unresolved link(s)".format(
        len(touched), verb, len(unresolved)))


# One registry of every rule `check` runs: its stable ID (`okf/` = OKF spec rule,
# `kc/` = local catalogue invariant), its severity, and the callable.
# scope "file":   check(ctx) -> [message]            one concept file per call
# scope "bundle": check({"bundle", "bp"}) -> [(path, message)]   one bundle per call
Rule = namedtuple("Rule", "id severity scope check")


def _ctx_rule(rule_id, severity):
    """One ctx sub-rule: ctx_findings reports every ctx problem under its ID, and
    this rule keeps the ones that carry its own."""
    def check(ctx):
        if ctx["bundle"] != CTX_DIR or ctx["is_reserved"]:
            return []
        if "ctx_findings" not in ctx:
            ctx["ctx_findings"] = ctx_findings(ctx["root"], ctx["ap"])
        return [m for r, m in ctx["ctx_findings"] if r == rule_id]
    return Rule(rule_id, severity, "file", check)


RULES = [
    Rule("okf/frontmatter/parseable", "error", "file", check_fm_parseable),
    Rule("okf/frontmatter/type-nonempty", "error", "file", check_type_nonempty),
    Rule("okf/type/reserved-no-type", "error", "file", check_reserved_no_type),
    Rule("kc/name/filename-chars", "error", "file", check_filename_chars),
    Rule("kc/type/registered", "warning", "file",
         lambda c: check_type_registered(c, c["types_set"])),
    Rule("kc/tag/registered", "warning", "file",
         lambda c: check_tag_registered(c, c["tags_set"])),
    Rule("kc/frontmatter/english-keys", "warning", "file", check_english_keys),
    Rule("kc/link/crosslink-format", "warning", "file", check_crosslink_format),
    Rule("kc/supersede/resolves", "error", "file", check_superseded_by_resolves),
    Rule("kc/supersede/scope", "warning", "file", check_superseded_by_scope),
    Rule("kc/frontmatter/tags-block-form", "warning", "file", check_tags_block_form),
    Rule("kc/markup/xml-like-tags", "warning", "file", check_xml_like_tags),
    Rule("kc/link/wikilink-resolvable", "warning", "file",
         lambda c: wikilinks.check_wikilink_resolvable(c, c["wl_checked"], c["wl_index"])),
    Rule("kc/sync/block", "error", "file", lambda c: check_sync_integrity(c, c["canon_index"])),
    Rule("kc/sync/stale", "warning", "file", lambda c: check_sync_stale(c, c["canon_index"])),
    Rule("kc/sync/canon-block", "error", "file", check_canon_blocks),
    _ctx_rule("kc/ctx/type", "error"),
    _ctx_rule("kc/ctx/slug", "error"),
    _ctx_rule("kc/ctx/row-format", "error"),
    _ctx_rule("kc/ctx/mode", "error"),
    _ctx_rule("kc/ctx/required-positions", "error"),
    _ctx_rule("kc/ctx/reference-position", "error"),
    _ctx_rule("kc/ctx/duplicate-entry", "error"),
    _ctx_rule("kc/ctx/dead-entry", "error"),
    _ctx_rule("kc/ctx/empty-description", "warning"),
    _ctx_rule("kc/ctx/archived-entry", "warning"),
    _ctx_rule("kc/ctx/stale-entry", "warning"),
    Rule("kc/asset/placement", "error", "bundle",
         lambda b: [("{}/{}".format(b["bundle"], rel), "non-md file outside assets/")
                    for rel in check_asset_placement(b["bp"])]),
    Rule("kc/asset/entry-file-description", "warning", "bundle",
         lambda b: [(b["bundle"], msg) for msg in check_entry_file_description(b["bp"])]),
]


def rule_severity(rule_id):
    """The registry severity of `rule_id`; KeyError for an ID no rule registers."""
    return {r.id: r.severity for r in RULES}[rule_id]


def run_checks(root, target, types_source=None):
    """Run every RULES entry over `target` (bundle or
    bundle/subdir), or the whole catalogue when target is None.

    types_source overrides <root>/TYPES.md; absent, falls back to the
    .okf.toml `types_source` config key, then to <root>/TYPES.md.

    Returns (errors, warnings), each a list of (rule_id, rel_path, message),
    partitioned by the rule's registry severity.
    """
    scopes = resolve_scopes(root, target)
    config = load_okf_config(root)
    if types_source is None:
        types_source = config.get("types_source")
    types_set = load_types(root, types_source)
    tags_set = load_tags(root)
    # The basename index costs a full catalogue walk, so it is built only when
    # a bundle IN THIS RUN'S SCOPE has opted in — an unconfigured catalogue, or
    # a scan targeting a bundle that did not opt in, pays nothing.
    wl_checked = (wikilinks.wikilink_checked_bundles(config, root)
                  & {b.lower() for b, _ in scopes})
    wl_index = wikilinks.build_concept_basename_index(root) if wl_checked else {}
    # Same deliberate laziness as wl_index above: the canon index costs a full
    # catalogue walk, and a catalogue with no materialised block never asks
    # for it — check_sync_* return before calling this on such a file.
    canon = {"loaded": False, "idx": {}}

    def canon_index():
        if not canon["loaded"]:
            canon["idx"] = sync.build_canon_block_index(root)
            canon["loaded"] = True
        return canon["idx"]

    run = {"types_set": types_set, "tags_set": tags_set, "wl_checked": wl_checked,
           "wl_index": wl_index, "canon_index": canon_index}
    file_rules = [r for r in RULES if r.scope == "file"]
    bundle_rules = [r for r in RULES if r.scope == "bundle"]

    errors, warnings = [], []

    def add(rule, path, msg):
        (errors if rule.severity == "error" else warnings).append((rule.id, path, msg))

    for bundle, bp in scopes:
        for ap in iter_all_md(bp):
            ctx = gather_file_context(root, bundle, ap)
            ctx.update(run)
            for rule in file_rules:
                for msg in rule.check(ctx):
                    add(rule, ctx["rel"], msg)
        for rule in bundle_rules:
            for path, msg in rule.check({"bundle": bundle, "bp": bp}):
                add(rule, path, msg)
    return errors, warnings


def cmd_check(root, args):
    target = getattr(args, "target", None)
    if target and not os.path.isdir(os.path.join(root, os.path.normpath(target))):
        # Without this a typo'd or renamed bundle scanned nothing and exited 0 —
        # a clean bill of health for a directory that does not exist.
        raise OkfError("not_found", "not a directory: {}".format(target))
    errors, warnings = run_checks(root, getattr(args, "target", None),
                                  types_source=getattr(args, "types", None))
    if args.strict:
        errors, warnings = errors + warnings, []
    _print_findings(errors, warnings, args.json)
    if errors:
        raise OkfError("non_conformant", "")


def _print_findings(errors, warnings, as_json):
    if as_json:
        print(json.dumps({
            "errors": [{"check": n, "path": p, "message": m} for n, p, m in errors],
            "warnings": [{"check": n, "path": p, "message": m} for n, p, m in warnings],
        }))
    else:
        for name, path, msg in errors:
            print("ERROR    {:<20} {}  ({})".format(name, path, msg))
        for name, path, msg in warnings:
            print("WARNING  {:<20} {}  ({})".format(name, path, msg))
        print("OK — 0 violations" if not errors else "{} VIOLATIONS".format(len(errors)))


def add_check_parser(sub):
    pc = _sub(sub, "check", "maintenance",
              "conformance scan: §9 hard rules + local invariants")
    pc.add_argument("target", nargs="?", help="<bundle> or <bundle>/<subdir> (default: whole catalogue)").completer = _complete_scopes
    pc.add_argument("--strict", action="store_true", help="promote warnings to errors")
    pc.add_argument("--json", action="store_true", help="machine-readable output")
    pc.add_argument("--types", help="explicit TYPES.md path (overrides .okf.toml types_source)").completer = _complete_files


def add_fix_crosslinks_parser(sub):
    pfx = _sub(sub, "fix-crosslinks", "maintenance",
               "rewrite links to catalogue-root-absolute form (/bundle/subdir/concept.md)")
    pfx.add_argument("target", nargs="?", help="<bundle> or <bundle>/<subdir> (default: whole catalogue)").completer = _complete_scopes
    pfx.add_argument("--check", action="store_true", help="dry-run: report without writing")
    pfx.add_argument("--include-reserved", action="store_true",
                      dest="include_reserved",
                      help="also rewrite RESERVED files (index.md, log.md, "
                           "readme.md, index-map.md), narrowed to the text "
                           "outside the managed <!-- okf:index --> block, "
                           "which stays byte-identical (D-fxcr-01, off by "
                           "default)")


def add_fix_xml_tags_parser(sub):
    pfxt = _sub(sub, "fix-xml-tags", "maintenance",
                "wrap `<tag>`/`<tag>.<tag2>` placeholders in inline code")
    pfxt.add_argument("target", nargs="?", help="<bundle> or <bundle>/<subdir> (default: whole catalogue)").completer = _complete_scopes
    pfxt.add_argument("--check", action="store_true", help="dry-run: report without writing")


COMMANDS = {
    "check": (cmd_check, add_check_parser),
    "fix-crosslinks": (cmd_fix_crosslinks, add_fix_crosslinks_parser),
    "fix-xml-tags": (cmd_fix_xml_tags, add_fix_xml_tags_parser),
}
