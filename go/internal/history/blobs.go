package history

import (
	"bufio"
	"bytes"
	"errors"
	"fmt"
	"io"
	"os/exec"
	"strconv"
	"unicode/utf8"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
)

// blobs is `git cat-file --batch` of one repository: one process, versions read on request.
type blobs struct {
	cmd  *exec.Cmd
	in   io.WriteCloser
	outc io.Closer
	out  *bufio.Reader
}

func startBlobs(top string) (*blobs, error) {
	cmd := exec.Command("git", "-C", top, "cat-file", "--batch")
	in, err := cmd.StdinPipe()
	if err != nil {
		return nil, err
	}
	out, err := cmd.StdoutPipe()
	if err != nil {
		return nil, err
	}
	if err := cmd.Start(); err != nil {
		return nil, err
	}
	return &blobs{cmd: cmd, in: in, outc: out, out: bufio.NewReader(out)}, nil
}

// text is the blob sha as text, undecodable bytes replaced and line endings as stored; ok is false
// when the repository lacks the object.
func (b *blobs) text(sha string) (text string, ok bool, err error) {
	if _, err := io.WriteString(b.in, sha+"\n"); err != nil {
		return "", false, err
	}
	line, err := b.out.ReadBytes('\n')
	if err != nil && !errors.Is(err, io.EOF) {
		return "", false, err
	}
	header := bytes.Fields(line)
	if len(header) != 3 {
		return "", false, nil
	}
	size, err := strconv.Atoi(string(header[2]))
	if err != nil {
		return "", false, fmt.Errorf("git cat-file: size %q of %s: %w", header[2], sha, err)
	}
	data := make([]byte, size)
	n, err := io.ReadFull(b.out, data)
	if err != nil && !errors.Is(err, io.EOF) && !errors.Is(err, io.ErrUnexpectedEOF) {
		return "", false, err
	}
	if _, err := b.out.ReadBytes('\n'); err != nil && !errors.Is(err, io.EOF) { // the LF after the content
		return "", false, err
	}
	return decode(data[:n]), true, nil
}

// close ends the process: git sees the end of its input and exits. Its exit status is not asked.
func (b *blobs) close() error {
	err := b.in.Close()
	b.outc.Close()
	var exit *exec.ExitError
	if werr := b.cmd.Wait(); werr != nil && !errors.As(werr, &exit) && err == nil {
		err = werr
	}
	return err
}

// decode is bytes.decode("utf-8", errors="replace"): every ill-formed sequence becomes one U+FFFD
// and line endings stay as they are. catalogue.DecodeText does the replacing but also turns \r
// into \n; a \r is never part of a multi-byte sequence, so ill-formed text is decoded piece by
// piece around the \r.
func decode(b []byte) string {
	if utf8.Valid(b) {
		return string(b)
	}
	pieces := bytes.Split(b, []byte{'\r'})
	for i, piece := range pieces {
		pieces[i] = []byte(catalogue.DecodeText(piece))
	}
	return string(bytes.Join(pieces, []byte{'\r'}))
}
