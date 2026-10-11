#!/usr/bin/env python3
"""The `--json` envelope of the commands that print one: the read and report commands
(find, info, prime, read, sync-export, tags, toc, ctx read, ctx toc) and those that always had
a JSON form (check, ctx check/inbound/list/outbound/show, index, list, recent, refs,
sync-status, wikilinks). One five-key document per call, `data` carrying
what the text output prints, classified failures in `error`. Every call runs the real entry
file against a throwaway catalogue; no call reaches an embedding backend.

Run: just test tests.test_okf_envelope -v
"""
import contextlib
import io
import os
import re
import shutil
import sqlite3
import struct
import subprocess
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
from okf.parser import build_parser
from okf.parser_support import subcommand_parsers
from tests.okf_testkit import run_cli, run_json

ALPHA = ("---\ntype: Note\ntitle: Alpha Note\ndescription: the alpha note about pineapples\n"
         "tags:\n  - alpha\n---\n\n# Alpha\n\nPineapples grow on plants.\n\n## One\n\ntext one\n\n"
         "## Dup\n\nfirst\n\n## Dup\n\nsecond\n\n### Deep\n\ndeep text\n")
BETA = ("---\ntype: Note\ntitle: Beta Note\ndescription: the beta note\ntags:\n  - beta\n"
        "  - gamma\n---\n\n# Beta\n\nBananas.\n\n## Only\n\nx\n")
OLD = ("---\ntype: Note\ntitle: Old Note\ndescription: zebra relic\nsuperseded_by: /kc-a/beta.md\n"
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
        self.assertEqual(hit.get("superseded_by"), "/kc-a/beta.md")
        self.assertIn("superseded_by: /kc-a/beta.md", text)
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
        args = types.SimpleNamespace(query="zzz-no-keyword-match-zzz", limit=10, where=None,
                                     breakdown=True, **kw)
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
                self.assertEqual(env["data"]["text"], text)
        self.assertEqual(run_json(self.root, "read", "kc-a/alpha", "--section", "One")[0]["data"]["text"],
                         "## One\n\ntext one\n\n")

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


class ExistingJsonCommands(Fixture):
    """The twelve commands that had their own `--json` before the envelope: check, ctx check,
    ctx inbound, ctx list, ctx outbound, ctx show, index, list, recent, refs, sync-status,
    wikilinks. A git history is committed first, so `recent` has something to read."""

    def setUp(self):
        super().setUp()
        self._git("init", "-q")
        self._git("add", "-A")
        self._git("commit", "-qm", "fixture")

    def _git(self, *argv):
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
        subprocess.run(["git", "-c", "commit.gpgsign=false", "-C", self.root, *argv],
                       check=True, env=env, capture_output=True)

    def test_data_is_the_payload_the_command_printed_before(self):
        data = lambda *argv: run_json(self.root, *argv)[0]["data"]
        self.assertEqual(list(data("index")), ["bundles"])
        self.assertEqual(list(data("index", "kc-a")), ["bundle", "concepts"])
        self.assertEqual(data("index", "kc-a")["bundle"], "kc-a")
        self.assertEqual([r["path"] for r in data("list", "--where", "type = Note")],
                         ["kc-a/alpha", "kc-a/beta", "kc-a/old"])
        self.assertEqual(list(data("refs", "kc-a/alpha.md")), ["target", "inbound", "outbound"])
        self.assertEqual(list(data("wikilinks")), ["links", "by_bundle", "totals", "filtered"])
        self.assertEqual(list(data("ctx", "list")[0]), ["slug", "description", "entries", "required", "path"])
        self.assertEqual(list(data("ctx", "show", "demo")),
                         ["slug", "description", "path", "entries", "dead", "tokens_required"])
        self.assertEqual(list(data("ctx", "inbound", "demo")),
                         ["slug", "direction", "include_internal", "members"])
        self.assertEqual(list(data("recent")[0]),
                         ["created", "created_ts", "title", "type", "path", "description"])

    def test_a_note_arrives_as_a_warning_and_not_on_stderr(self):
        self._w("kc-a/late.md", BETA)  # never committed
        env, err, code = run_json(self.root, "recent")
        self.assertEqual((code, err), (0, ""))
        (warning,) = env["warnings"]
        self.assertIn("have no commit that added them", warning)
        _out, text_err, _code = run_cli(self.root, "recent")
        self.assertIn("note: 1 concept(s) have no commit that added them", text_err)

    def test_a_config_note_of_check_arrives_as_a_warning(self):
        self._w(".okf.toml", 'ignore_rules = "kc/*"\n')
        env, err, _code = run_json(self.root, "check")
        self.assertEqual(err, "")
        self.assertTrue(any("ignore_rules must be an array" in w for w in env["warnings"]), env["warnings"])

    def test_other_classified_failures_keep_their_class(self):
        for argv, kind, code in ((["list"], "invalid_input", 2),
                                 (["ctx", "show", "nosuch"], "not_found", 3),
                                 (["index", "nosuch"], "not_found", 3),
                                 (["refs", "nosuch.md"], "not_found", 3),
                                 (["check", "nosuch"], "not_found", 3)):
            with self.subTest(argv=argv):
                env, err, exit_code = run_json(self.root, *argv)
                self.assertEqual((env["ok"], env["data"], env["error"]["kind"], env["error"]["code"],
                                  exit_code, err), (False, None, kind, code, code, ""))


class CheckFindings(unittest.TestCase):
    """`check` and `ctx check`: findings live in data.findings with rule and severity; the
    envelope's warnings stay for notes about the call."""

    KEYS = ["rule", "severity", "path", "message"]

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        self._w(".okf.toml", "")
        self._w("b/index.md", "# B\n\nBundle entry with an intro paragraph.\n")
        self._w("b/g.md", "---\ntype: Concept\ntitel: X\n---\n# G\n")  # a warning-severity finding

    def _w(self, rel, text):
        ap = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(ap), exist_ok=True)
        with open(ap, "w", encoding="utf-8") as f:
            f.write(text)

    def test_an_error_finding_is_non_conformant_with_the_findings_in_data(self):
        self._w("b/nofm.md", "# no frontmatter\n")
        env, err, code = run_json(self.root, "check")
        self.assertEqual((env["ok"], env["error"]["kind"], env["error"]["code"], code, err),
                         (False, "non_conformant", 4, 4, ""))
        self.assertEqual(list(env["data"]), ["findings"])
        self.assertEqual(sorted((f["rule"], f["severity"], f["path"]) for f in env["data"]["findings"]),
                         [("kc/frontmatter/english-keys", "warning", "b/g.md"),
                          ("okf/frontmatter/parseable", "error", "b/nofm.md")])
        self.assertEqual([list(f) for f in env["data"]["findings"]], [self.KEYS] * 2)
        self.assertEqual(env["warnings"], [])

    def test_a_warning_only_tree_passes_and_still_lists_the_warning(self):
        env, err, code = run_json(self.root, "check")
        self.assertEqual((env["ok"], env["error"], code, err), (True, None, 0, ""))
        self.assertEqual([(f["rule"], f["severity"]) for f in env["data"]["findings"]],
                         [("kc/frontmatter/english-keys", "warning")])
        self.assertEqual(env["warnings"], [])

    def test_strict_counts_the_warning(self):
        env, _err, code = run_json(self.root, "check", "--strict")
        self.assertEqual((env["ok"], env["error"]["kind"], code), (False, "non_conformant", 4))
        self.assertEqual(env["data"]["findings"][0]["severity"], "warning")

    def test_ctx_check_reports_a_dead_entry_the_same_way(self):
        out, err, code = run_cli(self.root, "ctx", "create", "bad", "b/g.md")
        self.assertEqual(code, 0, err)
        os.remove(os.path.join(self.root, "b/g.md"))
        env, err, code = run_json(self.root, "ctx", "check")
        self.assertEqual((env["command"], env["ok"], env["error"]["kind"], code, err),
                         ("ctx check", False, "non_conformant", 4, ""))
        (finding,) = [f for f in env["data"]["findings"] if f["rule"] == "kc/ctx/dead-entry"]
        self.assertEqual((list(finding), finding["severity"], finding["path"]),
                         (self.KEYS, "error", "_ctx/bad.md"))


class SyncStatusDrift(Fixture):
    def test_an_outdated_block_is_drift_with_the_rows_in_data(self):
        out, err, code = run_cli(self.root, "sync-insert", "kc-a/beta", "kc-gov/ownership",
                                 "ownership-rule", "--apply")
        self.assertEqual(code, 0, err)
        env, _err, code = run_json(self.root, "sync-status")
        self.assertEqual((env["ok"], env["error"], code), (True, None, 0))
        self.assertEqual(env["data"]["totals"]["synced"], 1)
        self._w("kc-gov/ownership.md", OWNERSHIP.replace("Every statement has one owner.", "Neuer Kanon."))
        env, err, code = run_json(self.root, "sync-status")
        self.assertEqual((env["ok"], env["error"]["kind"], env["error"]["code"], code, err),
                         (False, "drift", 5, 5, ""))
        (block,) = env["data"]["blocks"]
        self.assertEqual((block["consumer"], block["id"], block["status"]),
                         ("kc-a/beta.md", "ownership-rule", "source-changed"))
        self.assertEqual(env["data"]["totals"]["source-changed"], 1)


class WriteFixture(Fixture):
    """The catalogue as a git repository, plus the content the write commands act on."""

    def setUp(self):
        super().setUp()
        self._w("kc-a/inline.md", "---\ntype: Note\ntitle: Inline\ndescription: d\ntags: [alpha, zeta]\n---\n\n# Inline\n\nSee [beta](beta.md) and <tag> here.\n")
        self._w("kc-a/index.md", "# A\n\nIntro paragraph.\n\n<!-- okf:index -->\n<!-- /okf:index -->\n")
        self._git("init", "-q")
        self._git("add", "-A")
        self._git("commit", "-qm", "fixture")

    def _git(self, *argv):
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
        subprocess.run(["git", "-c", "commit.gpgsign=false", "-C", self.root, *argv],
                       check=True, env=env, capture_output=True)

    def read(self, rel):
        with open(os.path.join(self.root, rel), encoding="utf-8") as f:
            return f.read()

    def exists(self, rel):
        return os.path.exists(os.path.join(self.root, rel))

    def ok(self, *argv, **kw):
        """The envelope of a call that must succeed with no stderr."""
        env, err, code = run_json(self.root, *argv, **kw)
        self.assertEqual((env["ok"], env["error"], code, err), (True, None, 0, ""), env)
        return env

    def fails(self, kind, code, *argv, **kw):
        env, err, exit_code = run_json(self.root, *argv, **kw)
        self.assertEqual((env["ok"], env["error"]["kind"], env["error"]["code"], exit_code, err),
                         (False, kind, code, code, ""), env)
        return env


class TagWrites(WriteFixture):
    def test_merge_preview_then_apply(self):
        preview = self.ok("merge-tags", "alpha", "--into", "omega")["data"]
        self.assertEqual(preview, {"applied": False, "files": ["kc-a/alpha.md", "kc-a/inline.md"],
                                   "unparseable": [], "from": ["alpha"], "into": "omega"})
        self.assertIn("alpha", self.read("kc-a/alpha.md"))
        text = self.text("merge-tags", "alpha", "--into", "omega")
        self.assertEqual(re.findall(r"^would rewrite\s+(\S+)$", text, re.M), preview["files"])
        applied = self.ok("merge-tags", "alpha", "--into", "omega", "--apply")["data"]
        self.assertEqual((applied["applied"], applied["files"]), (True, preview["files"]))
        self.assertIn("omega", self.read("kc-a/alpha.md"))
        self.assertIn("tags:\n  - omega\n", self.read("kc-a/alpha.md"))
        self.assertNotIn("  - alpha", self.read("kc-a/alpha.md"))

    def test_merge_reports_a_tags_field_it_cannot_rewrite(self):
        self._w("kc-a/odd.md", "---\ntype: Note\ntitle: Odd\ndescription: d\ntags: alpha, beta\n---\n\n# Odd\n")
        data = self.ok("merge-tags", "alpha", "--into", "omega")["data"]
        self.assertEqual((data["files"], data["unparseable"]), (["kc-a/alpha.md", "kc-a/inline.md"], ["kc-a/odd.md"]))
        self.assertIn("unparseable    kc-a/odd.md", self.text("merge-tags", "alpha", "--into", "omega"))

    def test_remove_preview_then_apply_names_the_emptied_files(self):
        preview = self.ok("remove-tags", "beta", "gamma")["data"]
        self.assertEqual(preview, {"applied": False, "files": ["kc-a/beta.md"], "emptied": ["kc-a/beta.md"],
                                   "unparseable": [], "removed": ["beta", "gamma"]})
        self.assertIn("tags:", self.read("kc-a/beta.md"))
        applied = self.ok("remove-tags", "beta", "gamma", "--apply")["data"]
        self.assertEqual((applied["applied"], applied["emptied"]), (True, ["kc-a/beta.md"]))
        self.assertNotIn("tags:", self.read("kc-a/beta.md"))
        partial = self.ok("remove-tags", "alpha")["data"]
        self.assertEqual((partial["files"], partial["emptied"]),
                         (["kc-a/alpha.md", "kc-a/inline.md"], ["kc-a/alpha.md"]))

    def test_normalize_rewrites_an_inline_list(self):
        preview = self.ok("normalize-tags")["data"]
        self.assertEqual(preview, {"applied": False, "files": ["kc-a/inline.md"]})
        self.assertIn("tags: [alpha, zeta]", self.read("kc-a/inline.md"))
        self.assertEqual(self.ok("normalize-tags", "--apply")["data"], {"applied": True, "files": ["kc-a/inline.md"]})
        self.assertIn("tags:\n  - alpha\n  - zeta", self.read("kc-a/inline.md"))

    def test_where_limits_the_rewrite(self):
        self.assertEqual(self.ok("merge-tags", "alpha", "--into", "omega", "--where", "path ~ kc-gov/")["data"]["files"], [])


class IndexBuilds(WriteFixture):
    def test_build_index_reports_what_it_built_and_skips_a_current_index(self):
        data = self.ok("build-index")["data"]
        self.assertEqual((data["applied"], data["concepts"]), (True, 6))
        self.assertTrue(self.exists(".fts/fts.sqlite"))
        self.assertTrue(data["path"].endswith(os.path.join(".fts", "fts.sqlite")))
        again = self.ok("build-index", "--if-stale")["data"]
        self.assertEqual((again["applied"], again["concepts"]), (False, None))
        self.assertIn("index is current, skipping rebuild", self.text("build-index", "--if-stale"))

    def test_build_semantic_index_without_a_key_degrades_with_a_warning(self):
        env = self.ok("build-semantic-index")
        self.assertEqual((env["data"]["applied"], env["data"]["embedded"]), (False, 0))
        self.assertEqual(len(env["warnings"]), 1)
        self.assertIn("VOYAGE_API_KEY not set", env["warnings"][0])
        self.assertFalse(self.exists(".tagvec"))
        _out, text_err, code = run_cli(self.root, "build-semantic-index")
        self.assertEqual(code, 0)
        self.assertIn("note: semantic index build skipped (VOYAGE_API_KEY not set)", text_err)

    def test_reindex_check_names_the_stale_bundle_as_drift(self):
        self._w("kc-a/index.md", self.read("kc-a/index.md").replace("<!-- /okf:index -->", "stale line\n<!-- /okf:index -->"))
        env = self.fails("drift", 5, "reindex", "kc-a", "--check")
        self.assertEqual((env["data"]["applied"], env["data"]["stale"]), (False, ["kc-a/index.md"]))
        out, _err, code = run_cli(self.root, "reindex", "kc-a", "--check")
        self.assertIn("STALE        kc-a/index.md", out)
        self.assertEqual(code, 5)
        self.assertIn("stale line", self.read("kc-a/index.md"))

    def test_reindex_apply_rewrites_the_listing(self):
        data = self.ok("reindex", "kc-a")["data"]
        self.assertEqual((data["applied"], data["updated"], data["stale"]), (True, ["kc-a/index.md"], []))
        self.assertIn("alpha", self.read("kc-a/index.md"))
        self.assertEqual(self.ok("reindex", "kc-a", "--check")["data"]["stale"], [])

    def test_reindex_init_lists_conversions_and_skips(self):
        self._w("kc-gov/index.md", "# Gov\n\nCovers the rules.\n\n## Concepts\n\n* [Ownership](ownership.md) - rule\n")
        preview = self.ok("reindex", "kc-gov", "--init", "--check")["data"]
        self.assertEqual((preview["applied"], preview["init"]["converted"]), (False, ["kc-gov/index.md"]))
        self.assertNotIn("okf:index", self.read("kc-gov/index.md"))
        applied = self.ok("reindex", "kc-gov", "--init")["data"]
        self.assertEqual((applied["applied"], applied["init"]["converted"]), (True, ["kc-gov/index.md"]))
        self.assertIn("okf:index", self.read("kc-gov/index.md"))

    def test_reindex_of_a_missing_bundle_is_not_found(self):
        self.assertEqual(self.fails("not_found", 3, "reindex", "nosuch")["data"], None)


class LinkFixes(WriteFixture):
    def test_fix_crosslinks_preview_then_apply(self):
        preview = self.ok("fix-crosslinks", "--check")["data"]
        self.assertEqual(preview, {"applied": False, "files": [{"path": "kc-a/inline.md", "links": 1}],
                                   "unresolved": []})
        self.assertIn("](beta.md)", self.read("kc-a/inline.md"))
        text = self.text("fix-crosslinks", "--check")
        self.assertIn("would rewrite  kc-a/inline.md  (1 link(s))", text)
        applied = self.ok("fix-crosslinks")["data"]
        self.assertEqual((applied["applied"], applied["files"]), (True, preview["files"]))
        self.assertIn("](/kc-a/beta.md)", self.read("kc-a/inline.md"))

    def test_fix_crosslinks_lists_an_unresolved_link(self):
        self._w("kc-a/dead.md", "---\ntype: Note\ntitle: Dead\ndescription: d\n---\n\n# Dead\n\n[gone](/kc-a/gone.md)\n")
        data = self.ok("fix-crosslinks", "--check")["data"]
        self.assertEqual(data["unresolved"], [{"path": "kc-a/dead.md", "target": "/kc-a/gone.md"}])

    def test_fix_xml_tags_preview_then_apply(self):
        preview = self.ok("fix-xml-tags", "--check")["data"]
        self.assertEqual(preview, {"applied": False, "files": [{"path": "kc-a/inline.md", "chains": 1}]})
        self.assertIn(" <tag> ", self.read("kc-a/inline.md"))
        self.assertEqual(self.ok("fix-xml-tags")["data"]["applied"], True)
        self.assertIn("`<tag>`", self.read("kc-a/inline.md"))

    def test_fix_commands_refuse_a_missing_target(self):
        for command in ("fix-crosslinks", "fix-xml-tags"):
            with self.subTest(command=command):
                self.fails("not_found", 3, command, "nosuch")

    def test_rewrite_path_preview_then_apply(self):
        self._w("kc-a/refs.md", "---\ntype: Note\ntitle: R\ndescription: d\n---\n\n# R\n\nsee old/place.md twice: old/place.md\n")
        preview = self.ok("rewrite-path", "old/place.md", "new/place.md", "--check")["data"]
        self.assertEqual(preview, {"applied": False, "files": [{"path": "kc-a/refs.md", "count": 2}]})
        self.assertIn("old/place.md", self.read("kc-a/refs.md"))
        self.assertEqual(self.ok("rewrite-path", "old/place.md", "new/place.md")["data"]["applied"], True)
        self.assertNotIn("old/place.md", self.read("kc-a/refs.md"))


class MovesAndArchive(WriteFixture):
    def test_rename_preview_carries_the_plan_and_apply_the_outcome(self):
        self._w("kc-a/pointer.md", "---\ntype: Note\ntitle: P\ndescription: d\n---\n\n# P\n\n[o](/kc-a/old.md)\n")
        preview = self.ok("rename", "kc-a/old.md", "kc-a/older.md")["data"]
        self.assertEqual((preview["applied"], preview["old"], preview["new"]), (False, "kc-a/old.md", "kc-a/older.md"))
        self.assertEqual(preview["inbound"], [{"source": "kc-a/pointer.md", "old": "/kc-a/old.md", "new": "/kc-a/older.md"}])
        self.assertEqual(preview["reindex_bundles"], ["kc-a"])
        self.assertTrue(self.exists("kc-a/old.md"))
        text = self.text("rename", "kc-a/old.md", "kc-a/older.md")
        self.assertIn("would move   kc-a/old.md  ->  kc-a/older.md", text)
        self.assertIn("  inbound    kc-a/pointer.md   /kc-a/old.md  ->  /kc-a/older.md", text)
        applied = self.ok("rename", "kc-a/old.md", "kc-a/older.md", "--apply")["data"]
        self.assertEqual((applied["applied"], applied["moved_with"]), (True, "git mv"))
        self.assertEqual(applied["rewritten"]["inbound_links"], 1)
        self.assertFalse(self.exists("kc-a/old.md"))
        self.assertIn("/kc-a/older.md", self.read("kc-a/pointer.md"))

    def test_rename_plan_lists_wikilinks_sync_sources_and_ctx_memberships(self):
        self.ok("sync-insert", "kc-a/beta", "kc-gov/ownership", "ownership-rule", "--apply")
        self._w("kc-a/pointer.md", "---\ntype: Note\ntitle: P\ndescription: d\n---\n\n# P\n\nsee [[ownership]]\n")
        self.ok("ctx", "add", "demo", "kc-gov/ownership")
        argv = ("rename", "kc-gov/ownership.md", "kc-gov/rule.md")
        preview = self.ok(*argv)["data"]
        self.assertEqual(preview["wikilinks"], [{"source": "kc-a/pointer.md", "region": "body",
                                                 "raw": "[[ownership]]", "new_raw": "[[rule]]"}])
        self.assertEqual(preview["sync_sources"], [{"consumer": "kc-a/beta.md", "blocks": 1}])
        self.assertEqual(preview["ctx"], ["demo (pos 3)"])
        self.assertEqual([r["source"] for r in preview["inbound"]], ["_ctx/demo.md"])
        text = self.text(*argv)
        self.assertIn("  wikilink   kc-a/pointer.md [body]   [[ownership]]  ->  [[rule]]", text)
        self.assertIn("  sync-source  kc-a/beta.md   1 block(s)", text)
        self.assertIn("  ctx        demo (pos 3)", text)
        applied = self.ok(*argv, "--apply")["data"]
        self.assertEqual(applied["rewritten"], {"inbound_links": 1, "inbound_files": 1, "outbound_links": 0,
                                                "wikilinks": 1, "wikilink_files": 1, "sync_sources": 1,
                                                "sync_files": 1})
        self.assertIn("[[rule]]", self.read("kc-a/pointer.md"))
        self.assertIn("source=/kc-gov/rule.md ", self.read("kc-a/beta.md"))

    def test_rename_across_bundles_plans_the_outbound_links(self):
        argv = ("rename", "kc-a/inline.md", "kc-gov/inline.md")
        preview = self.ok(*argv)["data"]
        self.assertEqual(preview["outbound"], [{"old": "beta.md", "new": "/kc-a/beta.md"}])
        self.assertEqual(preview["reindex_bundles"], ["kc-a", "kc-gov"])
        self.assertIn("  outbound   beta.md  ->  /kc-a/beta.md", self.text(*argv))
        self.assertEqual(self.ok(*argv, "--apply")["data"]["rewritten"]["outbound_links"], 1)
        self.assertIn("](/kc-a/beta.md)", self.read("kc-gov/inline.md"))

    def test_rename_force_reports_the_overwritten_destination(self):
        data = self.ok("rename", "kc-a/alpha.md", "kc-a/beta.md", "--apply", "--force")["data"]
        self.assertEqual((data["applied"], data["overwrote_inbound"]), (True, 2))
        self.assertNotIn("overwrote_inbound", self.ok("rename", "kc-a/old.md", "kc-a/older.md")["data"])

    def test_rename_refusals_are_invalid_input(self):
        for argv in (["rename", "kc-a/alpha.md", "kc-a/alpha.txt"],
                     ["rename", "kc-a/alpha.md", "kc-a/alpha.md"],
                     ["rename", "kc-a/alpha.md", "kc-a/beta.md", "--apply"]):
            with self.subTest(argv=argv):
                env = self.fails("invalid_input", 2, *argv)
                self.assertEqual(env["data"], None)
                self.assertTrue(env["error"]["message"].startswith("rename: "))
        self.assertTrue(self.exists("kc-a/alpha.md"))

    def test_rename_of_a_missing_source_is_not_found(self):
        self.fails("not_found", 3, "rename", "kc-a/nosuch.md", "kc-a/other.md")

    def test_a_source_under_archive_is_pointed_at_restore(self):
        self.assertEqual(self.ok("archive", "kc-a/old", "--apply")["data"]["applied"], True)
        env = self.fails("invalid_input", 2, "rename", "_archive/kc-a/old.md", "kc-a/back.md")
        self.assertIn("use archive --restore", env["error"]["message"])

    def test_archive_preview_apply_and_restore(self):
        preview = self.ok("archive", "kc-a/old")["data"]
        self.assertEqual((preview["applied"], preview["old"], preview["new"], preview["restore"],
                          preview["active_inbound_concepts"]),
                         (False, "kc-a/old.md", "_archive/kc-a/old.md", False, 0))
        self.assertTrue(self.exists("kc-a/old.md"))
        self.assertIn("0 active concept(s) still link to this concept", self.text("archive", "kc-a/old"))
        applied = self.ok("archive", "kc-a/old", "--apply")["data"]
        self.assertEqual((applied["applied"], self.exists("kc-a/old.md"), self.exists("_archive/kc-a/old.md")),
                         (True, False, True))
        restored = self.ok("archive", "_archive/kc-a/old", "--restore", "--apply")["data"]
        self.assertEqual((restored["restore"], restored["new"], self.exists("kc-a/old.md")),
                         (True, "kc-a/old.md", True))

    def test_archive_counts_the_concepts_that_still_link(self):
        self._w("kc-a/pointer.md", "---\ntype: Note\ntitle: P\ndescription: d\n---\n\n# P\n\n[o](/kc-a/old.md)\n")
        self.assertEqual(self.ok("archive", "kc-a/old")["data"]["active_inbound_concepts"], 1)

    def test_archive_refusals(self):
        env = self.fails("invalid_input", 2, "archive", "kc-a/alpha", "--restore")
        self.assertIn("--restore source must lie under _archive/", env["error"]["message"])
        self.fails("not_found", 3, "archive", "kc-a/nosuch")


class SyncWrites(WriteFixture):
    def test_insert_preview_then_apply(self):
        argv = ("sync-insert", "kc-a/beta", "kc-gov/ownership", "ownership-rule")
        preview = self.ok(*argv)["data"]
        self.assertEqual(preview, {"applied": False, "consumer": "kc-a/beta.md",
                                   "source": "/kc-gov/ownership.md", "id": "ownership-rule"})
        self.assertNotIn("okf:canon", self.read("kc-a/beta.md"))
        self.assertIn("would insert    kc-a/beta.md   /kc-gov/ownership.md#ownership-rule", self.text(*argv))
        self.assertEqual(self.ok(*argv, "--apply")["data"]["applied"], True)
        self.assertIn("Every statement has one owner.", self.read("kc-a/beta.md"))

    def test_insert_refusals_are_invalid_input(self):
        self.ok("sync-insert", "kc-a/beta", "kc-gov/ownership", "ownership-rule", "--apply")
        self.fails("invalid_input", 2, "sync-insert", "kc-a/beta", "kc-gov/ownership", "ownership-rule")
        self.fails("invalid_input", 2, "sync-insert", "kc-gov/ownership", "kc-gov/ownership", "ownership-rule")

    def _outdate(self):
        self.ok("sync-insert", "kc-a/beta", "kc-gov/ownership", "ownership-rule", "--apply")
        self._w("kc-gov/ownership.md", OWNERSHIP.replace("Every statement has one owner.", "Neuer Kanon."))

    def test_update_preview_then_apply(self):
        self._outdate()
        preview = self.ok("sync-update")["data"]
        row = {"consumer": "kc-a/beta.md", "source": "/kc-gov/ownership.md", "id": "ownership-rule"}
        self.assertEqual(preview, {"applied": False, "updated": [row], "refused": [], "unresolvable": []})
        self.assertIn("Every statement", self.read("kc-a/beta.md"))
        self.assertIn("would update   kc-a/beta.md", self.text("sync-update"))
        self.assertEqual(self.ok("sync-update", "--apply")["data"]["updated"], [row])
        self.assertIn("Neuer Kanon.", self.read("kc-a/beta.md"))

    def test_update_refuses_a_modified_consumer_as_drift_with_the_per_block_outcome(self):
        self._outdate()
        self._w("kc-a/beta.md", self.read("kc-a/beta.md").replace("Every statement has one owner.", "Local edit."))
        env = self.fails("drift", 5, "sync-update", "--apply")
        row = {"consumer": "kc-a/beta.md", "source": "/kc-gov/ownership.md", "id": "ownership-rule"}
        self.assertEqual(env["data"], {"applied": True, "updated": [], "refused": [row], "unresolvable": []})
        self.assertIn("Local edit.", self.read("kc-a/beta.md"))
        forced = self.ok("sync-update", "--apply", "--force")["data"]
        self.assertEqual(forced["updated"], [row])
        self.assertIn("Neuer Kanon.", self.read("kc-a/beta.md"))

    def test_update_reports_an_unresolvable_block_with_its_status(self):
        self.ok("sync-insert", "kc-a/beta", "kc-gov/ownership", "ownership-rule", "--apply")
        os.remove(os.path.join(self.root, "kc-gov/ownership.md"))
        env = self.fails("drift", 5, "sync-update")
        (row,) = env["data"]["unresolvable"]
        self.assertEqual((row["consumer"], row["id"], row["status"]), ("kc-a/beta.md", "ownership-rule", "source-missing"))

    def test_update_of_a_missing_target_is_not_found(self):
        self.fails("not_found", 3, "sync-update", "nosuch")


class VisualizeAndCtx(WriteFixture):
    EDITOR = {"VISUAL": "true", "EDITOR": "true"}  # VISUAL wins over EDITOR, so set both

    def test_visualize_reports_what_it_wrote(self):
        data = self.ok("visualize", "kc-a")["data"]
        self.assertEqual((data["applied"], data["nodes"], data["edges"]), (True, 4, 1))
        self.assertEqual(data["path"], os.path.join(self.root, "kc-a", "assets", "viz.html"))
        self.assertTrue(os.path.isfile(data["path"]))
        self.assertIn("(4 nodes, 1 edges)", self.text("visualize", "kc-a"))
        out = os.path.join(self.root, "elsewhere", "g.html")
        self.assertEqual(self.ok("visualize", "kc-a", "--out", out)["data"]["path"], out)

    def test_visualize_of_a_missing_bundle_fails(self):
        self.assertEqual(self.fails("not_found", 3, "visualize", "nosuch")["data"], None)

    def test_ctx_create_add_move_drop(self):
        data = self.ok("ctx", "create", "fresh", "kc-a/alpha", "--description", "d")["data"]
        self.assertEqual(data, {"applied": True, "slug": "fresh", "path": "_ctx/fresh.md", "entries": 1})
        self.assertTrue(self.exists("_ctx/fresh.md"))
        added = self.ok("ctx", "add", "fresh", "kc-gov/ownership", "--mode", "nachschlag")["data"]
        self.assertEqual(added, {"applied": True, "slug": "fresh", "path": "kc-gov/ownership.md", "where": "reference"})
        moved = self.ok("ctx", "move", "fresh", "kc-gov/ownership", "--mode", "pflicht", "--pos", "1")["data"]
        self.assertEqual(moved["where"], "pos 1")
        self.assertIn("moved kc-gov/ownership.md in fresh to pos 2",
                      self.text("ctx", "move", "fresh", "kc-gov/ownership", "--pos", "2"))
        dropped = self.ok("ctx", "drop", "fresh", "kc-gov/ownership")["data"]
        self.assertEqual(dropped, {"applied": True, "slug": "fresh", "path": "kc-gov/ownership.md"})
        self.assertNotIn("ownership", self.read("_ctx/fresh.md"))

    def test_ctx_write_refusals_keep_their_class(self):
        for argv, kind, code in ((["ctx", "create", "BadSlug", "kc-a/alpha"], "invalid_input", 2),
                                 (["ctx", "create", "demo", "kc-a/alpha"], "invalid_input", 2),
                                 (["ctx", "create", "fresh", "kc-a/nosuch"], "not_found", 3),
                                 (["ctx", "add", "demo", "kc-a/alpha"], "invalid_input", 2),
                                 (["ctx", "add", "demo", "kc-a/nosuch"], "not_found", 3),
                                 (["ctx", "drop", "demo", "kc-gov/ownership"], "not_found", 3),
                                 (["ctx", "move", "demo", "kc-a/alpha"], "invalid_input", 2),
                                 (["ctx", "remove", "nosuch"], "not_found", 3),
                                 (["ctx", "rename", "demo", "Bad Slug"], "invalid_input", 2),
                                 (["ctx", "rename", "nosuch", "other"], "not_found", 3)):
            with self.subTest(argv=argv):
                self.fails(kind, code, *argv)

    def test_ctx_rename_carries_the_move_and_the_new_slug(self):
        data = self.ok("ctx", "rename", "demo", "renamed")["data"]
        self.assertEqual((data["old_slug"], data["new_slug"], data["old"], data["new"], data["applied"]),
                         ("demo", "renamed", "_ctx/demo.md", "_ctx/renamed.md", True))
        self.assertTrue(self.exists("_ctx/renamed.md"))
        self.assertFalse(self.exists("_ctx/demo.md"))
        self.assertIn("renamed", self.read("_ctx/renamed.md"))

    def test_ctx_remove_lists_the_files_that_still_link_in_data_and_not_in_warnings(self):
        self._w("kc-a/pointer.md", "---\ntype: Note\ntitle: P\ndescription: d\n---\n\n# P\n\n[c](/_ctx/demo.md)\n")
        env = self.ok("ctx", "remove", "demo")
        self.assertEqual(env["data"], {"applied": True, "slug": "demo", "path": "_ctx/demo.md",
                                       "entries": 2, "linked_from": ["kc-a/pointer.md"]})
        self.assertEqual(env["warnings"], [])
        self.assertFalse(self.exists("_ctx/demo.md"))
        run_cli(self.root, "ctx", "create", "demo", "kc-a/alpha")
        text = self.text("ctx", "remove", "demo")
        self.assertIn("warning: 1 file(s) still link to _ctx/demo.md:\n  kc-a/pointer.md\n", text)

    def test_ctx_edit_reports_the_findings_of_the_file_it_validated(self):
        env = self.ok("ctx", "edit", "demo", env=self.EDITOR)
        self.assertEqual([(f["rule"], f["severity"]) for f in env["data"]["findings"]],
                         [("kc/ctx/empty-description", "warning")])
        os.remove(os.path.join(self.root, "kc-a/beta.md"))
        failed = self.fails("non_conformant", 4, "ctx", "edit", "demo", env=self.EDITOR)
        self.assertIn(("kc/ctx/dead-entry", "error", "_ctx/demo.md"),
                      [(f["rule"], f["severity"], f["path"]) for f in failed["data"]["findings"]])

    def test_ctx_edit_fails_when_the_editor_does(self):
        env = self.fails("invalid_input", 2, "ctx", "edit", "demo", env={"VISUAL": "false", "EDITOR": "false"})
        self.assertIn("editor exited 1", env["error"]["message"])


class Conformance(WriteFixture):
    """R-04: every subparser of the built parser, each ctx verb included, answers `--json`
    with one five-key envelope. The command list comes from the parser; the table only says how
    to invoke each, and a command it does not name fails the test."""

    TABLE = {
        "archive": ["archive", "kc-a/old"],
        "build-index": ["build-index"],
        "build-semantic-index": ["build-semantic-index"],
        "check": ["check"],
        "ctx add": ["ctx", "add", "demo", "kc-gov/ownership"],
        "ctx check": ["ctx", "check"],
        "ctx create": ["ctx", "create", "fresh", "kc-a/alpha"],
        "ctx drop": ["ctx", "drop", "demo", "kc-a/beta"],
        "ctx edit": ["ctx", "edit", "demo"],
        "ctx inbound": ["ctx", "inbound", "demo"],
        "ctx list": ["ctx", "list"],
        "ctx move": ["ctx", "move", "demo", "kc-a/beta", "--mode", "nachschlag"],
        "ctx outbound": ["ctx", "outbound", "demo"],
        "ctx read": ["ctx", "read", "demo"],
        "ctx remove": ["ctx", "remove", "demo"],
        "ctx rename": ["ctx", "rename", "demo", "renamed"],
        "ctx show": ["ctx", "show", "demo"],
        "ctx toc": ["ctx", "toc", "demo"],
        "find": ["find", "pineapples"],
        "fix-crosslinks": ["fix-crosslinks", "--check"],
        "fix-xml-tags": ["fix-xml-tags", "--check"],
        "index": ["index"],
        "info": ["info"],
        "install": ["install", "--only", "claude"],
        "list": ["list", "--where", "type = Note"],
        "merge-tags": ["merge-tags", "alpha", "--into", "omega"],
        "normalize-tags": ["normalize-tags"],
        "prime": ["prime", "--compact"],
        "read": ["read", "kc-a/alpha"],
        "recent": ["recent"],
        "refs": ["refs", "kc-a/alpha.md"],
        "reindex": ["reindex", "kc-a"],
        "remove-tags": ["remove-tags", "gamma"],
        "rename": ["rename", "kc-a/old.md", "kc-a/older.md"],
        "rewrite-path": ["rewrite-path", "old/place.md", "new/place.md", "--check"],
        "sync-export": ["sync-export", "kc-gov/ownership", "ownership-rule"],
        "sync-insert": ["sync-insert", "kc-a/beta", "kc-gov/ownership", "ownership-rule"],
        "sync-status": ["sync-status"],
        "sync-update": ["sync-update"],
        "tags": ["tags"],
        "toc": ["toc", "kc-a/alpha"],
        "visualize": ["visualize", "kc-a"],
        "wikilinks": ["wikilinks"],
    }

    @staticmethod
    def registered():
        """Every command of the built parser, a ctx verb as `ctx <verb>`."""
        names = set()
        for name, parser in subcommand_parsers(build_parser()).items():
            verbs = subcommand_parsers(parser)
            names.update("{} {}".format(name, verb) for verb in verbs) if verbs else names.add(name)
        return names

    def test_the_table_names_exactly_the_registered_commands(self):
        registered = self.registered()
        self.assertEqual(sorted(registered - set(self.TABLE)), [], "no conformance entry for these commands")
        self.assertEqual(sorted(set(self.TABLE) - registered), [], "conformance entry for a command that is not registered")

    def test_every_command_answers_json_with_one_envelope_naming_itself(self):
        for name in sorted(self.registered()):
            with self.subTest(command=name):
                self.assertIn(name, self.TABLE, "no conformance entry for {}".format(name))
                fresh = tempfile.mkdtemp()
                self.addCleanup(shutil.rmtree, fresh, True)
                shutil.copytree(self.root, fresh, dirs_exist_ok=True)
                home = tempfile.mkdtemp()
                self.addCleanup(shutil.rmtree, home, True)
                env, err, code = run_json(fresh, *self.TABLE[name], home=home,
                                          env={"VISUAL": "true", "EDITOR": "true"})
                self.assertEqual((env["command"], env["ok"], env["error"], code, err), (name, True, None, 0, ""), env)

    def test_an_envelope_error_carries_the_exit_code_of_the_process(self):
        for kind, code, argv in (("invalid_input", 2, ["rename", "kc-a/alpha.md", "kc-a/alpha.txt"]),
                                 ("not_found", 3, ["reindex", "nosuch"]),
                                 ("non_conformant", 4, ["ctx", "read", "demo"]),
                                 ("drift", 5, ["reindex", "kc-a", "--check"])):
            with self.subTest(kind=kind):
                if kind == "non_conformant":
                    os.remove(os.path.join(self.root, "kc-a/beta.md"))
                if kind == "drift":
                    self._w("kc-a/index.md", self.read("kc-a/index.md").replace(
                        "<!-- /okf:index -->", "stale line\n<!-- /okf:index -->"))
                env, err, exit_code = run_json(self.root, *argv)
                self.assertEqual((env["ok"], env["error"]["kind"], env["error"]["code"], exit_code, err),
                                 (False, kind, code, code, ""))


if __name__ == "__main__":
    unittest.main()
