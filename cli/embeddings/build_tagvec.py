#!/usr/bin/env python3
"""Producer for .tagvec/tag_vectors.sqlite — see cli/embeddings/README.md.

Brought in-repo from the ad-hoc offline SOP
(Knowledge-Catalogue/okf-meta-wiki/extensions/embedding-based-tag-consolidation.md,
RET11) so the cache's `emb(key, tag, model, dim, vec)` schema (RET10) is
reproducible from a catalogue root rather than living only as prose.

This is an OFFLINE, NON-runtime-dependency script:
- `okf-cli.py find` reads the cache at query time; it never produces it.
- Import and argument parsing here NEVER touch the network.
- Network calls (Ollama for bge-m3, Voyage AI for voyage-3-large) run ONLY
  behind the explicit --produce flag. Without --produce this is a pure
  dry-run: it reports which (tag, model) pairs are missing from the cache
  and writes nothing.

Usage:
    python3 cli/embeddings/build_tagvec.py [--root ROOT] [--output PATH]
        [--model bge-m3] [--model voyage-3-large] [--produce]

Run: python3 -m unittest cli.test_embeddings_tagvec -v
"""
import argparse
import hashlib
import importlib.util
import json
import os
import sqlite3
import struct
import sys
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
_CLI_PATH = os.path.join(_HERE, "..", "okf-cli.py")

# model -> (embedding dim, network endpoint). Both rows in the live cache are
# 1024-dim (627 bge-m3 + 650 voyage-3-large, RET10).
MODELS = {
    "bge-m3": {
        "dim": 1024,
        "endpoint": "http://localhost:11434/api/embed",
    },
    "voyage-3-large": {
        "dim": 1024,
        "endpoint": "https://api.voyageai.com/v1/embeddings",
    },
}

SCHEMA = "CREATE TABLE IF NOT EXISTS emb(key TEXT PRIMARY KEY, tag TEXT, model TEXT, dim INT, vec BLOB)"

# P8/8c (okf-cli-8uaf) — separate table, NOT touching `emb`'s tags-only
# schema/rows. Per the corrected Task-7 finding (bean okf-cli-3geg): tag
# embeddings alone cannot satisfy fixture S3 (tags=[], body-only token), so
# 8c extends this producer to also embed concept titles/bodies. `path` is
# the concept identity (bundle/concept-id, no .md); `key` is content+path
# addressed so re-embedding responds to either changing.
CONCEPT_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS concept_emb"
    "(key TEXT PRIMARY KEY, path TEXT, model TEXT, dim INT, vec BLOB)"
)


def _load_okf_cli():
    """Import okf-cli.py (hyphenated filename, not an importable package) for
    catalogue_root()/all_tags() — same importlib pattern as test_okf_cli.py."""
    spec = importlib.util.spec_from_file_location("okf_cli", _CLI_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def slug_text(tag):
    """Critical design decision from the SOP: embed the SLUG only
    (`tag.replace('-', ' ')`), never concept titles/bodies. Body-enrichment
    was tried and rejected — it measures concept co-occurrence, not label
    meaning (`task-brief -> superwhisper` scored 0.92 purely because both
    tags live on the same concept). This is the tags-only scope the README
    and the Task-8 finding depend on."""
    return tag.replace("-", " ")


def cache_key(model, text):
    """key = sha1(model + '\\x00slug\\x00' + text) — the live cache's key
    scheme (RET10). Keeps bge-m3 and voyage-3-large rows co-resident without
    collision, and re-embeds only on genuine (model, text) change."""
    payload = (model + "\x00slug\x00" + text).encode("utf-8")
    return hashlib.sha1(payload).hexdigest()


def existing_keys(db_path):
    """Cache keys already present in the output db — the delta-reuse gate."""
    if not os.path.exists(db_path):
        return set()
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(SCHEMA)
        return {row[0] for row in conn.execute("SELECT key FROM emb")}
    finally:
        conn.close()


def plan_delta(tags, model, db_path):
    """Which (tag, slug_text, key) triples still need embedding for `model`
    against db_path. Pure/offline — no network — this is what --produce acts
    on and what the dry-run reports."""
    have = existing_keys(db_path)
    out = []
    for tag in sorted(tags):
        text = slug_text(tag)
        key = cache_key(model, text)
        if key not in have:
            out.append((tag, text, key))
    return out


def concept_text(title, body):
    """Title + body — the embedding unit for the concept-scope pass (8c),
    deliberately distinct from slug_text()'s tag-only scope: this is what
    lets a body-only-token concept (S3-class) be found by the semantic
    backstop at all."""
    return (title + "\n\n" + body).strip()


def concept_cache_key(model, path, text):
    """key = sha1(model + '\\x00concept\\x00' + path + '\\x00' + text) —
    path-scoped (unlike cache_key()'s tag keys), so a concept's key changes
    if EITHER its content or its identity (path) changes; two different
    concepts with identical content never collide since path is part of
    the payload."""
    payload = (model + "\x00concept\x00" + path + "\x00" + text).encode("utf-8")
    return hashlib.sha1(payload).hexdigest()


def existing_concept_keys(db_path):
    """Cache keys already present in concept_emb — the delta-reuse gate,
    mirroring existing_keys() for the tag-scope table."""
    if not os.path.exists(db_path):
        return set()
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(CONCEPT_SCHEMA)
        return {row[0] for row in conn.execute("SELECT key FROM concept_emb")}
    finally:
        conn.close()


def _iter_all_concepts(okf, root):
    """(path, abspath) for every concept in the catalogue, path = bundle/cid
    (no .md) — the same identity form okf-cli.py's find prints."""
    for b in okf.list_bundles(root):
        bp = os.path.join(root, b)
        for cid, ap in okf.iter_concepts(bp):
            yield "{}/{}".format(b, cid), ap


def plan_concept_delta(root, model, db_path, path_prefix=None, limit=None):
    """Which (path, text, key) triples still need title+body embedding for
    `model` against db_path. Pure/offline — no network. `path_prefix`
    scopes candidates (e.g. to one bundle or one fixture prefix) — useful
    to keep a manual --produce run small and deterministic; `limit` caps
    the count after that filter."""
    okf = _load_okf_cli()
    have = existing_concept_keys(db_path)
    out = []
    for path, ap in sorted(_iter_all_concepts(okf, root)):
        if path_prefix and not path.startswith(path_prefix):
            continue
        fm, body = okf.split_frontmatter(okf.read_file(ap))
        title = okf._dequote(fm.get("title", "")) or os.path.basename(ap)[:-3]
        text = concept_text(title, body)
        key = concept_cache_key(model, path, text)
        if key not in have:
            out.append((path, text, key))
            if limit and len(out) >= limit:
                break
    return out


def write_concept_rows(db_path, rows):
    """rows: iterable of (key, path, model, dim, vec_bytes)."""
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(CONCEPT_SCHEMA)
        conn.executemany(
            "INSERT OR REPLACE INTO concept_emb(key, path, model, dim, vec) VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def embed_bge_m3(texts):
    """Local Ollama bge-m3 embed call. NETWORK — only reached under --produce."""
    vectors = []
    for t in texts:
        req = urllib.request.Request(
            MODELS["bge-m3"]["endpoint"],
            data=json.dumps({"model": "bge-m3", "input": t}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        vectors.append(body["embeddings"][0])
    return vectors


def embed_voyage(texts):
    """Voyage AI voyage-3-large embed call. NETWORK — only reached under
    --produce. Requires VOYAGE_API_KEY in the environment (SOP note: the
    context-mode sandbox does not inherit it; a plain bash subprocess does)."""
    api_key = os.environ.get("VOYAGE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "VOYAGE_API_KEY not set — required for --produce --model voyage-3-large")
    req = urllib.request.Request(
        MODELS["voyage-3-large"]["endpoint"],
        data=json.dumps({
            "model": "voyage-3-large",
            "input": texts,
            "input_type": "document",
        }).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + api_key,
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return [d["embedding"] for d in body["data"]]


def pack_vec(vec):
    """Float32 blob, matching the live cache's `vec BLOB` encoding."""
    return struct.pack("<{}f".format(len(vec)), *vec)


def write_rows(db_path, rows):
    """rows: iterable of (key, tag, model, dim, vec_bytes)."""
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(SCHEMA)
        conn.executemany(
            "INSERT OR REPLACE INTO emb(key, tag, model, dim, vec) VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def build_parser():
    p = argparse.ArgumentParser(
        prog="build_tagvec.py",
        description=(
            "Offline producer for .tagvec/tag_vectors.sqlite (emb schema, RET10). "
            "NOT a runtime dependency of okf-cli.py find — see cli/embeddings/README.md. "
            "Without --produce this only plans the delta; no network, no writes."
        ),
    )
    p.add_argument("--root", default=None,
                    help="catalogue root (default: this script's okf-cli.py location)")
    p.add_argument("--output", default=None,
                    help="output sqlite path (default: <root>/.tagvec/tag_vectors.sqlite)")
    p.add_argument("--model", choices=sorted(MODELS), action="append", dest="models",
                    help="model to (re)embed with; repeatable. Default: both models.")
    p.add_argument("--target", choices=("tags", "concepts", "both"), default="tags",
                    help="what to embed: tags only (default, unchanged behavior), "
                         "concept titles+bodies only (P8/8c), or both.")
    p.add_argument("--concept-path-prefix", default=None,
                    help="only plan/produce concept embeddings for paths starting with "
                         "this prefix (e.g. 'bundle/' or 'bundle/_okfeval-') — scoping "
                         "for small, deterministic manual --produce runs.")
    p.add_argument("--concept-limit", type=int, default=None,
                    help="cap the number of concepts (re-)embedded per model, after "
                         "--concept-path-prefix filtering.")
    p.add_argument("--produce", action="store_true",
                    help="perform network embedding calls and write rows. Without this "
                         "flag: dry-run only (plan + print, no network, no writes).")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    okf = _load_okf_cli()
    root = okf.catalogue_root(args.root)
    output = args.output or os.path.join(root, ".tagvec", "tag_vectors.sqlite")
    models = args.models or sorted(MODELS)

    do_tags = args.target in ("tags", "both")
    do_concepts = args.target in ("concepts", "both")

    tags = set(okf.all_tags(root)) if do_tags else set()
    total_delta = 0

    def _embed(model, texts):
        if model == "bge-m3":
            return embed_bge_m3(texts)
        if model == "voyage-3-large":
            return embed_voyage(texts)
        raise ValueError("unknown model: {}".format(model))

    for model in models:
        if do_tags:
            delta = plan_delta(tags, model, output)
            total_delta += len(delta)
            print("{}: {} tag(s) need embedding, {} already cached".format(
                model, len(delta), len(tags) - len(delta)))

            if args.produce and delta:
                texts = [text for _tag, text, _key in delta]
                vectors = _embed(model, texts)
                rows = [
                    (key, tag, model, MODELS[model]["dim"], pack_vec(vec))
                    for (tag, _text, key), vec in zip(delta, vectors)
                ]
                write_rows(output, rows)
                print("{}: wrote {} row(s) to {}".format(model, len(rows), output))

        if do_concepts:
            cdelta = plan_concept_delta(
                root, model, output,
                path_prefix=args.concept_path_prefix, limit=args.concept_limit)
            total_delta += len(cdelta)
            print("{}: {} concept(s) need title+body embedding".format(model, len(cdelta)))

            if args.produce and cdelta:
                texts = [text for _path, text, _key in cdelta]
                vectors = _embed(model, texts)
                rows = [
                    (key, path, model, MODELS[model]["dim"], pack_vec(vec))
                    for (path, _text, key), vec in zip(cdelta, vectors)
                ]
                write_concept_rows(output, rows)
                print("{}: wrote {} concept row(s) to {}".format(model, len(rows), output))

    if not args.produce and total_delta:
        print("(dry-run — no network calls, no writes. Re-run with --produce to embed.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
