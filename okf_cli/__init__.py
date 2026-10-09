"""Console-script entry of the pip, pipx and uv installs.

The CLI is cli/okf-cli.py: a hyphenated file, so it cannot be imported. The
wheel carries it inside this package with the same relative layout as the git
checkout (cli/, mcp/, skills/; see force-include in pyproject.toml), so no code
has to know which of the two it runs from.
"""
import os
import runpy


def main():
    # run_name="__main__" runs the file's own entry block, BrokenPipe handling
    # included. The returned globals are dropped on purpose: a console script
    # passes main()'s result to sys.exit().
    runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "cli", "okf-cli.py"),
                   run_name="__main__")
