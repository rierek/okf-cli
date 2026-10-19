package tagwrite

import (
	"context"
	"os/exec"
	"sort"
	"strings"
	"time"

	"nas/volume1/data/git/okf-tools/go/internal/pytext"
	"nas/volume1/data/git/okf-tools/go/internal/rank"
)

// fuzzyMatches is Python fuzzy_matches: the candidates that match query, merging two signals so
// both typo/subsequence matches (fzf --filter) and abbreviation/reordering matches (difflib
// ratio, e.g. `km-management` for `knowledge-management`) surface. The fzf hits come first, in
// fzf's order, then the difflib hits best ratio first; each candidate once; cut to limit as the
// Python slice merged[:limit] does.
func fuzzyMatches(query string, candidates []string, limit int) []string {
	if len(candidates) == 0 {
		return nil
	}
	fzfHits := fzfFilter(query, candidates)

	ql := pytext.Lower(query)
	type scored struct {
		ratio float64
		tag   string
	}
	all := make([]scored, len(candidates))
	for i, c := range candidates {
		cl := pytext.Lower(c)
		ratio := seqRatio(ql, cl)
		if strings.Contains(cl, ql) || strings.Contains(ql, cl) {
			ratio += 0.3
		}
		all[i] = scored{ratio, c}
	}
	sort.SliceStable(all, func(i, j int) bool { return all[i].ratio > all[j].ratio })

	seen := map[string]bool{}
	var merged []string
	add := func(c string) {
		if !seen[c] {
			seen[c] = true
			merged = append(merged, c)
		}
	}
	for _, c := range fzfHits {
		add(c)
	}
	for _, s := range all {
		if s.ratio > 0.5 {
			add(s.tag)
		}
	}
	return rank.Cut(merged, limit)
}

// fzfFilter is the external arm: the lines `fzf --filter query` keeps from candidates, one per line.
// fzf missing, failing to start or running past 5 seconds gives no hits and no error, as in Python
// (FileNotFoundError and SubprocessError are swallowed); an exit status of fzf (1: no match) does
// not discard its output.
func fzfFilter(query string, candidates []string) []string {
	path, err := exec.LookPath("fzf")
	if err != nil {
		return nil
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, path, "--filter", query)
	cmd.Stdin = strings.NewReader(strings.Join(candidates, "\n"))
	out, err := cmd.Output()
	if ctx.Err() != nil {
		return nil
	}
	if _, exited := err.(*exec.ExitError); err != nil && !exited {
		return nil
	}
	var hits []string
	for _, line := range pytext.SplitLines(string(out), false) {
		if pytext.Strip(line) != "" {
			hits = append(hits, line)
		}
	}
	return hits
}

// seqRatio is difflib.SequenceMatcher(None, a, b).ratio() over code points, autojunk on: twice
// the size of the matching blocks over the length of both strings. The unexported matcher of
// package rank fixes one side to the query word of get_close_matches; here a is the query and b
// the candidate, which decides ties, so the matcher is written out.
func seqRatio(a, b string) float64 {
	ar, br := []rune(a), []rune(b)
	total := len(ar) + len(br)
	if total == 0 {
		return 1.0
	}
	m := seqMatcher{a: ar, b: br, b2j: map[rune][]int{}}
	for j, r := range br {
		m.b2j[r] = append(m.b2j[r], j)
	}
	if n := len(br); n >= 200 {
		popular := n/100 + 1
		for r, idxs := range m.b2j {
			if len(idxs) > popular {
				delete(m.b2j, r)
			}
		}
	}
	return 2.0 * float64(m.matches()) / float64(total)
}

type seqMatcher struct {
	a, b []rune
	b2j  map[rune][]int
}

// matches is the sum of the sizes of the matching blocks (get_matching_blocks), found by taking
// the longest block of a range and splitting around it.
func (m *seqMatcher) matches() int {
	type span struct{ alo, ahi, blo, bhi int }
	queue := []span{{0, len(m.a), 0, len(m.b)}}
	sum := 0
	for len(queue) > 0 {
		s := queue[len(queue)-1]
		queue = queue[:len(queue)-1]
		i, j, k := m.longest(s.alo, s.ahi, s.blo, s.bhi)
		if k == 0 {
			continue
		}
		sum += k
		if s.alo < i && s.blo < j {
			queue = append(queue, span{s.alo, i, s.blo, j})
		}
		if i+k < s.ahi && j+k < s.bhi {
			queue = append(queue, span{i + k, s.ahi, j + k, s.bhi})
		}
	}
	return sum
}

// longest is find_longest_match for a matcher without junk: the earliest longest block of
// a[alo:ahi] and b[blo:bhi], then extended over equal neighbours (popular elements included).
func (m *seqMatcher) longest(alo, ahi, blo, bhi int) (besti, bestj, bestsize int) {
	besti, bestj = alo, blo
	j2len := map[int]int{}
	for i := alo; i < ahi; i++ {
		newj2len := map[int]int{}
		for _, j := range m.b2j[m.a[i]] {
			if j < blo {
				continue
			}
			if j >= bhi {
				break
			}
			k := j2len[j-1] + 1
			newj2len[j] = k
			if k > bestsize {
				besti, bestj, bestsize = i-k+1, j-k+1, k
			}
		}
		j2len = newj2len
	}
	for besti > alo && bestj > blo && m.a[besti-1] == m.b[bestj-1] {
		besti, bestj, bestsize = besti-1, bestj-1, bestsize+1
	}
	for besti+bestsize < ahi && bestj+bestsize < bhi && m.a[besti+bestsize] == m.b[bestj+bestsize] {
		bestsize++
	}
	return besti, bestj, bestsize
}
