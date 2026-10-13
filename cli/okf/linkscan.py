"""Link scanning: which spans of a markdown file count as links (the dead-zone
mask), which files a rename or reference scan visits, where a markdown link
points, outbound links and the reference matrix."""

import os
import re

from okf.catalogue import (
    SYNC_SPAN_RE, _prune_walk_dirs, fence_line_spans, list_bundles, read_file, read_frontmatter, sorted_walk,
)


def resolve_md_link(scan_root, src_abs, raw):
    """Absolute path a markdown link `raw` written in `src_abs` points at, or
    None for an empty target, a `<scheme>://` URL or mailto:. Leading / = scan_root
    (OKF catalogue-root convention, = Obsidian vault root), NOT the bundle."""
    tgt = raw.split("#", 1)[0].split("?", 1)[0].strip()
    if not tgt or re.match(r"^[a-z][a-z0-9+.-]*://", tgt) or tgt.startswith("mailto:"):
        return None
    if tgt.startswith("/"):
        return os.path.abspath(os.path.join(scan_root, tgt.lstrip("/")))
    return os.path.abspath(os.path.join(os.path.dirname(src_abs), tgt))


_MD_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def _file_md_links(scan_root, ap):
    """(raw, resolved_abs) per markdown link of one file, over the masked text."""
    text = read_file(ap)
    for m in _MD_LINK_RE.finditer(wikilink_scan_text(text)):
        raw = text[m.start(1):m.end(1)]
        resolved = resolve_md_link(scan_root, ap, raw)
        if resolved is not None:
            yield raw, resolved


def iter_md_links(scan_root):
    """Yield (source_rel, raw, resolved_abs) for every markdown link in every file
    of iter_rename_scan_md(scan_root). Same traversal and same dead-zone mask as
    the wikilink half of a rename, so the two halves of one move cannot disagree
    about which files and which occurrences they cover. A root-level walk alone
    cannot enter a symlinked bundle, which left a mounted file with its wikilink
    rewritten and its markdown link dangling in the same line."""
    for ap in iter_rename_scan_md(scan_root):
        rel = os.path.relpath(ap, scan_root).replace(os.sep, "/")
        for raw, resolved in _file_md_links(scan_root, ap):
            yield rel, raw, resolved


def outbound_links(root, src_abs):
    """[(raw, target_abs, exists)] for the markdown links of src_abs, file order."""
    return [(raw, resolved, os.path.exists(resolved))
            for raw, resolved in _file_md_links(root, os.path.abspath(src_abs))]


def build_ref_matrix(scan_root, target_abspath):
    """List every markdown link under scan_root that resolves to target_abspath.
    Returns [(source_rel, raw_link), ...]. Strips fenced code, ignores
    http(s)/mailto and anchors. Both relative and catalogue-root-absolute
    (leading /) links are resolved path-wise."""
    target_abspath = os.path.abspath(target_abspath)
    hits = []
    for rel, raw, resolved in iter_md_links(scan_root):
        if resolved != target_abspath:
            # A link may spell its target in a different case than the disk
            # does; on a case-insensitive filesystem that link is live and
            # must be rewritten too. samefile only runs on a case-equal
            # near-miss, so this stays correct on a case-sensitive one.
            if (resolved.lower() != target_abspath.lower()
                    or not os.path.exists(resolved)
                    or not os.path.samefile(resolved, target_abspath)):
                continue
        hits.append((rel, raw))
    return hits


def _refs_display(scan_root, p):
    """Scan-root-relative POSIX path when under it, else ~/… under $HOME, else absolute."""
    for base, prefix in ((scan_root, ""), (os.path.expanduser("~"), "~/")):
        rel = os.path.relpath(p, base)
        if rel != ".." and not rel.startswith(".." + os.sep) and not os.path.isabs(rel):
            return prefix + rel.replace(os.sep, "/")
    return p


# Spans Obsidian does not index as links. Fences are found line-based, not by
# regex: a regex pairs backtick runs left to right with no notion of line start
# or fence length, so one prose ``` mention or a 4-backtick fence shifts every
# later pairing by one and leaves a real code block exposed to the rewriter.
# (FENCE_LINE_RE, the line rule itself, lives in catalogue with iter_headings.)
COMMENT_RE = re.compile(r"%%[\s\S]*?%%|<!--[\s\S]*?-->")
INLINE_CODE_RE = re.compile(r"(`+)(?:(?!\1).)+?\1")
LIST_ITEM_RE = re.compile(r"^[ \t]*(?:[-*+]|\d+[.)])[ \t]")


def _split_lines_with_offsets(text):
    lines, offs, pos = [], [], 0
    for ln in text.splitlines(keepends=True):
        lines.append(ln)
        offs.append(pos)
        pos += len(ln)
    offs.append(pos)
    return lines, offs


def _fenced_code_spans(lines, offs):
    """fence_line_spans as character-offset spans over the same lines."""
    return [(offs[first], offs[end]) for first, end in fence_line_spans(lines)]


def _indented_code_spans(lines, offs):
    """4-space/tab indented code blocks.

    Indentation alone does not make one: the same shape is markdown's
    list-continuation form, which Obsidian renders as prose and does index. A
    run of indented lines opens a code block only when it follows a blank line
    whose own predecessor is neither a list item nor itself indented."""
    def indented(ln):
        return ln.startswith("    ") or ln.startswith("\t")

    spans, i, n = [], 0, len(lines)
    while i < n:
        if not lines[i].strip() or not indented(lines[i]):
            i += 1
            continue
        if i == 0 or lines[i - 1].strip():
            i += 1
            continue                                  # no blank line opens it
        prev = next((lines[j] for j in range(i - 2, -1, -1) if lines[j].strip()), None)
        if prev is not None and (LIST_ITEM_RE.match(prev) or indented(prev)):
            i += 1
            continue                                  # list continuation, not code
        start = i
        i += 1                                        # guaranteed progress
        while i < n and (not lines[i].strip() or indented(lines[i])):
            i += 1
        end = i
        while end > start and not lines[end - 1].strip():
            end -= 1
        spans.append((offs[start], offs[end]))
    return spans


def _blank(text, spans):
    """`text` with every span blanked to NUL, LENGTH PRESERVED, newlines kept.

    Length preservation is the point: offsets in the masked copy address the
    same bytes in the original, so a scan can report and rewrite against the
    real text without a stash/restore round trip. A stash lost content whenever
    one masked span held another's placeholder — `re.sub` does not rescan its
    replacement, so the inner token reached disk verbatim."""
    if not spans:
        return text
    out = list(text)
    for a, b in spans:
        for i in range(a, b):
            if out[i] != "\n":
                out[i] = "\x00"
    return "".join(out)


def _dead_zone_mask(text, yaml=False):
    """Blank every span Obsidian does not index, in stages.

    Each stage runs over the output of the previous one, so a construct inside
    an already-masked span cannot open a new one: no nesting, no pairing drift.

    `yaml=True` skips only the indented-code stage, because YAML indentation is
    structure — a block list under a blank line is not a code block. Inline code
    is masked in both regions: exempting it in frontmatter cost more than it
    bought, since a `---` thematic rule whose first line happens to read like
    `key: value` lands here and its prose backticks are then rewritable, while a
    genuine link property wrapped in backticks has zero occurrences catalogue-
    wide and would only be under-reported, never corrupted.

    The sync stage sits between the fence stage and the comment stage, and the
    order is load-bearing: COMMENT_RE would blank the `<!-- okf:sync … -->`
    markers first and leave the payload between them live, so a [[wikilink]] in
    a materialised canon block would still be reported — and, worse, rewritten
    by `rename`. Masked here, the owner's copy stays the only one reported and
    rewritten, which is where the link belongs."""
    lines, offs = _split_lines_with_offsets(text)
    masked = _blank(text, _fenced_code_spans(lines, offs))
    masked = _blank(masked,
                    [(m.start(), m.end()) for m in SYNC_SPAN_RE.finditer(masked)])
    masked = _blank(masked, [(m.start(), m.end()) for m in COMMENT_RE.finditer(masked)])
    masked = _blank(masked,
                    [(m.start(), m.end()) for m in INLINE_CODE_RE.finditer(masked)])
    if yaml:
        return masked
    lines, offs = _split_lines_with_offsets(masked)
    return _blank(masked, _indented_code_spans(lines, offs))


def wikilink_regions(text):
    """[(label, start, end)] — the frontmatter region, then the body.

    Only a head whose block parses as a YAML mapping is frontmatter; any other head, such as a `---`
    thematic rule opening the body, is body text and reported as such."""
    parsed = read_frontmatter(text)
    fm_end = len(parsed.head) if parsed.data is not None else 0
    return [("frontmatter", 0, fm_end), ("body", fm_end, len(text))]


def wikilink_scan_text(text, fm_end=None):
    """The masked copy a wikilink scan reads, aligned byte-for-byte with `text`. A caller that
    already holds the frontmatter end passes it, which saves a second parse."""
    if fm_end is None:
        fm_end = wikilink_regions(text)[0][2]
    return (_dead_zone_mask(text[:fm_end], yaml=True)
            + _dead_zone_mask(text[fm_end:]))


def iter_rename_scan_md(root):
    """Every .md the rename inbound scan must see.

    build_ref_matrix's own traversal (a root-level walk under
    _prune_walk_dirs: dot-dirs and node_modules out, `_`-prefixed staging dirs
    and root-level files IN — unlike iter_all_md) plus a second pass over each
    symlinked bundle, because os.walk does not descend into a symlinked
    subdirectory and five catalogue bundles are symlinks. Either half alone
    leaves a stale reference behind: the root walk misses the mounts, a
    per-bundle walk misses root-level staging.

    Deliberately wider than the reporting surfaces: staging directories, root-
    level files and `assets/` are all rewritten. A stale reference in a file
    `wikilinks` never lists is still a stale reference, and the markdown half of
    the same rename already reaches every one of them — pruning here would leave
    a file with its markdown link updated and its wikilink dangling in the same
    line."""
    seen = set()
    starts = [root] + [os.path.join(root, b) for b in list_bundles(root)
                       if os.path.islink(os.path.join(root, b))]
    for start in starts:
        for dirpath, dirnames, filenames in sorted_walk(start):
            _prune_walk_dirs(dirnames)
            for fn in filenames:
                if not fn.endswith(".md"):
                    continue
                ap = os.path.join(dirpath, fn)
                if ap not in seen:
                    seen.add(ap)
                    yield ap
