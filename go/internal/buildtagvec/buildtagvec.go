// Package buildtagvec is the hidden `build-tagvec` command, the offline producer of
// `<root>/.tagvec/tag_vectors.sqlite` (Python cli/embeddings/build_tagvec.py main). Without
// --produce it plans the missing (tag or concept, model) pairs and prints them: no network, no
// write. With --produce it embeds them batch by batch; a batch that cannot be embedded is
// skipped and reappears in the next plan.
package buildtagvec

import (
	"fmt"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/cli"
	"nas/volume1/data/git/okf-tools/go/internal/sqlstore"
	"nas/volume1/data/git/okf-tools/go/internal/stdio"
	"nas/volume1/data/git/okf-tools/go/internal/tagvec"
)

// Register attaches the `build-tagvec` command.
func Register(app *cli.App) {
	app.Attach("build-tagvec", cli.Spec{Args: []cli.Arg{
		{Flags: []string{"--output"},
			Help: "output sqlite path (default: <root>/.tagvec/tag_vectors.sqlite)"},
		{Flags: []string{"--model"}, Dest: "models", Choices: tagvec.ModelNames(), Action: cli.Append,
			Help: "model to (re)embed with; repeatable. Default: both models."},
		{Flags: []string{"--target"}, Choices: []string{"tags", "concepts", "both"}, Default: "tags",
			Help: "what to embed: tags only (default, unchanged behavior), " +
				"concept titles+bodies only (P8/8c), or both."},
		{Flags: []string{"--concept-path-prefix"},
			Help: "only plan/produce concept embeddings for paths starting with " +
				"this prefix (e.g. 'bundle/' or 'bundle/_okfeval-') — scoping " +
				"for small, deterministic manual --produce runs."},
		{Flags: []string{"--concept-limit"}, Type: cli.Int,
			Help: "cap the number of concepts (re-)embedded per model, after " +
				"--concept-path-prefix filtering."},
		{Flags: []string{"--produce"}, Action: cli.StoreTrue,
			Help: "perform network embedding calls and write rows. Without this " +
				"flag: dry-run only (plan + print, no network, no writes)."},
	}, Handler: run})
}

// embedder is the embed call of each model.
var embedder = map[string]func([]string) ([][]float32, error){
	"bge-m3":         tagvec.EmbedBGEM3,
	"voyage-3-large": tagvec.EmbedVoyage,
}

// run is Python main().
func run(root string, a *cli.Args) (any, error) {
	output := a.String("output")
	if output == "" {
		output = sqlstore.TagvecPath(root)
	}
	models := a.Strings("models")
	if len(models) == 0 {
		models = tagvec.ModelNames()
	}
	produce := a.Bool("produce")
	target := a.String("target")
	doTags := target == "tags" || target == "both"
	doConcepts := target == "concepts" || target == "both"

	var tags []string
	if doTags {
		counts, err := catalogue.AllTags(root)
		if err != nil {
			return nil, err
		}
		for tag := range counts {
			tags = append(tags, tag)
		}
	}
	totalDelta := 0
	for _, model := range models {
		if doTags {
			delta, err := tagvec.PlanDelta(tags, model, output)
			if err != nil {
				return nil, err
			}
			totalDelta += len(delta)
			stdio.Printf("%s: %d tag(s) need embedding, %d already cached\n", model, len(delta), len(tags)-len(delta))
			if produce && len(delta) > 0 {
				err := embedAll(model, "tag", delta, func(batch []tagvec.Triple, vectors [][]float32) error {
					rows := make([]tagvec.TagRow, len(batch))
					for i, t := range batch {
						rows[i] = tagvec.TagRow{Key: t.Key, Tag: t.Item, Model: model, Dim: tagvec.Dim(model),
							Vec: tagvec.PackVec(vectors[i])}
					}
					return tagvec.WriteTagRows(output, rows)
				})
				if err != nil {
					return nil, err
				}
			}
		}
		if doConcepts {
			delta, err := tagvec.PlanConceptDelta(root, model, output, a.String("concept_path_prefix"), a.Int("concept_limit"))
			if err != nil {
				return nil, err
			}
			totalDelta += len(delta)
			stdio.Printf("%s: %d concept(s) need title+body embedding\n", model, len(delta))
			if produce && len(delta) > 0 {
				err := embedAll(model, "concept", delta, func(batch []tagvec.Triple, vectors [][]float32) error {
					rows := make([]tagvec.ConceptRow, len(batch))
					for i, t := range batch {
						rows[i] = tagvec.ConceptRow{Key: t.Key, Path: t.Item, Model: model, Dim: tagvec.Dim(model),
							Vec: tagvec.PackVec(vectors[i])}
					}
					return tagvec.WriteConceptRows(output, rows)
				})
				if err != nil {
					return nil, err
				}
			}
		}
	}
	if !produce && totalDelta > 0 {
		stdio.Println("(dry-run — no network calls, no writes. Re-run with --produce to embed.)")
	}
	return nil, nil
}

// embedAll is the produce loop of one model and one kind of row (noun is "tag" or "concept"): it
// embeds delta batch by batch and hands each embedded batch to write at once, so a later failure
// keeps what is done. A batch that cannot be embedded is skipped.
func embedAll(model, noun string, delta []tagvec.Triple, write func(batch []tagvec.Triple, vectors [][]float32) error) error {
	maxItems, maxChars := tagvec.BatchLimits(model)
	written := 0
	for _, batch := range tagvec.Batches(delta, maxItems, maxChars) {
		texts := make([]string, len(batch))
		for i, t := range batch {
			texts[i] = t.Text
		}
		label := fmt.Sprintf("%s %ss %s..", model, noun, batch[0].Item)
		vectors := tagvec.EmbedResilient(embedder[model], texts, label, stdio.Writer)
		if vectors == nil {
			continue
		}
		if err := write(batch, vectors); err != nil {
			return err
		}
		written += len(batch)
		stdio.Printf("%s: wrote %d/%d %s row(s)\n", model, written, len(delta), noun)
	}
	return nil
}
