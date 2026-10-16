package catalogue

import (
	"path/filepath"
	"strings"
)

// Join is Python os.path.join for two parts: an absolute second part replaces the first, else the
// parts are concatenated with one separator and no normalisation (the result may still hold `..`).
func Join(base, p string) string {
	if filepath.IsAbs(p) {
		return p
	}
	if base == "" || strings.HasSuffix(base, "/") {
		return base + p
	}
	return base + "/" + p
}
