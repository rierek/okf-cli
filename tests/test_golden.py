"""Black-box golden outputs of the okf CLI (tests/okf_golden.py). A difference names the case and
shows the diff golden -> actual; `just golden --update` rewrites the goldens after an intended change."""
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from tests import okf_golden


class GoldenOutput(unittest.TestCase):
    def test_every_case_matches_its_golden(self):
        cases = okf_golden.load_cases()
        records = okf_golden.run_all(cases, okf_golden.command())
        for case in cases:
            with self.subTest(case=case.name):
                delta = okf_golden.diff(case, records[case.name])
                self.assertIsNone(delta, delta)


def _listener(port=0):
    server = socket.socket()
    server.bind(("127.0.0.1", port))
    server.listen(8)
    server.setblocking(False)
    return server


def _accepted(server):
    try:
        server.accept()[0].close()
        return True
    except BlockingIOError:
        return False


class NetworkBlock(unittest.TestCase):
    def test_process_cannot_reach_a_loopback_listener(self):
        with _listener() as server:
            port = server.getsockname()[1]
            proc = subprocess.run(okf_golden.blocked([sys.executable, "-c", okf_golden._PROBE, str(port)]),
                                  capture_output=True, text=True, timeout=60)
            self.assertEqual((proc.returncode, proc.stdout.strip()), (0, "blocked"), proc.stderr)
            self.assertFalse(_accepted(server))

    def test_harness_stops_when_the_block_does_not_hold(self):
        okf_golden.check_block.cache_clear()
        try:
            with mock.patch.object(okf_golden, "blocked", lambda cmd: cmd):
                with self.assertRaisesRegex(SystemExit, "does not hold"):
                    okf_golden.check_block()
        finally:
            okf_golden.check_block.cache_clear()

    def test_record_ignores_a_service_on_the_ollama_port(self):
        case = next(c for c in okf_golden.load_cases() if c.name == "tags-register")
        with tempfile.TemporaryDirectory() as tmp:
            template = okf_golden.build_template(os.path.join(tmp, "template"))
            okf_golden.check_block()
            without = okf_golden.run_case(case, okf_golden.command(), template, os.path.join(tmp, "a"))
            try:
                server = _listener(11434)
            except OSError:
                self.skipTest("port 11434 is in use: the service there is the listener")
            with server:
                with_listener = okf_golden.run_case(case, okf_golden.command(), template, os.path.join(tmp, "b"))
                self.assertFalse(_accepted(server))
        self.assertEqual(without, with_listener)

    def test_embed_warning_detail_is_neutral_and_the_rest_stays_pinned(self):
        line = "warning: auto-embed skipped for new tag(s) ({}) \u2014 run cli/embeddings/build_tagvec.py --produce manually later\n"
        python = okf_golden._stderr(line.format("URLError: <urlopen error [Errno 1] Operation not permitted>"))
        go = okf_golden._stderr(line.format("Post \"http://localhost:11434/api/embed\": dial tcp: socket: operation not permitted"))
        self.assertEqual(python, go)
        self.assertIn("(<network error>)", python)
        self.assertNotEqual(okf_golden._stderr(line.replace("run", "ran").format("x")), python)


if __name__ == "__main__":
    unittest.main()
