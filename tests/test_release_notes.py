import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("rn", Path(__file__).parent.parent / "scripts" / "release-notes.py")
rn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rn)

M = {"id": "M1", "title": "Milestone", "extra": {"summary": "Lead."}}
KIDS = [
    {"id": "F1", "type": "feature", "status": "completed", "title": "Feat", "extra": {"summary": "Does X."}},
    {"id": "B1", "type": "bug", "status": "to-review", "title": "Bug title"},
    {"id": "T1", "type": "task", "status": "completed", "title": "Task"},
    {"id": "D1", "type": "feature", "status": "draft", "title": "Draft"},
]
PAGE = f"---\ntitle: \"T\"\n---\n\nHand \u00e4 text\r\n\n{rn.START}\n\nold\n\n{rn.END}\n\nUpgrade notes.\n"


class T(unittest.TestCase):
    def test_render(self):
        b = rn.render_block(M, KIDS)
        self.assertIn("- [F1] Does X.", b)
        self.assertIn("## Fixes\n\n- [B1] Bug title", b)
        self.assertNotIn("T1", b)
        self.assertNotIn("D1", b)

    def test_splice_keeps_outside_and_is_idempotent(self):
        b = rn.render_block(M, KIDS)
        once = rn.splice(PAGE, b)
        self.assertEqual(once.split(rn.START)[0], PAGE.split(rn.START)[0])
        self.assertEqual(once.split(rn.END)[1], PAGE.split(rn.END)[1])
        self.assertIn("Does X.", once)
        self.assertNotIn("old", once)
        self.assertEqual(rn.splice(once, b), once)

    def test_missing_marker_fails(self):
        for bad in (PAGE.replace(rn.END, ""), PAGE.replace(rn.START, ""), PAGE + rn.START):
            with self.assertRaises(ValueError):
                rn.splice(bad, "x")


if __name__ == "__main__":
    unittest.main()
