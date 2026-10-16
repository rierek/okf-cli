package diffs

import "slices"

// Opcode tags of difflib's get_opcodes.
const (
	tagEqual   = 'e'
	tagReplace = 'r'
	tagDelete  = 'd'
	tagInsert  = 'i'
)

// opcode is one (tag, i1, i2, j1, j2) tuple of difflib's get_opcodes: a[i1:i2] against b[j1:j2].
type opcode struct {
	tag            byte
	i1, i2, j1, j2 int
}

// match is difflib's Match(a, b, size): a[a:a+size] equals b[b:b+size].
type match struct{ a, b, size int }

// matcher is difflib.SequenceMatcher(None, a, b) with autojunk on, the only way unified_diff builds
// one. Only the popular lines of b (more than 1 + len(b)//100 copies in a b of 200 or more lines)
// are left out of b2j. Lines are interned to integer ids so that comparing two lines is comparing
// two integers.
//
// ponytail: no isjunk function, because unified_diff passes none. The junk set would stay empty, so
// the Python's loops that extend a block over junk never run, and adjacent blocks never exist for
// get_matching_blocks to merge: find_longest_match extends every block over all the equal lines
// next to it. A caller with junk needs bjunk, those loops and that merge.
type matcher struct {
	aid, bid []int   // line id per line of a (-1: the line is not in b) and of b
	b2j      [][]int // per id: the ascending indices of that line in b, nil for a popular line
	prev     []int   // scratch rows of find_longest_match: j2len, shifted by one so j-1 is never -1
	cur      []int
}

// newMatcher is SequenceMatcher.__init__ with __chain_b.
func newMatcher(a, b []string) *matcher {
	m := &matcher{aid: make([]int, len(a)), bid: make([]int, len(b))}
	ids := make(map[string]int, len(b))
	for j, line := range b {
		id, ok := ids[line]
		if !ok {
			id = len(m.b2j)
			ids[line] = id
			m.b2j = append(m.b2j, nil)
		}
		m.bid[j] = id
		m.b2j[id] = append(m.b2j[id], j)
	}
	if n := len(b); n >= 200 {
		ntest := n/100 + 1
		for id, idxs := range m.b2j {
			if len(idxs) > ntest {
				m.b2j[id] = nil
			}
		}
	}
	for i, line := range a {
		id, ok := ids[line]
		if !ok {
			id = -1
		}
		m.aid[i] = id
	}
	m.prev = make([]int, len(b)+1)
	m.cur = make([]int, len(b)+1)
	return m
}

// findLongestMatch is SequenceMatcher.find_longest_match(alo, ahi, blo, bhi): of all maximal
// matching blocks the one that starts earliest in a, and of those the one that starts earliest in
// b; (alo, blo, 0) when nothing matches. The block is found over the lines that are in b2j, then
// extended over the popular lines that sit next to it. j2len of the Python is the pair of
// zero-filled rows prev and cur: a row is cleared again right after its successor is built, so
// both rows are all zero between two calls.
func (m *matcher) findLongestMatch(alo, ahi, blo, bhi int) match {
	besti, bestj, bestsize := alo, blo, 0
	prev, cur := m.prev, m.cur
	var prevJs []int
	for i := alo; i < ahi; i++ {
		var js []int
		if id := m.aid[i]; id >= 0 {
			js = m.b2j[id]
		}
		for _, j := range js {
			if j < blo {
				continue
			}
			if j >= bhi {
				break
			}
			k := prev[j] + 1
			cur[j+1] = k
			if k > bestsize {
				besti, bestj, bestsize = i-k+1, j-k+1, k
			}
		}
		for _, j := range prevJs {
			prev[j+1] = 0
		}
		prev, cur = cur, prev
		prevJs = js
	}
	for _, j := range prevJs {
		prev[j+1] = 0
	}
	for besti > alo && bestj > blo && m.aid[besti-1] == m.bid[bestj-1] {
		besti, bestj, bestsize = besti-1, bestj-1, bestsize+1
	}
	for besti+bestsize < ahi && bestj+bestsize < bhi && m.aid[besti+bestsize] == m.bid[bestj+bestsize] {
		bestsize++
	}
	return match{besti, bestj, bestsize}
}

// matchingBlocks is SequenceMatcher.get_matching_blocks: the maximal blocks of equal lines in
// ascending order, ended by the sentinel (len(a), len(b), 0).
func (m *matcher) matchingBlocks() []match {
	la, lb := len(m.aid), len(m.bid)
	queue := [][4]int{{0, la, 0, lb}}
	var blocks []match
	for len(queue) > 0 {
		q := queue[len(queue)-1]
		queue = queue[:len(queue)-1]
		alo, ahi, blo, bhi := q[0], q[1], q[2], q[3]
		x := m.findLongestMatch(alo, ahi, blo, bhi)
		if x.size == 0 {
			continue
		}
		blocks = append(blocks, x)
		if alo < x.a && blo < x.b {
			queue = append(queue, [4]int{alo, x.a, blo, x.b})
		}
		if x.a+x.size < ahi && x.b+x.size < bhi {
			queue = append(queue, [4]int{x.a + x.size, ahi, x.b + x.size, bhi})
		}
	}
	// The blocks do not overlap and none is empty, so no two start at the same line of a: sorting by
	// a is the Python's sort of the (a, b, size) tuples.
	slices.SortFunc(blocks, func(x, y match) int { return x.a - y.a })
	return append(blocks, match{la, lb, 0})
}

// opcodes is SequenceMatcher.get_opcodes.
func (m *matcher) opcodes() []opcode {
	var answer []opcode
	i, j := 0, 0
	for _, blk := range m.matchingBlocks() {
		var tag byte
		switch {
		case i < blk.a && j < blk.b:
			tag = tagReplace
		case i < blk.a:
			tag = tagDelete
		case j < blk.b:
			tag = tagInsert
		}
		if tag != 0 {
			answer = append(answer, opcode{tag, i, blk.a, j, blk.b})
		}
		i, j = blk.a+blk.size, blk.b+blk.size
		if blk.size > 0 {
			answer = append(answer, opcode{tagEqual, blk.a, i, blk.b, j})
		}
	}
	return answer
}

// groupedOpcodes is SequenceMatcher.get_grouped_opcodes(n): the opcodes cut into groups of changes
// with up to n lines of context, a stretch of more than 2n unchanged lines ending a group. Two
// identical sequences give no group.
func groupedOpcodes(codes []opcode, n int) [][]opcode {
	if len(codes) == 0 {
		codes = []opcode{{tagEqual, 0, 1, 0, 1}}
	}
	if c := &codes[0]; c.tag == tagEqual {
		c.i1, c.j1 = max(c.i1, c.i2-n), max(c.j1, c.j2-n)
	}
	if c := &codes[len(codes)-1]; c.tag == tagEqual {
		c.i2, c.j2 = min(c.i2, c.i1+n), min(c.j2, c.j1+n)
	}
	var groups [][]opcode
	var group []opcode
	for _, c := range codes {
		if c.tag == tagEqual && c.i2-c.i1 > 2*n {
			group = append(group, opcode{c.tag, c.i1, min(c.i2, c.i1+n), c.j1, min(c.j2, c.j1+n)})
			groups = append(groups, group)
			group = nil
			c.i1, c.j1 = max(c.i1, c.i2-n), max(c.j1, c.j2-n)
		}
		group = append(group, c)
	}
	if len(group) > 0 && !(len(group) == 1 && group[0].tag == tagEqual) {
		groups = append(groups, group)
	}
	return groups
}
