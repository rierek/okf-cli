"""`verify`: append one `verified` entry to a concept (OKF §5.2). The one command that writes
`verified`; nothing calls it for the caller. Written through the round-trip writer, so every other
key, comment, quoting style and the body stay as they were."""

import os

from ruamel.yaml.comments import CommentedMap, CommentedSeq

from okf import spec
from okf.catalogue import (
    RESERVED, YAML_RT, read_file, read_frontmatter, render_frontmatter, resolve_concept, write_file,
)
from okf.errors import OkfError
from okf.output import _add_output
from okf.parser_support import _complete_concepts, _sub


def _entry(by, at):
    """The `{by, at}` entry; `at` is loaded from its own text, so it is written as the plain
    timestamp the spec shows, not as a quoted string."""
    entry = CommentedMap()
    entry["by"] = by
    entry["at"] = YAML_RT.load("at: " + at)["at"]
    return entry


def cmd_verify(root, args):
    if spec.parse_actor(args.by) is None:
        raise OkfError("invalid_input", "--by {!r} is not `<producer>/<version>`, `human:<id>` or "
                       "`process:<id>`".format(args.by))
    ap = resolve_concept(root, args.concept)
    if os.path.basename(ap).lower() in RESERVED:
        raise OkfError("invalid_input", "{} is a reserved file; verify takes a concept".format(args.concept))
    fm = read_frontmatter(read_file(ap))
    if fm.head and fm.data is None:
        raise OkfError("invalid_input", "frontmatter does not parse: {}".format(fm.error))
    data = fm.data if fm.data is not None else CommentedMap()  # no block yet: the write gives the file one
    at = spec.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    entry = _entry(args.by, at)
    entries = spec.verified_entries(data)
    if "verified" in data and (entries is None or not all(isinstance(e, dict) for e in entries)):
        raise OkfError("invalid_input", "`verified` is neither a mapping nor a list of mappings; "
                       "fix it by hand before verifying")
    if entries is None:
        data["verified"] = CommentedSeq([entry])
    elif isinstance(data["verified"], list):
        data["verified"].append(entry)
    else:
        data["verified"] = CommentedSeq([data["verified"], entry])
    write_file(ap, render_frontmatter(fm._replace(data=data)))
    rel = os.path.relpath(ap, root).replace(os.sep, "/")
    path, written = rel[:-3] if rel.endswith(".md") else rel, {"by": args.by, "at": at}
    if getattr(args, "json", False):
        return {"path": path, "entry": written}
    print("verified {} by {} at {}".format(path, written["by"], written["at"]))


def add_verify_parser(sub):
    pv = _sub(sub, "verify", "maintenance", "record that a concept was checked against its sources")
    pv.add_argument("concept", help="<bundle>/<concept-id> of the concept").completer = _complete_concepts
    pv.add_argument("--by", required=True, metavar="ACTOR",
                    help="who verified it: `human:<id>`, `process:<id>` or `<producer>/<version>`")
    _add_output(pv)


COMMANDS = {"verify": (cmd_verify, add_verify_parser)}
