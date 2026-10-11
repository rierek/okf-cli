"""Test package bootstrap for source modules under cli/."""
import os
import sys


SOURCE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cli")
if SOURCE_DIR not in sys.path:
    sys.path.insert(0, SOURCE_DIR)
