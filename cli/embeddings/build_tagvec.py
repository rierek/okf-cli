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

    tags = set(okf.all_tags(root))
    total_delta = 0
    for model in models:
        delta = plan_delta(tags, model, output)
        total_delta += len(delta)
        print("{}: {} tag(s) need embedding, {} already cached".format(
            model, len(delta), len(tags) - len(delta)))

        if not args.produce or not delta:
            continue

        texts = [text for _tag, text, _key in delta]
        if model == "bge-m3":
            vectors = embed_bge_m3(texts)
        elif model == "voyage-3-large":
            vectors = embed_voyage(texts)
        else:
            raise ValueError("unknown model: {}".format(model))

        rows = [
            (key, tag, model, MODELS[model]["dim"], pack_vec(vec))
            for (tag, _text, key), vec in zip(delta, vectors)
        ]
        write_rows(output, rows)
        print("{}: wrote {} row(s) to {}".format(model, len(rows), output))

    if not args.produce and total_delta:
        print("(dry-run — no network calls, no writes. Re-run with --produce to embed.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
