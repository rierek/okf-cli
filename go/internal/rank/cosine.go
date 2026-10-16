package rank

import (
	"cmp"
	"math"
	"slices"
	"strings"
)

// neumaier is CPython's float sum() since 3.12: Neumaier's compensated summation (the float fast
// path of builtin_sum_impl). The first item is added exactly because the running sum starts at 0.
// The summands must be rounded floats: callers pass float64(x * y), the explicit conversion keeping
// the compiler from fusing the product into the addition, which would round differently from
// Python (the Go compiler does fuse it on arm64).
type neumaier struct{ sum, comp float64 }

func (n *neumaier) add(x float64) {
	t := n.sum + x
	if math.Abs(n.sum) >= math.Abs(x) {
		n.comp += (n.sum - t) + x
	} else {
		n.comp += (x - t) + n.sum
	}
	n.sum = t
}

// total is the sum with its compensation, left out when it is zero or not finite.
func (n *neumaier) total() float64 {
	if n.comp != 0 && !math.IsInf(n.comp, 0) && !math.IsNaN(n.comp) {
		return n.sum + n.comp
	}
	return n.sum
}

// norm is math.sqrt(sum(x * x for x in q)).
func norm(q []float64) float64 {
	var sq neumaier
	for _, x := range q {
		sq.add(float64(x * x))
	}
	return math.Sqrt(sq.total())
}

// Cosine is semantic._cosine(q, v): the dot product of the pairs both vectors have (the longer
// one is cut to the shorter, like zip), divided by the norms of the whole vectors; 0 when either
// norm is 0. The float32 elements of v widen exactly.
func Cosine(q []float64, v []float32) float64 {
	return cosine(q, norm(q), v)
}

// cosine is Cosine with the norm of q given, so a ranking computes it once.
func cosine(q []float64, na float64, v []float32) float64 {
	var dot, sq neumaier
	n := min(len(q), len(v))
	for i := range n {
		y := float64(v[i])
		dot.add(float64(q[i] * y))
		sq.add(float64(y * y))
	}
	for _, f := range v[n:] {
		y := float64(f)
		sq.add(float64(y * y))
	}
	nb := math.Sqrt(sq.total())
	if na == 0.0 || nb == 0.0 {
		return 0.0
	}
	return dot.total() / (na * nb)
}

// Scored is one entry of the semantic ranking: a concept path with its cosine.
type Scored struct {
	Cosine float64
	Path   string
}

// PathVec is a concept's stored embedding.
type PathVec struct {
	Path string
	Vec  []float32
}

// RankCosine is `sorted(((_cosine(q, vec), path) ...), key=lambda x: (-x[0], x[1]))`: every
// vector scored and ordered by descending cosine, equal cosines by path (code point order).
func RankCosine(q []float64, vecs []PathVec) []Scored {
	na := norm(q)
	out := make([]Scored, len(vecs))
	for i, pv := range vecs {
		out[i] = Scored{Cosine: cosine(q, na, pv.Vec), Path: pv.Path}
	}
	slices.SortStableFunc(out, func(a, b Scored) int {
		if c := cmp.Compare(b.Cosine, a.Cosine); c != 0 {
			return c
		}
		return strings.Compare(a.Path, b.Path)
	})
	return out
}

// TagVec is a tag's stored embedding.
type TagVec struct {
	Tag string
	Vec []float32
}

// NearestTags is the ranking half of semantic._expand_query_tags: the topK tags closest to q by
// cosine, equal cosines keeping the order of vecs, of which those scoring at least floor remain.
func NearestTags(q []float64, vecs []TagVec, topK int, floor float64) []string {
	type scored struct {
		cosine float64
		tag    string
	}
	na := norm(q)
	ranked := make([]scored, len(vecs))
	for i, tv := range vecs {
		ranked[i] = scored{cosine: cosine(q, na, tv.Vec), tag: tv.Tag}
	}
	slices.SortStableFunc(ranked, func(a, b scored) int { return cmp.Compare(b.cosine, a.cosine) })
	out := []string{}
	for _, r := range Cut(ranked, topK) {
		if r.cosine >= floor {
			out = append(out, r.tag)
		}
	}
	return out
}
