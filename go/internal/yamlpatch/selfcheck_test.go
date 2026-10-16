package yamlpatch

import (
	"errors"
	"strings"
	"testing"
)

// The self-check is the guard that turns a fault of the patcher into a rejection (R-04). Apply never
// shows it a faulty text, so these tests hand it faulty texts directly: every kind of damage a wrong
// patch could do must be refused, and the right text must pass.

func TestSelfCheckRefusesDamagedTexts(t *testing.T) {
	const in = "---\ntype: X\ntags:\n  - a\n  - b\nn: 1\nz: 'q'\n---\n# T\n"
	p, err := newPatcher(in)
	if err != nil {
		t.Fatal(err)
	}
	if err := p.do(AppendItem("tags", Str("c"))); err != nil {
		t.Fatal(err)
	}
	good := p.result()
	if want := "---\ntype: X\ntags:\n  - a\n  - b\n  - c\nn: 1\nz: 'q'\n---\n# T\n"; good != want {
		t.Fatalf("the patch is %q, want %q", good, want)
	}
	if err := p.selfCheck(good); err != nil {
		t.Fatalf("the right text is refused: %v", err)
	}
	damaged := map[string]string{
		"a line of another key dropped":      strings.Replace(good, "n: 1\n", "", 1),
		"the new item dropped":               strings.Replace(good, "  - c\n", "", 1),
		"the new item written twice":         strings.Replace(good, "  - c\n", "  - c\n  - c\n", 1),
		"a wrong value":                      strings.Replace(good, "- c", "- d", 1),
		"items in another order":             strings.Replace(good, "  - a\n  - b\n", "  - b\n  - a\n", 1),
		"keys in another order":              strings.NewReplacer("type: X\n", "n: 1\n", "n: 1\n", "type: X\n").Replace(good),
		"a type changed (int to string)":     strings.Replace(good, "n: 1", "n: '1'", 1),
		"a type changed (string to int)":     strings.Replace(good, "z: 'q'", "z: 5", 1),
		"the item turned into a nested one":  strings.Replace(good, "  - c", "    - c", 1),
		"the item joined the one before":     strings.Replace(good, "  - c", "    c", 1),
		"the item lost its dash":             strings.Replace(good, "  - c", "  c", 1),
		"a key lost":                         strings.Replace(good, "type: X\n", "", 1),
		"a key added":                        strings.Replace(good, "n: 1\n", "n: 1\nextra: 1\n", 1),
		"the body changed":                   strings.Replace(good, "# T", "# U", 1),
		"the body lost":                      good[:strings.LastIndex(good, "---")+3],
		"the frontmatter gone":               "# T\n",
		"the whole block dropped":            good[strings.LastIndex(good, "---")+3:],
		"an anchor added":                    strings.Replace(good, "n: 1", "n: &x 1", 1),
		"the closing delimiter gone":         strings.Replace(good, "---\n# T\n", "", 1),
		"the closing delimiter moved up":     strings.Replace(good, "n: 1\n", "---\nn: 1\n", 1),
		"invalid yaml":                       strings.Replace(good, "- b", "- [b", 1),
		"a duplicate key":                    strings.Replace(good, "n: 1\n", "n: 1\ntype: Y\n", 1),
		"a value turned into a comment":      strings.Replace(good, "n: 1", "n: # 1", 1),
		"a trailing space turned into a key": strings.Replace(good, "n: 1\n", "n: 1\n: x\n", 1),
	}
	for name, text := range damaged {
		t.Run(name, func(t *testing.T) {
			err := p.selfCheck(text)
			var rej *Rejection
			if !errors.As(err, &rej) {
				t.Errorf("the damaged text %q passes (err = %v)", text, err)
			}
		})
	}
}

// A typed plain scalar must read back plain (a quoted timestamp is a string), and a string must read
// back as a string (a plain timestamp is not).
func TestSelfCheckSeesTypesOfNewScalars(t *testing.T) {
	check := func(edit Edit, bad string) {
		t.Helper()
		p, err := newPatcher("---\na: 1\n---\n")
		if err != nil {
			t.Fatal(err)
		}
		if err := p.do(edit); err != nil {
			t.Fatal(err)
		}
		if err := p.selfCheck(p.result()); err != nil {
			t.Fatalf("the right text is refused: %v", err)
		}
		if p.selfCheck(bad) == nil {
			t.Errorf("the wrong text %q passes", bad)
		}
	}
	check(NewKey("at", Plain("2026-10-12T19:00:00Z")), "---\na: 1\nat: '2026-10-12T19:00:00Z'\n---\n")
	check(NewKey("at", Str("2026-10-12T19:00:00Z")), "---\na: 1\nat: 2026-10-12T19:00:00Z\n---\n")
	check(NewKey("s", Str("1")), "---\na: 1\ns: 1\n---\n")
	check(NewKey("m", Map("a", Str("1"))), "---\na: 1\nm:\n  - a\n  - '1'\n---\n")
	check(NewKey("l", List(Str("a"), Str("b"))), "---\na: 1\nl:\n  a: b\n---\n")
}

// Flow to block changes no data: the check must accept the rewritten list and refuse a changed one.
func TestSelfCheckOfFlowToBlock(t *testing.T) {
	p, err := newPatcher("---\ntags: [a, 'b c']\n---\n")
	if err != nil {
		t.Fatal(err)
	}
	if err := p.do(FlowToBlock("tags")); err != nil {
		t.Fatal(err)
	}
	if err := p.selfCheck(p.result()); err != nil {
		t.Fatal(err)
	}
	for _, bad := range []string{"---\ntags:\n  - a\n---\n", "---\ntags:\n  - a\n  - 'b'\n---\n"} {
		if p.selfCheck(bad) == nil {
			t.Errorf("%q passes", bad)
		}
	}
}

// The guard is wired into every edit: a patch that does something else than it intends gives a
// rejection and no text, whatever the fault.
func TestFaultyPatchesBecomeRejections(t *testing.T) {
	const in = "---\ntype: X\ntags:\n  - a\n  - b\nn: 1\n---\n# T\n"
	patch := func(fault func(p *patcher)) func(*patcher) error {
		return func(p *patcher) error {
			if err := p.do(AppendItem("tags", Str("c"))); err != nil {
				return err
			}
			if fault != nil {
				fault(p)
			}
			return nil
		}
	}
	if got, err := applyWith(in, patch(nil)); err != nil || got != "---\ntype: X\ntags:\n  - a\n  - b\n  - c\nn: 1\n---\n# T\n" {
		t.Fatalf("the right patch gives %q, %v", got, err)
	}
	faults := map[string]func(p *patcher){
		"the item one column to the left":    func(p *patcher) { p.lines[5] = " - c\n" },
		"the item in the wrong place":        func(p *patcher) { p.lines[5], p.lines[6] = p.lines[6], p.lines[5] },
		"an item lost":                       func(p *patcher) { p.lines = append(p.lines[:4], p.lines[5:]...) },
		"the wrong item":                     func(p *patcher) { p.lines[5] = "  - d\n" },
		"a line of another key changed":      func(p *patcher) { p.lines[6] = "n: 2\n" },
		"a line of another key lost":         func(p *patcher) { p.lines = p.lines[:6] },
		"a line inserted":                    func(p *patcher) { p.insertLines(2, "extra: 1\n") },
		"a type changed by a quote":          func(p *patcher) { p.lines[6] = "n: '1'\n" },
		"text added behind the block":        func(p *patcher) { p.lines = append(p.lines, "- x\n") },
		"the body lost":                      func(p *patcher) { p.body = "" },
		"the body changed":                   func(p *patcher) { p.body += "more" },
		"the opening delimiter line damaged": func(p *patcher) { p.lines[0] = "x\n" },
		"a line ending lost":                 func(p *patcher) { p.lines[5] = "  - c" },
	}
	for name, fault := range faults {
		t.Run(name, func(t *testing.T) {
			got, err := applyWith(in, patch(fault))
			var rej *Rejection
			if !errors.As(err, &rej) || got != "" {
				t.Errorf("a faulty patch gave %q, %v; want a rejection and no text", got, err)
			}
		})
	}
}

// The flow scan is checked against the parser's nodes: a scan that finds other items than the parser is
// refused, never trusted.
func TestFlowScanIsCheckedAgainstTheParser(t *testing.T) {
	p, err := newPatcher("---\ntags: [a, b]\n---\n")
	if err != nil {
		t.Fatal(err)
	}
	list := p.doc.Root.Content[1]
	if _, err := p.scanFlow(list); err != nil {
		t.Fatalf("the right scan is refused: %v", err)
	}
	extra := *list.Content[1]
	list.Content = append(list.Content, &extra)
	if _, err := p.scanFlow(list); err == nil {
		t.Error("a scan with fewer items than the parser finds is accepted")
	}
	list.Content = list.Content[:1]
	if _, err := p.scanFlow(list); err == nil {
		t.Error("a scan with more items than the parser finds is accepted")
	}
	list.Content = append(list.Content, &extra)
	list.Content[1].Column++
	if _, err := p.scanFlow(list); err == nil {
		t.Error("a scan that starts an item elsewhere than the parser is accepted")
	}
}
