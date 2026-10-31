package semantic

import (
	"errors"
	"sync"
	"sync/atomic"
	"testing"
)

// Overlapping searches look up and store query vectors at once; under -race the cache must not
// race, and a failed embedding is not cached.
func TestQueryVectorConcurrent(t *testing.T) {
	var calls atomic.Int32
	original := embedQuery
	t.Cleanup(func() { embedQuery = original })
	embedQuery = func(text string) ([]float64, error) {
		calls.Add(1)
		if text == "fails" {
			return nil, errors.New("backend down")
		}
		return []float64{float64(len(text))}, nil
	}
	var wg sync.WaitGroup
	for i := range 32 {
		wg.Add(1)
		go func() {
			defer wg.Done()
			text := []string{"alpha", "beta", "gamma", "fails"}[i%4]
			v, err := queryVector(text)
			if text == "fails" {
				if err == nil {
					t.Error("failure not reported")
				}
				return
			}
			if err != nil || len(v) != 1 || v[0] != float64(len(text)) {
				t.Errorf("queryVector(%q) = %v, %v", text, v, err)
			}
		}()
	}
	wg.Wait()
	before := calls.Load()
	if _, err := queryVector("alpha"); err != nil || calls.Load() != before {
		t.Errorf("a stored vector must not embed again (calls %d -> %d, err %v)", before, calls.Load(), err)
	}
	if _, err := queryVector("fails"); err == nil || calls.Load() != before+1 {
		t.Errorf("a failure must not be cached (calls %d, err %v)", calls.Load(), err)
	}
}
