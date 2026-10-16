package tagvec

import (
	"bytes"
	"encoding/binary"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"maps"
	"math"
	"net"
	"net/http"
	"os"
	"slices"
	"strings"
	"syscall"
	"time"
	"unicode/utf8"
)

// model is everything the producer knows about one embedding model: the dimension of its vectors,
// the endpoint of its embed call and the limits of one request (Python MODELS and BATCH_LIMITS).
// This table is the only copy of these facts.
type model struct {
	dim                int
	endpoint           string
	maxItems, maxChars int
}

var models = map[string]model{
	"bge-m3":         {1024, "http://localhost:11434/api/embed", 32, 90000},
	"voyage-3-large": {1024, "https://api.voyageai.com/v1/embeddings", 128, 90000},
}

// ModelNames is sorted(MODELS): the models the producer can embed with.
func ModelNames() []string { return slices.Sorted(maps.Keys(models)) }

// Dim is the dimension of the vectors of model.
func Dim(model string) int { return models[model].dim }

// BatchLimits is BATCH_LIMITS[model]: the most items and the most characters (code points of
// the texts) that one embed request of model carries.
func BatchLimits(model string) (maxItems, maxChars int) {
	m := models[model]
	return m.maxItems, m.maxChars
}

// EmbedBGEM3 is Python embed_bge_m3: one POST of all texts to the local Ollama, the vectors in
// input order. NETWORK.
func EmbedBGEM3(texts []string) ([][]float32, error) {
	var body struct {
		Embeddings [][]float64 `json:"embeddings"`
	}
	payload := map[string]any{"model": "bge-m3", "input": texts}
	if err := post(models["bge-m3"].endpoint, "", 300*time.Second, payload, &body); err != nil {
		return nil, err
	}
	return narrow(body.Embeddings, len(texts))
}

// EmbedVoyage is Python embed_voyage: one POST of all texts to Voyage AI as documents, the
// vectors in input order. It needs VOYAGE_API_KEY in the environment. NETWORK.
func EmbedVoyage(texts []string) ([][]float32, error) {
	key := os.Getenv("VOYAGE_API_KEY")
	if key == "" {
		return nil, errors.New("VOYAGE_API_KEY not set — required for --produce --model voyage-3-large")
	}
	var body struct {
		Data []struct {
			Embedding []float64 `json:"embedding"`
		} `json:"data"`
	}
	payload := map[string]any{"model": "voyage-3-large", "input": texts, "input_type": "document"}
	if err := post(models["voyage-3-large"].endpoint, key, 60*time.Second, payload, &body); err != nil {
		return nil, err
	}
	if body.Data == nil {
		return nil, errors.New("malformed response")
	}
	vecs := make([][]float64, len(body.Data))
	for i, d := range body.Data {
		vecs[i] = d.Embedding
	}
	return narrow(vecs, len(texts))
}

// EmbedVoyageQuery is the query embedding of the semantic arm (okf.semantic): one text embedded
// as a query by Voyage AI, the vector as the service returned it (float64, no float32 rounding).
// NETWORK.
func EmbedVoyageQuery(text string) ([]float64, error) {
	key := os.Getenv("VOYAGE_API_KEY")
	if key == "" {
		return nil, errors.New("VOYAGE_API_KEY not set")
	}
	var body struct {
		Data []struct {
			Embedding []float64 `json:"embedding"`
		} `json:"data"`
	}
	payload := map[string]any{"model": "voyage-3-large", "input": []string{text}, "input_type": "query"}
	if err := post(models["voyage-3-large"].endpoint, key, 10*time.Second, payload, &body); err != nil {
		return nil, err
	}
	if len(body.Data) == 0 || body.Data[0].Embedding == nil {
		return nil, errors.New("malformed response")
	}
	return body.Data[0].Embedding, nil
}

// narrow checks the vectors of a response against the texts that were sent and rounds each
// number to float32, as struct.pack('<f') does with the double that json.loads returns.
func narrow(vecs [][]float64, texts int) ([][]float32, error) {
	if vecs == nil {
		return nil, errors.New("malformed response")
	}
	if len(vecs) != texts {
		return nil, fmt.Errorf("response holds %d embeddings for %d texts", len(vecs), texts)
	}
	out := make([][]float32, len(vecs))
	for i, v := range vecs {
		if v == nil {
			return nil, errors.New("malformed response")
		}
		out[i] = make([]float32, len(v))
		for j, f := range v {
			out[i][j] = float32(f)
		}
	}
	return out, nil
}

// post sends payload as JSON to url (with a bearer key when key is not empty) and decodes the
// answer into out. Every failure is an error whose text names the cause in a few lower-case
// words. The client lives for one call: the binary pays nothing for it unless it embeds.
func post(url, key string, timeout time.Duration, payload, out any) error {
	data, err := json.Marshal(payload)
	if err != nil {
		return errors.New("malformed request")
	}
	req, err := http.NewRequest(http.MethodPost, url, bytes.NewReader(data))
	if err != nil {
		return errors.New("malformed request")
	}
	req.Header.Set("Content-Type", "application/json")
	if key != "" {
		req.Header.Set("Authorization", "Bearer "+key)
	}
	client := &http.Client{Timeout: timeout}
	resp, err := client.Do(req)
	if err != nil {
		return transportError(err, timeout)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		text := http.StatusText(resp.StatusCode)
		if text == "" {
			text = strings.TrimSpace(strings.TrimPrefix(resp.Status, fmt.Sprint(resp.StatusCode)))
		}
		return fmt.Errorf("HTTP %d %s", resp.StatusCode, text)
	}
	if err := json.NewDecoder(resp.Body).Decode(out); err != nil {
		var ne net.Error
		if errors.As(err, &ne) && ne.Timeout() {
			return timeoutError(timeout)
		}
		return errors.New("malformed response")
	}
	return nil
}

func timeoutError(d time.Duration) error { return fmt.Errorf("timeout after %ds", int(d.Seconds())) }

// transportError names the cause of a failed request without the vocabulary of the Go net
// stack.
func transportError(err error, timeout time.Duration) error {
	var dns *net.DNSError
	var ne net.Error
	switch {
	case errors.Is(err, syscall.ECONNREFUSED):
		return errors.New("connection refused")
	case errors.As(err, &dns):
		return errors.New("unknown host")
	case errors.As(err, &ne) && ne.Timeout():
		return timeoutError(timeout)
	case errors.Is(err, syscall.ECONNRESET):
		return errors.New("connection reset")
	case errors.Is(err, io.EOF), errors.Is(err, io.ErrUnexpectedEOF):
		return errors.New("connection closed")
	}
	return errors.New("connection failed")
}

// PackVec is Python pack_vec: the float32 blob of the cache, little-endian, 4 bytes a number.
func PackVec(vec []float32) []byte {
	out := make([]byte, 4*len(vec))
	for i, f := range vec {
		binary.LittleEndian.PutUint32(out[4*i:], math.Float32bits(f))
	}
	return out
}

// Batches is Python batches: items cut into request-sized pieces, bounded by both the item
// count and the total text length in code points. A single item that alone exceeds maxChars is
// still a batch of its own.
func Batches(items []Triple, maxItems, maxChars int) [][]Triple {
	var out [][]Triple
	var cur []Triple
	chars := 0
	for _, item := range items {
		n := utf8.RuneCountInString(item.Text)
		if len(cur) > 0 && (len(cur) >= maxItems || chars+n > maxChars) {
			out = append(out, cur)
			cur, chars = nil, 0
		}
		cur = append(cur, item)
		chars += n
	}
	if len(cur) > 0 {
		out = append(out, cur)
	}
	return out
}

// sleep is time.Sleep; a variable so that the retry ladder can be exercised without waiting.
var sleep = time.Sleep

// EmbedResilient is Python embed_resilient: the vectors for texts, or nil when the batch is
// unrecoverable. Up to three attempts with an exponential backoff of 2, 4 and 8 seconds; from
// the second failure on every text is cut to half its length (at least 500 code points), as a
// 400 of these endpoints usually means an over-long input. Each failure and the final give-up
// are reported on progress; the run goes on with the next batch.
func EmbedResilient(embed func([]string) ([][]float32, error), texts []string, label string, progress io.Writer) [][]float32 {
	delay := 2 * time.Second
	for attempt := range 3 {
		vecs, err := embed(texts)
		if err == nil {
			return vecs
		}
		fmt.Fprintf(progress, "    retry %d (%d texts) %s: %s\n", attempt+1, len(texts), label, err)
		sleep(delay)
		delay *= 2
		if attempt >= 1 {
			cut := make([]string, len(texts))
			for i, t := range texts {
				cut[i] = head(t, max(utf8.RuneCountInString(t)/2, 500))
			}
			texts = cut
		}
	}
	fmt.Fprintf(progress, "    SKIPPED %s — %d text(s) left unembedded\n", label, len(texts))
	return nil
}

// head is the first n code points of s (Python s[:n]).
func head(s string, n int) string {
	for i := range s {
		if n == 0 {
			return s[:i]
		}
		n--
	}
	return s
}
