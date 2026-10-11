"""OKF v0.2 spec helpers shared by check, the derived output, the filter and verify."""

import os

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
