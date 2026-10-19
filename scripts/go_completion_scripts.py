#!/usr/bin/env python3
"""Keep go/internal/complete/okf.{zsh,bash,fish} equal to their sources: cli/_okf for zsh,
argcomplete 3.7.2 shellcode(["okf"], shell=...) for bash and fish. `just go-completion-scripts`
rewrites the files, `--check` only compares and exits 1 on a difference."""
import pathlib
import sys
from importlib.metadata import version

from argcomplete.shell_integration import shellcode

PIN = "3.7.2"  # the argcomplete of the Python install (pyproject, packaging/homebrew/okf-cli.rb)
root = pathlib.Path(__file__).resolve().parent.parent
dest = root / "go" / "internal" / "complete"

if version("argcomplete") != PIN:
    sys.exit("argcomplete {} found, {} wanted".format(version("argcomplete"), PIN))
want = {
    "zsh": (root / "cli" / "_okf").read_bytes(),
    "bash": shellcode(["okf"], shell="bash").encode(),
    "fish": shellcode(["okf"], shell="fish").encode(),
}
stale = [sh for sh, data in want.items() if not (dest / ("okf." + sh)).is_file() or (dest / ("okf." + sh)).read_bytes() != data]
if "--check" in sys.argv:
    if stale:
        sys.exit("out of date: " + ", ".join("okf." + sh for sh in stale) + " (run `just go-completion-scripts`)")
else:
    for sh in stale:
        (dest / ("okf." + sh)).write_bytes(want[sh])
