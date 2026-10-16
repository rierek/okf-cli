// Package tagvec is the offline half of the tag-vector store `<root>/.tagvec/tag_vectors.sqlite`
// (Python cli/embeddings/build_tagvec.py and okf.semantic.semantic_coverage): the cache keys of
// the two embedding scopes, the planners that decide which tags and concepts still lack an
// embedding, and the coverage count. Nothing here embeds, writes a row or touches the network.
package tagvec

import (
	"crypto/sha1"
	"encoding/hex"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

// SemanticModel is the model of the productive semantic arm (Python SEMANTIC_MODEL).
const SemanticModel = "voyage-3-large"

// Schema creates the tag table `emb` (Python SCHEMA).
const Schema = "CREATE TABLE IF NOT EXISTS emb(key TEXT PRIMARY KEY, tag TEXT, model TEXT, dim INT, vec BLOB)"

// ConceptSchema creates the concept table `concept_emb` (Python CONCEPT_SCHEMA).
const ConceptSchema = "CREATE TABLE IF NOT EXISTS concept_emb" +
	"(key TEXT PRIMARY KEY, path TEXT, model TEXT, dim INT, vec BLOB)"

// Triple is one planned embedding, Python's (item, text, key) tuple: the tag slug or the concept
// path, the text to embed and its cache key.
type Triple struct{ Item, Text, Key string }

// SlugText is Python slug_text: the text a tag is embedded as, its slug with hyphens as spaces.
func SlugText(tag string) string { return strings.ReplaceAll(tag, "-", " ") }

// CacheKey is Python cache_key: the sha1 hex of model + "\x00slug\x00" + text, UTF-8 encoded.
func CacheKey(model, text string) string { return sha1Hex(model + "\x00slug\x00" + text) }

// ConceptText is Python concept_text: the embedding unit of a concept, its title and body with
// the whitespace at both ends of the whole stripped (str.strip).
func ConceptText(title, body string) string { return pytext.Strip(title + "\n\n" + body) }

// ConceptCacheKey is Python concept_cache_key: the sha1 hex of
// model + "\x00concept\x00" + path + "\x00" + text, UTF-8 encoded. The path is part of the
// payload, so the key changes when a concept's content or its identity changes.
func ConceptCacheKey(model, path, text string) string {
	return sha1Hex(model + "\x00concept\x00" + path + "\x00" + text)
}

func sha1Hex(payload string) string {
	sum := sha1.Sum([]byte(payload))
	return hex.EncodeToString(sum[:])
}
