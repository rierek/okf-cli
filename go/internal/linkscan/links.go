package linkscan

import (
	"iter"
	"os"
	"path/filepath"
	"regexp"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/catalogue"
	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

// schemeRE is a `<scheme>://` URL prefix; like the Python pattern it knows lower-case schemes only.
var schemeRE = regexp.MustCompile(`^[a-z][a-z0-9+.-]*://`)

// Link is one markdown link of a file: its target text exactly as written (anchor, query and
// surrounding blanks included) and the absolute path the target resolves to.
type Link struct{ Raw, Resolved string }

// SourceLink is a Link together with the file that holds it. Source is that file's path relative
// to the scan root, slash separated.
type SourceLink struct {
	Source string
	Link
}

// Ref is one row of a reference matrix: the source file (relative to the scan root, slash
// separated) and the link target text as written there.
type Ref struct{ Source, Raw string }

// Outbound is one outbound link of a file: the target text as written, the absolute path it
// resolves to and whether that path exists.
type Outbound struct {
	Raw, Target string
	Exists      bool
}

// ResolveMdLink is the absolute path a markdown link target raw, written in the file srcAbs,
// points at; ok is false for an empty target, a `<scheme>://` URL or mailto:. A query and an
// anchor are dropped. A leading / means scanRoot (the OKF catalogue-root convention, which is
// also the Obsidian vault root), not the bundle. The error is the failure to make a relative
// path absolute.
func ResolveMdLink(scanRoot, srcAbs, raw string) (resolved string, ok bool, err error) {
	tgt, _, _ := strings.Cut(raw, "#")
	tgt, _, _ = strings.Cut(tgt, "?")
	tgt = pytext.Strip(tgt)
	if tgt == "" || schemeRE.MatchString(tgt) || strings.HasPrefix(tgt, "mailto:") {
		return "", false, nil
	}
	var joined string
	if strings.HasPrefix(tgt, "/") {
		joined = catalogue.Join(scanRoot, strings.TrimLeft(tgt, "/"))
	} else {
		joined = catalogue.Join(filepath.Dir(srcAbs), tgt)
	}
	resolved, err = catalogue.Abspath(joined)
	if err != nil {
		return "", false, err
	}
	return resolved, true, nil
}

// FileMdLinks is the markdown links of one file, in file order, with their resolved targets. The
// links are the matches of catalogue.CrosslinkRE (group 2 is the target) over the masked text
// (WikilinkScanText), so a link in code, a comment or a sync span is none; the target text is cut
// from the original, never from the mask.
func FileMdLinks(scanRoot, ap string) ([]Link, error) {
	text, err := catalogue.ReadFile(ap)
	if err != nil {
		return nil, err
	}
	links := []Link{}
	for _, m := range catalogue.CrosslinkRE.FindAllStringSubmatchIndex(WikilinkScanText(text), -1) {
		raw := text[m[4]:m[5]]
		resolved, ok, err := ResolveMdLink(scanRoot, ap, raw)
		if err != nil {
			return nil, err
		}
		if ok {
			links = append(links, Link{raw, resolved})
		}
	}
	return links, nil
}

// IterMdLinks yields every markdown link of every file of IterRenameScanMd(scanRoot), file by file.
// It has the same traversal and the same dead-zone mask as the wikilink half of a rename, so the
// two halves of one move cannot disagree about which files and which occurrences they cover. A
// root-level walk alone cannot enter a symlinked bundle, which left a mounted file with its
// wikilink rewritten and its markdown link dangling in the same line.
//
// A failure (the root cannot be listed, a file cannot be read) is yielded once as the error of
// the last pair; the sequence ends after it.
func IterMdLinks(scanRoot string) iter.Seq2[SourceLink, error] {
	return func(yield func(SourceLink, error) bool) {
		files, err := IterRenameScanMd(scanRoot)
		if err != nil {
			yield(SourceLink{}, err)
			return
		}
		for ap := range files {
			rel, err := relpath(ap, scanRoot)
			if err != nil {
				yield(SourceLink{}, err)
				return
			}
			links, err := FileMdLinks(scanRoot, ap)
			if err != nil {
				yield(SourceLink{}, err)
				return
			}
			for _, l := range links {
				if !yield(SourceLink{filepath.ToSlash(rel), l}, nil) {
					return
				}
			}
		}
	}
}

// OutboundLinks is the markdown links of srcAbs in file order with the existence of each target.
func OutboundLinks(root, srcAbs string) ([]Outbound, error) {
	src, err := catalogue.Abspath(srcAbs)
	if err != nil {
		return nil, err
	}
	links, err := FileMdLinks(root, src)
	if err != nil {
		return nil, err
	}
	out := make([]Outbound, 0, len(links))
	for _, l := range links {
		_, statErr := os.Stat(l.Resolved)
		out = append(out, Outbound{l.Raw, l.Resolved, statErr == nil})
	}
	return out, nil
}

// BuildRefMatrix is every markdown link under scanRoot that resolves to targetAbspath, as
// (source file relative to the scan root, link target as written) in scan order. Code, comments
// and sync spans are masked, http(s) and mailto links and anchors are ignored, and both relative
// and catalogue-root-absolute (leading /) links resolve path-wise.
//
// A link that spells its target in another case than the disk does counts when it names the same
// existing file: on a case-insensitive filesystem such a link is live and a rename must rewrite
// it too. That test only runs on a case-equal near miss, so it stays correct on a case-sensitive
// filesystem; when the target itself does not exist the near miss fails with the stat error, as
// Python's os.path.samefile does.
func BuildRefMatrix(scanRoot, targetAbspath string) ([]Ref, error) {
	target, err := catalogue.Abspath(targetAbspath)
	if err != nil {
		return nil, err
	}
	lowerTarget := pytext.Lower(target)
	hits := []Ref{}
	for l, err := range IterMdLinks(scanRoot) {
		if err != nil {
			return nil, err
		}
		if l.Resolved != target {
			same, err := sameFileNearMiss(l.Resolved, target, lowerTarget)
			if err != nil {
				return nil, err
			}
			if !same {
				continue
			}
		}
		hits = append(hits, Ref{l.Source, l.Raw})
	}
	return hits, nil
}

// sameFileNearMiss reports whether resolved differs from target in case only and both name the
// same file. lowerTarget is pytext.Lower(target).
func sameFileNearMiss(resolved, target, lowerTarget string) (bool, error) {
	if pytext.Lower(resolved) != lowerTarget {
		return false, nil
	}
	ri, err := os.Stat(resolved)
	if err != nil {
		return false, nil // os.path.exists is false
	}
	ti, err := os.Stat(target)
	if err != nil {
		return false, err
	}
	return os.SameFile(ri, ti), nil
}

// RefsDisplay is p as the reference views print it: the scan-root-relative slash path when p is
// under scanRoot, else `~/…` under the home directory, else p unchanged.
func RefsDisplay(scanRoot, p string) (string, error) {
	for _, b := range [...]struct{ base, prefix string }{{scanRoot, ""}, {catalogue.ExpandUser("~"), "~/"}} {
		rel, err := relpath(p, b.base)
		if err != nil {
			return "", err
		}
		if rel != ".." && !strings.HasPrefix(rel, "../") {
			return b.prefix + filepath.ToSlash(rel), nil
		}
	}
	return p, nil
}

// relpath is Python os.path.relpath: the lexical relative path from start to path, both made
// absolute first.
func relpath(path, start string) (string, error) {
	p, err := catalogue.Abspath(path)
	if err != nil {
		return "", err
	}
	s, err := catalogue.Abspath(start)
	if err != nil {
		return "", err
	}
	return filepath.Rel(s, p)
}
