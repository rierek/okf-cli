#!/usr/bin/env python3
"""Throwaway: build the paraphrase ground-truth set.

Samples N concepts, asks the LOCAL qwen3.5:9b for one realistic short search
query per concept that deliberately AVOIDS the concept's own distinctive
vocabulary (title words + tags). The target is known by construction, which
is exactly what the 10-concept demo lacked.

Run this only when the bge-m3 embedding passes are done — otherwise Ollama
swaps models between every request.
"""
import argparse
import json
import os
import random
import re
import sys
import urllib.request

REPO = "/Users/erik/Obsidian/tools/okf-tools"
sys.path.insert(0, os.path.join(REPO, "cli", "embeddings"))
import build_tagvec as bt  # noqa: E402

GEN_URL = "http://localhost:11434/api/generate"   # overridden by --ollama-host
GEN_MODEL = "qwen3.5:9b"

PROMPT = """You generate realistic search queries for a personal knowledge base.

Below is one note. Write ONE short search query (2-5 words) that a developer
would plausibly type when looking for exactly this note WITHOUT remembering
its wording — a paraphrase from intent, not a quote.

Hard rules:
- Do NOT reuse any of these forbidden words (or their obvious inflections): {forbidden}
- Use the same language the note is written in.
- Output ONLY the query. No quotes, no explanation, no preamble.

--- NOTE ---
title: {title}
tags: {tags}

{excerpt}
--- END ---"""


def ask(prompt):
    req = urllib.request.Request(
        GEN_URL,
        data=json.dumps({"model": GEN_MODEL, "prompt": prompt, "stream": False,
                         "think": False, "options": {"temperature": 0.7}}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode("utf-8"))["response"]


def clean(raw):
    txt = re.sub(r"<think>.*?</think>", "", raw, flags=re.S).strip()
    txt = txt.strip().strip('"').strip("'").splitlines()[0] if txt.strip() else ""
    return txt.strip().strip('"').strip("'")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/Users/erik/Obsidian/Knowledge-Catalogue")
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--seed", type=int, default=20260725)
    ap.add_argument("--out", default="queries_generated.json")
    ap.add_argument("--ollama-host", default="localhost",
                    help="run generation on another Ollama (Mac Mini over "
                         "Tailscale) so it does not evict bge-m3 here")
    args = ap.parse_args()

    global GEN_URL
    GEN_URL = "http://{}:11434/api/generate".format(args.ollama_host)

    okf = bt._load_okf_cli()
    all_concepts = sorted(bt._iter_all_concepts(okf, args.root))
    random.Random(args.seed).shuffle(all_concepts)

    out = []
    for path, abspath in all_concepts:
        if len(out) >= args.n:
            break
        raw = okf.read_file(abspath)
        fm, body = okf.split_frontmatter(raw)
        title = okf._dequote(fm.get("title", "")) or path.rsplit("/", 1)[-1]
        tags = okf.extract_tags(raw)
        body = body.strip()
        if len(body) < 400:      # too thin to paraphrase meaningfully
            continue
        forbidden = sorted({w.lower() for w in re.split(r"[^A-Za-zÄÖÜäöüß0-9]+", title) if len(w) > 3}
                           | {t.lower() for t in tags})
        # The generator ignores the forbidden list often enough to matter: a
        # leaked title word makes the query trivially keyword-findable and
        # would flatter arm K. Retry, keep the cleanest attempt.
        best, best_leak = None, None
        for attempt in range(3):
            cand = clean(ask(PROMPT.format(
                forbidden=", ".join(forbidden) or "(none)",
                title=title, tags=", ".join(tags) or "(none)",
                excerpt=body[:1500])))
            if not cand or len(cand) > 80:
                continue
            leak = [w for w in forbidden if w in cand.lower()]
            if best is None or len(leak) < len(best_leak):
                best, best_leak = cand, leak
            if not leak:
                break
        if best is None:
            continue
        q, leaked = best, best_leak
        out.append({"query": q, "target": path, "forbidden": forbidden,
                    "leaked": leaked, "source": "generated"})
        print("{:3d} {:<55} -> {}{}".format(
            len(out), q, path, "  LEAK:" + ",".join(leaked) if leaked else ""),
            flush=True)

    with open(args.out, "w") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)
    leaks = sum(1 for r in out if r["leaked"])
    print("wrote {} queries to {} ({} with leaked vocabulary — kept, flagged)".format(
        len(out), args.out, leaks))


if __name__ == "__main__":
    main()
