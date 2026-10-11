#!/usr/bin/env python3
"""The `--json` envelope of the read and report commands (find, info, prime, read,
sync-export, tags, toc, ctx read, ctx toc): one five-key document per call, `data` carrying
what the text output prints, classified failures in `error`. Every call runs the real entry
file against a throwaway catalogue; no call reaches an embedding backend.

Run: python3 -m unittest tests.test_okf_envelope -v
"""
import contextlib
import io
import os
import re
import shutil
import sqlite3
import struct
import sys
import tempfile
import types
import unittest
from unittest import mock

_HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "cli")
if _HERE not in sys.path:  # cli/ holds the okf package
    sys.path.insert(0, _HERE)
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from okf import find as okf_find
from okf import semantic as okf_semantic
from okf import tags as okf_tags
from tests.okf_testkit import run_cli, run_json

ALPHA = ("---\ntype: Note\ntitle: Alpha Note\ndescription: the alpha note about pineapples\n"
         "tags:\n  - alpha\n---\n\n# Alpha\n\nPineapples grow on plants.\n\n## One\n\ntext one\n\n"
         "## Dup\n\nfirst\n\n## Dup\n\nsecond\n\n### Deep\n\ndeep text\n")
BETA = ("---\ntype: Note\ntitle: Beta Note\ndescription: the beta note\ntags:\n  - beta\n"
        "  - gamma\n---\n\n# Beta\n\nBananas.\n\n## Only\n\nx\n")
OLD = ("---\ntype: Note\ntitle: Old Note\ndescription: zebra relic\nsuperseded_by: kc-a/beta\n"
       "---\n\n# Old\n\nZebra.\n")
OWNERSHIP = ("---\ntype: Rule\ndescription: d\n---\n\n# Ownership\n\n"
             "<!-- okf:canon id=ownership-rule -->\nEvery statement has one owner.\n"
             "<!-- /okf:canon -->\n")
TAGS_MD = "| Tag | Meaning |\n|---|---|\n| `alpha` | first |\n| `beta` | second |\n"
TYPES_MD = "| Type | Meaning | Example |\n|---|---|---|\n| `Note` | x | |\n| `Rule` | x | |\n"


class Fixture(unittest.TestCase):
    """A throwaway catalogue: two bundles, a canon block, a registry, a ctx bundle."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        self._w(".okf.toml", "")
        self._w("TYPES.md", TYPES_MD)
        self._w("TAGS.md", TAGS_MD)
        self._w("kc-a/alpha.md", ALPHA)
        self._w("kc-a/beta.md", BETA)
        self._w("kc-a/old.md", OLD)
        self._w("kc-gov/ownership.md", OWNERSHIP)
        out, err, code = run_cli(self.root, "ctx", "create", "demo", "kc-a/alpha", "kc-a/beta")
        self.assertEqual(code, 0, err)

    def _w(self, rel, text):
        ap = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(ap), exist_ok=True)
        with open(ap, "w", encoding="utf-8") as f:
            f.write(text)

    def text(self, *argv):
        out, _err, code = run_cli(self.root, *argv)
        self.assertEqual(code, 0)
        return out


class EnvelopeShape(Fixture):
    CALLS = [
        ("find", ["find", "pineapples"]),
        ("info", ["info"]),
        ("prime", ["prime"]),
        ("prime", ["prime", "--compact"]),
        ("read", ["read", "kc-a/alpha"]),
        ("sync-export", ["sync-export", "kc-gov/ownership", "ownership-rule"]),
        ("tags", ["tags"]),
        ("tags", ["tags", "alph"]),
        ("toc", ["toc", "kc-a/alpha"]),
        ("ctx read", ["ctx", "read", "demo"]),
        ("ctx toc", ["ctx", "toc", "demo"]),
    ]

    def test_each_command_prints_one_envelope_naming_itself(self):
        for name, argv in self.CALLS:
            with self.subTest(argv=argv):
                env, _err, code = run_json(self.root, *argv)
                self.assertEqual((env["command"], env["ok"], env["error"], code),
                                 (name, True, None, 0))
                self.assertIsNotNone(env["data"])


class FindData(Fixture):
    LABELS = (("title", "title"), ("type", "type"), ("path", "path"),
              ("description", "description"), ("body-snippet", "snippet"),
              ("provenance", "provenance"))

    def test_hits_are_the_text_blocks_in_the_same_order(self):
        env, _err, _code = run_json(self.root, "find", "note")
        text = self.text("find", "note")
        hits = env["data"]["hits"]
        self.assertGreaterEqual(len(hits), 2)
        self.assertEqual(re.findall(r"^rank: (\d+)$", text, re.M),
                         [str(h["rank"]) for h in hits])
        self.assertEqual([h["rank"] for h in hits], list(range(1, len(hits) + 1)))
        for label, key in self.LABELS:
            self.assertEqual(re.findall(r"^{}: (.*)$".format(label), text, re.M),
                             [h[key] for h in hits], label)

    def test_superseded_by_is_present_only_on_a_superseded_hit(self):
        env, _err, _code = run_json(self.root, "find", "zebra")
        text = self.text("find", "zebra")
        (hit,) = env["data"]["hits"]
        self.assertEqual(hit.get("superseded_by"), "kc-a/beta")
        self.assertIn("superseded_by: kc-a/beta", text)
        plain = run_json(self.root, "find", "pineapples")[0]["data"]["hits"][0]
        self.assertNotIn("superseded_by", plain)

    def test_breakdown_carries_the_lexical_arm_values(self):
        env, _err, _code = run_json(self.root, "find", "pineapples", "--breakdown")
        text = self.text("find", "pineapples", "--breakdown")
        (hit,) = env["data"]["hits"]
        self.assertEqual(hit["breakdown"], {"score": 1, "max_score": 6,
                                            "contrib": {"title": [], "tags": [], "body": ["pineapples"]}})
        self.assertIn("score: 1/6", text)
        self.assertIn("contrib: body=[pineapples]", text)
        self.assertNotIn("breakdown", run_json(self.root, "find", "pineapples")[0]["data"]["hits"][0])

    def test_no_match_lists_the_nearest_registered_tags(self):
        env, _err, _code = run_json(self.root, "find", "alphq")
        text = self.text("find", "alphq")
        self.assertEqual(env["data"]["hits"], [])
        self.assertEqual(env["data"]["nearest_tags"], ["alpha"])
        self.assertIn("(no matches for: alphq)", text)
        self.assertIn("nearest registered tags: alpha", text)

    def test_empty_query_has_no_hits(self):
        env, _err, _code = run_json(self.root, "find", "!!")
        self.assertEqual(env["data"], {"hits": [], "nearest_tags": []})
        self.assertIn("(empty query)", self.text("find", "!!"))

    def test_degradation_notes_arrive_as_warnings_and_not_on_stderr(self):
        env, err, code = run_json(self.root, "find", "pineapples")
        self.assertEqual(len(env["data"]["hits"]), 1)
        self.assertEqual(err, "")
        self.assertEqual(code, 0)
        self.assertTrue(any("lexical index absent" in w for w in env["warnings"]), env["warnings"])
        self.assertTrue(any("semantic arm skipped" in w for w in env["warnings"]), env["warnings"])
        _out, text_err, _code = run_cli(self.root, "find", "pineapples")
        self.assertIn("note: lexical index absent", text_err)


class FindSemanticBreakdown(unittest.TestCase):
    """The semantic arm's own value under --breakdown. In-process, with the embedding call
    stubbed on the module as the other semantic tests do: no network."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self._orig_embed = okf_semantic._embed_query_voyage
        okf_semantic._QUERY_VEC_CACHE.clear()
        self.addCleanup(setattr, okf_semantic, "_embed_query_voyage", self._orig_embed)
        ap = os.path.join(self.tmp, "b", "near.md")
        os.makedirs(os.path.dirname(ap))
        with open(ap, "w", encoding="utf-8") as f:
            f.write("---\ntype: Concept\ntitle: Near\ntags: []\ndescription: d\n---\n# Near\n\nprose\n")
        db = os.path.join(self.tmp, ".tagvec", "tag_vectors.sqlite")
        os.makedirs(os.path.dirname(db))
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE concept_emb(key TEXT PRIMARY KEY, path TEXT, model TEXT, "
                     "dim INT, vec BLOB)")
        conn.execute("INSERT INTO concept_emb VALUES (?,?,?,?,?)",
                     ("k1", "b/near", "voyage-3-large", 2, struct.pack("<2f", 1.0, 0.0)))
        conn.commit()
        conn.close()
        okf_semantic._embed_query_voyage = lambda text: [1.0, 0.0]

    def _call(self, **kw):
        args = types.SimpleNamespace(query="zzz-no-keyword-match-zzz", limit=10, type=None,
                                     tag=None, scope=None, breakdown=True, **kw)
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            data = okf_find.cmd_find(self.tmp, args)
        return data, out.getvalue()

    def test_semantic_hit_carries_its_cosine(self):
        data, _text = self._call(json=True)
        (hit,) = data["hits"]
        self.assertEqual((hit["provenance"], hit["path"]), ("semantic", "b/near"))
        self.assertEqual(hit["breakdown"], {"cosine": 1.0})
        _data, text = self._call(json=False)
        self.assertIn("score: cosine 1.00", text)


class ReadData(Fixture):
    def test_data_text_is_the_selection_the_text_mode_prints(self):
        for flags in ([], ["--body-only"], ["--frontmatter-only"], ["--section", "One"],
                      ["--section", "Alpha > Deep"]):
            with self.subTest(flags=flags):
                env, _err, _code = run_json(self.root, "read", "kc-a/alpha", *flags)
                text = self.text("read", "kc-a/alpha", *flags)
                self.assertEqual(env["data"]["path"], "kc-a/alpha")
                self.assertEqual(env["data"]["text"].rstrip("\n"), text.rstrip("\n"))
        self.assertEqual(run_json(self.root, "read", "kc-a/alpha", "--section", "One")[0]["data"]["text"],
                         "## One\n\ntext one\n")

    def test_a_directory_resolves_to_its_index_and_reports_that_path(self):
        self._w("kc-a/index.md", "---\ntype: Index\n---\n\n# A\n")
        env, _err, _code = run_json(self.root, "read", "kc-a")
        self.assertEqual(env["data"]["path"], "kc-a/index")


class TocData(Fixture):
    def test_headings_match_the_text_lines(self):
        for level, argv in ((2, []), (0, ["--level", "0"]), (3, ["--level", "3"])):
            with self.subTest(level=level):
                env, _err, _code = run_json(self.root, "toc", "kc-a/alpha", *argv)
                lines = self.text("toc", "kc-a/alpha", *argv).splitlines()
                data = env["data"]
                self.assertEqual((data["path"], data["title"], data["type"]),
                                 ("kc-a/alpha", "Alpha Note", "Note"))
                self.assertEqual(lines[0], "# Alpha Note  [Note]")
                self.assertEqual([l.lstrip()[2:] for l in lines[1:]],
                                 [h["text"] for h in data["headings"]])
                if level:
                    self.assertEqual({h["level"] for h in data["headings"]}, {level})
        full = run_json(self.root, "toc", "kc-a/alpha", "--level", "0")[0]["data"]["headings"]
        self.assertEqual([(h["level"], h["text"]) for h in full],
                         [(1, "Alpha"), (2, "One"), (2, "Dup"), (2, "Dup"), (3, "Deep")])

    def test_no_headings_is_an_empty_list(self):
        env, _err, _code = run_json(self.root, "toc", "kc-a/alpha", "--level", "5")
        self.assertEqual(env["data"]["headings"], [])
        self.assertIn("(no h5 headings)", self.text("toc", "kc-a/alpha", "--level", "5"))


class InfoData(Fixture):
    def test_files_are_the_text_blocks_and_a_missing_file_is_null(self):
        env, _err, _code = run_json(self.root, "info")
        text = self.text("info")
        self.assertEqual(env["data"]["files"],
                         [{"name": "TYPES.md", "text": TYPES_MD}, {"name": "PROPERTIES.md", "text": None}])
        self.assertIn(TYPES_MD, text)
        self.assertIn("(missing: PROPERTIES.md)", text)


class PrimeData(Fixture):
    def test_every_unit_is_part_of_the_text_output(self):
        for argv in ([], ["--compact"], ["--full"]):
            with self.subTest(argv=argv):
                data = run_json(self.root, "prime", *argv)[0]["data"]
                text = self.text("prime", *argv)
                self.assertEqual(set(data), {"guide", "commands", "find", "state", "bundles"})
                for key in ("guide", "commands", "find", "state"):
                    self.assertTrue(data[key].strip(), key)
                    self.assertIn(data[key], text, key)
                self.assertEqual(len(data["bundles"]), 3)  # kc-a, kc-gov and the ctx bundle
                for bundle in data["bundles"]:
                    self.assertIn(bundle, text)
                    self.assertEqual("\n" in bundle, argv != ["--compact"])  # compact: one line each
        full = run_json(self.root, "prime", "--full")[0]["data"]["bundles"]
        default = run_json(self.root, "prime")[0]["data"]["bundles"]
        self.assertNotEqual(full, default)

    def test_the_command_directory_lists_the_new_flag(self):
        data = run_json(self.root, "prime")[0]["data"]
        self.assertIn("--json", data["find"])


class SyncExportData(Fixture):
    def test_payload_is_the_printed_payload(self):
        env, _err, _code = run_json(self.root, "sync-export", "kc-gov/ownership", "ownership-rule")
        text = self.text("sync-export", "kc-gov/ownership", "ownership-rule")
        self.assertEqual(env["data"], {"payload": "Every statement has one owner."})
        self.assertEqual(text, "Every statement has one owner.\n")


class TagsData(Fixture):
    def test_listing_is_the_text_rows(self):
        env, _err, _code = run_json(self.root, "tags")
        text = self.text("tags")
        rows = [(m.group(1), int(m.group(2))) for m in re.finditer(r"^  (\S+)\s+(\d+)$", text, re.M)]
        self.assertEqual([(r["tag"], r["count"]) for r in env["data"]["tags"]], rows)
        self.assertEqual(rows, [("alpha", 1), ("beta", 1), ("gamma", 1)])

    def test_singletons_filter_the_listing(self):
        self._w("kc-a/gamma2.md", BETA.replace("Beta Note", "Gamma Two"))
        env, _err, _code = run_json(self.root, "tags", "--singletons")
        self.assertEqual([r["tag"] for r in env["data"]["tags"]], ["alpha"])
        env, _err, _code = run_json(self.root, "tags")
        self.assertEqual(env["data"]["tags"][0], {"tag": "beta", "count": 2})

    def test_an_empty_listing_is_an_empty_list(self):
        for rel in ("kc-a/alpha.md", "kc-a/beta.md"):
            os.remove(os.path.join(self.root, rel))
        env, _err, _code = run_json(self.root, "tags")
        self.assertEqual(env["data"], {"tags": []})
        self.assertIn("(no tags found)", self.text("tags"))

    def test_fuzzy_matches_per_query(self):
        env, _err, _code = run_json(self.root, "tags", "alph", "zzzzzz")
        text = self.text("tags", "alph", "zzzzzz")
        self.assertEqual(env["data"]["searches"],
                         [{"query": "alph", "matches": [{"tag": "alpha", "count": 1}]},
                          {"query": "zzzzzz", "matches": []}])
        self.assertIn("== searched: alph ==\n  - alpha  (1)", text)
        self.assertIn("== searched: zzzzzz ==\n  (no match — new tag)", text)

    def test_validate_reports_the_unregistered_tags_as_non_conformant(self):
        env, err, code = run_json(self.root, "tags", "--validate", "alpha", "nope")
        self.assertEqual((env["ok"], env["data"], env["error"]["kind"], env["error"]["code"], code),
                         (False, {"closed_vocabulary": True, "unknown": ["nope"]},
                          "non_conformant", 4, 4))
        self.assertEqual(err, "")
        out, _err, text_code = run_cli(self.root, "tags", "--validate", "alpha", "nope")
        self.assertIn("UNKNOWN  nope", out)
        self.assertEqual(text_code, 4)
        env, _err, code = run_json(self.root, "tags", "--validate", "alpha", "beta")
        self.assertEqual((env["ok"], env["data"], code), (True, {"closed_vocabulary": True, "unknown": []}, 0))

    def test_validate_without_a_registry_is_open_vocabulary(self):
        os.remove(os.path.join(self.root, "TAGS.md"))
        env, _err, code = run_json(self.root, "tags", "--validate", "anything")
        self.assertEqual((env["data"], code), ({"closed_vocabulary": False, "unknown": []}, 0))

    def test_register_reports_added_and_already_registered(self):
        args = types.SimpleNamespace(json=True, register=[["fresh", "a new tag"], ["alpha", "dup"]],
                                     validate=None, query=[], singletons=False, limit=8)
        with mock.patch.object(okf_tags, "auto_embed_new_tags") as embed:
            data = okf_tags.cmd_tags(self.root, args)
        self.assertEqual(data, {"registered": ["fresh"], "already_registered": ["alpha"]})
        embed.assert_called_once_with(self.root, ["fresh"])
        with open(os.path.join(self.root, "TAGS.md"), encoding="utf-8") as f:
            self.assertIn("`fresh`", f.read())

    def test_register_in_envelope_mode_prints_nothing(self):
        args = types.SimpleNamespace(json=True, register=[["fresh", "a new tag"]],
                                     validate=None, query=[], singletons=False, limit=8)
        out = io.StringIO()
        with mock.patch.object(okf_tags, "auto_embed_new_tags"), contextlib.redirect_stdout(out):
            okf_tags.cmd_tags(self.root, args)
        self.assertEqual(out.getvalue(), "")


class CtxData(Fixture):
    def test_read_entries_are_the_printed_sections(self):
        env, _err, _code = run_json(self.root, "ctx", "read", "demo")
        text = self.text("ctx", "read", "demo")
        data = env["data"]
        self.assertEqual((data["slug"], data["references_not_printed"]), ("demo", 0))
        self.assertEqual([(e["position"], e["path"], e["alive"]) for e in data["entries"]],
                         [(1, "kc-a/alpha.md", True), (2, "kc-a/beta.md", True)])
        for e in data["entries"]:
            self.assertIn("===== {}/2 {} =====\n{}".format(e["position"], e["abspath"], e["text"]), text)
        self.assertEqual(data["entries"][0]["text"], ALPHA)

    def test_read_counts_reference_entries(self):
        out, err, code = run_cli(self.root, "ctx", "add", "demo", "kc-a/old", "--mode", "nachschlag")
        self.assertEqual(code, 0, err)
        env, _err, _code = run_json(self.root, "ctx", "read", "demo")
        self.assertEqual(env["data"]["references_not_printed"], 1)
        self.assertIn("1 reference entry not printed", self.text("ctx", "read", "demo"))

    def test_a_dead_entry_fails_non_conformant_with_the_readable_entries_in_data(self):
        os.remove(os.path.join(self.root, "kc-a/beta.md"))
        env, err, code = run_json(self.root, "ctx", "read", "demo")
        self.assertFalse(env["ok"])
        self.assertEqual((env["error"]["kind"], env["error"]["code"], code, err),
                         ("non_conformant", 4, 4, ""))
        self.assertIsNotNone(env["data"])
        first, second = env["data"]["entries"]
        self.assertEqual((first["alive"], first["text"]), (True, ALPHA))
        self.assertEqual((second["alive"], second["text"]), (False, None))
        out, text_err, text_code = run_cli(self.root, "ctx", "read", "demo")
        self.assertIn("[DEAD]", out)
        self.assertEqual((text_err, text_code), ("", 4))

    def test_toc_headings_match_the_text_and_follow_depth(self):
        env, _err, _code = run_json(self.root, "ctx", "toc", "demo", "--depth", "2")
        text = self.text("ctx", "toc", "demo", "--depth", "2")
        entries = env["data"]["entries"]
        self.assertEqual([e["path"] for e in entries], ["kc-a/alpha.md", "kc-a/beta.md"])
        self.assertEqual([(h["level"], h["text"]) for h in entries[0]["headings"]],
                         [(1, "Alpha"), (2, "One"), (2, "Dup"), (2, "Dup")])
        for e in entries:
            for h in e["headings"]:
                self.assertIn("{} {}".format("#" * (h["level"] + 1), h["text"]), text)
        deep = run_json(self.root, "ctx", "toc", "demo")[0]["data"]["entries"][0]["headings"]
        self.assertIn({"level": 3, "text": "Deep"}, deep)

    def test_toc_marks_a_dead_entry(self):
        os.remove(os.path.join(self.root, "kc-a/beta.md"))
        env, _err, code = run_json(self.root, "ctx", "toc", "demo")
        self.assertEqual(code, 0)
        self.assertEqual(env["data"]["entries"][1], {"path": "kc-a/beta.md", "alive": False, "headings": []})
        self.assertIn("# kc-a/beta.md [DEAD]", self.text("ctx", "toc", "demo"))


class ClassifiedFailures(Fixture):
    def _failure(self, *argv):
        env, err, code = run_json(self.root, *argv)
        self.assertFalse(env["ok"])
        self.assertEqual((env["error"]["code"], err), (code, ""))
        return env, code

    def test_a_missing_concept_is_not_found(self):
        for argv in (["read", "kc-a/nope"], ["toc", "kc-a/nope"]):
            with self.subTest(argv=argv):
                env, code = self._failure(*argv)
                self.assertEqual((env["error"]["kind"], code, env["data"]), ("not_found", 3, None))
                self.assertIn("kc-a/nope", env["error"]["message"])

    def test_an_ambiguous_section_is_invalid_input_with_the_candidates(self):
        env, code = self._failure("read", "kc-a/alpha", "--section", "Dup")
        self.assertEqual((env["error"]["kind"], code), ("invalid_input", 2))
        self.assertEqual(env["data"], {"candidates": [{"heading": "Alpha > Dup", "line": 17},
                                                      {"heading": "Alpha > Dup", "line": 21}]})
        out, err, text_code = run_cli(self.root, "read", "kc-a/alpha", "--section", "Dup")
        self.assertEqual((out, text_code), ("", 2))
        self.assertIn("ambiguous section: Dup matches 2 headings", err)
        self.assertIn("  line 17: Alpha > Dup", err)

    def test_a_path_resolves_an_ambiguous_section(self):
        env, _err, code = run_json(self.root, "read", "kc-a/alpha", "--section", "Alpha > One")
        self.assertEqual((env["ok"], code), (True, 0))

    def test_an_unknown_section_is_not_found(self):
        env, code = self._failure("read", "kc-a/alpha", "--section", "Nowhere")
        self.assertEqual((env["error"]["kind"], code, env["data"]), ("not_found", 3, None))

    def test_other_classified_failures_keep_their_class(self):
        for argv in (["ctx", "read", "nosuch"], ["ctx", "toc", "nosuch"],
                     ["sync-export", "kc-gov/ownership", "nope"]):
            with self.subTest(argv=argv):
                env, code = self._failure(*argv)
                self.assertEqual((env["error"]["kind"], code), ("not_found", 3))


if __name__ == "__main__":
    unittest.main()
