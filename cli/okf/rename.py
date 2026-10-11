"""The move-and-rewrite commands: rename and archive, which share one validation,
planning and application core (`perform_rename`, also the engine of `ctx rename`),
and rewrite-path, the literal path-string replace across text files."""

import os
import re
import subprocess
import sys

from okf import catalogue, check, linkscan, wikilinks
from okf.catalogue import (
    CROSSLINK_RE, RESERVED, SYNC_OPEN_LIT, SYNC_OPEN_RE, _prune_walk_dirs, ctx_memberships,
    iter_all_md, load_ctx, read_file, read_file_verbatim, reindex_tree, resolve_scopes, save_ctx,
    split_frontmatter, write_file_verbatim,
)
from okf.linkscan import iter_rename_scan_md, wikilink_scan_text
from okf.parser_support import _complete_concept_files, _complete_concepts, _complete_dirs, _sub
from okf.sync import parse_sync_blocks


REWRITE_EXTS = (".md", ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".rb",
                ".yml", ".yaml", ".toml", ".json", ".txt", ".rst", ".cfg", ".ini", ".sh")


def rewrite_path(scan_root, old, new, dry_run=False):
    """Literal old->new path-string replace across text files under scan_root
    (covers non-markdown references markdown tooling can't see). Prunes .git,
    node_modules, dotdirs. Returns [(rel_path, count), ...]."""
    touched = []
    for dirpath, dirnames, filenames in os.walk(scan_root):
        _prune_walk_dirs(dirnames)
        for fn in filenames:
            if not fn.endswith(REWRITE_EXTS):
                continue
            ap = os.path.join(dirpath, fn)
            text = read_file(ap)
            pat = re.compile(r"(?<![\w./-])" + re.escape(old) + r"(?![\w./-])")
            n = len(pat.findall(text))
            if not n:
                continue
            if not dry_run:
                with open(ap, "w", encoding="utf-8") as f:
                    f.write(pat.sub(lambda _m: new, text))
            touched.append((os.path.relpath(ap, scan_root).replace(os.sep, "/"), n))
    return touched


def cmd_rewrite_path(root, args):
    scan_root = os.path.abspath(args.scan_root) if getattr(args, "scan_root", None) else root
    dry = getattr(args, "check", False)
    touched = rewrite_path(scan_root, args.old, args.new, dry_run=dry)
    verb = "would rewrite" if dry else "rewrote"
    for rel, n in touched:
        print("{} {} ({}x)".format(verb, rel, n))
    print("{} file(s) {}".format(len(touched), "affected (dry-run)" if dry else "written"))


def bundle_of(root, abspath):
    """Top-level bundle dir a path lives in (its first component under root)."""
    rel = os.path.relpath(os.path.abspath(abspath), root).replace(os.sep, "/")
    return rel.split("/", 1)[0]


def link_expr(root, src_abs, dst_abs):
    """Canonical OKF link string FROM src file TO dst target: catalogue-root-
    absolute (`/bundle/subdir/concept.md`). Leading `/` = catalogue root =
    Obsidian vault root, so the same form addresses same- and cross-bundle
    targets and resolves identically for okf-cli and Obsidian. src_abs is kept
    in the signature for call-site symmetry with resolve_link_target."""
    dst_abs = os.path.abspath(dst_abs)
    return "/" + os.path.relpath(dst_abs, root).replace(os.sep, "/")


def _split_link_suffix(raw):
    """Split a link target into (path, suffix) where suffix is a #anchor/?query
    tail (kept verbatim so a rewrite preserves deep links)."""
    cut = len(raw)
    for ch in "#?":
        i = raw.find(ch)
        if i != -1:
            cut = min(cut, i)
    return raw[:cut], raw[cut:]


def resolve_link_target(root, src_abs, raw):
    """Absolute path a markdown link target resolves to, relative to src_abs's
    location. Handles catalogue-root-absolute (`/...`) and path-relative forms. Returns
    None for external / anchor-only / non-.md links."""
    path, _ = _split_link_suffix(raw.strip())
    if not path.endswith(".md") or re.match(r"^[a-z][a-z0-9+.-]*://", path) or path.startswith("mailto:"):
        return None
    if path.startswith("/"):
        # leading / = catalogue root (= Obsidian vault root), not the bundle root
        return os.path.abspath(os.path.join(root, path.lstrip("/")))
    return os.path.abspath(os.path.join(os.path.dirname(src_abs), path))


def _dedupe(pairs):
    seen, out = set(), []
    for p in pairs:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def canonical_case_path(root, abspath):
    """`abspath` respelled the way the filesystem stores it.

    On a case-insensitive filesystem the caller may name a file in any casing,
    and every downstream comparison — the basename index, the markdown ref
    matrix, the self-reference check in cmd_rename — then compares the caller's
    spelling against the scan's. Normalising once here is what keeps those
    comparisons exact rather than case-folded, which matters because a folded
    comparison would be wrong on a case-sensitive filesystem."""
    rel = os.path.relpath(abspath, root)
    if rel.startswith(".."):
        return abspath
    cur = root
    for seg in rel.replace(os.sep, "/").split("/"):
        try:
            match = next((e for e in os.listdir(cur) if e.lower() == seg.lower()), None)
        except OSError:
            match = None
        cur = os.path.join(cur, match or seg)
    return cur


def _rewrite_wikilink_raw(raw, new_link):
    """`[[old|Label]]` -> `[[new|Label]]`, given the target's new catalogue-root
    absolute path. Alias, heading/block suffix and an explicit `.md` carry over
    verbatim, so a deep link survives the rename.

    A path-qualified link keeps a path of the same depth, re-derived from the
    NEW location — carrying the old prefix over unchanged turned `[[a/old]]`
    into `[[a/new]]` after a move to bundle `b`, an address that resolves to
    nothing."""
    inner = raw[2:-2]
    cut = len(inner)
    for ch in "#|":
        i = inner.find(ch)
        if i != -1:
            cut = min(cut, i)
    head, rest = inner[:cut], inner[cut:]
    md = ".md" if head.endswith(".md") else ""
    depth = len((head[:-3] if md else head).split("/"))
    new_segments = new_link.lstrip("/")[:-3].split("/")
    page = "/".join(new_segments[-depth:])
    return "[[{}{}{}]]".format(page, md, rest)


def plan_wikilink_rewrites(root, old_abs, new_abs):
    """The wikilink half of plan_rename. Returns (records, collisions).

    Each record is a parse_wikilinks() record plus `status` (`rewrite` or
    `skipped-ambiguous`), `candidates` and `new_raw`. `collisions` are the
    concepts that ALREADY carry the new basename: renaming into an occupied
    basename turns every rewritten `[[old]]` — and every pre-existing
    `[[new]]` elsewhere — from a unique address into an ambiguous one, which
    is the very corruption the skipped-ambiguous rule refuses to commit. The
    caller decides; this function only refuses to hide it.

    A plain `[[name]]` carries no path, so a move keeping the basename leaves it
    valid — but a path-qualified `[[dir/name]]` does not survive one, which is
    why there is no basename short-circuit: every candidate occurrence is
    compared against the token the move would produce, and only a difference is
    planned. An occurrence whose page part is ambiguous is reported, never
    rewritten: guessing which of several same-named concepts the author meant is
    not a rename, it is a coin flip."""
    old_base, new_base = os.path.basename(old_abs)[:-3], os.path.basename(new_abs)[:-3]
    index = wikilinks.build_concept_basename_index(root)
    old_link = "/" + os.path.relpath(old_abs, root).replace(os.sep, "/")
    new_link = "/" + os.path.relpath(new_abs, root).replace(os.sep, "/")
    files = list(iter_rename_scan_md(root))
    # Collisions come from the rename scan's own reach, not from the resolution
    # index: the index skips staging, assets and root-level files, every one of
    # which this rename rewrites and Obsidian itself indexes.
    keep = {old_link.lower(), new_link.lower()}
    collisions = sorted(
        c for c in ("/" + os.path.relpath(ap, root).replace(os.sep, "/") for ap in files)
        if wikilinks._normalize_key(os.path.basename(c)[:-3]) == wikilinks._normalize_key(new_base)
        and c.lower() not in keep)
    # Casefolded, because resolve_wikilink is (D06). A case-sensitive filter
    # here silently excluded every case-variant inbound link from the plan — the
    # 96 live links D06 exists to rescue would have been orphaned by the very
    # rename that was supposed to carry them.
    old_key, new_key = wikilinks._normalize_key(old_base), wikilinks._normalize_key(new_base)
    after = _index_after_move(index, old_link, new_link, collisions)
    out = []
    for ap in files:
        rel = os.path.relpath(ap, root).replace(os.sep, "/")
        for rec in wikilinks.parse_wikilinks(read_file(ap), rel):
            key = wikilinks._normalize_key(rec["page"].rsplit("/", 1)[-1])
            if key not in (old_key, new_key):
                continue
            # Resolve the occurrence against the catalogue as it is and as it
            # will be. Deciding from the token alone missed the case where the
            # token does not change but its meaning does — a basename-preserving
            # move into a bundle where another concept shares the name turned a
            # unique address ambiguous with nothing to rewrite and nothing said.
            status, cands = wikilinks.resolve_wikilink(index, rel, rec["page"])
            was_ours = status == "resolved" and _same_path(cands, old_link)
            new_raw = _rewrite_wikilink_raw(rec["raw"], new_link) if was_ours else rec["raw"]
            page_after = wikilinks._split_wikilink_inner(new_raw[2:-2])[0]
            status_after, cands_after = wikilinks.resolve_wikilink(after, rel, page_after)
            turns = status == "resolved" and status_after != "resolved"
            if was_ours and new_raw != rec["raw"]:
                rec.update(status="rewrite", candidates=cands, new_raw=new_raw,
                           turns_ambiguous=turns)
            elif key == old_key and status == "ambiguous" and _contains_path(cands, old_link):
                rec.update(status="skipped-ambiguous", candidates=cands,
                           new_raw=None, turns_ambiguous=False)
            elif turns:
                # Either a bystander already pointing at the basename this move
                # is about to occupy, or a link whose token does not change but
                # whose target set does. Both lose a unique address without a
                # byte of them being touched.
                rec.update(status="collision-affected", candidates=cands_after,
                           new_raw=None, turns_ambiguous=True)
            else:
                continue
            out.append(rec)
    return out, collisions


def _index_after_move(index, old_link, new_link, collisions=()):
    """The basename index as it will look once the move has happened.

    `collisions` are folded in because they come from the rename scan's wider
    reach: a same-named draft in staging is invisible to the index but visible
    to Obsidian, so leaving it out made the simulation call an address unique
    that the app will show as ambiguous.

    `index` already carries R-06's precedence (it came out of
    build_concept_basename_index), so every key untouched by the move stays
    correct by construction. The slot the move LANDS in (`key`) is the one
    exception: it gains a brand-new candidate (`new_link`, plus any
    `collisions`) that was never subject to that precedence pass, so it is
    re-applied here via the same _apply_archive_precedence R-06 uses — this
    is R-07. Concretely: archiving a concept whose basename an active
    concept still holds must not leave the freshly archived path sitting
    next to that survivor as a second candidate; the survivor alone must
    win, exactly as it would in a freshly rebuilt index."""
    out = {}
    for k, v in index.items():
        kept = [c for c in v if c.lower() != old_link.lower()]
        if kept:
            out[k] = kept
    key = os.path.basename(new_link)[:-3].lower()
    out[key] = wikilinks._apply_archive_precedence(
        set(out.get(key, [])) | {new_link} | set(collisions))
    return out


def _same_path(cands, link):
    return len(cands) == 1 and cands[0].lower() == link.lower()


def _contains_path(cands, link):
    return any(c.lower() == link.lower() for c in cands)


def plan_rename(root, old_abs, new_abs):
    """Compute the reference rewrites a move old->new requires, WITHOUT touching
    disk (so it also drives the dry-run preview). Returns:
      inbound  = [(source_rel, old_raw, new_raw), ...]  links pointing AT the file
      outbound = [(old_raw, new_raw), ...]              the moved file's own links
                 (only when the bundle changes; within a bundle they stay valid)
      wikilinks= [record, ...]                          see plan_wikilink_rewrites
      bundles  = sorted affected bundle names (reindex targets)
      sync_sources = [(consumer_rel, count), ...]  consumers whose materialised
                 canon blocks record the moved file as their `source=`."""
    old_abs, new_abs = os.path.abspath(old_abs), os.path.abspath(new_abs)
    inbound = []
    for source_rel, raw in linkscan.build_ref_matrix(root, old_abs):
        src_abs = os.path.join(root, source_rel)
        if os.path.abspath(src_abs) == old_abs:
            continue  # self-reference: handled by the outbound pass
        _, suffix = _split_link_suffix(raw)
        new_raw = link_expr(root, src_abs, new_abs) + suffix
        if new_raw != raw:
            inbound.append((source_rel, raw, new_raw))
    outbound = []
    if bundle_of(root, old_abs) != bundle_of(root, new_abs):
        src = old_abs if os.path.exists(old_abs) else new_abs
        # Same mask the applier uses, or the plan reports rewrites the applier
        # then declines to make: the old ```-only strip left inline-code and
        # indented examples in the plan and out of the file.
        src_text = read_file(src)
        for m in CROSSLINK_RE.finditer(wikilink_scan_text(src_text)):
            raw = src_text[m.start(2):m.end(2)]
            tgt = resolve_link_target(root, old_abs, raw)
            if tgt is None or not os.path.isfile(tgt):
                continue
            _, suffix = _split_link_suffix(raw)
            new_raw = link_expr(root, new_abs, tgt) + suffix
            if new_raw != raw:
                outbound.append((raw, new_raw))
        outbound = _dedupe(outbound)
    bundles = sorted({bundle_of(root, old_abs), bundle_of(root, new_abs)})
    wikilinks, collisions = plan_wikilink_rewrites(root, old_abs, new_abs)
    return {"inbound": inbound, "outbound": outbound,
            "wikilinks": wikilinks, "wikilink_collisions": collisions,
            "bundles": bundles,
            "sync_sources": find_sync_source_refs(
                root, "/" + os.path.relpath(old_abs, root).replace(os.sep, "/"))}


def find_sync_source_refs(root, source_value):
    """[(consumer_rel, block_count)] — every concept carrying at least one
    materialised canon block whose `source=` is exactly `source_value`.

    Without this a rename of a canonical concept breaks the whole ownership
    graph into `source-missing`: the markdown link rewriters never see a
    `source=` attribute, because it is not a link. prune_staging=False: a
    consumer in a staging dir (_inbox, _archive, ...) must also get its
    `source=` repointed, same reasoning as build_canon_block_index."""
    out = []
    for _, bp in resolve_scopes(root, None, include_archive=True):
        for ap in iter_all_md(bp, prune_staging=False):
            _, body = split_frontmatter(read_file(ap))
            if SYNC_OPEN_LIT not in body:
                continue
            n = sum(1 for r in parse_sync_blocks(body)
                    if r["source"] == source_value)
            if n:
                out.append((os.path.relpath(ap, root).replace(os.sep, "/"), n))
    return sorted(out)


def _apply_sync_source_rewrites(abspath, old_source, new_source):
    """Repoint every `source=old_source` sync marker in one file at
    `new_source`, splicing only that attribute's slice so the payload, the
    recorded hash and the attribution line stay byte-identical — the block was
    not re-materialised, only its owner moved.

    Re-scans at apply time rather than trusting a span computed during
    planning, the same idiom _apply_link_rewrites and _apply_wikilink_rewrites
    follow."""
    text = read_file_verbatim(abspath)
    if text is None:
        sys.stderr.write("note: skipping {} — not valid UTF-8\n".format(abspath))
        return 0
    out, last, n = [], 0, 0
    for m in SYNC_OPEN_RE.finditer(text):
        if m.group("source") != old_source:
            continue
        a, b = m.start("source"), m.end("source")
        out.append(text[last:a])
        out.append(new_source)
        last = b
        n += 1
    if not n:
        return 0
    out.append(text[last:])
    write_file_verbatim(abspath, "".join(out))
    return n


def _apply_link_rewrites(abspath, rewrites):
    """Rewrite one file's markdown link targets, splicing by offset over the
    same dead-zone mask build_ref_matrix used to find them.

    A whole-file `str.replace` edited bytes the planner never reported: a link
    inside a code fence was rewritten and not counted, so the run changed a
    documentation sample while claiming a smaller edit than it made."""
    text = read_file_verbatim(abspath)
    if text is None:
        sys.stderr.write("note: skipping {} — not valid UTF-8\n".format(abspath))
        return
    mapping = dict(rewrites)
    out, last = [], 0
    for m in CROSSLINK_RE.finditer(wikilink_scan_text(text)):
        a, b = m.start(2), m.end(2)
        new_raw = mapping.get(text[a:b])
        if new_raw is None:
            continue
        out.append(text[last:a])
        out.append(new_raw)
        last = b
    out.append(text[last:])
    write_file_verbatim(abspath, "".join(out))


def _apply_wikilink_rewrites(abspath, rename_map):
    """Rewrite one file's wikilinks. `rename_map` maps an old raw token to its
    replacement; every occurrence the scanner accepts and the map names is
    spliced in by offset.

    The file is re-scanned here rather than trusting offsets from planning
    time, so this is correct regardless of what else has already rewritten the
    file in this run. Splicing by offset — instead of replacing the token
    string — is what guarantees an identical-looking `[[old]]` inside a fence,
    an indented block or a comment is never touched: the scanner never returned
    it, so no offset points at it."""
    text = read_file_verbatim(abspath)
    if text is None:
        sys.stderr.write("note: skipping {} — not valid UTF-8\n".format(abspath))
        return
    out, last = [], 0
    for rec in wikilinks.parse_wikilinks(text):
        new_raw = rename_map.get(rec["raw"])
        if new_raw is None:
            continue
        a, b = rec["span"]
        out.append(text[last:a])
        out.append(new_raw)
        last = b
    out.append(text[last:])
    write_file_verbatim(abspath, "".join(out))


def _git_mv(root, old_abs, new_abs):
    """History-preserving, staged move.

    Tries `git mv` at `root` first. When that fails because the source lies
    beyond a symlinked bundle boundary — its real path leaves root's own
    tree, into the foreign project repo the bundle links to — it resolves
    that real repository and retries `git mv` there; that only succeeds when
    the destination ALSO resolves into that same repo, i.e. an ordinary
    rename that stays inside the bundle (AC1, okf-cli-mk7m). `archive`'s
    destination never does: `_archive/<bundle>/…` lives in the catalogue
    root, so the two repositories differ and a single `git mv` cannot span
    them. That case, and a plain untracked file where git declines for an
    unrelated reason (PO review 2026-08-10), both fall back to a plain fs
    rename.

    Returns (moved_via_git, repo, reason):
      moved_via_git — True once a `git mv` staged the move, at `root` or at
                      a resolved foreign repository.
      repo          — the real repository that received the write, whenever
                      it differs from `root` (AC2); None when it is the
                      same, or when none could be resolved.
      reason        — git's own stderr explaining why it declined, verbatim
                      (proc.stderr was captured and never read before this
                      fix); None when git succeeded or the git binary itself
                      is unavailable.
    """
    try:
        proc = subprocess.run(["git", "-C", root, "mv", "-f", old_abs, new_abs],
                              capture_output=True, text=True)
    except OSError:
        os.rename(old_abs, new_abs)
        return False, None, None
    if proc.returncode == 0:
        return True, None, None

    reason = proc.stderr.strip() or None
    real_root = os.path.realpath(root)
    real_old = os.path.realpath(old_abs)
    foreign_repo = None
    if not (real_old == real_root or real_old.startswith(real_root + os.sep)):
        top, why = catalogue._git_toplevel(os.path.dirname(real_old))
        if why is None and os.path.realpath(top) != real_root:
            foreign_repo = os.path.realpath(top)
            real_new_dir = os.path.realpath(os.path.dirname(new_abs))
            if (real_new_dir == foreign_repo
                    or real_new_dir.startswith(foreign_repo + os.sep)):
                real_new = os.path.join(real_new_dir, os.path.basename(new_abs))
                proc2 = subprocess.run(
                    ["git", "-C", foreign_repo, "mv", "-f", real_old, real_new],
                    capture_output=True, text=True)
                if proc2.returncode == 0:
                    return True, foreign_repo, None
                reason = proc2.stderr.strip() or reason

    os.rename(old_abs, new_abs)
    return False, foreign_repo, reason


def perform_rename(root, old_abs, new_abs, apply, force, verb="rename",
                   plan=None):
    """The validation, planning and application core shared by `rename` and
    (per okf-cli-16rg) `archive`/`archive --restore`. Callers pass already
    resolved absolute paths; `verb` only steers the prefix of error messages
    ("rename: " vs "archive: ") — every other line of output is unchanged.

    `plan` (okf-cli-h12o, D01): an already-computed plan_rename() result, so
    a caller that built one for its own reporting (cmd_archive's AC7 inbound
    count) does not pay for a second build_ref_matrix scan here. Absent, this
    recomputes exactly as before — cmd_rename's call site is unchanged,
    which is what keeps AC3 (rename byte-identical) cheap to satisfy."""

    def die(msg):
        sys.stderr.write("{}: {}\n".format(verb, msg))
        sys.exit(2)

    if not old_abs.endswith(".md") or not new_abs.endswith(".md"):
        die("both paths must be .md concept files")
    if not os.path.isfile(old_abs):
        die("source not found: {}".format(old_abs))
    if os.path.basename(old_abs).lower() in RESERVED:
        die("refusing to move a reserved file ({})".format(os.path.basename(old_abs)))
    if os.path.basename(new_abs).lower() in RESERVED:
        # A reserved name is not a concept, so nothing can resolve to it: every
        # inbound wikilink would be rewritten to an address that is dead on
        # arrival, and the report would still say it succeeded.
        die("refusing to rename onto a reserved name ({}) — no wikilink can "
            "resolve to it".format(os.path.basename(new_abs)))
    new_base_raw = os.path.basename(new_abs)[:-3]
    if not new_base_raw.strip():
        die("destination has an empty basename — `[[…]]` would become `[[]]`, "
            "which no scan can find again")
    if new_base_raw != new_base_raw.strip():
        # The scanner strips the page part, the index does not strip filenames,
        # so the two keys could never meet: the rewritten link would resolve to
        # nothing while the run reported success.
        die("destination basename has leading or trailing whitespace — the "
            "rewritten `[[{}]]` would resolve to nothing".format(new_base_raw))
    if any(ord(c) < 32 for c in new_base_raw):
        die("destination basename contains a control character — the rewritten "
            "link would be unmatchable by any later scan")
    if old_abs == new_abs:
        die("source and destination are identical")
    if os.path.commonpath([old_abs, root]) != root or os.path.commonpath([new_abs, root]) != root:
        die("both paths must live under the catalogue root")
    for p in (old_abs, new_abs):
        if os.path.relpath(p, root).count(os.sep) < 1:
            die("path must be inside a bundle (<bundle>/<concept>.md)")
    badchars = check.FILENAME_FORBIDDEN_CHARS & set(os.path.basename(new_abs)[:-3])
    if badchars:
        die("forbidden char(s) in new filename: {}".format("".join(sorted(badchars))))
    # samefile: on a case-insensitive filesystem a case-only rename has a
    # destination that "exists" because it IS the source. Refusing that would
    # make `Foo.md` -> `foo.md` impossible without --force overwriting itself.
    if (os.path.exists(new_abs) and apply and not force
            and not os.path.samefile(old_abs, new_abs)):
        die("destination exists (use --force to overwrite): {}".format(new_abs))

    # From here on the source is addressed exactly as the filesystem spells it,
    # so the two halves of the rename and the self-reference check all compare
    # the same string. The destination keeps the caller's spelling of its own
    # basename — that is the rename — but its directory part is canonicalised
    # for the same reason.
    old_abs = canonical_case_path(root, old_abs)
    new_abs = os.path.join(canonical_case_path(root, os.path.dirname(new_abs)),
                           os.path.basename(new_abs))

    if plan is None:
        plan = plan_rename(root, old_abs, new_abs)
    old_rel = os.path.relpath(old_abs, root).replace(os.sep, "/")
    new_rel = os.path.relpath(new_abs, root).replace(os.sep, "/")
    ctx_hits = ctx_memberships(root, old_rel)
    ctx_where = ["{} ({})".format(s, "reference" if e["pos"] is None
                                  else "pos {}".format(e["pos"])) for s, e in ctx_hits]

    wl_rewrite = [r for r in plan["wikilinks"] if r["status"] == "rewrite"]
    wl_skipped = [r for r in plan["wikilinks"] if r["status"] == "skipped-ambiguous"]
    collisions = plan["wikilink_collisions"]

    # Every occurrence the plan says loses its unique target, whether or not a
    # byte of it changes. Derived from resolving each one against the catalogue
    # before AND after the move, so the tie-break is honoured on both sides:
    # counting rewrites blindly refused renames that broke nothing, and looking
    # only at rewrites missed the ones that break without being rewritten.
    wl_ambiguous = [r for r in plan["wikilinks"] if r.get("turns_ambiguous")]

    def _print_skipped():
        for r in wl_skipped:
            print("  skipped-ambiguous  {} [{}]  {}  candidates: {}".format(
                r["source"], r["region"], r["raw"], ", ".join(r["candidates"])))
        for c in collisions:
            print("  wikilink-collision  new basename already taken by {}".format(c))
        for r in wl_ambiguous:
            print("  turns-ambiguous  {} [{}]  {}  candidates after the move: {}"
                  .format(r["source"], r["region"], r["raw"],
                          ", ".join(r["candidates"])))

    if apply and wl_ambiguous and not force:
        die("this move leaves {} inbound wikilink(s) ambiguous: {} — the same "
            "corruption `skipped-ambiguous` declines to commit, so it may not "
            "happen by accident either (use --force to proceed)"
            .format(len(wl_ambiguous),
                    ", ".join(sorted({r["source"] for r in wl_ambiguous}))))

    if not apply:
        print("would move   {}  ->  {}".format(old_rel, new_rel))
        for src, oraw, nraw in plan["inbound"]:
            print("  inbound    {}   {}  ->  {}".format(src, oraw, nraw))
        for oraw, nraw in plan["outbound"]:
            print("  outbound   {}  ->  {}".format(oraw, nraw))
        for r in wl_rewrite:
            print("  wikilink   {} [{}]   {}  ->  {}".format(
                r["source"], r["region"], r["raw"], r["new_raw"]))
        for consumer_rel, n in plan["sync_sources"]:
            print("  sync-source  {}   {} block(s)".format(consumer_rel, n))
        for w in ctx_where:
            print("  ctx        " + w)
        _print_skipped()
        print("  reindex    {}".format(", ".join(plan["bundles"])))
        print("rename (dry-run): {} inbound, {} outbound link(s), {} wikilink(s) "
              "({} skipped-ambiguous), {} bundle(s), {} sync source(s). "
              "Re-run with --apply.".format(
                  len(plan["inbound"]), len(plan["outbound"]), len(wl_rewrite),
                  len(wl_skipped), len(plan["bundles"]),
                  len(plan["sync_sources"])))
        return

    if os.path.exists(new_abs) and not os.path.samefile(old_abs, new_abs):
        # --force got us here. Say what it costs: the destination's content is
        # gone and every reference to it now addresses different content.
        clobbered = linkscan.build_ref_matrix(root, new_abs)
        print("overwrote      {}  ({} inbound markdown reference(s) now point at "
              "different content)".format(new_rel, len(clobbered)))
    os.makedirs(os.path.dirname(new_abs), exist_ok=True)
    moved, git_repo, git_reason = _git_mv(root, old_abs, new_abs)
    if plan["outbound"]:
        _apply_link_rewrites(new_abs, plan["outbound"])
    by_src = {}
    for src, oraw, nraw in plan["inbound"]:
        by_src.setdefault(src, []).append((oraw, nraw))
    for src, rw in by_src.items():
        _apply_link_rewrites(os.path.join(root, src), _dedupe(rw))
    wl_by_src = {}
    for r in wl_rewrite:
        # A self-reference lives in the file that just moved — rewrite it at its
        # new location, not at the path it no longer occupies.
        ap = new_abs if r["source"] == old_rel else os.path.join(root, r["source"])
        wl_by_src.setdefault(ap, {})[r["raw"]] = r["new_raw"]
    for ap, rename_map in wl_by_src.items():
        _apply_wikilink_rewrites(ap, rename_map)
    # The `source=` attribute of a materialised canon block is not a link, so
    # neither link rewriter touches it — without this the move silently breaks
    # every consumer of the moved concept's canon blocks into `source-missing`.
    old_source = "/" + old_rel
    new_source = "/" + new_rel
    n_sync = 0
    for consumer_rel, _ in plan["sync_sources"]:
        # A self-reference lives in the file that just moved — same rule as the
        # wikilink pass above.
        ap = new_abs if consumer_rel == old_rel else os.path.join(root, consumer_rel)
        n_sync += _apply_sync_source_rewrites(ap, old_source, new_source)
    ctx_notes = []
    for slug in dict.fromkeys(s for s, _ in ctx_hits):
        c = load_ctx(root, slug)
        if c["problems"]:
            ctx_notes.append("  ctx        {}: not refreshed, {} parse problem(s) — "
                             "run okf ctx check".format(slug, len(c["problems"])))
        else:
            save_ctx(root, c)
    reidx = []
    for b in plan["bundles"]:
        reidx += reindex_tree(root, os.path.join(root, b))
    print("moved ({})  {}  ->  {}".format("git mv" if moved else "fs", old_rel, new_rel))
    if moved:
        if git_repo:
            print("  tracked in {} (repository differs from --root)".format(git_repo))
    else:
        # AC3 (okf-cli-mk7m, widened by the PO review 2026-08-10): never say
        # this looks tracked, whichever of the two causes git declined for —
        # a symlinked-bundle boundary or a plain untracked file. Always name
        # git's own reason (point 4 of the gate: proc.stderr read, not
        # dropped) and, only when a different repository actually received
        # part of the write, name it (AC2).
        print("  untracked — git declined: {}".format(
            git_reason if git_reason else "git binary unavailable"))
        if git_repo:
            print("  the untracked change also touches {} (repository "
                  "differs from --root)".format(git_repo))
    print("rewrote {} inbound link(s) in {} file(s), {} outbound link(s)".format(
        len(plan["inbound"]), len(by_src), len(plan["outbound"])))
    print("rewrote {} wikilink(s) in {} file(s)".format(len(wl_rewrite), len(wl_by_src)))
    print("rewrote {} sync source(s) in {} file(s)".format(
        n_sync, len(plan["sync_sources"])))
    if ctx_where:
        print("listed in {} ctx bundle(s): {}".format(len(ctx_where), ", ".join(ctx_where)))
        for note in ctx_notes:
            print(note)
    _print_skipped()
    print("reindexed {} index file(s) across: {}".format(len(reidx), ", ".join(plan["bundles"])))
    print("staged for commit — run `okf-cli.py check` before committing.")


def cmd_rename(root, args):
    old_abs = os.path.abspath(args.old if os.path.isabs(args.old) else os.path.join(root, args.old))
    new_abs = os.path.abspath(args.new if os.path.isabs(args.new) else os.path.join(root, args.new))

    # D02 (okf-cli-tk33, PO decision on Q02): a rename whose source lies
    # under _archive/ reproduces, through this command, the invisible
    # empty-directory residue okf-cli-gqss closed for `archive --restore`.
    # Guarded HERE, not in perform_rename: that function is also
    # `archive --restore`'s own path back OUT of _archive/ (AC5) — a shared
    # guard would refuse the operation this message points users at
    # (SPEC.md §2 placement rule, same as the direction guards in
    # cmd_archive). Runs unconditionally, before the apply/dry-run branch,
    # so a preview never promises a move --apply would then decline (AC2).
    #
    # "Resolved source" (AC1): os.path.realpath, the same idiom
    # _prune_empty_archive_dirs (:4286-4288) and _git_mv (:4084-4087) already
    # use for a root/_archive boundary check. os.path.abspath alone already
    # collapses a `..`-traversal argument lexically, but only realpath also
    # follows a symlink whose target lands inside _archive/ even though
    # neither the argument nor old_abs ever spells "_archive/" — a prefix
    # match on the raw argument string would miss both.
    archive_root = os.path.realpath(os.path.join(root, "_archive"))
    resolved_old = os.path.realpath(old_abs)
    if resolved_old == archive_root or resolved_old.startswith(archive_root + os.sep):
        old_rel = os.path.relpath(old_abs, root).replace(os.sep, "/")
        sys.stderr.write(
            "rename: source lies under _archive/ — use archive --restore to "
            "bring it back: {}\n".format(old_rel))
        sys.exit(2)

    perform_rename(root, old_abs, new_abs, args.apply, args.force)


def _prune_empty_archive_dirs(root, freed_dir):
    """okf-cli-gqss (AC1/AC2): after a restore vacates `freed_dir` — the
    directory that held the concept before the move — remove every directory
    from there up to and including `_archive/` that the move has left empty.
    Stops at the first directory that still holds something (AC3, including a
    sibling concept's now-empty subdirectory of its own) and never touches
    anything outside `_archive/`.

    Git does not track empty directories, so a leftover here is invisible to
    `git status` — the defect this bean exists to close. This is why the walk
    is a plain `os.listdir`/`os.rmdir` filesystem operation, not a git one:
    there is nothing for git to be told, the directory was never tracked in
    the first place."""
    archive_root = os.path.realpath(os.path.join(root, "_archive"))
    d = os.path.realpath(freed_dir)
    while d == archive_root or d.startswith(archive_root + os.sep):
        try:
            if os.listdir(d):
                break
            os.rmdir(d)
        except OSError:
            break
        if d == archive_root:
            break
        d = os.path.dirname(d)


def cmd_archive(root, args):
    """R-01..R-03 (okf-cli-16rg): `archive <bundle>/<concept>[.md]` moves a
    concept to `_archive/<bundle>/<concept>.md`, preserving any subdirectory
    substructure of the concept id; `archive --restore
    _archive/<bundle>/<concept>[.md]` moves it back. The destination is
    derived, never typed (SPEC.md §1) — the three direction guards below are
    archive's own and run before perform_rename's shared guards, because they
    are not part of that shared core (SPEC.md §2)."""
    verb = "archive"

    def die(msg):
        sys.stderr.write("{}: {}\n".format(verb, msg))
        sys.exit(2)

    ref = args.path[:-3] if args.path.endswith(".md") else args.path
    p = ref + ".md"
    src_abs = os.path.abspath(p if os.path.isabs(p) else os.path.join(root, p))
    src_rel = os.path.relpath(src_abs, root).replace(os.sep, "/")
    segs = src_rel.split("/")

    if args.restore:
        if segs[0] != "_archive":
            die("--restore source must lie under _archive/, not: {}".format(src_rel))
        if len(segs) < 3:
            die("archive path carries no bundle segment — destination is not "
                "derivable from: {}".format(src_rel))
        dest_rel = "/".join(segs[1:])
    else:
        if segs[0] == "_archive":
            die("source already lies under _archive/ — use --restore to bring "
                "it back: {}".format(src_rel))
        dest_rel = "/".join(["_archive"] + segs)

    dest_abs = os.path.join(root, dest_rel)

    # okf-cli-5436 (AC1/AC2/AC4): a missing source whose derived counterpart
    # exists is not a bare miss — the tool already holds `dest_rel` at this
    # point, so a reader following a stale reference gets pointed at where
    # the concept actually is, instead of just being told it is gone. This
    # is archive-specific knowledge, not perform_rename's: it lives here,
    # same reasoning as the three direction guards above (SPEC.md §2).
    if not os.path.isfile(src_abs) and os.path.isfile(dest_abs):
        if args.restore:
            die("source not found: {} — the active copy already exists at "
                "{}".format(src_abs, dest_rel))
        die("source not found: {} — already archived at {} (use --restore "
            "to bring it back)".format(src_abs, dest_rel))

    # The inbound-reference count is a report line, not a guard: it must not
    # gate the move, only disclose what the move leaves behind (SPEC.md §1).
    # A nonexistent source with no archived counterpart is left to
    # perform_rename's own "source not found", so a plan is only built once
    # there is a file to plan a move for.
    plan = None
    if os.path.isfile(src_abs):
        plan = plan_rename(root, src_abs, dest_abs)
        n_concepts = len({src for src, _o, _n in plan["inbound"]})
        print("{} active concept(s) still link to this concept".format(n_concepts))

    perform_rename(root, src_abs, dest_abs, args.apply, args.force, verb=verb,
                   plan=plan)

    # okf-cli-gqss (AC1/AC2): only a restore can empty an _archive/ directory
    # — `archive` in the other direction only ever adds to one. perform_rename
    # already exited on failure above, so reaching here means the move
    # happened; freed_dir is the directory the concept just vacated.
    if args.restore and args.apply:
        _prune_empty_archive_dirs(root, os.path.dirname(src_abs))


def add_archive_parser(sub):
    pah = _sub(sub, "archive", "maintenance",
               "move a concept into _archive/<bundle>/, or back with --restore (dry-run default)")
    pah.add_argument("path", help="<bundle>/<concept>[.md]; with --restore: "
                                   "_archive/<bundle>/<concept>[.md]. The other end is derived, "
                                   "never typed").completer = _complete_concepts
    pah.add_argument("--restore", action="store_true",
                     help="move the path back out of _archive/ instead of into it")
    pah.add_argument("--apply", action="store_true", help="perform the move (default: dry-run preview only)")
    pah.add_argument("--force", action="store_true",
                     help="overwrite an existing destination, and proceed when the new "
                          "basename is already taken and inbound wikilinks would turn ambiguous")


def add_rename_parser(sub):
    prn = _sub(sub, "rename", "maintenance",
               "move a concept + rewrite every inbound/outbound link + reindex (dry-run default)")
    prn.add_argument("old", help="source concept path (<bundle>/<concept>.md, abs or --root-relative)").completer = _complete_concept_files
    prn.add_argument("new", help="destination path (same or different bundle)").completer = _complete_concept_files
    prn.add_argument("--apply", action="store_true", help="perform the move (default: dry-run preview only)")
    prn.add_argument("--force", action="store_true",
                     help="overwrite an existing destination, and proceed when the new "
                          "basename is already taken and inbound wikilinks would turn ambiguous")


def add_rewrite_path_parser(sub):
    prw = _sub(sub, "rewrite-path", "maintenance",
               "literal path-string rewrite across text files")
    prw.add_argument("old", help="literal path string to replace")
    prw.add_argument("new", help="replacement path string")
    prw.add_argument("--scan-root", help="dir to scan (default: --root)").completer = _complete_dirs
    prw.add_argument("--check", action="store_true", help="dry-run: report, write nothing")


COMMANDS = {
    "archive": (cmd_archive, add_archive_parser),
    "rename": (cmd_rename, add_rename_parser),
    "rewrite-path": (cmd_rewrite_path, add_rewrite_path_parser),
}
