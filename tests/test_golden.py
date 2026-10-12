"""Black-box golden outputs of the okf CLI (tests/okf_golden.py). A difference names the case and
shows the diff golden -> actual; `just golden --update` rewrites the goldens after an intended change."""
import unittest

from tests import okf_golden


class GoldenOutput(unittest.TestCase):
    def test_every_case_matches_its_golden(self):
        cases = okf_golden.load_cases()
        records = okf_golden.run_all(cases, okf_golden.command())
        for case in cases:
            with self.subTest(case=case.name):
                delta = okf_golden.diff(case, records[case.name])
                self.assertIsNone(delta, delta)


if __name__ == "__main__":
    unittest.main()
