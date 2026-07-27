#!/usr/bin/env python3
"""Throwaway experiment (Think session okf-retrieval-architecture).

Populates a SEPARATE eval sqlite with concept vectors for the whole live
catalogue, in two independent arms:

  arm A  model='bge-m3+title'      -> embeds the concept TITLE only
  arm B  model='bge-m3+titlebody'  -> embeds title + "\\n\\n" + body (today's
                                      concept_text(), the accused candidate)

Never touches the live .tagvec cache and never writes model='bge-m3', so the
production semantic backstop stays dormant either way.
"""
import argparse
import hashlib
import os
import re
import sqlite3
import struct
import sys
import time

REPO = "/Users/erik/dev/okf-tools"
sys.path.insert(0, os.path.join(REPO, "cli", "embeddings"))
import build_tagvec as bt  # noqa: E402

ARMS = {
    "title": lambda title, body: title.strip(),
    "titlebody": lambda title, body: bt.concept_text(title, body),
    "chunk": None,  # multi-vector, see chunks_of()
}
# Every arm can run under either backend; the model column keeps them apart
# ("bge-m3+chunk" vs "voyage-3-large+chunk"), so a weak arm and a weak model
# stay separable — otherwise "embedding does not work here" would conflate
# design and model capability.
BACKENDS = {
    "bge-m3": {"batch": 1, "fn": lambda texts: bt.embed_bge_m3(texts)},
    "voyage-3-large": {"batch": 48, "fn": lambda texts: bt.embed_voyage(texts)},
}
MAX_BATCH_CHARS = 90000
HEADING = re.compile(r"^(#{2,3})\s+(.*)$")
MIN_CHUNK_CHARS = 30
# bge-m3 context is 8192 tokens; cap the body so a few very long concepts
# cannot silently blow up or stall the run. Truncations are counted+reported —
# a high count is itself a finding for arm B.
MAX_CHARS = 24000

SCHEMA = """CREATE TABLE IF NOT EXISTS concept_emb (
  key TEXT PRIMARY KEY, path TEXT, model TEXT, dim INTEGER, vec BLOB)"""


def chunks_of(title, body):
    """[(chunk_id, text), ...] — one unit per h2/h3 section, plus the
    preamble before the first heading. Each chunk carries its own heading
    line as context but NOT the concept title (arm A already measures the
    title signal in isolation; mixing it into every chunk would blur the
    comparison). Sections shorter than MIN_CHUNK_CHARS are dropped as noise."""
    sections, cur_head, cur_lines = [], "", []
    for line in body.splitlines():
        m = HEADING.match(line)
        if m:
            sections.append((cur_head, "\n".join(cur_lines)))
            cur_head, cur_lines = m.group(2).strip(), []
        else:
            cur_lines.append(line)
    sections.append((cur_head, "\n".join(cur_lines)))

    out = []
    for i, (head, text) in enumerate(sections):
        text = text.strip()
        if len(head) + len(text) < MIN_CHUNK_CHARS:
            continue
        unit = (head + "\n\n" + text).strip() if head else text
        out.append(("{}".format(i), unit[:MAX_CHARS]))
    # A concept with no usable section at all still needs one vector, or it
    # becomes structurally unfindable in this arm (S3-class guarantee).
    if not out:
        out = [("0", (title + "\n\n" + body).strip()[:MAX_CHARS])]
    return out


def embed_resilient(fn, texts, label):
    """Vectors for `texts`, or None. Arm B died once on a plain HTTP 400 from
    Ollama under three concurrent workers; a single failure must not throw
    away the whole pass. Retry with backoff, then progressively halve every
    text (a 400 on these endpoints is usually an over-long input), then give
    up and report."""
    delay = 2
    for attempt in range(3):
        try:
            return fn(texts)
        except Exception as exc:
            print("    retry {} ({} texts) {}: {}".format(
                attempt + 1, len(texts), label, exc), flush=True)
            time.sleep(delay)
            delay *= 2
            if attempt >= 1:
                texts = [t[: max(len(t) // 2, 500)] for t in texts]
    print("    SKIPPED {}".format(label), flush=True)
    return None


def batches(todo, max_items, max_chars):
    cur, chars = [], 0
    for item in todo:
        if cur and (len(cur) >= max_items or chars + len(item[2]) > max_chars):
            yield cur
            cur, chars = [], 0
        cur.append(item)
        chars += len(item[2])
    if cur:
        yield cur


def key_of(model, path, text):
    payload = (model + "\x00concept\x00" + path + "\x00" + text).encode("utf-8")
    return hashlib.sha1(payload).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=sorted(ARMS), required=True)
    ap.add_argument("--root", default="/Users/erik/Obsidian/Knowledge-Catalogue")
    ap.add_argument("--db", required=True)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--ollama-host", default="localhost",
                    help="offload the embed calls to another Ollama (e.g. the "
                         "Mac Mini over Tailscale) — only the HTTP call moves, "
                         "the sqlite write stays local")
    ap.add_argument("--reverse", action="store_true",
                    help="walk the todo list backwards, so a second worker can "
                         "meet the forward one in the middle")
    ap.add_argument("--embed-model", choices=sorted(BACKENDS), default="bge-m3")
    args = ap.parse_args()

    bt.MODELS["bge-m3"]["endpoint"] = "http://{}:11434/api/embed".format(args.ollama_host)
    backend = BACKENDS[args.embed_model]
    model = "{}+{}".format(args.embed_model, args.arm)
    textfn = ARMS[args.arm]
    okf = bt._load_okf_cli()

    conn = sqlite3.connect(args.db)
    conn.execute(SCHEMA)
    have = {r[0] for r in conn.execute(
        "SELECT key FROM concept_emb WHERE model = ?", (model,))}
    conn.close()

    todo = []
    truncated = 0
    for path, abspath in sorted(bt._iter_all_concepts(okf, args.root)):
        fm, body = okf.split_frontmatter(okf.read_file(abspath))
        title = okf._dequote(fm.get("title", "")) or os.path.basename(abspath)[:-3]
        if args.arm == "chunk":
            units = [t for _cid, t in chunks_of(title, body)]
        else:
            units = [textfn(title, body)]
        for text in units:
            if len(text) > MAX_CHARS:
                text = text[:MAX_CHARS]
                truncated += 1
            k = key_of(model, path, text)
            if k not in have:
                todo.append((k, path, text))
        if args.limit and len(todo) >= args.limit:
            break

    if args.reverse:
        todo.reverse()
    print("arm={} model={} todo={} truncated={} host={} reverse={}".format(
        args.arm, model, len(todo), truncated, args.ollama_host, args.reverse),
        flush=True)

    batch, done, t0 = [], 0, time.time()
    for group in batches(todo, backend["batch"], MAX_BATCH_CHARS):
        group = [g for g in group if g[0] not in have]  # done by the other worker
        if not group:
            continue
        vecs = embed_resilient(backend["fn"], [g[2] for g in group], group[0][1])
        if vecs is None:
            continue
        for (k, path, _text), vec in zip(group, vecs):
            batch.append((k, path, model, len(vec), struct.pack(
                "<{}f".format(len(vec)), *vec)))
            done += 1
        if len(batch) >= 50:
            conn = sqlite3.connect(args.db)
            conn.execute(SCHEMA)
            conn.executemany(
                "INSERT OR REPLACE INTO concept_emb(key, path, model, dim, vec)"
                " VALUES (?, ?, ?, ?, ?)", batch)
            conn.commit()
            have = {r[0] for r in conn.execute(
                "SELECT key FROM concept_emb WHERE model = ?", (model,))}
            conn.close()
            batch = []
            rate = done / (time.time() - t0)
            print("  {}/{} ({:.1f}/s, eta {:.0f}s)".format(
                done, len(todo), rate, (len(todo) - done) / max(rate, 0.01)),
                flush=True)
    if batch:
        conn = sqlite3.connect(args.db)
        conn.execute(SCHEMA)
        conn.executemany(
            "INSERT OR REPLACE INTO concept_emb(key, path, model, dim, vec)"
            " VALUES (?, ?, ?, ?, ?)", batch)
        conn.commit()
        conn.close()
    print("arm={} DONE {} rows in {:.0f}s".format(
        args.arm, done, time.time() - t0), flush=True)


if __name__ == "__main__":
    main()
