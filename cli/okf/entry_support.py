"""Support for the __main__ guard of cli/okf-cli.py."""

import os
import sys


def _silence_broken_pipe_streams():
    devnull = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(devnull, sys.stdout.fileno())
        os.dup2(devnull, sys.stderr.fileno())
    finally:
        os.close(devnull)
