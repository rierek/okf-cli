package linkscan

import "testing"

func TestWikilinkRegions(t *testing.T) {
	// Offsets are bytes: the umlaut in the second head counts twice.
	for _, tc := range []struct{ text, head string }{
		{"---\ntype: Concept\n---\nbody\n", "---\ntype: Concept\n---"},
		{"---\n---\nbody\n", "---\n---"},
		{"---\ntype: Concept\nnote: |\n  ```\n  [[a]]\n  ```\n---\nbody\n",
			"---\ntype: Concept\nnote: |\n  ```\n  [[a]]\n  ```\n---"},
		{"---\ntitle: Übersicht\n---\nbody é\n", "---\ntitle: Übersicht\n---"},
	} {
		want := [2]Region{{"frontmatter", 0, len(tc.head)}, {"body", len(tc.head), len(tc.text)}}
		if got := WikilinkRegions(tc.text); got != want {
			t.Errorf("WikilinkRegions(%q) = %v, want %v", tc.text, got, want)
		}
	}
	// A head that does not parse as a YAML mapping is body text.
	for _, text := range []string{
		"no frontmatter at all\n",
		"---\ntype: Concept\nbody never closes\n",
		"---\njust a thematic rule and prose\n---\nbody\n",
		"---\n- a\n- b\n---\nbody\n",
		"---\ntype: [unclosed\n---\nbody\n",
		"---\n\nIntro.\n\n    code sample: [[a]]\n\n---\n\nTail.\n",
	} {
		want := [2]Region{{"frontmatter", 0, 0}, {"body", 0, len(text)}}
		if got := WikilinkRegions(text); got != want {
			t.Errorf("WikilinkRegions(%q) = %v, want %v", text, got, want)
		}
	}
}

func TestWikilinkScanText(t *testing.T) {
	for _, tc := range []struct{ name, text, want string }{
		{"frontmatter under the YAML mask, body under the full mask",
			"---\ntype: Concept\nnote: \"`[[x]]`\"\nrelated:\n\n    - \"[[b]]\"\n---\n# X\n\n    code [[c]]\n\nlive [[d]] `e`\n",
			"---\ntype: Concept\nnote: \"" + hashes("`[[x]]`") + "\"\nrelated:\n\n    - \"[[b]]\"\n---\n# X\n\n" +
				hashes("    code [[c]]") + "\n\nlive [[d]] ###\n"},
		{"a thematic rule head is body text",
			"---\n\nIntro.\n\n    code sample: [[a]]\n\n---\n\nTail.\n",
			"---\n\nIntro.\n\n" + hashes("    code sample: [[a]]") + "\n\n---\n\nTail.\n"},
		{"multi-byte text stays aligned", "---\ntitle: Übersicht\n---\n`é` [[a]] 日本\n",
			"---\ntitle: Übersicht\n---\n#### [[a]] 日本\n"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			got := WikilinkScanText(tc.text)
			if len(got) != len(tc.text) {
				t.Fatalf("the scan text changed the byte length: %d to %d", len(tc.text), len(got))
			}
			if show(got) != tc.want {
				t.Errorf("scan text of %q\n got %q\nwant %q", tc.text, show(got), tc.want)
			}
			if at := WikilinkScanTextAt(tc.text, WikilinkRegions(tc.text)[0].End); at != got {
				t.Errorf("WikilinkScanTextAt differs from WikilinkScanText: %q", show(at))
			}
		})
	}
}
