"""The OKF v0.2 rules of `check`. Every rule here is registered in check.RULES with the gate
`okf_version="0.2"`: the engine runs it only on non-reserved files of a bundle that declares
v0.2. Each rule reads the frontmatter mapping of the file context and returns messages."""

from collections.abc import Mapping

from okf.catalogue import fm_text, scalar_text
from okf.spec import parse_actor, parse_okf_datetime, verified_entries

STATUSES = ("draft", "stable", "deprecated")
COMPUTATION_TYPE = "Attested Computation"


def _filled(value):
    """A value that says something: not None, not blank text, not an empty list or mapping."""
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, Mapping)):
        return bool(value)
    return True


def _sources(ctx):
    """The `sources` value when it is a list, else [] (the shape rule reports the rest)."""
    sources = ctx["fm"].get("sources") if ctx["has_fm"] else None
    return sources if isinstance(sources, list) else []


def _window_ok(window):
    return isinstance(window, Mapping) and "from" in window and "to" in window


def check_sources_shape(ctx):
    """OKF §5.1: `sources` is a list of mappings."""
    if not ctx["has_fm"] or "sources" not in ctx["fm"]:
        return []
    sources = ctx["fm"]["sources"]
    if not isinstance(sources, list):
        return ["`sources` is not a list of mappings"]
    return ["`sources[{}]` is not a mapping".format(i)
            for i, entry in enumerate(sources) if not isinstance(entry, Mapping)]


def check_source_resource(ctx):
    """OKF §5.1: every `sources` entry has a non-empty `resource` (the field the spec marks REQUIRED)."""
    out = []
    for i, entry in enumerate(_sources(ctx)):
        if not isinstance(entry, Mapping):
            continue
        resource = entry.get("resource")
        if not (isinstance(resource, str) and resource.strip()):
            out.append("`sources[{}]` has no non-empty `resource`".format(i))
    return out


def check_usage_window(ctx):
    """OKF §5.1: a shared or per-entry `usage_window` is a mapping with `from` and `to`."""
    if not ctx["has_fm"]:
        return []
    out = []
    if "usage_window" in ctx["fm"] and not _window_ok(ctx["fm"]["usage_window"]):
        out.append("`usage_window` is not a mapping with `from` and `to`")
    for i, entry in enumerate(_sources(ctx)):
        if isinstance(entry, Mapping) and "usage_window" in entry and not _window_ok(entry["usage_window"]):
            out.append("`sources[{}].usage_window` is not a mapping with `from` and `to`".format(i))
    return out


def check_generated(ctx):
    """OKF §5.2: `generated` is a mapping with a non-empty `by`."""
    if not ctx["has_fm"] or "generated" not in ctx["fm"]:
        return []
    generated = ctx["fm"]["generated"]
    if not isinstance(generated, Mapping):
        return ["`generated` is not a mapping"]
    return [] if _filled(generated.get("by")) else ["`generated` has no non-empty `by`"]


def check_verified(ctx):
    """OKF §5.2: `verified` is a mapping or a list of mappings, each with a non-empty `by` and `at`."""
    if not ctx["has_fm"] or "verified" not in ctx["fm"]:
        return []
    entries = verified_entries(ctx["fm"])
    out = []
    if entries is None or not all(isinstance(entry, Mapping) for entry in entries):
        out.append("`verified` is neither a mapping nor a list of mappings")
    for i, entry in enumerate(entries or []):
        if isinstance(entry, Mapping):
            out += ["`verified[{}]` has no non-empty `{}`".format(i, key)
                    for key in ("by", "at") if not _filled(entry.get(key))]
    return out


def check_status(ctx):
    """OKF §5.4: `status` is draft, stable or deprecated; an absent `status` is stable."""
    if not ctx["has_fm"] or "status" not in ctx["fm"]:
        return []
    value = ctx["fm"]["status"]
    if isinstance(value, str) and value in STATUSES:
        return []
    return ["`status` is `{}`, not draft, stable or deprecated".format(scalar_text(value))]


def check_stale_after(ctx):
    """OKF §5.5: a `stale_after` that is an instant at or before the run's `now` has passed."""
    if not ctx["has_fm"]:
        return []
    at = parse_okf_datetime(ctx["fm"].get("stale_after"))
    if at is None or ctx["now"] < at:
        return []
    return ["`stale_after` {} has passed".format(scalar_text(ctx["fm"]["stale_after"]))]


def _actor_fields(fm):
    """[(label, value)] of `generated.by` and every `verified[].by` that says something; a blank
    one is a Trust finding already."""
    pairs = []
    generated = fm.get("generated")
    if isinstance(generated, Mapping):
        pairs.append(("generated.by", generated.get("by")))
    for i, entry in enumerate(verified_entries(fm) or []):
        if isinstance(entry, Mapping):
            pairs.append(("verified[{}].by".format(i), entry.get("by")))
    return [(label, value) for label, value in pairs if _filled(value)]


def _window_fields(label, window):
    return ([("{}.{}".format(label, key), window[key]) for key in ("from", "to") if key in window]
            if isinstance(window, Mapping) else [])


def _timestamp_fields(fm):
    """[(label, value)] of every timestamp-valued v0.2 key that is present. A blank `verified[].at`
    is left to the Trust rule, which reports the missing field once."""
    pairs = []
    generated = fm.get("generated")
    if isinstance(generated, Mapping) and "at" in generated:
        pairs.append(("generated.at", generated["at"]))
    for i, entry in enumerate(verified_entries(fm) or []):
        if isinstance(entry, Mapping) and _filled(entry.get("at")):
            pairs.append(("verified[{}].at".format(i), entry["at"]))
    if "stale_after" in fm:
        pairs.append(("stale_after", fm["stale_after"]))
    pairs += _window_fields("usage_window", fm.get("usage_window"))
    sources = fm.get("sources")
    for i, entry in enumerate(sources if isinstance(sources, list) else []):
        if isinstance(entry, Mapping):
            if "last_modified" in entry:
                pairs.append(("sources[{}].last_modified".format(i), entry["last_modified"]))
            pairs += _window_fields("sources[{}].usage_window".format(i), entry.get("usage_window"))
    return pairs


def check_actor(ctx):
    """OKF §7: `generated.by` and `verified[].by` follow the actor convention."""
    if not ctx["has_fm"]:
        return []
    return ["`{}` is `{}`, not `<producer>/<version>`, `human:<id>` or `process:<id>`".format(
                label, scalar_text(value))
            for label, value in _actor_fields(ctx["fm"]) if parse_actor(value) is None]


def check_timestamp(ctx):
    """OKF §7: every timestamp-valued key is an ISO 8601 datetime with an explicit UTC offset,
    whether the loader left it a string or resolved it to a datetime."""
    if not ctx["has_fm"]:
        return []
    return ["`{}` is `{}`, not an ISO 8601 datetime with an explicit UTC offset".format(
                label, scalar_text(value))
            for label, value in _timestamp_fields(ctx["fm"]) if parse_okf_datetime(value) is None]


def check_runtime(ctx):
    """OKF §10.2: an Attested Computation names its `runtime`; no other field of the type is required."""
    if not ctx["has_fm"] or fm_text(ctx["fm"], "type").strip() != COMPUTATION_TYPE:
        return []
    return [] if _filled(ctx["fm"].get("runtime")) else [
        "`{}` has no non-empty `runtime`".format(COMPUTATION_TYPE)]


def check_drift(ctx):
    """OKF §5.2 with D45: the body changed in a commit after `generated.at` that did not touch
    `generated.at` itself, so the provenance may no longer describe the body. Nothing is written."""
    if not ctx["has_fm"]:
        return []
    generated = ctx["fm"].get("generated")
    at = parse_okf_datetime(generated.get("at")) if isinstance(generated, Mapping) else None
    if at is None:
        return []  # no generated.at, or one the Format rule reports: nothing to compare
    commit = ctx["history"].last_body_commit(ctx["ap"], keep_generated=True)
    if commit is None or commit.time <= at:
        return []
    return ["body changed on {} without a new `generated.at` ({})".format(
        commit.time.isoformat(), scalar_text(generated["at"]))]
