package linkscan

import "nas/volume1/data/git/okf-tools/go/internal/frontmatter"

// Region is a labelled span of a file text: the byte offsets [Start, End).
type Region struct {
	Label      string
	Start, End int
}

// WikilinkRegions is the frontmatter region, then the body region, of text.
//
// Only a head whose block parses as a YAML mapping is frontmatter; any other head, such as a
// `---` thematic rule opening the body, is body text and reported as such: the frontmatter
// region is then empty ([0, 0)).
func WikilinkRegions(text string) [2]Region {
	fmEnd := 0
	if doc := frontmatter.Read(text); doc.Data() != nil {
		fmEnd = len(doc.Head)
	}
	return [2]Region{{"frontmatter", 0, fmEnd}, {"body", fmEnd, len(text)}}
}

// WikilinkScanText is the masked copy a wikilink scan reads, aligned byte for byte with text: the
// frontmatter region under the YAML mask, the body under the full mask.
func WikilinkScanText(text string) string {
	return WikilinkScanTextAt(text, WikilinkRegions(text)[0].End)
}

// WikilinkScanTextAt is WikilinkScanText for a caller that already holds the frontmatter end
// fmEnd (the End of the first WikilinkRegions region, a byte offset), which saves a second parse.
func WikilinkScanTextAt(text string, fmEnd int) string {
	return DeadZoneMask(text[:fmEnd], true) + DeadZoneMask(text[fmEnd:], false)
}
