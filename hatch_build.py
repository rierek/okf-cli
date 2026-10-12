"""Build hook: the wheel's dependencies and Python floor come from the PEP 723 header of
cli/okf-cli.py, the one place that declares them, so the installed console script and
`uv run --script` start the same program with the same requirements."""
import re
import tomllib

from hatchling.metadata.plugin.interface import MetadataHookInterface

# The reference pattern of PEP 723 for a `# /// script` block.
SCRIPT_BLOCK = re.compile(r"(?m)^# /// script$\s(?P<content>(?:^#(?: .*)?$\s)+)^# ///$")


class Pep723MetadataHook(MetadataHookInterface):
    PLUGIN_NAME = "custom"

    def update(self, metadata):
        with open("cli/okf-cli.py", encoding="utf-8") as f:
            block = SCRIPT_BLOCK.search(f.read())
        if block is None:
            raise ValueError("cli/okf-cli.py carries no PEP 723 `# /// script` block")
        header = tomllib.loads("".join(line[2:] for line in block.group("content").splitlines(True)))
        metadata["dependencies"] = header["dependencies"]
        metadata["requires-python"] = header["requires-python"]
