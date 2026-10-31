package semantic

import (
	"errors"
	"io"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/sqlstore"
	"nas/volume1/data/git/okf-tools/go/internal/tagvec"
)

// Facade of the semantic index for the TUI: the same coverage check and build as `prime
// --check-semantic` and `build-semantic-index`, called in process. Errors come back as values;
// nothing is noted on the envelope or printed.

// Coverage is the coverage check of `build-semantic-index --if-stale`: of the indexable concepts,
// how many have a current embedding. ok is false when the catalogue has no usable store.
func Coverage(root string) (cov tagvec.Coverage, ok bool, err error) {
	bundles, err := catalogue.ListIndexableBundles(root, "")
	if err != nil {
		return tagvec.Coverage{}, false, err
	}
	var paths []string
	for _, b := range bundles {
		for cid := range catalogue.IterConcepts(catalogue.Join(root, b), true) {
			paths = append(paths, b+"/"+cid)
		}
	}
	return tagvec.SemanticCoverage(root, paths)
}

// Pending is the number of concepts Refresh would embed now: those without a current vector.
func Pending(root string) (int, error) {
	delta, err := tagvec.PlanConceptDelta(root, tagvec.SemanticModel, sqlstore.TagvecPath(root), "", 0)
	return len(delta), err
}

// Refresh embeds every concept without a current vector with embed and stores the vectors. left
// counts planned concepts that stayed unembedded because a batch kept failing. A failure of the
// store or of the backend is returned with its Python class and message, as the command notes it.
func Refresh(root string, embed func([]string) ([][]float32, error), progress io.Writer) (written, left int, err error) {
	written, left, err = fill(root, sqlstore.TagvecPath(root), embed, progress)
	if err != nil {
		err = errors.New(failureText(err))
	}
	return written, left, err
}

// failureText is "Class: message" of a failed build: the SQLite class, the embedding exception,
// or "Error" for anything else.
func failureText(err error) string {
	class, message, ok := sqlstore.PyError(err)
	var exception *tagvec.Exception
	switch {
	case ok:
	case errors.As(err, &exception):
		class, message = exception.Class, exception.Message
	default:
		class, message = "Error", err.Error()
	}
	return class + ": " + message
}
