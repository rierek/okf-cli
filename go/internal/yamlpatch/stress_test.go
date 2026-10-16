package yamlpatch_test

import (
	"errors"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"testing"

	"go.yaml.in/yaml/v3"

	"nas/volume1/data/git/okf-tools/go/internal/frontmatter"
	. "nas/volume1/data/git/okf-tools/go/internal/yamlpatch"
)

// The R-04 stress test over the 60 hand-written special cases of the spike (testdata/stress, copied
// from docs/topics/okf-go-port/spike/stress). Every outcome of op1, op2a, op2b, op3 and op4 is either a text
// that reads and differs from the input only inside the lines of the targeted key, or a rejection (the
// input is then untouched: Apply returns no text) or "not applicable".

var stressOps = []string{"op1", "op2a", "op2b", "op3", "op4"}

// mustReject are the pairs the leaf names (AC29); every file the reader refuses is rejected too.
var mustReject = map[string][]string{
	"48-flow-tags-inline-comment.md": {"op1"},
	"51-flow-mapping-root.md":        {"op1", "op2a", "op2b", "op3"},
	"54-description-anchor.md":       {"op2a"},
	"15-anchors-aliases.md":          {"op1"},
}

// wantOK pins how many of the 60 files each op writes. Without it a patcher that answered "not
// applicable" everywhere would pass.
var wantOK = map[string]int{"op1": 24, "op2a": 46, "op2b": 53, "op3": 51, "op4": 5}

func TestStressFiles(t *testing.T) {
	files, err := filepath.Glob("testdata/stress/*.md")
	if err != nil || len(files) != 60 {
		t.Fatalf("stress files: %d, %v; want 60", len(files), err)
	}
	ok := map[string]int{}
	for _, path := range files {
		name := filepath.Base(path)
		raw, err := os.ReadFile(path)
		if err != nil {
			t.Fatal(err)
		}
		text := string(raw)
		doc := frontmatter.Read(text)
		for _, op := range stressOps {
			got, err := SpikeOp(op, text)
			var rej *Rejection
			var parse *ParseError
			switch {
			case doc.Err != "":
				if !errors.As(err, &parse) || got != "" || parse.Reason != doc.Err {
					t.Errorf("%s %s: the reader refuses this file; got %q, %v", name, op, got, err)
				}
			case slices.Contains(mustReject[name], op):
				if !errors.As(err, &rej) || got != "" {
					t.Errorf("%s %s: want a rejection, got %q, %v", name, op, got, err)
				}
			case errors.Is(err, ErrNotApplicable):
			case errors.As(err, &rej):
				if got != "" {
					t.Errorf("%s %s: a rejection came with the text %q", name, op, got)
				}
				t.Errorf("%s %s: unexpected rejection: %v", name, op, rej)
			case err != nil:
				t.Errorf("%s %s: %v", name, op, err)
			default:
				ok[op]++
				checkConfined(t, name, op, text, got)
			}
		}
	}
	for _, op := range stressOps {
		if ok[op] != wantOK[op] {
			t.Errorf("%s wrote %d of the stress files, want %d", op, ok[op], wantOK[op])
		}
	}
}

// checkConfined: the new text reads, the text behind the frontmatter is the same, and the lines that
// differ lie inside the range of the key the op targets (the lines of the key up to the next key; for an
// op that adds a key: behind the last key). The range is cut from the node positions of the reader.
func checkConfined(t *testing.T, name, op, text, got string) {
	t.Helper()
	old, now := frontmatter.Read(text), frontmatter.Read(got)
	if now.Err != "" || now.Head == "" {
		t.Errorf("%s %s: the new text does not read: %q", name, op, now.Err)
		return
	}
	if now.Body != old.Body {
		t.Errorf("%s %s: the text behind the frontmatter changed", name, op)
	}
	lo, hiOld, _ := hunk(lines(text), lines(got))
	closing := strings.Count(old.Head, "\n") // the line of the closing delimiter
	type rng struct{ from, to int }
	keyRange := func(key string) (rng, bool) {
		c := old.Root.Content
		for i := 0; i+1 < len(c); i += 2 {
			if c[i].Value == key {
				to := closing
				if i+2 < len(c) {
					to = c[i+2].Line - 1
				}
				return rng{c[i].Line - 1, to}, true
			}
		}
		return rng{}, false
	}
	var allowed rng
	switch op {
	case "op1", "op2a", "op4":
		key := map[string]string{"op1": "tags", "op2a": "description", "op4": "timestamp"}[op]
		r, found := keyRange(key)
		if !found {
			t.Errorf("%s %s: the targeted key is missing", name, op)
			return
		}
		allowed = r
	default: // op2b, op3
		if r, found := keyRange("verified"); op == "op3" && found {
			allowed = r
			break
		}
		allowed = rng{closing, closing} // an added key goes in at the end of the block
		if n := len(old.Root.Content); n > 0 {
			allowed.from = old.Root.Content[n-2].Line // behind the key line of the last key
		}
		if old.Root.Style&yaml.FlowStyle != 0 {
			allowed = rng{1, closing} // `{}` turns into a block
		}
	}
	if lo < allowed.from || hiOld > allowed.to {
		t.Errorf("%s %s: the lines %d..%d changed, outside the key range %d..%d", name, op, lo, hiOld, allowed.from, allowed.to)
	}
}

func lines(s string) []string { return strings.SplitAfter(s, "\n") }

// hunk returns the changed region: old[lo:hiOld] became new[lo:hiNew], the lines around are identical.
func hunk(old, now []string) (lo, hiOld, hiNew int) {
	n := min(len(old), len(now))
	for lo < n && old[lo] == now[lo] {
		lo++
	}
	suffix := 0
	for suffix < n-lo && old[len(old)-1-suffix] == now[len(now)-1-suffix] {
		suffix++
	}
	return lo, len(old) - suffix, len(now) - suffix
}
