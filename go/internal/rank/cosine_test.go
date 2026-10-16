package rank_test

import (
	"fmt"
	"math"
	"slices"
	"testing"

	"nas/volume1/data/git/okf-tools/go/internal/rank"
)

func TestCosine(t *testing.T) {
	// Python reference: okf.semantic._cosine(q, v) under Python 3.14, whose sum() of floats is
	// Neumaier-compensated; the float32 elements of v are the stored embeddings widened to float
	// (struct.unpack("<f")). Compared bit for bit. A comment names the result of a naive running
	// sum where it differs: the compensation is what these cases pin.
	for _, c := range []struct {
		name string
		q    []float64
		v    []float32
		want float64
	}{
		{
			name: "known vectors",
			q:    []float64{1.0, 2.0, 3.0},
			v:    []float32{4, 5, 6},
			want: 0.9746318461970762,
		},
		{
			name: "same direction",
			q:    []float64{1.0, 2.0, 3.0},
			v:    []float32{2, 4, 6},
			want: 1.0,
		},
		{
			name: "orthogonal",
			q:    []float64{1.0, 0.0},
			v:    []float32{0, 1},
			want: 0.0,
		},
		{
			name: "opposite",
			q:    []float64{1.0, 2.0},
			v:    []float32{-1, -2},
			want: -0.9999999999999998,
		},
		{
			name: "zero query",
			q:    []float64{0.0, 0.0, 0.0},
			v:    []float32{1, 2, 3},
			want: 0.0,
		},
		{
			name: "zero vector",
			q:    []float64{1.0, 2.0, 3.0},
			v:    []float32{0, 0, 0},
			want: 0.0,
		},
		{
			name: "both empty",
			q:    []float64{},
			v:    []float32{},
			want: 0.0,
		},
		{
			name: "empty query",
			q:    []float64{},
			v:    []float32{1, 2},
			want: 0.0,
		},
		{
			name: "empty vector",
			q:    []float64{1.0, 2.0},
			v:    []float32{},
			want: 0.0,
		},
		{
			name: "query longer: the dot is cut, the norms stay whole",
			q:    []float64{1.0, 2.0, 3.0},
			v:    []float32{4, 5},
			want: 0.5843487097907776,
		},
		{
			name: "vector longer: the dot is cut, the norms stay whole",
			q:    []float64{1.0, 2.0},
			v:    []float32{4, 5, 6},
			want: 0.7135060680126757,
		},
		{
			name: "float32 elements widen exactly",
			q:    []float64{0.5, -0.25, 0.125},
			v:    []float32{0.1, 0.2, 0.3},
			want: 0.17496355460782226,
		},
		{
			name: "compensated sum differs from the naive one in the last bit",
			q:    []float64{-0.62, -0.516, -0.94},
			v:    []float32{-0.072, -0.119, 0.685},
			want: -0.6212318380064081, // naive sum: -0.6212318380064082
		},
		{
			name: "compensation when a term is larger than the running sum",
			q:    []float64{-0.67, 0.38, 0.27},
			v:    []float32{-0.042, -0.568, 0.585},
			want: -0.044642443850480176, // naive sum: -0.04464244385048017
		},
		{
			name: "sixteen dimensions, compensated sum differs from the naive one",
			q:    []float64{0.246, 0.484, 0.59, 0.885, 0.48, 0.845, -0.942, -0.069, 0.887, 0.298, 0.802, -0.774, -0.062, -0.507, 0.088, 0.148},
			v:    []float32{-0.974, -0.567, -0.441, 0.833, 0.531, -0.681, 0.594, -0.722, 0.235, -0.747, -0.996, 0.743, -0.581, -0.569, 0.965, 0.745},
			want: -0.2563544119057762, // naive sum: -0.2563544119057763
		},
	} {
		t.Run(c.name, func(t *testing.T) {
			got := rank.Cosine(c.q, c.v)
			if math.Float64bits(got) != math.Float64bits(c.want) {
				t.Errorf("Cosine = %v, want %v", got, c.want)
			}
		})
	}
}

func TestRankCosine(t *testing.T) {
	// Python reference: okf.semantic.semantic_ranking(root, query, limit, None) with the concept
	// vectors and the query vector stubbed, limit large: sorted by (-cosine, path), nothing cut.
	for _, c := range []struct {
		name string
		q    []float64
		vecs []rank.PathVec
		want []rank.Scored
	}{
		{
			name: "descending cosine",
			q:    []float64{1.0, 0.5, -0.25},
			vecs: []rank.PathVec{
				{Path: "kb/c", Vec: []float32{0.5, 0.5, 0.5}},
				{Path: "kb/a", Vec: []float32{1, 0.5, -0.25}},
				{Path: "kb/d", Vec: []float32{-1, 0, 0}},
				{Path: "kb/b", Vec: []float32{0, 1, 0}},
				{Path: "kb/e", Vec: []float32{0, 0, 0}},
				{Path: "kb/f", Vec: []float32{0.9, 0.5, -0.3}},
			},
			want: []rank.Scored{
				{Cosine: 1.0, Path: "kb/a"},
				{Cosine: 0.9970972347801251, Path: "kb/f"},
				{Cosine: 0.629940788348712, Path: "kb/c"},
				{Cosine: 0.4364357804719848, Path: "kb/b"},
				{Cosine: 0.0, Path: "kb/e"},
				{Cosine: -0.8728715609439696, Path: "kb/d"},
			},
		},
		{
			name: "equal cosines are ordered by path, zero vectors too",
			q:    []float64{1.0, 0.5, -0.25},
			vecs: []rank.PathVec{
				{Path: "kb/z", Vec: []float32{1, 0.5, -0.25}},
				{Path: "kb/m", Vec: []float32{1, 0.5, -0.25}},
				{Path: "kb/y0", Vec: []float32{0, 0, 0}},
				{Path: "kb/a", Vec: []float32{1, 0.5, -0.25}},
				{Path: "kb/b0", Vec: []float32{0, 0, 0}},
				{Path: "kb/n", Vec: []float32{2, 1, -0.5}},
			},
			want: []rank.Scored{
				{Cosine: 1.0, Path: "kb/a"},
				{Cosine: 1.0, Path: "kb/m"},
				{Cosine: 1.0, Path: "kb/n"},
				{Cosine: 1.0, Path: "kb/z"},
				{Cosine: 0.0, Path: "kb/b0"},
				{Cosine: 0.0, Path: "kb/y0"},
			},
		},
		{
			name: "paths compare by code point",
			q:    []float64{1.0, 0.5, -0.25},
			vecs: []rank.PathVec{
				{Path: "kb/😀a", Vec: []float32{1, 0.5, -0.25}},
				{Path: "kb/～a", Vec: []float32{1, 0.5, -0.25}},
				{Path: "kb/é", Vec: []float32{1, 0.5, -0.25}},
				{Path: "kb/z", Vec: []float32{1, 0.5, -0.25}},
				{Path: "kb/a", Vec: []float32{1, 0.5, -0.25}},
			},
			want: []rank.Scored{
				{Cosine: 1.0, Path: "kb/a"},
				{Cosine: 1.0, Path: "kb/z"},
				{Cosine: 1.0, Path: "kb/é"},
				{Cosine: 1.0, Path: "kb/～a"},
				{Cosine: 1.0, Path: "kb/😀a"},
			},
		},
		{
			name: "no vectors",
			q:    []float64{1.0, 0.5, -0.25},
			vecs: []rank.PathVec{},
			want: []rank.Scored{},
		},
	} {
		t.Run(c.name, func(t *testing.T) {
			if got := rank.RankCosine(c.q, c.vecs); !slices.Equal(got, c.want) {
				t.Errorf("RankCosine = %v, want %v", got, c.want)
			}
		})
	}
}

func TestNearestTags(t *testing.T) {
	// Python reference: okf.semantic._expand_query_tags(root, query, top_k, floor) with the tag
	// vectors and the query vector stubbed. Equal cosines keep the order of the vectors: "zeta"
	// and "beta" tie and stay in the order given, not in tag order.
	q := []float64{1, 0, 0}
	vecs := []rank.TagVec{
		{Tag: "gamma", Vec: []float32{0, 1, 0}},
		{Tag: "zeta", Vec: []float32{1, 1, 0}},
		{Tag: "beta", Vec: []float32{1, 1, 0}},
		{Tag: "alpha", Vec: []float32{1, 0, 0}},
		{Tag: "delta", Vec: []float32{2, 0.1, 0}},
		{Tag: "eps", Vec: []float32{-1, 0, 0}},
	}
	for _, c := range []struct {
		name  string
		topK  int
		floor float64
		want  []string
	}{
		{"top 3 above 0.6; the tie keeps the input order", 3, 0.6, []string{"alpha", "delta", "zeta"}},
		{"top 4 above 0.6", 4, 0.6, []string{"alpha", "delta", "zeta", "beta"}},
		{"floor drops tags inside the top 5", 5, 0.9, []string{"alpha", "delta"}},
		{"top 2 with floor 0", 2, 0.0, []string{"alpha", "delta"}},
		{"floor equal to a cosine keeps it", 4, 0.7071067811865475, []string{"alpha", "delta", "zeta", "beta"}},
		{"floor just above a cosine drops it", 4, 0.7071067811865476, []string{"alpha", "delta"}},
		{"floor above every cosine", 3, 1.1, []string{}},
		{"top 0", 0, 0.0, []string{}},
		{"everything, ranked", 10, -2.0, []string{"alpha", "delta", "zeta", "beta", "gamma", "eps"}},
	} {
		t.Run(c.name, func(t *testing.T) {
			got := rank.NearestTags(q, vecs, c.topK, c.floor)
			if got == nil || !slices.Equal(got, c.want) {
				t.Errorf("NearestTags(top %d, floor %v) = %q, want %q", c.topK, c.floor, got, c.want)
			}
		})
	}
}

// Thirty tags in three groups of equal cosine: the order inside a group is the order of the
// vectors, which an unstable sort or a tag tiebreak would change.
func TestNearestTagsKeepsTies(t *testing.T) {
	// Python reference: okf.semantic._expand_query_tags(root, query, 30, -2.0) with the query
	// vector [1, 0, 0] and the vector of tag "t%02d" % i the direction i % 3 of
	// [1, 0, 0], [1, 1, 0], [0, 1, 0].
	want := []string{
		"t00", "t03", "t06", "t09", "t12", "t15", "t18", "t21", "t24", "t27", "t01", "t04", "t07",
		"t10", "t13", "t16", "t19", "t22", "t25", "t28", "t02", "t05", "t08", "t11", "t14", "t17",
		"t20", "t23", "t26", "t29",
	}
	directions := [][]float32{{1, 0, 0}, {1, 1, 0}, {0, 1, 0}}
	var vecs []rank.TagVec
	for i := range 30 {
		vecs = append(vecs, rank.TagVec{Tag: fmt.Sprintf("t%02d", i), Vec: directions[i%3]})
	}
	if got := rank.NearestTags([]float64{1, 0, 0}, vecs, 30, -2); !slices.Equal(got, want) {
		t.Errorf("NearestTags = %q, want %q", got, want)
	}
}
