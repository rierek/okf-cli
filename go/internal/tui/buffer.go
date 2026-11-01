package tui

import (
	"path/filepath"
	"slices"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/find"
)

// bufferEntry is one buffered hit: a snapshot of the hit fields the hand-off export needs, so the
// entry survives a root change and a later search that no longer finds the file.
type bufferEntry struct {
	id          string // identity: the symlink-free absolute path, see fileID
	Abs         string // absolute path, in the spelling of the search that found it first
	Title       string
	Type        string
	Bundle      string
	Tags        []string
	Description string
	Snippet     string // the preview shows these four as the search that found the hit did
	Provenance  string
	Tier        string
	Stale       bool
	Note        string // free text, empty for none
}

// fileID is the identity of a concept file (SPEC D5): its absolute path with symlinks resolved and
// cleaned, so one file reached through a symlinked or differently spelled root is one entry. A
// path that cannot be resolved (file gone) keeps its cleaned spelling.
func fileID(abs string) string {
	if real, err := filepath.EvalSymlinks(abs); err == nil {
		return filepath.Clean(real)
	}
	return filepath.Clean(abs)
}

// entryOf snapshots hit h.
func entryOf(h find.Hit) bufferEntry {
	return bufferEntry{
		id: fileID(h.Abs), Abs: h.Abs, Title: h.Title, Type: h.Type, Bundle: h.Bundle,
		Tags: slices.Clone(h.Tags), Description: h.Description,
		Snippet: h.Snippet, Provenance: h.Provenance, Tier: h.Tier, Stale: h.Stale,
	}
}

// hit is the snapshot as the hit the preview pane draws.
func (e bufferEntry) hit() find.Hit {
	return find.Hit{
		Abs: e.Abs, Title: e.Title, Type: e.Type, Bundle: e.Bundle, Tags: e.Tags,
		Description: e.Description, Snippet: e.Snippet, Provenance: e.Provenance, Tier: e.Tier, Stale: e.Stale,
	}
}

// buffer is the session buffer: entries in the order they were added. Bubble Tea copies the model
// on every message, so every change clones the slice and earlier copies keep theirs.
type buffer struct{ entries []bufferEntry }

// Entries are the buffered entries in insertion order. The hand-off export renders from them.
func (b buffer) Entries() []bufferEntry { return slices.Clone(b.entries) }

func (b buffer) index(id string) int {
	return slices.IndexFunc(b.entries, func(e bufferEntry) bool { return e.id == id })
}

func (b buffer) has(id string) bool { return b.index(id) >= 0 }

// toggle adds e at the end, or removes the entry of the same file.
func (b buffer) toggle(e bufferEntry) buffer {
	if i := b.index(e.id); i >= 0 {
		return b.remove(i)
	}
	return buffer{entries: append(slices.Clone(b.entries), e)}
}

// remove drops entry i.
func (b buffer) remove(i int) buffer {
	return buffer{entries: slices.Delete(slices.Clone(b.entries), i, i+1)}
}

// setNote gives the file of e the note: a not yet buffered file is added with it when the note is
// not empty. An empty note clears the note of a buffered entry and keeps the entry.
func (b buffer) setNote(e bufferEntry, note string) buffer {
	note = strings.TrimSpace(note)
	i := b.index(e.id)
	if i < 0 {
		if note == "" {
			return b
		}
		e.Note = note
		return buffer{entries: append(slices.Clone(b.entries), e)}
	}
	entries := slices.Clone(b.entries)
	entries[i].Note = note
	return buffer{entries: entries}
}

// refresh replaces the snapshot of the buffered file of e by e's fields, keeping its note and its
// place; an unbuffered file changes nothing.
func (b buffer) refresh(e bufferEntry) buffer {
	i := b.index(e.id)
	if i < 0 {
		return b
	}
	entries := slices.Clone(b.entries)
	e.Note, e.Abs = entries[i].Note, entries[i].Abs
	entries[i] = e
	return buffer{entries: entries}
}

// hitIDs are the identities of hits, in order.
func hitIDs(hits []find.Hit) []string {
	ids := make([]string, len(hits))
	for i, h := range hits {
		ids[i] = fileID(h.Abs)
	}
	return ids
}

// buffered reports whether hit i of the list is in the buffer.
func (m model) buffered(i int) bool { return i < len(m.search.ids) && m.buf.has(m.search.ids[i]) }
