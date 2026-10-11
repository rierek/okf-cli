"""The OKF v0.2 rules of `check`. Every rule here is registered in check.RULES with the gate
`okf_version="0.2"`: the engine runs it only on non-reserved files of a bundle that declares
v0.2. Each rule reads the frontmatter mapping of the file context and returns messages."""

from collections.abc import Mapping


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
