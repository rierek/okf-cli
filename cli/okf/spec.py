"""OKF v0.2 spec helpers shared by check, the derived output, the filter and verify."""

import datetime
import os
from collections.abc import Mapping

from okf.catalogue import _find_reserved_name, read_file, read_frontmatter


def declared_okf_version(bundle_root):
    """The `okf_version` string in the frontmatter of `<bundle_root>/index.md` (OKF §12), read
    through the one frontmatter reader. None when there is no index.md, no frontmatter, no such
    key or a value that is not a YAML string: an unquoted `0.2` loads as a float and declares
    nothing."""
    try:
        name = _find_reserved_name(os.listdir(bundle_root), "index.md")
        if name is None:
            return None
        data = read_frontmatter(read_file(os.path.join(bundle_root, name))).data
    except OSError:
        return None
    value = data.get("okf_version") if data is not None else None
    return str(value) if isinstance(value, str) else None


def parse_actor(value):
    """(kind, text) for a value that follows the actor convention (OKF §7), else None:
    ("producer", "<producer>/<version>"), ("human", "<id>") or ("process", "<id>"), every part
    non-empty. Anything that is not a string is None."""
    if not isinstance(value, str) or value != value.strip():
        return None
    kind, colon, ident = value.partition(":")
    if colon and kind in ("human", "process"):
        return (kind, str(ident)) if ident.strip() else None
    producer, slash, version = value.partition("/")
    return ("producer", str(value)) if slash and producer.strip() and version.strip() else None


def parse_okf_datetime(value):
    """The timezone-aware datetime of an ISO 8601 datetime with an explicit UTC offset, given as a
    string or as the datetime object the YAML loader resolves an unquoted one to. None for an
    offset-less datetime, a date-only value or anything else, so a missing offset is never read
    as UTC."""
    if isinstance(value, str):
        try:
            value = datetime.datetime.fromisoformat(value)
        except ValueError:
            return None
    if isinstance(value, datetime.datetime) and value.utcoffset() is not None:
        return value
    return None


def verified_entries(fm):
    """The `verified` entries of a frontmatter mapping as a list; a bare mapping counts as a
    one-element list (§5.2, §11). None when `verified` is absent or neither a mapping nor a list.
    The items of a list come back as written, so a caller checks them for mappings."""
    value = fm.get("verified") if fm is not None else None
    if isinstance(value, Mapping):
        return [value]
    return list(value) if isinstance(value, list) else None
