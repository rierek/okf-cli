# `.tagvec` — offline embedding producer

`build_tagvec.py` regenerates `.tagvec/tag_vectors.sqlite`: the tag-similarity
cache that `okf-cli.py find`'s semantic backstop (P8) reads at query time.

## Offline pass, NOT a runtime dependency

- `find` **reads** this cache (stdlib `sqlite3`, no new runtime dep on
  `cli/okf-cli.py`) — it never produces it, and never falls over if the file
  is absent (graceful skip).
- `build_tagvec.py` **produces** it. It runs as a separate, occasional,
  human-triggered offline pass — not part of any request path, not imported
  by `okf-cli.py`, not exercised by CI beyond its own network-free unit
  tests (`cli/test_embeddings_tagvec.py`).
- Importing the module or parsing its arguments never touches the network.
  Network calls (Ollama for `bge-m3`, Voyage AI for `voyage-3-large`) happen
  ONLY behind the explicit `--produce` flag. Without it, the script only
  plans and prints the delta — nothing is written, nothing is called.

## Embedded scope: tags only

The cache's schema is `emb(key, tag, model, dim, vec BLOB)` (confirmed
against the live cache, 627 `bge-m3` + 650 `voyage-3-large` rows). The `tag`
column is the whole embedded unit: each row embeds **one tag's slug**
(`tag.replace("-", " ")`), never a concept's title, description, or body.

This was a deliberate, empirically-forced design choice in the source SOP
(`Knowledge-Catalogue/okf-meta-wiki/extensions/embedding-based-tag-consolidation.md`):
an earlier version enriched each tag with the titles/descriptions of the
concepts carrying it, which contaminated the similarity signal — two
unrelated tags living on the same concept scored ~0.9 purely from shared
enrichment text (`task-brief → superwhisper` 0.92), because that measured
concept co-occurrence, not label meaning. Slug-only embedding fixed it
(`sicherheit → security` 0.90, `custom-plugins → plugins` 0.87 — genuine
label synonymy).

## Usage

```bash
# dry-run (default): plan the delta, no network, no writes
python3 cli/embeddings/build_tagvec.py --root ~/Obsidian/Knowledge-Catalogue

# produce: (re)embed the missing delta and write rows
python3 cli/embeddings/build_tagvec.py \
    --root ~/Obsidian/Knowledge-Catalogue \
    --output ~/Obsidian/Knowledge-Catalogue/.tagvec/tag_vectors.sqlite \
    --model bge-m3 --model voyage-3-large \
    --produce
```

Flags:
- `--root` — catalogue root (default: this script's own location, matching
  `okf-cli.py`'s `catalogue_root`).
- `--output` — sqlite path (default: `<root>/.tagvec/tag_vectors.sqlite`).
- `--model` — repeatable, one of `bge-m3` / `voyage-3-large` (default: both).
- `--produce` — the only gate for network calls + writes. Omit it to get a
  pure dry-run: which `(tag, model)` pairs are missing from the cache.

Delta-reuse: a tag is only (re-)embedded if `sha1(model + "\x00slug\x00" +
slug_text)` is not already a key in the output db — matches the live cache's
key scheme exactly (verified against a real row: `abgeleitetes-artefakt` /
`bge-m3` → `9ed7f0099beeb094eb5bd182c33f1714c0c77b84`). `bge-m3` and
`voyage-3-large` rows for the same tag never collide, since `model` is part
of the key.

Model set + endpoints (SOP, unchanged): `bge-m3` (1024-dim) via a local
Ollama instance (`http://localhost:11434/api/embed`); `voyage-3-large`
(1024-dim, `input_type=document`) via `https://api.voyageai.com/v1/embeddings`
— requires `VOYAGE_API_KEY` in the environment for `--produce`.

## Finding for Task 8: tag-embeddings only vs. body-embeddings needed

**Verdict: tag-embeddings suffice as Task 8's semantic-backstop surface.**
Extending embedding to concept titles/bodies is NOT required for P8 — it
would be a materially bigger, separately-scoped undertaking, and the
residual gap it would close is small and already documented (see below).

**Coverage.** As of this pass, 2.0% of concepts in the live catalogue
(49 / 2435) carry zero tags; the remaining 98.0% carry at least one. A
tag-keyed semantic backstop can, in principle, help retrieval for any
concept in that 98%.

**Where tag-only helps.** The backstop rescues queries whose vocabulary is
closer to a tag's *label* than to the concept's literal title/body tokens —
exactly the synonym drift the source SOP measured directly during tag
consolidation: `sicherheit → security` (0.90), `portainer → docker`,
`worktree → git`, `jira → issue-tracking` (Voyage pass, none ranked by BGE).
That is the shape of a real paraphrase query missing a keyword hit today.

**Where tag-only structurally cannot help.** The eval fixtures
(`cli/eval/fixtures.py`) already encode this gap on purpose: S3 ("generic
title, no matching tags... to isolate the keyword-vs-semantic gap") and S4
("frontmatter type/tag missing on purpose... findable only via index-walk
or body search") both seed `tags=[]`. A tag-only backstop has nothing to
embed for these concepts — there is no tag vector to match a paraphrase
query against — so it cannot rescue S3/S4-class misses by construction, only
S1/S2-class ones (tags present, `["eval-fixture"]`). This is the same 2.0%
untagged slice quantified above; it is not a bug in Task 8, it's an inherent
boundary of a tag-keyed cache.

**Recommendation.** Ship P8's semantic backstop against `.tagvec` as
specified (tag-only). Treat the untagged-concept gap as an accepted,
documented residual — not silently absorbed into P8's scope. If it proves
material in practice (e.g. via P12's re-measurement), title/body embedding
is a legitimate follow-up task, but it is a different (larger: ~2435
concepts vs. 418 tags today) indexing problem and should be scoped as such
rather than folded into this task.
