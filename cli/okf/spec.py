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


def utcnow():
    """The instant of a call, in UTC: the one clock of every comparison with `stale_after`."""
    return datetime.datetime.now(datetime.timezone.utc)


def verified_is_well_formed(fm):
    """Whether `verified` is a mapping or a list of mappings (§5.2); an absent key is not."""
    entries = verified_entries(fm)
    return entries is not None and all(isinstance(entry, Mapping) for entry in entries)


def filled(value):
    """A value that says something: not None, not blank text, not an empty list or mapping."""
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, Mapping)):
        return bool(value)
    return True


def trust_tier(fm):
    """The trust tier of a frontmatter mapping (OKF §5.3), from `verified` alone: `unverified`
    without an entry that names a `by`, `human-reviewed` when one such actor is `human:<id>`,
    else `machine-confirmed` (an actor outside the convention is no human)."""
    actors = [entry.get("by") for entry in verified_entries(fm) or []
              if isinstance(entry, Mapping) and filled(entry.get("by"))]
    if not actors:
        return "unverified"
    if any((parse_actor(by) or ("",))[0] == "human" for by in actors):
        return "human-reviewed"
    return "machine-confirmed"


def is_stale(fm, now):
    """Whether `stale_after` (OKF §5.5), the one source, parses and `now` has reached it. `now` is
    timezone-aware; absent or unparseable `stale_after` is not stale."""
    at = parse_okf_datetime(fm.get("stale_after")) if fm is not None else None
    return at is not None and now >= at


def trust_fields(fm, now):
    """The `tier` and `stale` keys every concept record of `--json` output carries."""
    return {"tier": trust_tier(fm), "stale": is_stale(fm, now)}
