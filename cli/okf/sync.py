"""Canon block synchronisation: the canon and sync marker parsing, rendering and
hashing, the catalogue-wide canon index, the status classification, and the
sync-export, sync-insert, sync-status and sync-update commands."""

import hashlib
import json
import os
import sys

from okf.catalogue import (
    CANON_END, CANON_OPEN_RE, SYNC_BODY, SYNC_END, SYNC_OPEN_LIT, SYNC_OPEN_RE, iter_all_md,
    read_file, read_file_verbatim, resolve_concept, resolve_scopes, split_frontmatter,
    write_file_verbatim,
)
from okf.parser_support import _complete_concepts, _complete_scopes, _completion_root, _sub


# --- canon block synchronisation -------------------------------------------
# A canonical concept declares addressable blocks; a consumer carries
# materialised copies of them and stays verifiably in sync. There is no index
# and no staleness store: the relationship is derived by a catalogue walk at
# command time, exactly as `check` derives its own, so there is no second
# truth source that can go stale (PO decision 2026-09-13).

SYNC_STATUSES = ("synced", "source-changed", "consumer-modified",
                 "both-changed", "source-missing", "malformed")


def sync_hash(payload):
    """Fingerprint of a canon block payload. Normalised (CRLF folded, outer
    whitespace stripped) so a line-ending translation or a trailing newline
    gained in transit does not read as a content change. sha1, first 12 hex
    chars — same convention as concept_cache_key in embeddings/build_tagvec."""
    return hashlib.sha1(
        payload.replace("\r\n", "\n").strip().encode("utf-8")).hexdigest()[:12]


def parse_canon_blocks(body):
    """Every `okf:canon` block declared in one concept body, in document order:
    [{"id", "payload", "span"}]. `payload` is None when the opening marker has
    no matching CANON_END — an unterminated marker is reported, never guessed
    at, exactly as _split_managed_block refuses to guess for the index block.
    `span` is (start, end) in `body`, end past CANON_END (or end-of-body when
    unterminated)."""
    out = []
    for m in CANON_OPEN_RE.finditer(body):
        ei = body.find(CANON_END, m.end())
        if ei == -1:
            out.append({"id": m.group(1), "payload": None,
                        "span": (m.start(), len(body))})
            continue
        out.append({"id": m.group(1), "payload": body[m.end():ei],
                    "span": (m.start(), ei + len(CANON_END))})
    return out


def parse_sync_blocks(body):
    """Every materialised canon block in one consumer body, in document order:
    [{"id", "source", "hash", "payload", "span", "malformed"}].

    Scanning starts from each literal SYNC_OPEN_LIT occurrence rather than
    from the full-form regex, so a hand-edited marker still produces a record
    (malformed=True) instead of vanishing from every report — a block nobody
    can see is the one that silently turns a consumer authoritative.

    `span` is (start, end) in the ORIGINAL body, end past SYNC_END, so
    body[span[0]:span[1]] is the whole block verbatim. Same contract as
    parse_wikilinks' span: it is what the rewriters splice against."""
    out = []
    starts = []
    i = body.find(SYNC_OPEN_LIT)
    while i != -1:
        starts.append(i)
        i = body.find(SYNC_OPEN_LIT, i + 1)
    for n, start in enumerate(starts):
        # A malformed block must not swallow the next one: every structural
        # search is bounded by the following opening marker.
        limit = starts[n + 1] if n + 1 < len(starts) else len(body)
        rec = {"id": None, "source": None, "hash": None, "payload": None,
               "span": (start, limit), "malformed": True}
        m = SYNC_OPEN_RE.match(body, start)
        if not m or m.end() > limit:
            out.append(rec)
            continue
        rec["id"], rec["source"], rec["hash"] = (
            m.group("id"), m.group("source"), m.group("hash"))
        bi = body.find(SYNC_BODY, m.end(), limit)
        if bi == -1:
            out.append(rec)
            continue
        ei = body.find(SYNC_END, bi + len(SYNC_BODY), limit)
        if ei == -1:
            out.append(rec)
            continue
        rec["payload"] = body[bi + len(SYNC_BODY):ei]
        rec["span"] = (start, ei + len(SYNC_END))
        rec["malformed"] = False
        out.append(rec)
    return out


def render_sync_block(block_id, source, payload):
    """The one place the sync notation is authored — analogue of render_block
    for the index family. The visible callout is generated between the opening
    marker and SYNC_BODY, so an Obsidian reader sees the text is foreign Canon
    while the hash still covers the payload alone."""
    return (
        "<!-- okf:sync id={} source={} hash={} -->\n"
        "> [!quote] Synchronisiert aus `{}` — Canon-Owner, hier nicht bearbeiten.\n"
        "{}\n{}\n{}".format(block_id, source, sync_hash(payload), source,
                            SYNC_BODY, payload.strip("\n"), SYNC_END))


def build_canon_block_index(root):
    """{(concept_rel, block_id): payload} over the whole catalogue.

    `concept_rel` is spelled exactly like ctx["rel"], so a consumer's
    `source=/bundle/concept.md` compares by plain string after stripping the
    leading slash — no path arithmetic at classification time. Costs one
    catalogue walk, like check's basename index, which is why every caller
    builds it lazily."""
    idx = {}
    # include_archive: archiving an owner rewrites every consumer's `source=`
    # to the `/_archive/...` path, so the archived concept must stay a
    # resolvable owner — otherwise one archive turns every consumer into a
    # `source-missing` error. prune_staging=False (OKFT bug): "_"-prefixed
    # dirs (_inbox, _archive, any custom staging dir) are pruned by default,
    # so an owner living there was invisible here even though the file
    # exists — every consumer then misreported `source-missing`.
    for _, bp in resolve_scopes(root, None, include_archive=True):
        for ap in iter_all_md(bp, prune_staging=False):
            _, body = split_frontmatter(read_file(ap))
            if "okf:canon" not in body:
                continue
            rel = os.path.relpath(ap, root).replace(os.sep, "/")
            for blk in parse_canon_blocks(body):
                if blk["payload"] is None:
                    continue          # unterminated: check_canon_blocks reports it
                idx.setdefault((rel, blk["id"]), blk["payload"])
    return idx


def classify_sync_block(rec, canon):
    """One of six statuses for a parsed sync record against the canon index:
    malformed, source-missing, synced, source-changed, consumer-modified,
    both-changed.

    `consumer-modified` and `both-changed` outrank `source-changed`: a local
    edit to a materialised copy is the failure this whole mechanism exists to
    catch, and re-materialising over it would destroy the only copy of that
    edit."""
    if rec["malformed"] or not rec["source"].startswith("/"):
        return "malformed"
    payload = canon.get((rec["source"].lstrip("/"), rec["id"]))
    if payload is None:
        return "source-missing"
    src_matches = sync_hash(payload) == rec["hash"]
    local_matches = sync_hash(rec["payload"]) == rec["hash"]
    if src_matches and local_matches:
        return "synced"
    if local_matches:
        return "source-changed"
    return "consumer-modified" if src_matches else "both-changed"


def _canon_payload(root, concept, block_id):
    """(abspath, rel, payload) of one canon block, or exit 1 naming what is
    missing. Shared by sync-export and sync-insert so both refuse identically."""
    ap = resolve_concept(root, concept)
    rel = os.path.relpath(ap, root).replace(os.sep, "/")
    _, body = split_frontmatter(read_file(ap))
    for blk in parse_canon_blocks(body):
        if blk["id"] != block_id:
            continue
        if blk["payload"] is None:
            print("canon block `{}` in {} has no closing {}".format(
                block_id, rel, CANON_END), file=sys.stderr)
            sys.exit(1)
        return ap, rel, blk["payload"]
    print("no canon block `{}` in {}".format(block_id, rel), file=sys.stderr)
    sys.exit(1)


def scan_sync_blocks(root, target, source=None, block_id=None):
    """[(rel, ap, rec, status)] for every materialised canon block under
    `target`, filtered by exact `source`/`block_id` when given.

    Scope semantics are `check`'s, deliberately: the two surfaces must agree
    on which files carry a sync block, or a block `check` errors on is one
    `sync-update` cannot reach."""
    canon = build_canon_block_index(root)
    out = []
    for _, bp in resolve_scopes(root, target):
        for ap in iter_all_md(bp):
            _, body = split_frontmatter(read_file(ap))
            if SYNC_OPEN_LIT not in body:
                continue
            rel = os.path.relpath(ap, root).replace(os.sep, "/")
            for rec in parse_sync_blocks(body):
                if source is not None and rec["source"] != source:
                    continue
                if block_id is not None and rec["id"] != block_id:
                    continue
                out.append((rel, ap, rec, classify_sync_block(rec, canon)))
    return canon, out


def _sync_addr(rec):
    """`/bundle/owner.md#block-id` — the human-readable address of one block,
    degraded but still printable when the marker itself is malformed."""
    return "{}#{}".format(rec["source"] or "?", rec["id"] or "?")


def cmd_sync_export(root, args):
    _, _, payload = _canon_payload(root, args.concept, args.block_id)
    # Payload only, nothing else, so the output pipes.
    sys.stdout.write(payload.strip("\n") + "\n")


def cmd_sync_insert(root, args):
    owner_ap, owner_rel, payload = _canon_payload(root, args.concept, args.block_id)
    source = "/" + owner_rel
    cap = resolve_concept(root, args.consumer)
    consumer_rel = os.path.relpath(cap, root).replace(os.sep, "/")
    if cap == owner_ap:
        print("{} owns `{}` — a canon owner does not consume its own block"
              .format(consumer_rel, args.block_id), file=sys.stderr)
        sys.exit(1)
    text = read_file_verbatim(cap)
    if text is None:
        print("not valid UTF-8: {}".format(consumer_rel), file=sys.stderr)
        sys.exit(1)
    _, body = split_frontmatter(text)
    head = text[:len(text) - len(body)]
    for rec in parse_sync_blocks(body):
        if rec["id"] != args.block_id:
            continue
        if rec["source"] == source:
            print("{} already carries `{}` from {} — use sync-update to "
                  "refresh it".format(consumer_rel, args.block_id, source),
                  file=sys.stderr)
        else:
            # Two blocks with one id read as one block to a human, and
            # `sync-status --block` could not tell them apart either.
            print("{} already carries a block `{}` from {} — the id would be "
                  "ambiguous in this concept".format(
                      consumer_rel, args.block_id, rec["source"] or "?"),
                  file=sys.stderr)
        sys.exit(1)
    block = render_sync_block(args.block_id, source, payload)
    new_body = body.rstrip("\n") + "\n\n" + block + "\n"
    if not args.apply:
        print("would insert    {}   {}#{}".format(
            consumer_rel, source, args.block_id))
        print("sync-insert (dry-run): re-run with --apply.")
        return
    write_file_verbatim(cap, head + new_body)
    print("inserted        {}   {}#{}".format(
        consumer_rel, source, args.block_id))


def cmd_sync_status(root, args):
    target = getattr(args, "target", None)
    if target and not os.path.isdir(os.path.join(root, os.path.normpath(target))):
        # Same gate as cmd_check: a typo'd bundle scanned nothing and exited 0.
        print("not a directory: {}".format(target), file=sys.stderr)
        sys.exit(1)
    _, found = scan_sync_blocks(root, target, source=args.source,
                                block_id=args.block)
    totals = {s: 0 for s in SYNC_STATUSES}
    rows = []
    for rel, _ap, rec, status in found:
        totals[status] += 1
        rows.append({"consumer": rel, "id": rec["id"], "source": rec["source"],
                     "status": status})
    if getattr(args, "json", False):
        print(json.dumps({"blocks": rows, "totals": totals}))
    else:
        for row in rows:
            print("{:<18} {:<32} {}#{}".format(
                row["status"], row["consumer"], row["source"] or "?",
                row["id"] or "?"))
        print("sync-status: " + ", ".join(
            "{} {}".format(totals[s], s) for s in SYNC_STATUSES))
    sys.exit(1 if any(r["status"] != "synced" for r in rows) else 0)


def cmd_sync_update(root, args):
    target = getattr(args, "target", None)
    if target and not os.path.isdir(os.path.join(root, os.path.normpath(target))):
        print("not a directory: {}".format(target), file=sys.stderr)
        sys.exit(1)
    canon, found = scan_sync_blocks(root, target, source=args.source,
                                    block_id=args.block)
    verb = "updated" if args.apply else "would update"
    per_file, refused, unresolvable = {}, [], []
    for rel, ap, rec, status in found:
        if status == "synced":
            continue
        if status in ("source-missing", "malformed"):
            # Never written, always reported: repairing or deleting a block
            # whose owner is gone, or whose markers a human broke, is a human
            # decision, not a rewrite.
            unresolvable.append((rel, rec, status))
            continue
        if status in ("consumer-modified", "both-changed") and not args.force:
            refused.append((rel, rec, status))
            continue
        per_file.setdefault(ap, []).append((rel, rec))
    updated = []
    for ap, recs in per_file.items():
        text = read_file_verbatim(ap)
        if text is None:
            print("note: skipping {} — not valid UTF-8".format(ap),
                  file=sys.stderr)
            continue
        _, body = split_frontmatter(text)
        head = text[:len(text) - len(body)]
        out, last = [], 0
        for rel, rec in sorted(recs, key=lambda t: t[1]["span"][0]):
            a, b = rec["span"]
            payload = canon[(rec["source"].lstrip("/"), rec["id"])]
            out.append(body[last:a])
            out.append(render_sync_block(rec["id"], rec["source"], payload))
            last = b
            updated.append((rel, rec))
        out.append(body[last:])
        if args.apply:
            write_file_verbatim(ap, head + "".join(out))
    for rel, rec in updated:
        print("{:<14} {}   {}".format(verb, rel, _sync_addr(rec)))
    for rel, rec, _status in refused:
        print("refused        {}   {}  (consumer copy modified — reconcile "
              "into the canon owner first, or --force to discard)".format(
                  rel, _sync_addr(rec)))
    for rel, rec, status in unresolvable:
        print("{:<14} {}   {}".format(status, rel, _sync_addr(rec)))
    print("sync-update: {} {}, {} refused, {} unresolvable.{}".format(
        len(updated), verb, len(refused), len(unresolvable),
        "" if args.apply else " Re-run with --apply."))
    sys.exit(1 if (refused or unresolvable) else 0)


def _complete_block_ids(parsed_args, **_):
    """Canon block ids declared in the concept already on the line. An unknown
    concept makes resolve_concept exit, which ends the completion run with no
    candidates: the right answer."""
    root = _completion_root(parsed_args)
    concept = getattr(parsed_args, "concept", None)
    if root is None or not concept:
        return []
    _fm, body = split_frontmatter(read_file(resolve_concept(root, concept)))
    return [blk["id"] for blk in parse_canon_blocks(body)]


def _complete_canon_sources(parsed_args, **_):
    root = _completion_root(parsed_args)
    if root is None:
        return []
    return sorted({"/" + rel for rel, _bid in build_canon_block_index(root)})


def _complete_canon_block_ids(parsed_args, **_):
    """Every declared canon block id, narrowed to --source when given."""
    root = _completion_root(parsed_args)
    if root is None:
        return []
    source = getattr(parsed_args, "source", None)
    return sorted({bid for rel, bid in build_canon_block_index(root)
                   if not source or rel == source.lstrip("/")})


def add_sync_export_parser(sub):
    pse = _sub(sub, "sync-export", "navigation",
               "print a canonical block's payload for materialisation elsewhere")
    pse.add_argument("concept", help="canonical concept (<bundle>/<concept-id>)").completer = _complete_concepts
    pse.add_argument("block_id", metavar="block-id",
                     help="canon block id declared in that concept").completer = _complete_block_ids


def add_sync_insert_parser(sub):
    psi = _sub(sub, "sync-insert", "maintenance",
               "materialise a canonical block inside a consumer concept (dry-run default)")
    psi.add_argument("consumer", help="consumer concept to insert into (<bundle>/<concept-id>)").completer = _complete_concepts
    psi.add_argument("concept", help="canonical owner concept (<bundle>/<concept-id>)").completer = _complete_concepts
    psi.add_argument("block_id", metavar="block-id", help="canon block id to materialise").completer = _complete_block_ids
    psi.add_argument("--apply", action="store_true",
                     help="write the block (default: dry-run preview only)")


def add_sync_status_parser(sub):
    pss = _sub(sub, "sync-status", "maintenance",
               "drift report for every materialised canon block")
    pss.add_argument("target", nargs="?",
                     help="<bundle> or <bundle>/<subdir> (default: whole catalogue)").completer = _complete_scopes
    pss.add_argument("--source",
                     help="only blocks whose canonical source is this path (/bundle/concept.md)").completer = _complete_canon_sources
    pss.add_argument("--block", metavar="BLOCK_ID", help="only blocks with this id").completer = _complete_canon_block_ids
    pss.add_argument("--json", action="store_true", help="machine-readable output")


def add_sync_update_parser(sub):
    psu = _sub(sub, "sync-update", "maintenance",
               "re-materialise outdated consumer blocks from their canon owner (dry-run default)")
    psu.add_argument("target", nargs="?",
                     help="<bundle> or <bundle>/<subdir> (default: whole catalogue)").completer = _complete_scopes
    psu.add_argument("--source",
                     help="only blocks whose canonical source is this path (/bundle/concept.md)").completer = _complete_canon_sources
    psu.add_argument("--block", metavar="BLOCK_ID", help="only blocks with this id").completer = _complete_canon_block_ids
    psu.add_argument("--apply", action="store_true",
                     help="write changes (default: dry-run preview only)")
    psu.add_argument("--force", action="store_true",
                     help="also overwrite a consumer copy that was modified locally (discards it)")


COMMANDS = {
    "sync-export": (cmd_sync_export, add_sync_export_parser),
    "sync-insert": (cmd_sync_insert, add_sync_insert_parser),
    "sync-status": (cmd_sync_status, add_sync_status_parser),
    "sync-update": (cmd_sync_update, add_sync_update_parser),
}
