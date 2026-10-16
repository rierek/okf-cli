// Command corpus is the corpus driver of the frontmatter writer (work package C, R-03): it walks a
// corpus of concept files like docs/topics/okf-go-port/spike/main.go, applies every spike op to
// each file through the production edit set (yamlpatch.SpikeOp) and writes the layout that
// spike/ref.py measures:
//
//	<out>/surgical/<op>/<rel>   the new text of each op that applied
//	<out>/../status.json        {rel: {"surgical": {"parse": ..., "ops": {op: status}}}}
//
// Run it from the module root: go run ./internal/yamlpatch/corpus -corpus <WORK>/corpus -out <WORK>/out.
// It is not an okf command and is not part of the binary.
package main

import (
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/frontmatter"
	"nas/volume1/data/git/okf-tools/go/internal/yamlpatch"
)

// strategy is the name ref.py knows the writer by.
const strategy = "surgical"

type fileStatus struct {
	Parse string            `json:"parse"`
	Ops   map[string]string `json:"ops"`
}

func main() {
	corpus := flag.String("corpus", "", "corpus directory (WORK/corpus)")
	out := flag.String("out", "", "output directory (WORK/out)")
	flag.Parse()
	if *corpus == "" || *out == "" {
		fmt.Fprintln(os.Stderr, "usage: corpus -corpus DIR -out DIR")
		os.Exit(2)
	}
	if err := run(*corpus, filepath.Clean(*out)); err != nil {
		fmt.Fprintln(os.Stderr, "corpus:", err)
		os.Exit(1)
	}
}

func run(corpus, out string) error {
	if err := os.RemoveAll(out); err != nil {
		return err
	}
	status := map[string]map[string]*fileStatus{}
	n := 0
	err := filepath.WalkDir(corpus, func(path string, d fs.DirEntry, err error) error {
		if err != nil || d.IsDir() || !strings.HasSuffix(path, ".md") {
			return err
		}
		rel, _ := filepath.Rel(corpus, path)
		rel = filepath.ToSlash(rel)
		raw, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		text := string(raw)
		doc := frontmatter.Read(text)
		if doc.Head == "" {
			return fmt.Errorf("%s: corpus file without a frontmatter block", rel)
		}
		n++
		st := &fileStatus{Parse: "ok", Ops: map[string]string{}}
		if doc.Err != "" {
			st.Parse = "error: " + oneLine(doc.Err)
		}
		status[rel] = map[string]*fileStatus{strategy: st}
		for _, op := range yamlpatch.SpikeOps {
			next, err := safeSpikeOp(op, text)
			st.Ops[op] = statusOf(err)
			if err != nil {
				continue
			}
			dst := filepath.Join(out, strategy, op, filepath.FromSlash(rel))
			if err := os.MkdirAll(filepath.Dir(dst), 0o755); err != nil {
				return err
			}
			if err := os.WriteFile(dst, []byte(next), 0o644); err != nil {
				return err
			}
		}
		return nil
	})
	if err != nil {
		return err
	}
	b, err := json.Marshal(status)
	if err != nil {
		return err
	}
	if err := os.WriteFile(filepath.Join(filepath.Dir(out), "status.json"), b, 0o644); err != nil {
		return err
	}
	fmt.Printf("corpus: %d files x %d ops\n", n, len(yamlpatch.SpikeOps))
	return nil
}

// safeSpikeOp turns a panic into an error of the file: the run goes on and the file counts as failed.
func safeSpikeOp(op, text string) (next string, err error) {
	defer func() {
		if r := recover(); r != nil {
			err = fmt.Errorf("panic: %v", r)
		}
	}()
	return yamlpatch.SpikeOp(op, text)
}

// statusOf maps the result of a spike op to the status string ref.py reads: ok, na,
// `declined: <reason>`, `error: parse: <reason>`, `error: <reason>`.
func statusOf(err error) string {
	var rej *yamlpatch.Rejection
	var parse *yamlpatch.ParseError
	switch {
	case err == nil:
		return "ok"
	case errors.Is(err, yamlpatch.ErrNotApplicable):
		return "na"
	case errors.As(err, &rej):
		return "declined: " + oneLine(rej.Reason)
	case errors.As(err, &parse):
		return "error: parse: " + oneLine(parse.Reason)
	}
	return "error: " + oneLine(err.Error())
}

func oneLine(s string) string { return strings.Join(strings.Fields(s), " ") }
