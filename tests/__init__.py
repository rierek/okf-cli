"""Test package bootstrap for source modules under cli/."""
import os
import sys
import tempfile


SOURCE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cli")
if SOURCE_DIR not in sys.path:
    sys.path.insert(0, SOURCE_DIR)
# A real ~/.config/okf/config.toml never reaches a test: catalogue_root()
# falls back to its `root` when no marker sits above cwd.
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="okf-tests-xdg-")
