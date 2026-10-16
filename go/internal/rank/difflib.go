package rank

import (
	"cmp"
	"slices"
	"strings"
)

// matcher is difflib.SequenceMatcher(isjunk=None, autojunk=True) as get_close_matches drives it:
// b is the word (set_seq2, indexed once), a is the candidate (set_seq1, replaced per candidate).
// Both are sequences of code points. There is no junk predicate, so the junk-extension loops of
// find_longest_match cannot fire and are left out.
type matcher struct {
	a, b       []rune
	b2j        map[rune][]int // ascending positions in b of each element that is not popular
	fullbcount map[rune]int   // occurrences of each element in the whole of b
	avail      map[rune]int   // quickRatio scratch
	prev, cur  []span         // longestMatch scratch
	stack      [][4]int       // matchingSize scratch
}

// span is one entry of find_longest_match's j2len dict: a match of length k ends at b[j].
type span struct{ j, k int }

// newMatcher is SequenceMatcher.set_seq2(word) with __chain_b: it indexes the positions of each
// element and, for a word of 200 or more elements, drops the elements that occur more than
// n//100+1 times from the index (autojunk's "popular" elements).
func newMatcher(word string) *matcher {
	m := &matcher{
		b:          []rune(word),
		b2j:        map[rune][]int{},
		fullbcount: map[rune]int{},
		avail:      map[rune]int{},
	}
	for i, r := range m.b {
		m.b2j[r] = append(m.b2j[r], i)
		m.fullbcount[r]++
	}
	if n := len(m.b); n >= 200 {
		ntest := n/100 + 1
		for r, idxs := range m.b2j {
			if len(idxs) > ntest {
				delete(m.b2j, r)
			}
		}
	}
	return m
}

// setA is set_seq1.
func (m *matcher) setA(x string) {
	m.a = m.a[:0]
	for _, r := range x {
		m.a = append(m.a, r)
	}
}

// calculateRatio is difflib._calculate_ratio.
func calculateRatio(matches, length int) float64 {
	if length == 0 {
		return 1.0
	}
	return 2.0 * float64(matches) / float64(length)
}

// realQuickRatio is SequenceMatcher.real_quick_ratio.
func (m *matcher) realQuickRatio() float64 {
	return calculateRatio(min(len(m.a), len(m.b)), len(m.a)+len(m.b))
}

// quickRatio is SequenceMatcher.quick_ratio: the multiset intersection of a and b, an upper bound
// of ratio.
func (m *matcher) quickRatio() float64 {
	clear(m.avail)
	matches := 0
	for _, r := range m.a {
		numb, ok := m.avail[r]
		if !ok {
			numb = m.fullbcount[r]
		}
		m.avail[r] = numb - 1
		if numb > 0 {
			matches++
		}
	}
	return calculateRatio(matches, len(m.a)+len(m.b))
}

// ratio is SequenceMatcher.ratio.
func (m *matcher) ratio() float64 {
	return calculateRatio(m.matchingSize(), len(m.a)+len(m.b))
}

// matchingSize is the sum of the sizes of get_matching_blocks: the longest match of the whole,
// then, in the same stack order, of the regions left of it and right of it. Sorting the blocks and
// merging adjacent ones, the rest of get_matching_blocks, leaves the sum as it is.
func (m *matcher) matchingSize() int {
	total := 0
	m.stack = append(m.stack[:0], [4]int{0, len(m.a), 0, len(m.b)})
	for len(m.stack) > 0 {
		r := m.stack[len(m.stack)-1]
		m.stack = m.stack[:len(m.stack)-1]
		alo, ahi, blo, bhi := r[0], r[1], r[2], r[3]
		i, j, k := m.longestMatch(alo, ahi, blo, bhi)
		if k == 0 {
			continue
		}
		total += k
		if alo < i && blo < j {
			m.stack = append(m.stack, [4]int{alo, i, blo, j})
		}
		if i+k < ahi && j+k < bhi {
			m.stack = append(m.stack, [4]int{i + k, ahi, j + k, bhi})
		}
	}
	return total
}

// longestMatch is SequenceMatcher.find_longest_match(alo, ahi, blo, bhi): the longest block
// a[i:i+k] == b[j:j+k] inside the two ranges, the one starting first in a and, among those, first
// in b. A popular element is not in b2j, so the block found through b2j is then extended over
// equal elements on both sides.
func (m *matcher) longestMatch(alo, ahi, blo, bhi int) (besti, bestj, bestsize int) {
	a, b := m.a, m.b
	besti, bestj = alo, blo
	// prev holds the j2len of the last row: the blocks ending with a[i-1], ascending by j, so the
	// lookup of j-1 is a forward scan.
	prev, cur := m.prev[:0], m.cur[:0]
	for i := alo; i < ahi; i++ {
		cur = cur[:0]
		p := 0
		for _, j := range m.b2j[a[i]] {
			if j < blo {
				continue
			}
			if j >= bhi {
				break
			}
			for p < len(prev) && prev[p].j < j-1 {
				p++
			}
			k := 1
			if p < len(prev) && prev[p].j == j-1 {
				k = prev[p].k + 1
			}
			cur = append(cur, span{j, k})
			if k > bestsize {
				besti, bestj, bestsize = i-k+1, j-k+1, k
			}
		}
		prev, cur = cur, prev
	}
	m.prev, m.cur = prev, cur
	for besti > alo && bestj > blo && a[besti-1] == b[bestj-1] {
		besti, bestj, bestsize = besti-1, bestj-1, bestsize+1
	}
	for besti+bestsize < ahi && bestj+bestsize < bhi && a[besti+bestsize] == b[bestj+bestsize] {
		bestsize++
	}
	return besti, bestj, bestsize
}

// CloseMatches is difflib.get_close_matches(word, possibilities, n, cutoff): the at most n
// possibilities whose similarity to word is at least cutoff, most similar first, equal
// similarities in descending string order. Python raises ValueError for n <= 0; here that is an
// empty result.
func CloseMatches(word string, possibilities []string, n int, cutoff float64) []string {
	type match struct {
		ratio float64
		x     string
	}
	out := []string{}
	if n <= 0 {
		return out
	}
	m := newMatcher(word)
	var found []match
	for _, x := range possibilities {
		m.setA(x)
		if m.realQuickRatio() >= cutoff && m.quickRatio() >= cutoff {
			if r := m.ratio(); r >= cutoff {
				found = append(found, match{r, x})
			}
		}
	}
	slices.SortFunc(found, func(p, q match) int {
		if c := cmp.Compare(q.ratio, p.ratio); c != 0 {
			return c
		}
		return strings.Compare(q.x, p.x)
	})
	for _, f := range Cut(found, n) {
		out = append(out, f.x)
	}
	return out
}

// zeroHitCutoff is the similarity cutoff of find._zero_hit_suggestions.
const zeroHitCutoff = 0.7

// ZeroHitSuggestions is find._zero_hit_suggestions after the tags are loaded: the registered tags
// closest to each query term in turn, each tag once, cut to limit. tags arrive sorted and terms
// are the tokenised query. The result is empty, never nil, when there is nothing to suggest.
func ZeroHitSuggestions(terms, tags []string, limit int) []string {
	out := []string{}
	if len(tags) == 0 {
		return out
	}
	for _, term := range terms {
		for _, cand := range CloseMatches(term, tags, limit, zeroHitCutoff) {
			if !slices.Contains(out, cand) {
				out = append(out, cand)
			}
		}
	}
	return Cut(out, limit)
}
