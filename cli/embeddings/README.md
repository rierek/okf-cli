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

## Embedded scope, part 1: tags

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

## Embedded scope, part 2: concept title+body (since P8/8c)

`--target concepts` (default `--target tags`, so this is opt-in and does not
change any existing behavior) additionally embeds a SECOND, independent
unit into a SEPARATE table, `concept_emb(key, path, model, dim, vec BLOB)` —
never touching `emb`'s tags-only rows/schema above. Each row embeds one
concept's `title + "\n\n" + body` (see `concept_text()`); `path` is the
concept identity (`bundle/concept-id`, no `.md`) that `okf-cli.py find`'s
semantic backstop maps a query's nearest vector back to.

**Why this exists, and why tags-only wasn't enough (bean okf-cli-3geg,
corrected finding).** Task 8c's acceptance names fixture S3 explicitly: a
concept with `tags=[]` where the query token lives only in the body. A
tag-keyed backstop has no vector to match a body-only paraphrase query
against for such concepts — this is not a coverage gap that improves with
more tags, it's a structural boundary of a tag-keyed cache (see "Finding
for Task 8" below for the full reasoning). `--target concepts` closes this
by embedding the concept itself, independent of its tags.

`--target {tags,concepts,both}` (default `tags`) selects which table(s) a
run touches; `--concept-path-prefix` scopes concept candidates to one
bundle/prefix (e.g. `agent-memory/_okfeval-`) and `--concept-limit` caps
the count — both exist to keep a manual `--produce` run small and
deterministic (this is how P8's own smoke test was run against the real
catalogue: 3-4 fixture concepts, never the full ~2435), not required for a
full production run.

`okf-cli.py find`'s semantic backstop currently only reads `concept_emb`
for model `bge-m3` (local Ollama, no API key, no per-query cost) — never
`voyage-3-large` at query time, even though the producer can embed concepts
with either model; a query-time Voyage call would need `VOYAGE_API_KEY` and
a paid network round-trip, which conflicts with "best-effort, no hard
dependency, no cost" graceful degradation.

## Usage

```bash
# dry-run (default): plan the tags-only delta, no network, no writes
python3 cli/embeddings/build_tagvec.py --root ~/Obsidian/Knowledge-Catalogue

# produce tags: (re)embed the missing tag delta and write rows
python3 cli/embeddings/build_tagvec.py \
    --root ~/Obsidian/Knowledge-Catalogue \
    --output ~/Obsidian/Knowledge-Catalogue/.tagvec/tag_vectors.sqlite \
    --model bge-m3 --model voyage-3-large \
    --produce

# produce concept title+body embeddings too (P8/8c) — bge-m3 only, scoped
# to keep a manual run small:
python3 cli/embeddings/build_tagvec.py \
    --root ~/Obsidian/Knowledge-Catalogue \
    --output ~/Obsidian/Knowledge-Catalogue/.tagvec/tag_vectors.sqlite \
    --model bge-m3 --target concepts \
    --concept-path-prefix agent-memory/ \
    --produce
```

Flags:
- `--root` — catalogue root (default: this script's own location, matching
  `okf-cli.py`'s `catalogue_root`).
- `--output` — sqlite path (default: `<root>/.tagvec/tag_vectors.sqlite`).
- `--model` — repeatable, one of `bge-m3` / `voyage-3-large` (default: both).
- `--target` — `tags` (default), `concepts`, or `both`. See "Embedded scope,
  part 2" above.
- `--concept-path-prefix` / `--concept-limit` — only relevant with
  `--target concepts`/`both`; scope/cap which concepts are (re-)embedded.
- `--produce` — the only gate for network calls + writes. Omit it to get a
  pure dry-run: which `(tag/concept, model)` pairs are missing from the
  cache.

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

**Verdict (corrected 2026-07-25, post-review F01): tag-embeddings alone are
INSUFFICIENT to satisfy Task 8c's S3 acceptance as specified.** PLAN.md
Task 8c's EARS names fixture S3 by name ("WHEN a paraphrase query ... for
fixture S3 AND an embedding backend is available, THE CLI SHALL surface the
expected concept within top-5"); S3 is `tags=[]` by construction with the
token only in its body, so a tag-only backstop cannot satisfy that SHALL —
see "Where tag-only structurally cannot help" below. Per PLAN.md Task 8c's
own contingency clause, Task 8c SHALL extend the offline producer to also
embed titles/bodies (not tags only). Full corrected finding + reasoning:
bean `okf-cli-3geg`, section "Finding for Task 8 — CORRECTED 2026-07-25
(post-review F01)".

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

**Recommendation.** Task 8c extends this producer to also embed concept
titles/bodies (not tags only) so S3-class, body-only-token concepts are
reachable by the semantic backstop — this is the scope call PLAN.md's
contingency clause already anticipated for this exact finding. Alternative
(PO-only): formally revise or drop 8c's S3 acceptance criterion before
implementation; a Task-7 finding is not the authority to drop it silently.
