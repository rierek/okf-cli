---
type: Analysis
title: "Acceptance report — okf Go port: golden run, deviation list, corpus diff, catalogue parity, startup"
description: "Evidence package of work package K (OKFT-8dnw): full golden run of the Go binary with a one-by-one deviation list, minimal-diff corpus run of the production frontmatter writer on 7,538 files, parity on frozen copies of the three production catalogues, final startup measurement. PO decisions are open."
tags:
  - okf-go-port
  - acceptance
generated: { by: claude-code/claude-sonnet-5-5, at: 2026-10-16T16:25:07Z }
---

# Acceptance report — okf Go port (work package K, OKFT-8dnw)

K builds no port code; it measured the finished port at commit `e3305f2be4cf` of the chore line `chore/OKFT-jyvt-go-port` (binary built by `just go-build`, sha256 `5bf685d173ea46abbfe99df8340c47e43babb3d6e0c80dcea40db481cb4b23d5`). Four evidence blocks: the golden run with its deviation list (§2), the corpus run of the production frontmatter writer (§3), parity on the three production catalogues (§4), startup (§5). The PO decision field of every deviation entry is empty; no deviation is marked accepted.

## 0. Result at a glance

### 0.1 Blocking findings (capability preserved: no)

**18 of the 77 deviation entries answer `capability preserved: no`** (22 at K's run; D-02, D-41, D-42 and D-61 were fixed afterwards, §0.4, and now answer `yes`). Per criterion 4 they are blocking for the PO decision; each names its owning item (cut table of OKFT-jyvt). Rule used for the answer: `no` means the Go binary cannot do something the Python CLI does correctly and without data damage, or Go loses or changes data silently. A refusal that is a deliberate design choice (R-04, D05) counts as `no` for the input shapes it refuses, because the PO decides under D02 whether that loss is acceptable. A refusal of input on which Python writes damaged data is `yes`. The column `kind` is K's triage aid, not a decision.

Of the kind `Go writes wrong data or reports success wrongly` (D-02, D-41, D-61) and the exit status entry D-42 none is left in the table: they are fixed, see §0.4.

| ID | Title | Channel | Owner | Kind |
|---|---|---|---|---|
| D-03 | A lone CR that ends a line inside an LF frontmatter: Go refuses the edit, Python converts the CR to LF and writes | exit code, stderr, file-tree effect | Go frontmatter writer (F: OKFT-5lq2) | Go refuses or aborts valid work |
| D-04 | A frontmatter whose root is a flow mapping (or `~`/`null`, `--- {}`, `{ }`): Go refuses, Python writes | exit code, stdout (empty in Go), stderr (with --json: the error envelope on stdout), file- | Go frontmatter writer (F: OKFT-5lq2) | Go refuses or aborts valid work |
| D-05 | An anchor, alias or explicit tag on the edited value: Go refuses, Python writes | exit code, stderr, file-tree effect | Go frontmatter writer (F: OKFT-5lq2) | Go refuses or aborts valid work |
| D-06 | A comment inside a multi-line flow list: Go refuses, Python writes (and drops the comment) | exit code, stderr, file-tree effect | Go frontmatter writer (F: OKFT-5lq2) | Go refuses or aborts valid work |
| D-07 | Other shapes the line patcher cannot patch (null item, folded item, value after the dash, complex key, flow list on the next line, multi-line flow `verified`): Go refuses, Python writes | exit code, stderr, file-tree effect | Go frontmatter writer (F: OKFT-5lq2) | Go refuses or aborts valid work |
| D-08 | One refused file ends the whole run of `merge-tags`, `remove-tags` and `normalize-tags` (dry-run included): nothing is previewed or written for the other files | exit code, stdout, stderr, file-tree effect | Go tag and frontmatter writes (F: OKFT-dkdu) + Go frontmatter writer (F: OKFT-5lq2) | Go refuses or aborts valid work |
| D-09 | One refused file ends the whole `migrate` run (dry-run included): no plan is previewed or written for the other files | exit code, stdout, stderr, file-tree effect | Go tag and frontmatter writes (F: OKFT-dkdu) + Go frontmatter writer (F: OKFT-5lq2) | Go refuses or aborts valid work |
| D-17 | Go refuses a ctx edit when the frontmatter parses but its line patcher cannot patch it | exit code, stdout, stderr, file-tree effect | Go frontmatter writer (F: OKFT-5lq2) | Go refuses or aborts valid work |
| D-18 | A ctx position beyond int64 is dropped by Go and refused by the editing verbs | stdout, stderr, exit code (editing verbs), file-tree effect | Go frontmatter writer (F: OKFT-5lq2) | Go refuses or aborts valid work |
| D-26 | Go refuses frontmatter that ruamel reads (`\/` escape, odd anchor names, empty keys) | exit code, stdout, file-tree effect | Go core and read side (F: OKFT-daut) | Go cannot read or process input Python handles |
| D-27 | NEL (U+0085), LS (U+2028) and PS (U+2029) in frontmatter | exit code, stdout | Go core and read side (F: OKFT-daut) | Go cannot read or process input Python handles |
| D-28 | TOML integer above int64 aborts every command that reads the config | exit code, stderr | Go core and read side (F: OKFT-daut) | Go cannot read or process input Python handles |
| D-29 | Load-time checks of ruamel that Go skips (equal duplicate keys, invalid tag values, merge-key misuse) | exit code, stdout | Go core and read side (F: OKFT-daut) | Go validates less than Python |
| D-30 | Impossible dates and out-of-range timestamps in a custom key (`2026-02-30`, `T24:00:00Z`) | exit code, stdout, file-tree effect | Go core and read side (F: OKFT-daut) | Go validates less than Python |
| D-43 | Go aborts normalize-tags and verify on a non-scalar frontmatter key | exit code, stdout, stderr, file-tree effect | Go frontmatter writer (F: OKFT-5lq2) | Go refuses or aborts valid work |
| D-52 | `recent` prints UTC instead of local time when `TZ` is a POSIX rule string | stdout (clock time in text mode, the `created` offset in `--json`; `created_ts` is equal) | Go navigation commands (F: OKFT-se5f) | narrow: one display or ordering rule |
| D-59 | Cherokee letters: Go case folding is not idempotent, so a heading typed in the other case is not found | exit code, stderr (read); stdout order (list); file-tree effect (reindex writes `docs/inde | Go core and read side (F: OKFT-daut) | Go cannot read or process input Python handles |
| D-60 | Timeouts: Python limits each socket wait, Go limits the whole request | stdout, stderr, duration | Go find and FTS index (F: OKFT-y1zl) | exit status or timing semantics |

### 0.2 Findings by owning item

| Owning item | `no` entries | `yes` entries |
|---|---|---|
| Go check and verify (F: OKFT-agws) | – | D-02, D-10, D-73, D-74 |
| Go core and read side (F: OKFT-daut) | D-26, D-27, D-28, D-29, D-30, D-59 | D-01, D-23, D-24, D-31, D-32, D-33, D-34, D-35, D-36, D-37, D-38, D-39, D-40, D-41, D-42, D-44, D-45, D-46, D-47, D-54, D-55, D-56, D-57, D-62, D-63, D-76, D-77 |
| Go ctx bundles (F: OKFT-82n3) | – | D-22, D-23 |
| Go find and FTS index (F: OKFT-y1zl) | D-60 | D-61, D-62, D-63, D-64, D-65, D-66, D-67, D-68, D-69, D-70 |
| Go frontmatter writer (F: OKFT-5lq2) | D-03, D-04, D-05, D-06, D-07, D-08, D-09, D-17, D-18, D-43 | D-02, D-10, D-11, D-12, D-13, D-14, D-15, D-16, D-19, D-20, D-21, D-25, D-72, D-73, D-76 |
| Go link rewriting writes (F: OKFT-cm5o) | – | D-47, D-75 |
| Go navigation commands (F: OKFT-se5f) | D-52 | D-36, D-50, D-53, D-54, D-58 |
| Go shell completion (F: OKFT-50ly) | – | D-48, D-49, D-51 |
| Go tag and frontmatter writes (F: OKFT-dkdu) | D-08, D-09 | D-61, D-64, D-65, D-66, D-67, D-70, D-71, D-72, D-74, D-75 |
| Go wikilinks and sync blocks (F: OKFT-ca1y) | – | D-48 |

### 0.3 Criteria

| AC | Result | Evidence |
|---|---|---|
| 1 | met | §2.1 harness lines; `21 of 314 cases differ` is the one grouped entry D-01 listing all 21 case names; every other deviation is an entry of §2.2 |
| 2 | not applicable | the golden run has 21 deviating cases, not 0 |
| 3 | met | every entry ends in an empty `PO decision:`; nothing is marked accepted |
| 4 | met | 18 entries answer `no` (22 at K's run; D-02, D-41, D-42, D-61 fixed since, §0.4), listed in §0.1 with owners |
| 5 | met | §2.3 matches the four deliberate deviations of OKFT-5lq2 to entries with direct Python-against-Go runs; further deviations of that area sit beside them |
| 6 | met | Go run with `env PATH=<dir without python*/uv>`: same 21 deviating cases, byte-identical diff text (§2.1) |
| 7 | met | Python CLI on the same 314 cases: `0 of 314 cases differ` |
| 8 | met | 0 changed, deleted or added lines in `tests/golden` and `tests/okf_golden.py` since `5b5e05a` (§2.5); 314 cases before and after, 0 added cases |
| 9 | met | `real` 674 files, every op 100 % minimal (§3) |
| 10 | met | `hist` 6,864 versions, every op 100 % minimal (§3) |
| 11 | met | 0 files not minimal; nothing to list |
| 12 | met | self-test: 750 accepted outputs; damage seen 745/745 (space on a foreign line), 750/750 (wrong value), 745/745 (foreign line removed), 750/750 (no change); the whole corpus pipeline ran twice, the result counts are identical |
| 13 | met | `ref.py` run unchanged (sha256 in §3); pass criterion is `minimal`, never ruamel byte equality |
| 14 | met | 148 of 148 `build-index`, `check`, `index`, `find` cases identical on three catalogues (§4) |
| 15 | met | 32 / 18 / 12 fixed `find` queries (Knowledge-Catalogue / sproutling-okf / dev-okf), `--where` filters in 14 / 3 / 1 of them, all listed in §4 |
| 16 | met | 0 parity differences, so no parity entry |
| 17 | met | live trees byte-identical to the pre-copy manifest (§4.3) |
| 18 | met | `env -i PATH=<dir without python or uv> okf --root <copy> find git`: exit 0, 10 hits (§5.1; argument-order note in §6) |
| 19 | met | medians of 30 runs: `--help` 1.32 ms against 46.9 ms (Python direct) and 49.8 ms (`uv run --script`); `find git` 17.1 ms against 145.5 ms and 150.3 ms (§5) |
| 20 | met | early number of OKFT-y1zl next to the final ones, with run counts, machine, build command and Python command lines (§5.2) |
| 21 | met | K's run adds no Go test file (one commit: this report); the fixes of §0.4 add 4 cases to the existing `go/internal/yamlpatch/reject_test.go` and no new test file |

SC-01: D-01 and every further deviation carry case names, channel, difference, reason, answer, evidence and owner. SC-02 met (§3). SC-03 met (§4). SC-04 met (§5). R-01, R-02, R-03, R-13, R-15: evidence in §2, §3, §4, §5; R-02 stays open until the PO has decided the entries.

### 0.4 Fixes after the run (OKFT-8dnw)

The four entries that read as defects were fixed on `wt/OKFT-8dnw` after K's run. Each fix was shown by a Python-against-Go run before and after (private network namespace; stub servers answer the embed calls); the entries keep K's finding text and carry a `Fixed in` line with the evidence. The 18 other `no` entries and every PO decision are untouched.

| Entry | Fix | Commit |
|---|---|---|
| D-02 | `yamlpatch` refuses a CR-only frontmatter instead of creating a second block (`verify` and every tag verb) | `0a14338` |
| D-41, D-42 | package `stdio` is the one stdout of all commands: a failed write gives one stderr line and exit 120, a broken pipe is no failure (SIGPIPE no longer kills) | `bfaf900` |
| D-61 | the embed decode refuses a JSON null element with the Python exception and no retry | `0bbdcac` |

Checks on the fixed tree (`go/bin/okf` sha256 `290abe1aa47aa5f8b9f1229cacac7123e1d152a6827a31b97aa4a1825cbbd87b`): `go vet ./...` and `go test ./...` pass; `just golden --cmd go/bin/okf` gives `21 of 314 cases differ`, the same 21 case names and wording-only diffs as D-01; `just golden` (Python) gives `0 of 314 cases differ`; `tests.test_okf_mcp`, `tests.test_okf_install` and `tests.test_golden` (158 tests, 2 skipped), `just go-find-smoke` and `just completion-check` pass. Only the yamlpatch fix carries a Go test (R-05); the stdout and vector fixes are shown by the before/after runs in their entries.

## 1. Measured object, environment, method

| Item | Value |
|---|---|
| Line commit | `e3305f2be4cf500dc912eff7a56dd11e9b9c07c3` (`Merge branch 'wt/OKFT-qg0o' into chore/OKFT-jyvt-go-port`), worktree branch `wt/OKFT-8dnw`; Python reference tree `git describe` = `rel-0-2-4-88-ge3305f2` |
| Binary | `just go-build` = `CGO_ENABLED=0 go build -C go -o bin/okf ./cmd/okf` (the one build command of the module; `.github/workflows/release.yml` calls `just go-build` per target with only `GOOS` and `GOARCH` set, and the Homebrew formula `packaging/homebrew/okf-cli.rb` calls it too); `go version go1.27.0-X:nodwarf5 linux/amd64`; `go/bin/okf` 21,576,669 bytes, sha256 `5bf685d173ea46abbfe99df8340c47e43babb3d6e0c80dcea40db481cb4b23d5`; YAML parser `go.yaml.in/yaml/v3 v3.0.5` |
| Python CLI | Python 3.14.6 (mise), ruamel.yaml 0.19.1, argcomplete 3.7.2, uv 0.12.10; launched as `uv run --script cli/okf-cli.py` (what `okft` and `just golden` use) and as `/tmp/k-ev/pyenv/bin/python cli/okf-cli.py` (venv with the same dependencies, no uv in the start path, comparable to the installed wrapper) |
| Machine | `devt`: AMD Ryzen 9 9950X (16 cores, 32 threads), Linux 7.2.5-3-omarchy x86_64, governor `performance`, `/tmp` on tmpfs; no CPU-bound process in `top` before the timing runs; load average 1.45 before the first and 1.67 after the last round |
| Network | every `okf` call outside the golden harness ran under `unshare -rn` (empty network namespace) with `VOYAGE_API_KEY` unset; devt has a live Ollama on 11434 and a `VOYAGE_API_KEY` in its login environment, neither was reachable; golden runs use the harness's own seccomp block (R-06) |
| Frozen copies | made once, timestamp `20261016T144645Z` (copy window 14:46:45Z–14:46:48Z): `rsync -a` from the Mac of `~/Obsidian/Knowledge-Catalogue` (181 MB with `.git`, 121 MB without), `dev-okf` (`~/dev/meta/PRG_projekt-registry/dev-okf`, 3 files), `sproutling-okf` (`~/dev/prod/SPF_sproutling/sproutling-okf`, 116 `.md`) and `home-lab-wiki` (a bundle mounted in the Knowledge-Catalogue), plus the `.git` directories of the three workspace repos that hold these bundles (`PRG_projekt-registry`, `SPF_sproutling`, `HLO_home_lab_ops`), so that git-dependent commands see each bundle's history. The master copy equals the pre-copy checksum manifest (manifest sha256 `1883579f8dea9ce628164e6cac6751f40e1c246d76ed460d0d8b66dde0e3b296`: 8,252 files, 3 symlinks, 224,038,905 bytes). One copy per implementation was made from the master with `cp -a` |
| Points outside the roots | the Knowledge-Catalogue holds three absolute symlinks (`dev-okf`, `sproutling-okf`, `home-lab-wiki`) to Mac paths; in the copies they were re-pointed to the sibling copies. The workspace file `SPF_sproutling/.okf.toml` (absolute Mac paths `kc_root`, `types_source`) was not copied and lies outside `--root`; with `--root` on the `sproutling-okf` copy both implementations print the same note `carries no catalogue marker` (§4.1) |
| Scratch | all scratch (`/tmp/k-cat`, `/tmp/k-ev`) was deleted after the run; this report carries the evidence |

## 2. Block 1: golden run and deviation list

### 2.1 Harness runs

```text
$ just golden                      # Python CLI: uv run --no-project --with-requirements cli/okf-cli.py python tests/okf_golden.py
0 of 314 cases differ

$ just golden --cmd go/bin/okf
21 of 314 cases differ: check-all check-strict check-json check-strict-json check-bundle check-ignore-exact check-types check-types-registry-other check-types-missing merge-tags-dry merge-tags-apply merge-tags-multi merge-tags-unregistered-target merge-tags-no-match remove-tags-dry remove-tags-apply remove-tags-multi remove-tags-no-match normalize-tags-dry normalize-tags-apply verify-broken-yaml

$ just golden --cmd "env PATH=/tmp/k-ev/nopy-bin $PWD/go/bin/okf"     # child PATH: symlinks to the /usr/bin tools; no python*, no uv*, no pip*
21 of 314 cases differ: check-all check-strict check-json check-strict-json check-bundle check-ignore-exact check-types check-types-registry-other check-types-missing merge-tags-dry merge-tags-apply merge-tags-multi merge-tags-unregistered-target merge-tags-no-match remove-tags-dry remove-tags-apply remove-tags-multi remove-tags-no-match normalize-tags-dry normalize-tags-apply verify-broken-yaml
```

The two Go logs are byte-identical after removing the recipe and time lines: the same set of deviating cases and the same diff text (criterion 6); `env -i PATH=<that dir> sh -c 'command -v python python3 uv'` finds nothing. Differing channel: stdout in 20 cases, stderr in `verify-broken-yaml`; exit code and file-tree effect differ in none. All 21 are the one cause D-01. `--update` was never run.

### 2.2 Deviation entries

77 entries: D-01 from the golden run, D-02 to D-77 found by direct runs of the Go binary against the Python CLI outside the golden cases (differential sweeps on constructed inputs and on production-data copies; sizes and matrices in §2.6). Within each area the `no` entries come first (the order of K's run: D-02, D-41, D-42 and D-61 were fixed afterwards, answer `yes`, and keep their place). Per entry: cases, channel, difference with a Python and a Go excerpt, reason, capability answer with evidence, owner, reproduce line, empty PO decision. A `Fixed in` line (OKFT-8dnw, after the run) follows the answer of the four fixed entries.

### Area G. Golden run


#### D-01 YAML parse-error wording of `handbook/broken-yaml.md` in 21 golden cases
- **Cases (21):** `check-all`, `check-strict`, `check-json`, `check-strict-json`, `check-bundle`, `check-ignore-exact`, `check-types`, `check-types-registry-other`, `check-types-missing`, `merge-tags-dry`, `merge-tags-apply`, `merge-tags-multi`, `merge-tags-unregistered-target`, `merge-tags-no-match`, `remove-tags-dry`, `remove-tags-apply`, `remove-tags-multi`, `remove-tags-no-match`, `normalize-tags-dry`, `normalize-tags-apply`, `verify-broken-yaml`
- **Channel:** stdout in 20 cases (`check*`: the `okf/frontmatter/parseable` finding text and its `message` in `--json`; `merge-tags-*`, `remove-tags-*`, `normalize-tags-*`: the `unparseable ...` line); stderr in `verify-broken-yaml` (the error line). Exit code and file-tree effect are equal in all 21 cases; each case differs in exactly one line.
- **Difference:** only the text and the position of the YAML parser's own diagnostic differ. The fixture `handbook/broken-yaml.md` holds `title: [unclosed` on line 3 and `description: this frontmatter is not valid YAML` on line 4. ruamel names the token where it gives up (line 4, column 12, the colon of `description:`); yaml.v3 names the unclosed flow list (line 3, column 9).
```text
Python/golden (check-all, stdout): ERROR    okf/frontmatter/parseable handbook/broken-yaml.md  (no parseable frontmatter: expected ',' or ']', but got ':' (line 4, column 12))
Go            (check-all, stdout): ERROR    okf/frontmatter/parseable handbook/broken-yaml.md  (no parseable frontmatter: did not find expected ',' or ']' (line 3, column 9))
Python/golden (merge-tags-dry):    unparseable    handbook/broken-yaml.md  (frontmatter does not parse: expected ',' or ']', but got ':' (line 4, column 12) — skipped)
Go            (merge-tags-dry):    unparseable    handbook/broken-yaml.md  (frontmatter does not parse: did not find expected ',' or ']' (line 3, column 9) — skipped)
Python/golden (verify-broken-yaml, exit 2, stderr): frontmatter does not parse: expected ',' or ']', but got ':' (line 4, column 12)
Go            (verify-broken-yaml, exit 2, stderr): frontmatter does not parse: did not find expected ',' or ']' (line 3, column 9)
```
- **Reason:** ruamel.yaml (Python) and `go.yaml.in/yaml/v3` (Go) word and locate parse errors differently. The golden harness neutralises only the argparse usage text and the network-error detail (D07, D08), not YAML parser text, so the 21 goldens pin ruamel's sentence. The rule `okf/frontmatter/parseable`, its severity, its place among the findings and the skip rule of the tag verbs are the same.
- **Capability preserved:** yes. Both implementations report the same file under the same rule with the same severity and exit code (4 for `check`, 2 for `verify`), skip the same file in the tag verbs, and point at the defective list in the file. The parsers also agree on which files do not parse: the corpus run (§3) shows 0 files that one parser reads and the other refuses over 674 + 6,950 + 60 files (86 + 6 are refused by both). The same cause with other inputs is D-39.
- **Owner:** Go core and read side (F: OKFT-daut)
- **Reproduce:** `just golden --cmd go/bin/okf` (summary line in §2.1); a single case: `just golden --cmd go/bin/okf --only check-all`
- **PO decision:**

### Area A. Frontmatter writer: refusals, wrong writes, kept formatting

**Go frontmatter line-patch writer (yamlpatch) against Python's ruamel round-trip writer**

Evidence of work package K (OKFT-8dnw), area: refusals and kept formatting of the frontmatter writer. No code was changed. Entries with capability `no` come first, then `yes`; 9a to 9e and 7a/7b split one cause each by kind.
Fixture F of every Reproduce line: an empty directory holding `.okf.toml`, `TYPES.md`, `TAGS.md`, `PROPERTIES.md`, `SPEC.md` copied from `tests/golden/catalogue/`; `okf` is `python cli/okf-cli.py` or `go/bin/okf`, run as `env -u VOYAGE_API_KEY unshare -rn okf --root . <args>`; `(git)` = `git init`, `git add -A`, one commit first.
A Cases item reads `label: file text, command`. The file text is a Python string literal of the whole `w/x.md` without the frame `'---\ntype: Concept\n'` ... `'---\n# T\nbody\n'` when the file has that frame, else of the whole file. Excerpts show `w/x.md` as a Python string literal; `at: …Z` times written by `verify` are the time of each run, so the Python and Go lines differ in them.

#### D-02 `verify` writes a second frontmatter block (wrong data, exit 0) when the file has CR-only line breaks; the tag verbs refuse the same files
- **Cases:** e1b: '---\rtype: Concept\rtags: [a, b]\r---\r# T\rbody\r', verify w/x --by human:me; e8: '---\ntype: Concept\ntags: [a, b]\r---\nbody\n', verify w/x --by human:me;
  e10: the e1b file, verify w/x --by human:me, then read w/x and list --where 'type = Concept' --json; e1: '---\rtype: Concept\rtags: [a, b]\r---\r# T\rbody\r', merge-tags a --into c --apply;
  e8b: '---\ntype: Concept\ntags: [a, b]\r---\nbody\n', merge-tags a --into c --apply; e9: '---\rtype: Concept\rtags: [a, b]\r---\r# T\rbody\r', remove-tags a --apply; e9b: '---\rtype: Concept\rtags: [a, b]\r---\r# T\rbody\r', normalize-tags --apply
- **Channel:** file-tree effect (verify exits 0 and prints its success line); exit code and stderr (merge-tags, remove-tags, normalize-tags)
- **Difference:** Python appends `verified` to the original block and writes LF. Go exits 0 but writes a new block in front of the whole old text, so the old block becomes body text and the concept loses its `type` and
  `tags` for every reader. The tag verbs exit 2 on the same files, with a reason that is not true for them.
```text
Python (exit 0): verify w/x --by human:me -> w/x.md = '---\ntype: Concept\ntags: [a, b]\nverified:\n  - by: human:me\n    at: 2026-10-16T15:26:10Z\n---\n# T\nbody\n'
Python (exit 0): list --where 'type = Concept' --json -> {"command": "list", "ok": true, "data": [{"title": "x", "type": "Concept", "path": "w/x", "description": "", "tier": "human-reviewed", "stale": false}], "warnings": [], "error": null}
Python (exit 0): merge-tags a --into c --apply -> w/x.md = '---\ntype: Concept\ntags: [c, b]\n---\n# T\nbody\n'
Go (exit 0): verify w/x --by human:me -> w/x.md = '---\nverified:\n  - by: human:me\n    at: 2026-10-16T15:26:10Z\n---\n---\rtype: Concept\rtags: [a, b]\r---\r# T\rbody\r'
Go (exit 0): list --where 'type = Concept' --json -> {"command": "list", "ok": true, "data": [], "warnings": [], "error": null}
Go (exit 2): merge-tags a --into c --apply -> stderr: w/x.md: the key "tags" is not in the frontmatter (w/x.md unchanged)
```
- **Reason:** Python: `cmd_verify` reads with `read_file` (universal newlines), finds the block and writes `render_frontmatter` output with LF. Go: `runVerify` (check/verify.go) decides on
  `frontmatter.Read(catalogue.DecodeText(stored))` but runs `yamlpatch.Apply` on the stored bytes, where `newPatcher` sees no block and takes its create-a-block path, so `AppendItem` writes a new block
  in front of the old text and the read-back guard accepts it. The tag verbs (tagwrite `patch`) also select on the decoded text and patch the stored text, so `yamlpatch.target` reports `tags` as
  missing.
- **Capability preserved:** yes, since `0a14338` (K's run: no). K's finding, kept: Python writes correct data (file converted to LF, `verified` appended to the original block). Go exits 0 and prints the success line, but afterwards the concept has no `type` and no `tags` for any
  reader (`list --where 'type = Concept'` finds nothing); the tag verbs exit 2 on files Python rewrites correctly. Only workaround: convert the line endings by hand first.
- **Fixed in `0a14338` (2026-10-16):** `yamlpatch.newPatcher` (the one entry of every writer verb) no longer takes the create-a-block path when Python finds a block that `frontmatter.Read` (LF only) does not: a lone CR in front of the closing delimiter, which is every
  line break of a CR-only file, now gives the refusal of the other lone-CR cases (R-04, same class as D-03). Fixture F, `w/x.md = '---\rtype: Concept\rtags: [a, b]\r---\r# T\rbody\r'`: `verify w/x --by human:me` before exit 0, `verified w/x by human:me at ...`, `w/x.md` =
  `'---\nverified:\n  - by: human:me\n    at: 2026-10-16T16:35:35Z\n---\n---\rtype: Concept\r...'`, `list --where 'type = Concept' --json` `data: []`; after exit 2, stderr `the frontmatter holds a carriage return that does not end a line`, `w/x.md` byte-identical, `list` finds `w/x`.
  The e8 file (`'---\ntype: Concept\ntags: [a, b]\r---\nbody\n'`) gives the same. `merge-tags a --into c --apply`, `remove-tags a --apply` and `normalize-tags --apply` on both files: exit 2 as before, stderr now `w/x.md: the frontmatter holds a carriage return that does not
  end a line` (before: `the key "tags" is not in the frontmatter`), file byte-identical. `migrate --apply` skips a CR-only file in both Go builds, as Python's `migrate` does (it reads verbatim). Python still converts the file to LF and writes; Go refuses (R-04). Test: four cases of
  `TestRejections` in `go/internal/yamlpatch/reject_test.go`, red on the old code, green now.
- **Owner:** Go frontmatter writer (F: OKFT-5lq2) + Go check and verify (F: OKFT-agws)
- **Reproduce:** printf -- '---\rtype: Concept\rtags: [a, b]\r---\r# T\rbody\r' > w/x.md && okf --root . verify w/x --by human:me && okf --root . list --where 'type = Concept' --json
  printf -- '---\ntype: Concept\ntags: [a, b]\r---\nbody\n' > w/x.md && okf --root . verify w/x --by human:me
- **PO decision:**

#### D-03 A lone CR that ends a line inside an LF frontmatter: Go refuses the edit, Python converts the CR to LF and writes
- **Cases:** e2c: '---\ntype: Concept\rdescription: d\ntags: [a, b]\n---\n# T\nbody\n', merge-tags a --into c --apply; e7: '---\ntype: Concept\rdescription: d\ntags: [a, b]\n---\n# T\nbody\n', verify w/x --by human:me;
  e13: '---\ntype: Concept\rstatus: todo\n---\n# T\nbody\n', migrate --apply (git)
- **Channel:** exit code, stderr, file-tree effect
- **Difference:** Python re-dumps the block, so a lone CR that ends a line becomes an LF and the edit is written. Go exits 2 and leaves the file unchanged.
```text
Python (exit 0): merge-tags a --into c --apply -> w/x.md = '---\ntype: Concept\ndescription: d\ntags: [c, b]\n---\n# T\nbody\n'
Python (exit 0): merge-tags a --into c --apply -> stdout ends: merge-tags: 1 file(s) rewrote, 0 unparseable — a -> c
Python (exit 0): verify w/x --by human:me -> stdout: verified w/x by human:me at 2026-10-16T15:26:11Z
Python (exit 0): migrate --apply -> stdout ends: migrate: migrated 1 file(s), 0 unresolved
Go (exit 2): merge-tags a --into c --apply -> stderr: w/x.md: the frontmatter holds a carriage return that does not end a line
Go (exit 2): verify w/x --by human:me -> stderr: the frontmatter holds a carriage return that does not end a line
Go (exit 2): migrate --apply -> stderr: w/x.md: the frontmatter holds a carriage return that does not end a line
Go (exit 2): w/x.md after the run (unchanged) = '---\ntype: Concept\rdescription: d\ntags: [a, b]\n---\n# T\nbody\n'
```
- **Reason:** Go: `yamlpatch.newPatcher` refuses a CR that is not part of CRLF (`hasBareCR`), because its line model splits at LF only. Python: `render_frontmatter` re-dumps the whole mapping that `read_file`
  loaded with universal newlines.
- **Capability preserved:** no. Python's result is valid and data-intact; Go cannot do this edit on such a file. Workaround: replace the lone CR by an LF by hand. In a catalogue-wide verb one such file also aborts the other
  files (entry 7a, 7b).
- **Owner:** Go frontmatter writer (F: OKFT-5lq2)
- **Reproduce:** printf -- '---\ntype: Concept\rdescription: d\ntags: [a, b]\n---\n# T\nbody\n' > w/x.md && okf --root . merge-tags a --into c --apply
- **PO decision:**

#### D-04 A frontmatter whose root is a flow mapping (or `~`/`null`, `--- {}`, `{ }`): Go refuses, Python writes
- **Cases:** a1: '---\n{type: Concept, tags: [a, b]}\n---\n# T\nbody\n', merge-tags a --into c --apply; a2: '---\n{type: Concept, tags: [a, b]}\n---\n# T\nbody\n', remove-tags a --apply;
  a3: '---\n{type: Concept, tags: [a, b]}\n---\n# T\nbody\n', normalize-tags --apply; a4: '---\n{type: Concept, tags: [a, b]}\n---\n# T\nbody\n', verify w/x --by human:me;
  a5: '---\n{type: Concept, status: todo, timestamp: 2025-01-01T00:00:00Z}\n---\n# T\nbody\n', migrate --apply (git); a8: '---\n{\n  type: Concept,\n  tags: [a, b]\n}\n---\n# T\nbody\n', merge-tags a --into c --apply;
  a9: '---\n{type: Concept, tags: [a]}\n---\n# T\nbody\n', remove-tags a --apply; a10: '---\n{type: Concept, tags: [a, b]}\n---\n# T\nbody\n', merge-tags a --into c --apply --json; n8: '---\n{type: Concept}\n---\n# T\nbody\n', verify w/x --by human:me;
  a7: '---\n{}  # c\n---\n# T\nbody\n', verify w/x --by human:me; n1: '--- {}\n---\n# T\n', verify w/x --by human:me; n2: '---\n{ }\n---\n# T\nbody\n', verify w/x --by human:me; n6: '---\n~\n---\n# T\nbody\n', verify w/x --by human:me;
  n7: '---\nnull\n---\n# T\nbody\n', verify w/x --by human:me
- **Channel:** exit code, stdout (empty in Go), stderr (with --json: the error envelope on stdout), file-tree effect
- **Difference:** Python keeps a non-empty flow root in flow style and writes the edit; an empty or null root becomes a block mapping. Go exits 2 and leaves the file unchanged; for `normalize-tags` Python makes no
  change (exit 0) where Go refuses.
```text
Python (exit 0): merge-tags a --into c --apply -> w/x.md = '---\n{type: Concept, tags: [c, b]}\n---\n# T\nbody\n'
Python (exit 0): verify w/x --by human:me -> w/x.md = '---\n{type: Concept, tags: [a, b], verified: [{by: human:me, at: 2026-10-16T15:26:07Z}]}\n---\n# T\nbody\n'
Python (exit 0): normalize-tags --apply -> stdout: normalize-tags: 0 file(s) rewrote, 0 unparseable
Python (exit 0): verify w/x --by human:me ('~' root) -> w/x.md = '---\nverified:\n  - by: human:me\n    at: 2026-10-16T15:26:15Z\n---\n# T\nbody\n'
Go (exit 2): merge-tags a --into c --apply -> stderr: w/x.md: the frontmatter is a flow mapping
Go (exit 2): verify w/x --by human:me -> stderr: the frontmatter is a flow mapping
Go (exit 2): normalize-tags --apply -> stderr: w/x.md: the frontmatter is a flow mapping
Go (exit 2): verify w/x --by human:me ('~' root) -> stderr: the patched frontmatter does not read: mapping values are not allowed in this context (line 3, column 9)
Go (exit 2): merge-tags a --into c --apply --json -> stdout: {"command": "merge-tags", "ok": false, "data": null, "warnings": [], "error": {"kind": "invalid_input", "code": 2, "message": "w/x.md: the frontmatter is a flow mapping"}}
```
- **Reason:** Go: `yamlpatch.ensurePairs` accepts a flow root only when it is an empty `{}` alone on its line, and a `~`/`null` root fails the read-back guard (`selfCheck`). Python: `read_frontmatter` keeps the
  CommentedMap with its flow style and `render_frontmatter` dumps it.
- **Capability preserved:** no. Python writes correct data for every input listed; Go refuses, and in `normalize-tags` refuses a file Python leaves alone. Workaround: rewrite the root as a block mapping by hand. Production
  exposure: 2 flow-root files, both reserved `index.md` files that no write verb reaches.
- **Owner:** Go frontmatter writer (F: OKFT-5lq2)
- **Reproduce:** printf -- '---\n{type: Concept, tags: [a, b]}\n---\n# T\nbody\n' > w/x.md && okf --root . merge-tags a --into c --apply
  printf -- '---\n~\n---\n# T\nbody\n' > w/x.md && okf --root . verify w/x --by human:me
- **PO decision:**

#### D-05 An anchor, alias or explicit tag on the edited value: Go refuses, Python writes
- **Cases:** b1: 'tags: &t [a, b]\nother: *t\n', merge-tags a --into c --apply; b2: 'x: &t [a, b]\ntags: *t\n', merge-tags a --into c --apply; b3: 'x: &t [a, b]\ntags: *t\n', remove-tags a --apply; b3b: 'tags: &t [a, b]\n', remove-tags a --apply;
  b3c: 'tags: &t [a, b]\n', merge-tags a --into c --apply; b8: 'tags: !!seq\n  - a\n  - b\n', merge-tags a --into c --apply; b9: 'x: &a a\ntags:\n  - *a\n  - b\n', merge-tags a --into c --apply;
  b10: 'tags:\n  - &a a\n  - b\nother: *a\n', merge-tags a --into c --apply; b14: 'tags: &t [a, b]\nother: *t\n', normalize-tags --apply; b14b: 'tags: &t [a, b]\n', normalize-tags --apply;
  b11: 'verified: &v {by: human:x, at: 2026-01-01T00:00:00Z}\nref: *v\n', verify w/x --by human:me; b11b: 'verified: &v\n  - by: human:x\n    at: 2026-01-01T00:00:00Z\n', verify w/x --by human:me;
  b4: 'status: &s todo\nother: *s\n', migrate --apply (git); b4b: 'status: &s todo\n', migrate --apply (git); b5: 'timestamp: &ts 2025-01-01T00:00:00Z\nother: *ts\n', migrate --apply (git);
  b5b: 'other: &ts 2025-01-01T00:00:00Z\ntimestamp: *ts\n', migrate --apply (git); b7: 'tags:\n  - !!str a\n  - b\n', merge-tags a --into c --apply;
  controls, same result in both (anchor or tag on another key): b6: 'description: &x text\ntitle: *x\ntags: [a, b]\n', merge-tags a --into c --apply; b6b: 'description: &x text\ntitle: *x\ntags: [a, b]\n', verify w/x --by human:me; b13: 'title: !!str x\ntags: [a, b]\n', merge-tags a --into c --apply
- **Channel:** exit code, stderr, file-tree effect
- **Difference:** ruamel resolves anchors and aliases itself, so Python writes the edit; with a second alias user the edit changes both, by YAML semantics, and a tagged tags item (`- !!str a`) is silently ignored (exit
  0, nothing written). Go exits 2 with one text for every case.
```text
Python (exit 0): b3c merge-tags -> w/x.md = '---\ntype: Concept\ntags: [c, b]\n---\n# T\nbody\n'
Python (exit 0): b10 merge-tags -> w/x.md = '---\ntype: Concept\ntags:\n  - c\n  - b\nother: &a a\n---\n# T\nbody\n'
Python (exit 0): b1 merge-tags -> w/x.md = '---\ntype: Concept\ntags: &t [c, b]\nother: *t\n---\n# T\nbody\n'
Python (exit 0): b4 migrate --apply -> w/x.md = '---\ntype: Concept\nstatus: draft\nother: &s todo\n---\n# T\nbody\n'
Python (exit 0): b7 merge-tags -> w/x.md unchanged; stdout: merge-tags: 0 file(s) rewrote, 0 unparseable — a -> c
Go (exit 2): b1 to b5b, b7: stderr: w/x.md: the value of a key carries an anchor, an alias or an explicit tag (w/x.md unchanged)
Go (exit 2): b11, b11b verify: stderr: the value of a key carries an anchor, an alias or an explicit tag (no path prefix)
```
- **Reason:** Go: `yamlpatch.target` runs `plainTree` over the key and value nodes and refuses any anchor, alias or explicit tag, because a line patch would change every alias. Python: `tags._retag`, `cmd_verify`
  and `migrate._plan` assign into the loaded ruamel structure and ruamel re-dumps anchors and tags.
- **Capability preserved:** no. Python writes valid data in every case; Go cannot do any of these edits. Where an alias user follows the edit (b1, b2, b3, b11, b14) Python also changes a second key; whether that is wanted is a
  PO question. Workaround: remove the anchor or tag by hand. Production: 0 files carry an anchor, alias or explicit tag.
- **Owner:** Go frontmatter writer (F: OKFT-5lq2)
- **Reproduce:** printf -- '---\ntype: Concept\ntags: &t [a, b]\n---\n# T\nbody\n' > w/x.md && okf --root . merge-tags a --into c --apply
  printf -- '---\ntype: Concept\nstatus: &s todo\nother: *s\n---\n# T\nbody\n' > w/x.md && git init -q && git add -A && git -c user.name=G -c user.email=g@example.org commit -qm x && okf --root . migrate --apply
- **PO decision:**

#### D-06 A comment inside a multi-line flow list: Go refuses, Python writes (and drops the comment)
- **Cases:** c1: 'tags: [a, # c\n  b]\nz: 1\n', merge-tags a --into c --apply; c2: 'tags: [a, # c\n  b]\nz: 1\n', remove-tags a --apply; c3: 'tags: [a, # c\n  b]\nz: 1\n', normalize-tags --apply; c6: 'tags: [b, # c\n  a]\nz: 1\n', merge-tags a --into c --apply;
  c8: 'tags: [a, b,\n  # c\n  d]\nz: 1\n', merge-tags a --into c --apply;
  controls: c4: 'tags: [a,\n  b]\nz: 1\n', merge-tags a --into c --apply (both write, entry 9b); c7: 'tags: [a, b] # c\nz: 1\n', merge-tags a --into c --apply (comment after the closing bracket: identical)
- **Channel:** exit code, stderr, file-tree effect
- **Difference:** Python re-dumps the list: `merge-tags` and `remove-tags` write the new list and silently drop the comment; `normalize-tags` writes the block list and keeps the comment on a line of its own. Go exits 2
  and leaves the file unchanged.
```text
Python (exit 0): merge-tags a --into c --apply -> w/x.md = '---\ntype: Concept\ntags: [c, b]\nz: 1\n---\n# T\nbody\n'
Python (exit 0): remove-tags a --apply -> w/x.md = '---\ntype: Concept\ntags: [b]\nz: 1\n---\n# T\nbody\n'
Python (exit 0): normalize-tags --apply -> w/x.md = '---\ntype: Concept\ntags:\n  - a\n          # c\n  - b\nz: 1\n---\n# T\nbody\n'
Go (exit 2): c1, c2, c3, c6, c8: stderr: w/x.md: a comment sits inside a flow list (w/x.md unchanged)
```
- **Reason:** Go: `yamlpatch.scanFlow` (lines.go) refuses a flow list that holds a `#` comment, because a patch cannot place the comment safely. Python: ruamel re-dumps the list.
- **Capability preserved:** no. The data Python writes is correct in all five cases, but `merge-tags` and `remove-tags` silently delete the user's comment. If the PO counts that loss as damage, Go's refusal keeps the capability
  for c1, c2, c6 and c8; for c3 (`normalize-tags` keeps the comment) the answer stays no. Production: 0 files.
- **Owner:** Go frontmatter writer (F: OKFT-5lq2)
- **Reproduce:** printf -- '---\ntype: Concept\ntags: [a, # c\n  b]\nz: 1\n---\n# T\nbody\n' > w/x.md && okf --root . merge-tags a --into c --apply
- **PO decision:**

#### D-07 Other shapes the line patcher cannot patch (null item, folded item, value after the dash, complex key, flow list on the next line, multi-line flow `verified`): Go refuses, Python writes
- **Cases:** t13: 'tags:\n  - a\n  -\n  - b\n', merge-tags a --into c --apply; t17: 'tags:\n  - >-\n    a\n  - b\n', merge-tags a --into c --apply; k13: 'tags:\n  -\n    a\n  - b\n', merge-tags a --into c --apply;
  v16: 'verified:\n  -\n    by: human:x\n    at: 2026-01-01T00:00:00Z\n', verify w/x --by human:me; v07: 'verified: {by: human:x,\n  at: 2026-01-01T00:00:00Z}\n', verify w/x --by human:me; t35: '? tags\n: [a, b]\n', normalize-tags --apply;
  f14: 'tags: ["a\n  b", a]\n', normalize-tags --apply; f15: 'tags:\n  [a, b]\n', normalize-tags --apply; k04: '? tags\n:\n  - a\n', remove-tags a --apply
- **Channel:** exit code, stderr, file-tree effect
- **Difference:** Python re-dumps the whole block and writes a valid result for all nine inputs. Go exits 2, each time with the text of the patch rule it lacks, and leaves the file unchanged.
```text
Python (exit 0): t13 merge-tags -> w/x.md = '---\ntype: Concept\ntags:\n  - c\n  - \n  - b\n---\n# T\nbody\n'
Python (exit 0): t17 merge-tags -> w/x.md = '---\ntype: Concept\ntags:\n  - >-\n    c\n  - b\n---\n# T\nbody\n'
Python (exit 0): v07 verify -> w/x.md = '---\ntype: Concept\nverified:\n  - {by: human:x, at: 2026-01-01T00:00:00Z}\n  - by: human:me\n    at: 2026-10-16T15:26:15Z\n---\n# T\nbody\n'
Python (exit 0): t35 normalize-tags -> w/x.md = '---\ntype: Concept\ntags:\n  - a\n  - b\n---\n# T\nbody\n'
Go (exit 2): t13 -> w/x.md: list item 1 does not start behind its dash
Go (exit 2): t17 -> w/x.md: item 0 of "tags" is not a plain or quoted scalar
Go (exit 2): k13 -> w/x.md: list item 0 does not start behind its dash
Go (exit 2): v16 -> the last list item does not start behind its dash
Go (exit 2): v07 -> a flow mapping over several lines cannot become a list
Go (exit 2): t35 -> w/x.md: the flow list of "tags" does not start on its key line; f15 -> w/x.md: the flow list of "tags" does not start on its key line
Go (exit 2): f14 -> w/x.md: an item of the flow list of "tags" spans several lines
Go (exit 2): k04 -> w/x.md: the key "tags" is written in a form that is not patched
```
- **Reason:** Go: `yamlpatch/ops.go` patches only lines it can locate: `dashOf` and `appendBlock` need the item text on the dash line, `renameItem` takes plain or quoted scalars, `flowToBlock` needs the list on the
  key line with one-line items, `colonOf` needs a simple `key:` form, `flowMapToList` refuses a multi-line flow mapping. Python: `render_frontmatter` re-dumps the whole block.
- **Capability preserved:** no. Python's result is valid and data-correct for all nine inputs; Go cannot do these edits. Workaround: rewrite the item or key in the plain form by hand. Production: 0 files.
- **Owner:** Go frontmatter writer (F: OKFT-5lq2)
- **Reproduce:** printf -- '---\ntype: Concept\ntags:\n  - a\n  -\n  - b\n---\n# T\nbody\n' > w/x.md && okf --root . merge-tags a --into c --apply
  printf -- '---\ntype: Concept\nverified: {by: human:x,\n  at: 2026-01-01T00:00:00Z}\n---\n# T\nbody\n' > w/x.md && okf --root . verify w/x --by human:me
- **PO decision:**

#### D-08 One refused file ends the whole run of `merge-tags`, `remove-tags` and `normalize-tags` (dry-run included): nothing is previewed or written for the other files
- **Cases:** fixture T (w/a1..a7, see Reproduce): a2 is refused by Go; a4 broken YAML, a5 not UTF-8, a6 `tags: a, b` are skipped in both;
  f1 merge-tags a --into c; f1b ... --apply; f1c ... --apply --json; f1d ... --apply --where 'path != w/a2'; f2 remove-tags a; f2b ... --apply; f2c ... --apply --where 'path != w/a2'; f3 normalize-tags; f3b ... --apply;
  fixture N (a1 'tags: [a, b]', a2 'tags: [a, # c' newline 'b]', a3 'tags: [x, y]', a7 'tags: [p, q]'): f3c normalize-tags --apply; f3d ... --apply --where 'path != w/a2';
  f5 on fixture M of entry 7b: verify w/a2 --by human:me (refused), then verify w/a1 --by human:me;
  fixture W (a1 and a5 fine; a2 flow root, a3 'tags: &t [a, b]' + 'other: *t', a4 comment in a flow list): g1 merge-tags a --into c --apply; g1b ... --where 'path != w/a2'; g1c ... --where 'path in (w/a1, w/a5)';
  fixture H (a2 with tags items '- !!str a', '- b'; a1, a3 plain): h1 merge-tags a --into c --apply; h2 remove-tags a --apply; h3 normalize-tags --apply with a2 as flow-mapping root (Python: no change)
- **Channel:** exit code, stdout, stderr, file-tree effect
- **Difference:** When one file of the catalogue is refused, Go ends the run at the first refused file: exit 2, empty stdout (no diff, no `unparseable` list, no summary), also in the dry-run, and no file is written
  (sha256 of every file unchanged, no partial state). Python exits 0, prints all diffs and, with `--apply`, writes every rewritable file.
```text
Python (exit 0): merge-tags a --into c --apply -> changed: w/a1.md w/a2.md w/a3.md w/a7.md; stdout ends: merge-tags: 4 file(s) rewrote, 3 unparseable — a -> c
Python (exit 0): merge-tags a --into c (dry-run) -> stdout ends: merge-tags: 4 file(s) would rewrite, 3 unparseable — a -> c
Python (exit 0): normalize-tags --apply (fixture N) -> changed: w/a1.md w/a2.md w/a3.md w/a7.md; stdout ends: normalize-tags: 4 file(s) rewrote, 0 unparseable
Go (exit 2): merge-tags a --into c --apply -> changed: no file; stdout 0 bytes; stderr: w/a2.md: the frontmatter is a flow mapping
Go (exit 2): merge-tags a --into c (dry-run) -> stdout 0 bytes; stderr: w/a2.md: the frontmatter is a flow mapping
Go (exit 2): merge-tags a --into c --apply --json -> stdout: {"command": "merge-tags", "ok": false, "data": null, "warnings": [], "error": {"kind": "invalid_input", "code": 2, "message": "w/a2.md: the frontmatter is a flow mapping"}}
Go (exit 2): normalize-tags --apply (fixture N) -> changed: no file; stderr: w/a2.md: a comment sits inside a flow list
Go (exit 2): three refused files: stderr names only the first: w/a2.md: the frontmatter is a flow mapping; after --where 'path != w/a2': w/a3.md: the value of a key carries an anchor, an alias or an explicit tag
Go (exit 0): merge-tags a --into c --apply --where 'path != w/a2' -> changed: w/a1.md w/a3.md w/a7.md (Python: w/a1.md w/a3.md w/a7.md)
```
- **Reason:** Go, by design (package comment of tagwrite/common.go: a file the writer rejects ends the whole run before the first write): `patch()` (tagverbs.go) returns the first `*yamlpatch.Rejection` through
  `patchError`, so `writeResult` never runs. Python: `_retag` and `render_frontmatter` cannot refuse and `_write_result` writes the whole plan.
- **Capability preserved:** no. Go aborts valid work on the other files (rewrite and preview), dry-run included, and names only the first refused file per run. Workaround: `--where 'path != <file>'` gives the same files as
  Python (f1d, f2c, f3d), but the user must find every refused file. `verify` takes one concept, so a refusal has no catalogue-wide effect (f5). Production: 0 refused files.
- **Owner:** Go tag and frontmatter writes (F: OKFT-dkdu) + Go frontmatter writer (F: OKFT-5lq2)
- **Reproduce:** mkdir -p w; printf -- '---\ntype: Concept\ntags: [a, b]\n---\n# a1\n' > w/a1.md; printf -- '---\n{type: Concept, tags: [a, b]}\n---\n# a2 REFUSED BY GO\n' > w/a2.md; printf -- '---\ntype: Concept\ntags:\n  - a\n  - z\n---\n# a3\n' > w/a3.md
  okf --root . merge-tags a --into c --apply     # also a4 broken YAML, a5 not UTF-8, a6 'tags: a, b', a7 as a1 (see cases above)
- **PO decision:**

#### D-09 One refused file ends the whole `migrate` run (dry-run included): no plan is previewed or written for the other files
- **Cases:** fixture M (git; w/a1, a3, a7 'status: todo'; a2 '{type: Concept, status: todo}'): f4 migrate; f4b migrate --apply; f4c migrate w --apply; f4d migrate --json;
  fixture S (git; w/top.md, w/sub1/ok1.md, w/sub2/ok2.md 'status: todo'; w/sub1/refused.md '{type: Concept, status: todo}'): g2 migrate w/sub2 --apply; g2b migrate w --apply; g2c migrate w/sub1 --apply
- **Channel:** exit code, stdout, stderr, file-tree effect
- **Difference:** `migrate` behaves like the tag verbs: the first refused file ends the plan, dry-run included, and nothing is written. Python migrates every other file.
```text
Python (exit 0): migrate --apply (fixture M) -> changed: w/a1.md w/a2.md w/a3.md w/a7.md; stdout ends: migrate: migrated 4 file(s), 0 unresolved
Python (exit 0): migrate (dry-run) -> stdout ends: migrate: would migrate 4 file(s), 0 unresolved; dry-run: re-run with --apply
Python (exit 0): migrate w --apply (fixture S) -> changed: w/sub1/ok1.md w/sub1/refused.md w/sub2/ok2.md w/top.md
Go (exit 2): migrate --apply (fixture M) -> changed: no file; stdout 0 bytes; stderr: w/a2.md: the frontmatter is a flow mapping
Go (exit 2): migrate (dry-run) -> stdout 0 bytes; stderr: w/a2.md: the frontmatter is a flow mapping
Go (exit 2): migrate w --apply (fixture S) -> changed: no file; stderr: w/sub1/refused.md: the frontmatter is a flow mapping
Go (exit 2): migrate w/sub1 --apply -> changed: no file
Go (exit 0): migrate w/sub2 --apply -> changed: w/sub2/ok2.md (Python: w/sub2/ok2.md)
```
- **Reason:** Go: `planMigrate` and `concept` (tagwrite/migrate.go) return the first rejection, so `diffs.WritePlan` never runs. Python: `_plan` cannot refuse and `cmd_migrate` writes its plan.
- **Capability preserved:** no. Go aborts the whole migration, dry-run included. `migrate` has no `--where`: only a directory target avoids the refused file (g2 works), so files in the same tree (w/top.md, w/sub1/ok1.md) cannot
  be migrated until the refused file is fixed by hand. Production: 0 refused files.
- **Owner:** Go tag and frontmatter writes (F: OKFT-dkdu) + Go frontmatter writer (F: OKFT-5lq2)
- **Reproduce:** mkdir -p w/sub1 w/sub2; printf -- '---\ntype: Concept\nstatus: todo\n---\n# top\n' > w/top.md; printf -- '---\n{type: Concept, status: todo}\n---\n# refused\n' > w/sub1/refused.md; printf -- '---\ntype: Concept\nstatus: todo\n---\n# ok1\n' > w/sub1/ok1.md; printf -- '---\ntype: Concept\nstatus: todo\n---\n# ok2\n' > w/sub2/ok2.md
  git init -q && git add -A && git -c user.name=G -c user.email=g@example.org commit -qm x; okf --root . migrate w --apply
- **PO decision:**

#### D-10 A stored text that is not valid UTF-8: Go `verify` refuses, Python writes U+FFFD over the invalid byte
- **Cases:** d1: b'---\ntype: Concept\ntags: [a, b]\n---\n# T\ncaf\xe9 body\n', verify w/x --by human:me; d2: b'---\ntype: Concept\ntags: [a, b]\ndescription: caf\xe9\n---\n# T\nbody\n', verify w/x --by human:me;
  d7: b'---\ntype: Concept\ntags: [a, b]\n---\n# T\ncaf\xe9 body\n', verify w/x --by human:me --json;
  controls, same result in both (the file is skipped): d3: b'---\ntype: Concept\ntags: [a, b]\n---\n# T\ncaf\xe9 body\n', merge-tags a --into c --apply; d4: b'---\ntype: Concept\ntags: [a, b]\ndescription: caf\xe9\n---\n# T\nbody\n', remove-tags a --apply; d5: b'---\ntype: Concept\ntags: [a, b]\n---\n# T\ncaf\xe9 body\n', normalize-tags --apply; d6: b'---\ntype: Concept\nstatus: todo\n---\n# T\ncaf\xe9 body\n', migrate --apply (git)
- **Further cases (second sweep, same cause: `verify` on a concept with non-UTF-8 bytes):**   - `printf -- '---\ntitle: Bin\ntype: Concept\ntags: [a]\n---\nbody \xff\xfe bad bytes\n' > handbook/binary.md`, then `verify handbook/binary --by human:x`
  - The same with `--json`
  - `read`, `find`, `list`, `check`, `toc`, `index`, `tags`, `recent`, `wikilinks`, `refs`, `info` on that file are identical in both (no traceback in Python)
- **Channel:** exit code, stderr (with --json: stdout), file-tree effect
- **Difference:** Python reads with `errors="replace"` and writes the decoded text back, so the invalid byte 0xE9 becomes U+FFFD (bytes EF BF BD) in the file. Go refuses before it patches and leaves the file unchanged.
```text
Python (exit 0): verify w/x --by human:me (byte in the frontmatter) -> w/x.md = '---\ntype: Concept\ntags: [a, b]\ndescription: caf�\nverified:\n  - by: human:me\n    at: 2026-10-16T15:26:10Z\n---\n# T\nbody\n'
Python (exit 0): verify w/x --by human:me (byte in the body) -> w/x.md = '---\ntype: Concept\ntags: [a, b]\nverified:\n  - by: human:me\n    at: 2026-10-16T15:26:10Z\n---\n# T\ncaf� body\n'
Go (exit 2): verify w/x --by human:me (byte in the frontmatter) -> stderr: the stored text is not valid UTF-8; w/x.md = b'---\ntype: Concept\ntags: [a, b]\ndescription: caf\xe9\n---\n# T\nbody\n'
Go (exit 2): verify w/x --by human:me --json -> stdout: {"command": "verify", "ok": false, "data": null, "warnings": [], "error": {"kind": "invalid_input", "code": 2, "message": "the stored text is not valid UTF-8"}}
```
- **Reason:** Python: `cmd_verify` reads with `read_file` (`errors="replace"`) and writes with `write_file`. Go: `yamlpatch.Apply` refuses a non-UTF-8 text before it patches (`the stored text is not valid UTF-8`);
  the tag verbs and `migrate` read the file verbatim in both implementations and skip it.
- **Capability preserved:** yes. Python writes corrupted data (the invalid byte is lost); refusing that input keeps the capability. The Go message names no file because `verify` takes one concept; the tag verbs and `migrate`
  skip such a file in both.
- **Owner:** Go check and verify (F: OKFT-agws) + Go frontmatter writer (F: OKFT-5lq2)
- **Reproduce:** printf -- '---\ntype: Concept\ntags: [a, b]\ndescription: caf\351\n---\n# T\nbody\n' > w/x.md && okf --root . verify w/x --by human:me
- **PO decision:**

#### D-11 Line endings: Go keeps CRLF as CRLF and the stored body; Python writes LF over the whole file (the deliberate OKFT-5lq2 deviation)
- **Cases:** e4: '---\r\ntype: Concept\r\ntags: [a, b]\r\n---\r\n# T\r\nbody\r\n', merge-tags a --into c --apply; e4b: '---\r\ntype: Concept\r\ntags: [a, b]\r\n---\r\n# T\r\nbody\r\n', verify w/x --by human:me;
  e4c: '---\r\ntype: Concept\r\ntags:\r\n  - a\r\n  - b\r\n---\r\n# T\r\nbody\r\n', remove-tags a --apply; e4d: '---\r\ntype: Concept\r\ntags: [a, b]\r\n---\r\n# T\r\nbody\r\n', normalize-tags --apply;
  e4e: '---\r\ntype: Concept\r\nstatus: todo\r\ntimestamp: 2025-01-01T00:00:00Z\r\n---\r\n# T\r\nbody\r\n', migrate --apply (git); e5: '---\r\ntype: Concept\r\ntags: [a, b]\r\n---\n# T\nbody\n', merge-tags a --into c --apply;
  e5b: '---\ntype: Concept\ntags: [a, b]\n---\n# T\r\nbody\r\n', merge-tags a --into c --apply; e3: '---\ntype: Concept\ntags: [a, b]\n---\n# T\nbo\rdy\n', merge-tags a --into c --apply
- **Channel:** file-tree effect; stdout (the diff printed by merge-tags, remove-tags, normalize-tags and migrate shows the same difference)
- **Difference:** Go keeps the file's own line endings and the stored body bytes; Python writes LF over the whole file and, for `migrate`, an LF frontmatter in front of a CRLF body, and it turns a lone CR in the body
  into LF. The frontmatter data is equal.
```text
Python (exit 0): e4 (merge-tags a --into c --apply) -> w/x.md = '---\ntype: Concept\ntags: [c, b]\n---\n# T\nbody\n'
Python (exit 0): e4e (migrate --apply (git)) -> w/x.md = "---\ntype: Concept\nstatus: draft\ngenerated:\n  by: human:golden\n  at: '2026-01-06T00:00:00+00:00'\n---\r\n# T\r\nbody\r\n"
Python (exit 0): e3 (merge-tags a --into c --apply) -> w/x.md = '---\ntype: Concept\ntags: [c, b]\n---\n# T\nbo\ndy\n'
Go (exit 0): e4 (merge-tags a --into c --apply) -> w/x.md = '---\r\ntype: Concept\r\ntags: [c, b]\r\n---\r\n# T\r\nbody\r\n'
Go (exit 0): e4e (migrate --apply (git)) -> w/x.md = "---\r\ntype: Concept\r\nstatus: draft\r\ngenerated:\r\n  by: human:golden\r\n  at: '2026-01-06T00:00:00+00:00'\r\n---\r\n# T\r\nbody\r\n"
Go (exit 0): e3 (merge-tags a --into c --apply) -> w/x.md = '---\ntype: Concept\ntags: [c, b]\n---\n# T\nbo\rdy\n'
```
- **Reason:** Go: `yamlpatch` writes new lines with the file's own ending (`p.eol`) and touches only the key's lines. Python: `render_frontmatter` re-dumps the mapping that `read_file` loaded with universal
  newlines, so CR and CRLF become LF in frontmatter and body.
- **Capability preserved:** yes. Both results load to the same frontmatter data under ruamel (checked for every case above): Go keeps what the author wrote, Python normalises it. The body is equal apart from line endings. For
  `migrate` Python writes a mixed-ending file; no capability is lost.
- **Owner:** Go frontmatter writer (F: OKFT-5lq2)
- **Reproduce:** printf -- '---\r\ntype: Concept\r\ntags: [a, b]\r\n---\r\n# T\r\nbody\r\n' > w/x.md && okf --root . merge-tags a --into c --apply
  printf -- '---\ntype: Concept\ntags: [a, b]\n---\n# T\nbo\rdy\n' > w/x.md && okf --root . merge-tags a --into c --apply
- **PO decision:**

#### D-12 Spacing, escapes and flow-list layout of untouched text: Go keeps what the author wrote, ruamel normalises
- **Cases:** s2a: '---\ntype:   Concept\ntitle:    spaced\ntags: [a, b]\n---\n# T\nbody\n', merge-tags a --into c --apply; s2b: 'tags:   [a ,   b]\n', merge-tags a --into c --apply; s2c: 'tags: [ a,b ,  z ]\n', remove-tags a --apply;
  s2e: 'fm: {a: 1,   b:   2}\ntags: [a, b]\n', merge-tags a --into c --apply; s7i: '---\n  type: Concept\n  tags: [a, b]\n---\n# T\nbody\n', merge-tags a --into c --apply;
  s3d: 'title: "caf\\u00e9 \\t tab"\ntags: [a, b]\n', merge-tags a --into c --apply; c4: 'tags: [a,\n  b]\nz: 1\n', merge-tags a --into c --apply; t44: 'tags: [a, b,]\n', merge-tags a --into c --apply
- **Channel:** file-tree effect; stdout (the diff printed by merge-tags, remove-tags, normalize-tags and migrate shows the same difference)
- **Difference:** Go keeps the spacing, escapes, indentation of the whole block and line breaks of flow lists the author wrote; ruamel normalises them (in production 24 files carry `generated: { by: …, at: … }` and
  differ only by this). The data is equal.
```text
Python (exit 0): s2a (merge-tags a --into c --apply) -> w/x.md = '---\ntype: Concept\ntitle: spaced\ntags: [c, b]\n---\n# T\nbody\n'
Python (exit 0): s2b (merge-tags a --into c --apply) -> w/x.md = '---\ntype: Concept\ntags: [c, b]\n---\n# T\nbody\n'
Python (exit 0): s2e (merge-tags a --into c --apply) -> w/x.md = '---\ntype: Concept\nfm: {a: 1, b: 2}\ntags: [c, b]\n---\n# T\nbody\n'
Python (exit 0): s3d (merge-tags a --into c --apply) -> w/x.md = '---\ntype: Concept\ntitle: "café \\t tab"\ntags: [c, b]\n---\n# T\nbody\n'
Go (exit 0): s2a (merge-tags a --into c --apply) -> w/x.md = '---\ntype:   Concept\ntitle:    spaced\ntags: [c, b]\n---\n# T\nbody\n'
Go (exit 0): s2b (merge-tags a --into c --apply) -> w/x.md = '---\ntype: Concept\ntags:   [c ,   b]\n---\n# T\nbody\n'
Go (exit 0): s2e (merge-tags a --into c --apply) -> w/x.md = '---\ntype: Concept\nfm: {a: 1,   b:   2}\ntags: [c, b]\n---\n# T\nbody\n'
Go (exit 0): s3d (merge-tags a --into c --apply) -> w/x.md = '---\ntype: Concept\ntitle: "caf\\u00e9 \\t tab"\ntags: [c, b]\n---\n# T\nbody\n'
```
- **Reason:** Go: `yamlpatch` rewrites only the lines of the targeted key in the stored text (package comment: every other byte stays). Python: `render_frontmatter` re-dumps the whole mapping through `YAML_RT`
  (indent mapping 2, sequence 4, offset 2, width 2**30).
- **Capability preserved:** yes. Both results load to the same frontmatter data under ruamel (checked for every case above): Go keeps what the author wrote, Python normalises it. In the production copies 24 of 654 rewritten
  files differ only in this way.
- **Owner:** Go frontmatter writer (F: OKFT-5lq2)
- **Reproduce:** printf -- '---\ntype:   Concept\ntitle:    spaced\ntags: [a, b]\n---\n# T\nbody\n' > w/x.md && okf --root . merge-tags a --into c --apply
  printf -- '---\ntype: Concept\nfm: {a: 1,   b:   2}\ntags: [a, b]\n---\n# T\nbody\n' > w/x.md && okf --root . merge-tags a --into c --apply
- **PO decision:**

#### D-13 Indentation of block lists and mappings: Go keeps the author's indentation, ruamel re-indents
- **Cases:** s5a: 'tags:\n- a\n- b\nz: 1\n', merge-tags a --into c --apply; s5b: 'tags:\n    - a\n    - b\nz: 1\n', merge-tags a --into c --apply; s5c: 'm:\n    k: v\n    l:\n        - x\ntags: [a, b]\n', merge-tags a --into c --apply;
  s5d: 'verified:\n- by: human:x\n  at: 2026-01-01T00:00:00Z\n', verify w/x --by human:me
- **Channel:** file-tree effect; stdout (the diff printed by merge-tags, remove-tags, normalize-tags and migrate shows the same difference)
- **Difference:** Go keeps the author's list and mapping indentation and appends to a list in that list's own indentation; ruamel re-indents to mapping 2, sequence 4 with offset 2. The data is equal.
```text
Python (exit 0): s5a (merge-tags a --into c --apply) -> w/x.md = '---\ntype: Concept\ntags:\n  - c\n  - b\nz: 1\n---\n# T\nbody\n'
Python (exit 0): s5b (merge-tags a --into c --apply) -> w/x.md = '---\ntype: Concept\ntags:\n  - c\n  - b\nz: 1\n---\n# T\nbody\n'
Python (exit 0): s5c (merge-tags a --into c --apply) -> w/x.md = '---\ntype: Concept\nm:\n  k: v\n  l:\n    - x\ntags: [c, b]\n---\n# T\nbody\n'
Python (exit 0): s5d (verify w/x --by human:me) -> w/x.md = '---\ntype: Concept\nverified:\n  - by: human:x\n    at: 2026-01-01T00:00:00Z\n  - by: human:me\n    at: 2026-10-16T15:26:19Z\n---\n# T\nbody\n'
Go (exit 0): s5a (merge-tags a --into c --apply) -> w/x.md = '---\ntype: Concept\ntags:\n- c\n- b\nz: 1\n---\n# T\nbody\n'
Go (exit 0): s5b (merge-tags a --into c --apply) -> w/x.md = '---\ntype: Concept\ntags:\n    - c\n    - b\nz: 1\n---\n# T\nbody\n'
Go (exit 0): s5c (merge-tags a --into c --apply) -> w/x.md = '---\ntype: Concept\nm:\n    k: v\n    l:\n        - x\ntags: [c, b]\n---\n# T\nbody\n'
Go (exit 0): s5d (verify w/x --by human:me) -> w/x.md = '---\ntype: Concept\nverified:\n- by: human:x\n  at: 2026-01-01T00:00:00Z\n- by: human:me\n  at: 2026-10-16T15:26:19Z\n---\n# T\nbody\n'
```
- **Reason:** Go: `yamlpatch` rewrites only the lines of the targeted key in the stored text (package comment: every other byte stays). Python: `render_frontmatter` re-dumps the whole mapping through `YAML_RT`
  (indent mapping 2, sequence 4, offset 2, width 2**30).
- **Capability preserved:** yes. Both results load to the same frontmatter data under ruamel (checked for every case above): Go keeps what the author wrote, Python normalises it. 
- **Owner:** Go frontmatter writer (F: OKFT-5lq2)
- **Reproduce:** printf -- '---\ntype: Concept\ntags:\n- a\n- b\nz: 1\n---\n# T\nbody\n' > w/x.md && okf --root . merge-tags a --into c --apply
  printf -- '---\ntype: Concept\nverified:\n- by: human:x\n  at: 2026-01-01T00:00:00Z\n---\n# T\nbody\n' > w/x.md && okf --root . verify w/x --by human:me
- **PO decision:**

#### D-14 Comments, blank lines and markers: Go keeps them, Python drops or moves some
- **Cases:** t06: 'tags: [a, b] # c\n', remove-tags a --apply; t25: 'tags:\n  - a\n  # mid\n  - b\n', remove-tags a --apply; t40: 'tags:\n  - a # c\n# trailing\nz: 1\n', remove-tags a --apply; t24: 'tags:\n  - a\n\n  - b\n', remove-tags a --apply;
  m16: 'timestamp: 2025-01-01T00:00:00Z\n\n', migrate --apply (git); n5: '---\n# note\n---\n# T\nbody\n', verify w/x --by human:me; n4: '---\n{}\n# note\n---\n# T\nbody\n', verify w/x --by human:me;
  s7g: 'tags: [a, b]\n...\n', merge-tags a --into c --apply
- **Channel:** file-tree effect; stdout (the diff printed by merge-tags, remove-tags, normalize-tags and migrate shows the same difference)
- **Difference:** Go keeps comments, blank lines, comment padding and the `...` document-end marker exactly; Python re-dumps and drops or moves some of them (for example the comment between two list items goes with the
  removed item). The data is equal.
```text
Python (exit 0): t25 (remove-tags a --apply) -> w/x.md = '---\ntype: Concept\ntags:\n  - b\n---\n# T\nbody\n'
Python (exit 0): t40 (remove-tags a --apply) -> w/x.md = '---\ntype: Concept\nz: 1\n---\n# T\nbody\n'
Python (exit 0): n5 (verify w/x --by human:me) -> w/x.md = '---\nverified:\n  - by: human:me\n    at: 2026-10-16T15:26:15Z\n---\n# T\nbody\n'
Python (exit 0): s7g (merge-tags a --into c --apply) -> w/x.md = '---\ntype: Concept\ntags: [c, b]\n---\n# T\nbody\n'
Go (exit 0): t25 (remove-tags a --apply) -> w/x.md = '---\ntype: Concept\ntags:\n  # mid\n  - b\n---\n# T\nbody\n'
Go (exit 0): t40 (remove-tags a --apply) -> w/x.md = '---\ntype: Concept\n# trailing\nz: 1\n---\n# T\nbody\n'
Go (exit 0): n5 (verify w/x --by human:me) -> w/x.md = '---\n# note\nverified:\n  - by: human:me\n    at: 2026-10-16T15:26:15Z\n---\n# T\nbody\n'
Go (exit 0): s7g (merge-tags a --into c --apply) -> w/x.md = '---\ntype: Concept\ntags: [c, b]\n...\n---\n# T\nbody\n'
```
- **Reason:** Go: `yamlpatch` rewrites only the lines of the targeted key in the stored text (package comment: every other byte stays). Python: `render_frontmatter` re-dumps the whole mapping through `YAML_RT`
  (indent mapping 2, sequence 4, offset 2, width 2**30).
- **Capability preserved:** yes. Both results load to the same frontmatter data under ruamel (checked for every case above): Go keeps what the author wrote, Python normalises it. Python's changes lose text the author wrote.
- **Owner:** Go frontmatter writer (F: OKFT-5lq2)
- **Reproduce:** printf -- '---\ntype: Concept\ntags:\n  - a\n  # mid\n  - b\n---\n# T\nbody\n' > w/x.md && okf --root . remove-tags a --apply
  printf -- '---\n# note\n---\n# T\nbody\n' > w/x.md && okf --root . verify w/x --by human:me
- **PO decision:**

#### D-15 Spelling of untouched scalars and keys: Go keeps the author's spelling, Python writes ruamel's
- **Cases:** s6a: 'description: first line\n  second line\ntags: [a, b]\n', merge-tags a --into c --apply; s6c: 'n1: 1_000\nn2: .5\nn3: 1.0E+3\nn4: 0x1F\nn5: +1\nn6: 010\nn7: 0o14\ntags: [a, b]\n', merge-tags a --into c --apply;
  s6e: 'b1: yes\nb2: True\nb3: ~\nb4: null\nb5:\nb6: NULL\ntags: [a, b]\n', merge-tags a --into c --apply; s6f: 'k: v # c\n? complex\n: val\ntags: [a, b]\n', merge-tags a --into c --apply
- **Channel:** file-tree effect; stdout (the diff printed by merge-tags, remove-tags, normalize-tags and migrate shows the same difference)
- **Difference:** Go leaves untouched scalars and keys exactly as written; Python writes them in ruamel's spelling. The data is equal.
```text
Python (exit 0): s6a (merge-tags a --into c --apply) -> w/x.md = '---\ntype: Concept\ndescription: first line second line\ntags: [c, b]\n---\n# T\nbody\n'
Python (exit 0): s6c (merge-tags a --into c --apply) -> w/x.md = '---\ntype: Concept\nn1: 1_000\nn2: .5\nn3: 1.0E+3\nn4: 0x1F\nn5: 1\nn6: 010\nn7: 0o14\ntags: [c, b]\n---\n# T\nbody\n'
Python (exit 0): s6e (merge-tags a --into c --apply) -> w/x.md = '---\ntype: Concept\nb1: yes\nb2: true\nb3:\nb4:\nb5:\nb6:\ntags: [c, b]\n---\n# T\nbody\n'
Python (exit 0): s6f (merge-tags a --into c --apply) -> w/x.md = '---\ntype: Concept\nk: v # c\ncomplex: val\ntags: [c, b]\n---\n# T\nbody\n'
Go (exit 0): s6a (merge-tags a --into c --apply) -> w/x.md = '---\ntype: Concept\ndescription: first line\n  second line\ntags: [c, b]\n---\n# T\nbody\n'
Go (exit 0): s6c (merge-tags a --into c --apply) -> w/x.md = '---\ntype: Concept\nn1: 1_000\nn2: .5\nn3: 1.0E+3\nn4: 0x1F\nn5: +1\nn6: 010\nn7: 0o14\ntags: [c, b]\n---\n# T\nbody\n'
Go (exit 0): s6e (merge-tags a --into c --apply) -> w/x.md = '---\ntype: Concept\nb1: yes\nb2: True\nb3: ~\nb4: null\nb5:\nb6: NULL\ntags: [c, b]\n---\n# T\nbody\n'
Go (exit 0): s6f (merge-tags a --into c --apply) -> w/x.md = '---\ntype: Concept\nk: v # c\n? complex\n: val\ntags: [c, b]\n---\n# T\nbody\n'
```
- **Reason:** Go: `yamlpatch` rewrites only the lines of the targeted key in the stored text (package comment: every other byte stays). Python: `render_frontmatter` re-dumps the whole mapping through `YAML_RT`
  (indent mapping 2, sequence 4, offset 2, width 2**30).
- **Capability preserved:** yes. Both results load to the same frontmatter data under ruamel (checked for every case above): Go keeps what the author wrote, Python normalises it. 
- **Owner:** Go frontmatter writer (F: OKFT-5lq2)
- **Reproduce:** printf -- '---\ntype: Concept\nn1: 1_000\nn2: .5\nn3: 1.0E+3\nn4: 0x1F\nn5: +1\nn6: 010\nn7: 0o14\ntags: [a, b]\n---\n# T\nbody\n' > w/x.md && okf --root . merge-tags a --into c --apply
  printf -- '---\ntype: Concept\nk: v # c\n? complex\n: val\ntags: [a, b]\n---\n# T\nbody\n' > w/x.md && okf --root . merge-tags a --into c --apply
- **PO decision:**

#### D-16 Python writes an unreadable file or other data where Go writes the intended data
- **Cases:** intoq: 'tags: [a, b]\n', merge-tags a --into '?b' --apply; intocolon: 'tags: [a, b]\n', merge-tags a --into ': b' --apply; intonel: 'tags: [a, b]\n', merge-tags a --into 'ab' --apply;
  v19: 'verified: # c\n  by: human:x\n  at: 2026-01-01T00:00:00Z\n', verify w/x --by human:me; v20: 'verified: {by: human:x, at: 2026-01-01T00:00:00Z} # c\n', verify w/x --by human:me;
  sweeps: merge-tags a --into <value> over 99 values x 4 list shapes (396 runs) and verify --by <value> over 248 values x 6 `verified` shapes (1 488 runs): Python wrote other data in 9 and 15 runs (values `?b`, `? b`, `: b`, forms with U+0085, `?b/1`, `? b/1`, `: b/1`), Go in none; both refuse the same 8 and 78 runs
- **Channel:** file-tree effect
- **Difference:** In these inputs Python writes a plain scalar that its own reader reads differently (`?b` or `: b` inside a flow list, a raw U+0085) or writes a block that does not read, so the file is unreadable or
  holds other data. Go quotes the new text and checks the result by reading it back.
```text
Python (exit 0): merge-tags --into '?b' -> w/x.md = '---\ntype: Concept\ntags: [?b, b]\n---\n# T\nbody\n'; reads: tags = [{'b': None}, 'b']
Python (exit 0): merge-tags --into ': b' -> w/x.md = '---\ntype: Concept\ntags: [: b, b]\n---\n# T\nbody\n'; the frontmatter does NOT read (expected the node content, but found ':' (line 3, column 8))
Python (exit 0): verify on 'verified:  # c' + block mapping -> w/x.md = '---\ntype: Concept\nverified: # c\n  -       # c\n    by: human:x at: 2026-01-01T00:00:00Z\n  - by: human:me\n    at: 2026-10-16T15:26:15Z\n---\n# T\nbody\n'; the frontmatter does NOT read (mapping values are not allowed here (line 5, column 19))
Go (exit 0): merge-tags --into '?b' -> w/x.md = "---\ntype: Concept\ntags: ['?b', b]\n---\n# T\nbody\n"; reads: tags = ['?b', 'b']
Go (exit 0): merge-tags --into ': b' -> w/x.md = "---\ntype: Concept\ntags: [': b', b]\n---\n# T\nbody\n"; reads: tags = [': b', 'b']
Go (exit 0): verify on 'verified:  # c' + block mapping -> w/x.md = '---\ntype: Concept\nverified: # c\n  - by: human:x\n    at: 2026-01-01T00:00:00Z\n  - by: human:me\n    at: 2026-10-16T15:26:15Z\n---\n# T\nbody\n'; reads: verified = [{'by': 'human:x', 'at': "TimeStamp(2026, 1, 1, 0, 0, tzinfo=datetime.timezone(datetime.timedelta(0), 'Z'))"}, {'by': 'human:me', 'at': "TimeStamp(2026, 10, 16, 15, 26, 15, tzinfo=datetime.timezone(datetime.timedelta(0), 'Z'))"}]
```
- **Reason:** Python: `render_frontmatter` emits a plain scalar that `read_frontmatter` reads back differently in a flow context or with NEL. Go: `yamlpatch/quote.go` chooses the quoting and `selfCheck` reads the
  patched text back and compares it with the intended data.
- **Capability preserved:** yes. Go writes the intended data where Python writes an unreadable file or other data; refusing or correcting that input keeps the capability. No sweep run produced a Go result that reads back as
  other data than intended (except the input class of entry 1).
- **Owner:** Go frontmatter writer (F: OKFT-5lq2)
- **Reproduce:** printf -- '---\ntype: Concept\ntags: [a, b]\n---\n# T\nbody\n' > w/x.md && okf --root . merge-tags a --into '?b' --apply
- **PO decision:**

### Area B. ctx bundles

**Ctx bundles, ctx files and the ctx part of rename/archive: deviations of the Go okf from the Python okf**

Fixture of every Reproduce line: `R` is a copy of `tests/golden/catalogue` (a git repo); run from `R`. `okf` is the Python CLI or the Go binary, always called as `okf --root . ...`. `sed -i` is GNU sed. `<NUL>` and `<U+0085>` stand for the bytes themselves.

#### D-17 Go refuses a ctx edit when the frontmatter parses but its line patcher cannot patch it
- **Cases:**   - Flow-mapping root that needs an edit: `{type: Note, description: Cooking basics}`; `{type: Context}` (no description key).
  - Explicit tag or anchor on the type value: `type: !!str Note`; `type: &t Note`.
  - Type value is a list or a mapping: `type: [Context]`; `type:` with a block list `- Context`; `type: {a: b}`.
  - Other shapes the patcher refuses: key on the opening delimiter line `--- {type: Note}`; complex key `? [a, b]`; a `...` document-end line after `type: Context` (no description key).
  - Verbs (Python exit 0, Go exit 2 in every shape): `ctx add cooking recipes/salad`, `ctx drop cooking recipes/bread`, `ctx move cooking recipes/soup --pos 1`, `ctx rename cooking kitchen`, `rename recipes/pasta.md recipes/noodles.md` (dry run and `--apply`), `archive recipes/pasta --apply`.
  - Not affected (identical): the same shapes when `type: Context` and a description are already there, and block-style files with a wrong, missing or empty type or description.
- **Channel:** exit code, stdout, stderr, file-tree effect
- **Difference:** Python sets `type` to `Context` (or adds `description: ''`), keeps the rest of the block and style, and performs the edit. Go stops with exit 2 before anything is written, also in the dry run of `rename`.
```text
Python (exit 0): [flow root] -{type: Note, description: Cooking basics}
Python (exit 0): [flow root] +{type: Context, description: Cooking basics}
Python (exit 0): [type list] -type: [Context]
Python (exit 0): [type list] +type: Context
Python (exit 0): [tagged type] -type: !!str Note
Python (exit 0): [tagged type] +type: Context
Go (exit 2): [flow root] the frontmatter is a flow mapping
Go (exit 2): [type list] the value of "type" is a list or a mapping; a set-value edit takes a scalar
Go (exit 2): [tagged type] the value of a key carries an anchor, an alias or an explicit tag
```
- **Reason:** Go `ctxfile.RenderCtx` hands `SetValue("type")` or `NewKey("description")` to `yamlpatch.Apply`, whose patcher (`ensurePairs`, `setValue`, `plainTree`, the read-back self-check) returns a `*Rejection` (exit class 2) for these shapes. Python `render_ctx` assigns `fm.data["type"] = CTX_TYPE` on the ruamel mapping and dumps it.
- **Capability preserved:** no. Python does this correctly and without data loss; Go aborts the whole write. A user can still read, check (`ctx check` reports the wrong type), `ctx edit`, `ctx remove` and recreate such a ctx file, and still rename or archive concepts it does not list. For a concept it lists, and for `ctx add/drop/move/rename` on it, the user must first fix `type: Context` and add a `description:` key by hand in block style, then retry.
- **Owner:** Go frontmatter writer (F: OKFT-5lq2)
- **Reproduce:** `sed -i '2,3c {type: Note, description: Cooking basics}' _ctx/cooking.md` then `okf --root . ctx add cooking recipes/salad`
  Other shapes: replace the `sed` by `sed -i 's/^type: Context$/type: [Context]/' _ctx/cooking.md` or `.../type: !!str Note/`.
- **PO decision:**

#### D-18 A ctx position beyond int64 is dropped by Go and refused by the editing verbs
- **Cases:**   - Row `| 99999999999999999999 | pflicht | [bread](/recipes/bread.md) |  |`; same cause: `9223372036854775808` (2^63), `-99999999999999999999`, 25 Arabic-indic digits, and a huge pos on a `nachschlag` row. `9223372036854775807` (int64 maximum) is identical in both.
  - Read verbs (same exit codes, the entry is missing in Go): `ctx show cooking`, `ctx list`, `ctx read cooking`, `ctx toc cooking`, `ctx inbound cooking`, `ctx outbound cooking`, `ctx check cooking [--json|--stale]`, `ctx list --for recipes/pasta`.
  - Editing verbs (Python exit 0, Go exit 2): `ctx add cooking recipes/salad` (also `--mode nachschlag`, `--pos 2`), `ctx drop cooking recipes/bread`, `ctx move cooking recipes/soup --pos 1` (also `--mode nachschlag`).
  - Exit 0 in both, but Go leaves the ctx file unrefreshed and adds `ctx        cooking: not refreshed, 1 parse problem(s) — run okf ctx check`: `rename recipes/pasta.md recipes/noodles.md --apply`, `archive recipes/pasta --apply`, `ctx rename cooking kitchen`.
- **Channel:** stdout, stderr, exit code (editing verbs), file-tree effect
- **Difference:** Python reads any integer; Go reports a pos beyond int64 as a parse problem of its row, drops the row from the listing, and refuses `ctx add/drop/move` like for any parse problem. Python renumbers the file to 1..n on such a write.
```text
Python (exit 4): ERROR    kc/ctx/required-positions _ctx/cooking.md  (required positions are not 1..3 in table order: 99999999999999999999, 2, 3)
Python (exit 0): [ctx show] 3 entries (3 required, 0 reference), ~164 tokens for the required set
Python (exit 0): [ctx add] added recipes/salad.md to cooking (pos 4)
Go (exit 4): ERROR    kc/ctx/row-format    _ctx/cooking.md  (row 1: pos "99999999999999999999" is out of range)
Go (exit 4): ERROR    kc/ctx/required-positions _ctx/cooking.md  (required positions are not 1..2 in table order: 2, 3)
Go (exit 0): [ctx show] 2 entries (2 required, 0 reference), ~112 tokens for the required set
Go (exit 2): [ctx add] ctx: cooking has 1 parse problem(s) — fix with okf ctx edit, see okf ctx check
```
- **Reason:** Go `ctxfile.ctxPos` returns `fits=false` (strconv.Atoi) and `ctxfile.parseCtx` turns the row into a problem; `ctx.editable` refuses writers when problems exist. Python `parse_ctx` reads `int(pos_s)` of any size and `_ctx_editable` refuses only when `problems` is non-empty.
- **Capability preserved:** no (narrow, only for |pos| of 2^63 and more). Python's `ctx add/drop/move` repairs such a file correctly; Go refuses until the pos cell is edited by hand (`ctx check` names row 1). Reading, `ctx rename`, `rename` and `archive` still work in Go.
- **Owner:** Go frontmatter writer (F: OKFT-5lq2)
- **Reproduce:** `sed -i 's/^| 1 | pflicht | \[bread\]/| 99999999999999999999 | pflicht | [bread]/' _ctx/cooking.md` then `okf --root . ctx check cooking` and `okf --root . ctx add cooking recipes/salad`
- **PO decision:**

#### D-19 A ctx file whose frontmatter does not parse: Go refuses, Python rewrites it and loses the old frontmatter
- **Cases:**   - Verbs (Python exit 0, Go exit 2): `ctx add cooking recipes/salad`, `ctx drop cooking recipes/bread`, `ctx move cooking recipes/soup --pos 1`; `ctx add` also with `--json`.
  - `ctx rename cooking kitchen` (also `--json`); Go moves nothing.
  - `rename recipes/pasta.md recipes/noodles.md` as dry run, with `--apply`, `--apply --force`, `--json`, `--apply --json`.
  - `archive recipes/pasta` dry run, `--apply`, `--apply --json`; `archive --restore _archive/handbook/old-process [--apply]` with `_ctx/legacy.md` broken (Go prints `1 active concept(s) still link to this concept` first).
  - Broken shapes, all alike: `description: [unclosed`; block is a list `- a`; `description: "abc`; duplicate key `type`; tab-indented key; block is a plain scalar; `description: a: b`; valid keys followed by a broken line (comment, `owner`, `tags` lost too).
  - Identical in both: `ctx list/show/check/read/toc/inbound/outbound/remove`, `ctx edit` (EDITOR=true), `ctx create` of another slug, and rename/archive of a concept the broken file does not list.
- **Channel:** exit code, stdout, stderr, file-tree effect
- **Difference:** Python silently starts a new block `type: Context` / `description: ''`: the description, every other key and every comment of the old block are erased, and the `_ctx/index.md` line loses its description. Go exits 2 with the raw YAML error (no file name) and writes nothing; `ctx check` names the file (`kc/ctx/type ... type is ""`).
```text
Python (exit 0): added recipes/salad.md to cooking (pos 4)
Python (exit 0): _ctx/cooking.md: -# keep me
Python (exit 0): _ctx/cooking.md: -description: Cooking basics
Python (exit 0): _ctx/cooking.md: -owner: erik
Python (exit 0): _ctx/cooking.md: -tags: [kitchen, food
Python (exit 0): _ctx/cooking.md: +description: ''
Python (exit 0): _ctx/index.md: -* [cooking](/_ctx/cooking.md) - Cooking basics
Python (exit 0): _ctx/index.md: +* [cooking](/_ctx/cooking.md)
Go (exit 2): did not find expected ',' or ']' (line 6, column 8)
```
- **Reason:** Go `ctxfile.RenderCtx` (comment "Deviation (D02)") passes the stored text to `yamlpatch.Apply`, whose `newPatcher` returns a `ParseError`; `ctx.save`, `ctx.runRename` (checks before the move) and `move.planMoveTexts` stop on it. Python `render_ctx` does `if fm.data is None: fm = Frontmatter("", CommentedMap(), None, "")` and is called by `save_ctx` and `ctx_text` (rename.py `plan_move_texts`).
- **Capability preserved:** yes. Python's write is lossy, so refusing keeps the capability. A user can still rename a concept that a broken ctx file lists, after repairing that file: fix the one broken line by hand (or `okf ctx edit cooking`), then `rename` exits 0 and keeps all keys and comments; or `ctx remove cooking`, `rename`, `ctx create cooking --description ... <paths>`. Go has no way to rename while the broken file stays (not with `--force`, not as dry run).
- **Owner:** Go frontmatter writer (F: OKFT-5lq2)
- **Reproduce:** `sed -i '2,3c # keep me\ntype: Context\ndescription: Cooking basics\nowner: erik\ntags: [kitchen, food' _ctx/cooking.md` then `okf --root . ctx add cooking recipes/salad`
  Rename form: `sed -i 's/^description: .*/description: [unclosed/' _ctx/cooking.md; okf --root . rename recipes/pasta.md recipes/noodles.md --apply`
- **PO decision:**

#### D-20 A NUL byte in a ctx path: Python crashes with a ValueError, Go reports "not found" or a dead entry
- **Cases:**   - Import file line with a NUL inside a path that leaves the catalogue (Python exit 1, Go exit 3): `/tmp/nonexistent<NUL>x`, `~/x<NUL>y`, `~nosuchuser<NUL>x`, `~<NUL>x`, `/recipes/pasta.md<NUL>`, `../x<NUL>y`, and such a line followed by a valid path. Command: `ctx create foo --import imp.txt` (a NUL cannot come through argv, so the import file is the only command line).
  - Identical (exit 3 both): relative `recipes/pasta.md<NUL>x`, `recipes/pas<NUL>ta.md`, a line holding only NUL. Identical (exit 0): NUL in the comment after the TAB.
  - ctx file row whose code-span path is `~nosuchuser<NUL>x`: `ctx show|check|read cooking` Python exit 1 / Go exit 4 (dead entry); `ctx toc|inbound|outbound cooking` Python exit 1 / Go exit 0.
  - Identical: a NUL in a relative link path, an absolute code span, a `~/` code span or a comment cell of a ctx row.
- **Channel:** exit code, stderr (stdout for the ctx file row)
- **Difference:** Python's `os.path.realpath` / `os.path.expanduser` raise on the NUL and the traceback ends the run (exit 1). Go treats the path as not existing: not found when creating, a dead entry when reading. Nothing is written by either.
```text
Python (exit 1): [/tmp/nonexistent<NUL>x] ValueError: lstat: embedded null character in path
Python (exit 1): [~nosuchuser<NUL>x] ValueError: embedded null byte
Python (exit 1): [ctx show, row ~nosuchuser<NUL>x] ValueError: embedded null byte
Go (exit 3): [/tmp/nonexistent<NUL>x] ctx: not found: /tmp/nonexistent<NUL>x
Go (exit 3): [~nosuchuser<NUL>x] ctx: not found: ~nosuchuser<NUL>x
Go (exit 4): [ctx show, row ~nosuchuser<NUL>x]   2. [DEAD] ~nosuchuser<NUL>x
```
- **Reason:** Go `ctxfile` `pyExists` (os.Stat error means "no") and `pyRealpath` never raise; Python `ctx_normalize_path` (`filesystem()` calls `os.path.realpath`) and `ctx_entry_abspath` (`os.path.expanduser`) let the ValueError escape.
- **Capability preserved:** yes. Python crashes and writes nothing; Go reports the path as missing. No valid input is lost.
- **Owner:** Go frontmatter writer (F: OKFT-5lq2)
- **Reproduce:** `printf '/tmp/nonexistent\0x\n' > imp.txt` then `okf --root . ctx create foo --import imp.txt`
  Second form: `printf '~nosuchuser\0x\n' > imp.txt` (Python `ValueError: embedded null byte`, Go `ctx: not found: ~nosuchuser<NUL>x`).
- **PO decision:**

#### D-21 ctx description: 15 strings are quoted differently by `ctx create --description`
- **Cases:** (282 candidates tried with `ctx create sweep --description=<X> recipes/bread`, 267 identical; `ctx edit` cannot set a description)
  - Go quotes, Python writes plain: `0X1f`, `2026-1-1`.
  - Python quotes, Go writes plain: `---`, `...`.
  - Leading single quote (Python double quotes, Go single quotes with doubled quote): `'a`, `'`, `'quoted'`.
  - Control characters (Python `\e \b \v \f`, Go `\x1B \x08 \x0B \x0C`): U+001B in `a<ESC>b`, U+0008, U+000B, U+000C.
  - Line separators U+2028 and U+2029 in `a<LS>b`: Python single-quoted with the raw character and two spaces, Go `"a\Lb"` and `"a\Pb"`.
  - U+0085 alone and in `a<U+0085>b`: Python writes `'a<U+0085>  b'`, which ruamel itself reads back as `a b`; Go writes `"a\Nb"`, which reads back as written.
- **Channel:** file-tree effect (bytes of the new `_ctx/<slug>.md`; exit code, stdout, stderr and the `_ctx/index.md` text are identical)
- **Difference:** 13 of the 15 are data-equal after loading both files with ruamel. The two U+0085 strings are not: Python's file loads as `a b`, Go's as `a<U+0085>b`. Go-written files read identically in both implementations; Python's U+2028/U+2029 files read as `a<LS>b` in Python but `a<LS>  b` in Go.
```text
Python (exit 0): description: 0X1f
Python (exit 0): description: "'quoted'"
Python (exit 0): description: '---'
Python (exit 0): description: 'a<U+0085>  b'
Go (exit 0): description: '0X1f'
Go (exit 0): description: '''quoted'''
Go (exit 0): description: ---
Go (exit 0): description: "a\Nb"
```
- **Reason:** Go `yamlpatch` `quote.go` chooses the scalar style with its own rules; Python dumps through the ruamel emitter (`YAML_RT.dump` in `render_frontmatter`). The two disagree on the plain-scalar test, on single-quote handling and on the escape spellings.
- **Capability preserved:** yes. Data-equal in 13 cases; in the two U+0085 cases Python writes wrong data and Go writes the right data.
- **Owner:** Go frontmatter writer (F: OKFT-5lq2)
- **Reproduce:** `okf --root . ctx create sweep --description="'quoted'" recipes/bread; cat _ctx/sweep.md`
  `okf --root . ctx create sweep --description="$(printf 'a\302\205b')" recipes/bread; cat -A _ctx/sweep.md`
- **PO decision:**

#### D-22 Python crashes with a traceback where Go prints one message (same exit class)
- **Cases:**   - ctx row with `-` as pos of a required entry (`| - | pflicht | [pasta](/recipes/pasta.md) |  |`): `ctx show|read|toc|inbound|outbound cooking`, `ctx add|drop|move cooking ...` exit 1 in both; with `--json` both give an error envelope of kind `internal`, only the message differs.
  - Bad `EDITOR` for `ctx edit cooking` (exit 1 in both): unclosed quote `ed "unclosed`; program not found; `EDITOR=' '` (runs the ctx file itself); a directory; `./ed` missing.
  - Filesystem states (exit 1 in both): `_ctx` is a regular file (`ctx create np recipes/bread`); a 300-character slug; directory `_ctx/d.md` (`ctx check`); dangling symlink `_ctx/dang.md` (`ctx check`, `ctx rename`, `ctx remove`, `rename`).
  - Deleted working directory: `ctx add|create|drop ... nonexistent-thing` Python exit 1 / Go exit 3; `ctx list --for nonexistent-thing` Python exit 1 / Go exit 0.
  - Identical: 41 other EDITOR strings (quotes, escapes, `#`, tabs, empty arguments, VISUAL/EDITOR precedence, editor exit codes, signals).
- **Channel:** stderr (stdout for `--json`); exit code only in the deleted-directory cases
- **Difference:** Python lets the exception escape, so the last stderr line is the exception after a traceback. Go reports the condition in one line. Nothing is written by either.
```text
Python (exit 1): [ctx show, pos -] TypeError: '<' not supported between instances of 'NoneType' and 'int'
Python (exit 1): [ctx edit, EDITOR='ed "unclosed'] ValueError: No closing quotation
Go (exit 1): [ctx show, pos -] ctx: cooking has a required entry without a position; fix with okf ctx edit, see okf ctx check
Go (exit 1): [ctx edit, EDITOR='ed "unclosed'] No closing quotation
```
- **Reason:** Go `ctx.byPos`, `ctx.runEdit` and `ctxfile.normalizePath` check the error where Python `_ctx_members` (`sorted(... key=pos)`), `cmd_ctx_edit` (`shlex.split`, `subprocess.call`) and `ctx_normalize_path` (`os.path.abspath`) do not.
- **Capability preserved:** yes. Python only crashes; Go reports the condition and the data written is the same (none).
- **Owner:** Go ctx bundles (F: OKFT-82n3)
- **Reproduce:** `sed -i 's/^| 2 | pflicht |/| - | pflicht |/' _ctx/cooking.md; okf --root . ctx show cooking`
  `EDITOR='ed "unclosed' okf --root . ctx edit cooking`
- **PO decision:**

#### D-23 ctx create orders Cherokee small letters differently (casefold)
- **Cases:**   - `ctx create np cf/<U+13A0>.md cf/<U+AB70>.md` (Cherokee `Ꭰ` and `ꭰ`, arguments in this order).
  - Sweep of all 2,981 code points that have a case relation, each pair created in both argument orders: exactly 86 differ, U+13F8..U+13FD and U+AB70..U+ABBF (Cherokee small letters). All other folds order identically (ß, ſ, ς, ﬁ, İ, ı, ǅ, K, Ω, Adlam).
- **Channel:** file-tree effect (row order in the new ctx file)
- **Difference:** `ctx create` sorts the entries by the case-folded path. Python folds the Cherokee small letter to the capital, so both names tie and keep the argument order; Go does not fold them and puts the small letter first.
```text
Python (exit 0): | 1 | pflicht | [Ꭰ](/cf/Ꭰ.md) |  |
Python (exit 0): | 2 | pflicht | [ꭰ](/cf/ꭰ.md) |  |
Go (exit 0): | 1 | pflicht | [ꭰ](/cf/ꭰ.md) |  |
Go (exit 0): | 2 | pflicht | [Ꭰ](/cf/Ꭰ.md) |  |
```
- **Reason:** Go `ctx.runCreate` sorts with `pytext.Casefold`, which gives the Cherokee small letters a different key than Python `str.casefold()` in `cmd_ctx_create`; all other letters tested give the same order.
- **Capability preserved:** yes. The same rows are written; only the order of names that fold equal differs.
- **Owner:** Go ctx bundles (F: OKFT-82n3) + Go core and read side (F: OKFT-daut)
- **Reproduce:** `mkdir cf; printf '# x\n' > cf/Ꭰ.md; printf '# x\n' > cf/ꭰ.md` then `okf --root . ctx create np cf/Ꭰ.md cf/ꭰ.md; cat _ctx/np.md`
- **PO decision:**

#### D-24 Explicitly tagged or exotic scalars in a ctx `description` or `type` are read differently
- **Cases:** frontmatter value as written, shown by `ctx list [--json]`, `ctx show cooking` (description) and `ctx check cooking` (type):
  - `!!str Cooking basics`: Python `!!str Cooking basics`, Go `Cooking basics`; `!!str 3`: Python `!!str 3`, Go `3`; `!!float 3`: Python `!!float '3'`, Go `3`; `!custom abc`: Python `!custom abc`, Go `abc`; `!!str` alone: Python `!!str`, Go empty.
  - `!!binary aGk=`: Python `!!binary |`, Go `aGk=`; `!!set {a}`: Python `!!set {a}`, Go `!!set {a: ''}`.
  - `1__0`: Python `1_0`, Go `1__0`; `2001-12-14t21:59:43.10-05:00`: Python `2001-12-14T21:59:43.100000-05:00`, Go unchanged; `2001-12-14 21:59:43.10 -5`: Python `2001-12-14 21:59:43.100000-5`, Go unchanged.
  - `type: !!str Note` in `ctx check`: Python `type is "!!str Note"`, Go `type is "Note"`.
- **Channel:** stdout (and the `_ctx/index.md` text that Python then writes)
- **Difference:** Python shows the YAML tag or a re-spelled number or timestamp; Go shows the scalar text. Go's text is the intended one.
```text
Python (exit 0):   cooking     !!str Cooking basics  (3 entries, 3 required)
Python (exit 4): ERROR    kc/ctx/type          _ctx/cooking.md  (type is "!!str Note", expected "Context")
Go (exit 0):   cooking     Cooking basics  (3 entries, 3 required)
Go (exit 4): ERROR    kc/ctx/type          _ctx/cooking.md  (type is "Note", expected "Context")
```
- **Reason:** Python `scalar_text` dumps non-string ruamel values through `YAML_RT.dump` (keeps the tag, re-spells numbers and timestamps); Go `frontmatter.Text` returns the scalar text.
- **Capability preserved:** yes. Go shows what the author wrote; Python shows tag syntax.
- **Owner:** Go core and read side (F: OKFT-daut)
- **Reproduce:** `sed -i 's/^description: .*/description: !!str Cooking basics/' _ctx/cooking.md; okf --root . ctx list`
  `sed -i 's/^type: Context$/type: !!str Note/' _ctx/cooking.md; okf --root . ctx check cooking`
- **PO decision:**

#### D-25 After a ctx write the untouched frontmatter is formatted differently (data-equal)
- **Cases:** `ctx add cooking recipes/salad`, exit 0 in both, only the bytes of `_ctx/cooking.md` differ.
  - `description:` set to `True`, `TRUE`, `null`, `Null`, `NULL`, `~`, empty, `+1`, `-0`, `+.inf`, `!!int "3"`, `!!str 3`, `!!float 3`, `!!bool true`, `!!null x`, `!!binary aGk=`, `!custom abc`, `!!timestamp 2026-01-01`, `!!set {a}`, `"uni\u00e9"`, an indented plain scalar, multi-line plain or quoted scalars, `|+` and `>+` block scalars, `1__0`, two timestamp spellings.
  - `type:` empty, `'x'  # comment`, indented, `|+` and `>+` block scalars.
  - Keys indented by two spaces and no description key: Python dedents the block, Go keeps the indent.
- **Channel:** file-tree effect
- **Difference:** Python re-dumps the whole block and normalises spelling; Go patches only the lines it changes, so its `git diff` shows no change to the description line. Both files load to the same data (36 of 36 checked key by key with ruamel).
```text
Python (exit 0): added recipes/salad.md to cooking (pos 4)
Python (exit 0): _ctx/cooking.md: -description: True
Python (exit 0): _ctx/cooking.md: +description: true
Go (exit 0): added recipes/salad.md to cooking (pos 4)
```
- **Reason:** Go `ctxfile.RenderCtx` edits through `yamlpatch` (line patches, design D05); Python `render_ctx` calls `render_frontmatter`, which dumps the whole ruamel mapping.
- **Capability preserved:** yes. Same data written; Go keeps the author's formatting.
- **Owner:** Go frontmatter writer (F: OKFT-5lq2)
- **Reproduce:** `sed -i 's/^description: .*/description: True/' _ctx/cooking.md; okf --root . ctx add cooking recipes/salad; git diff -- _ctx/cooking.md`
- **PO decision:**

### Area C. Reading YAML and TOML

**Scalar semantics, frontmatter and config read: entries for the acceptance report (work package K, OKFT-8dnw)**

Reproduce lines are bash. Run each one twice, once with `OKF_BIN` set to the Python CLI (`okf-cli.py`) and once to the Go binary, and compare. `<R>` in an excerpt stands for the scratch catalogue `$R`. Helper functions:

```bash
okf() { env -u VOYAGE_API_KEY unshare -rn "$OKF_BIN" "$@"; }
mk() { R=$(mktemp -d); mkdir $R/b; printf '# TYPES.md\n| Type | Meaning |\n|---|---|\n| `Concept` | c |\n' > $R/TYPES.md; printf '# TAGS.md\n| Tag | Description |\n|-----|-------------|\n| `alpha` | a |\n' > $R/TAGS.md; printf '# SPEC\n' > $R/SPEC.md; }
put() { printf -- '---\ntype: Concept\ndescription: d\ntags:\n  - alpha\n%b\n---\n# T\n' "$2" > $R/b/$1.md; }
```

#### D-26 Go refuses frontmatter that ruamel reads (`\/` escape, odd anchor names, empty keys)
- **Cases:**   - `title: "a\/b"` (JSON-style `\/` escape): `check`, `list`
  - anchor names outside `[A-Za-z0-9_-]`: `title: &a.b x`, `title: &ä x`, `x: &s/1 y` with `ref: *s/1`: `check`, `list`
  - empty keys: `: v` (block mapping) and `m: {: a}` (flow mapping): `check`, `list`
  - alias used as a key (`x: &a title` with `*a : AliasKeyTitle`): `list` (Go reads the file but cannot find `title`, so the title falls back to the file name)
  - the same loss shows in `find`, `index` and `reindex`: type, title, description and tags come from the same read
- **Channel:** exit code, stdout, file-tree effect
- **Difference:** Python reads these files and `check` reports nothing (exit 0). Go refuses the whole frontmatter block: `check` reports `okf/frontmatter/parseable` (exit 4) and `list`, `find`, `index` see the file without type, title, description and tags.
```text
Python (exit 0):
  OK — 0 violations
Go (exit 4):
  ERROR    okf/frontmatter/parseable b/c.md  (no parseable frontmatter: found unknown escape character (line 6, column 10))
  1 VIOLATIONS
```
- **Reason:** Go: `frontmatter.parseBlock` passes the block to yaml.v3, whose scanner has no `\/` escape and accepts only `[0-9A-Za-z_-]` in anchor names, and `frontmatter.Lookup` skips alias keys. Python: `read_frontmatter` loads with ruamel.yaml 0.19.1, which accepts all of these.
- **Capability preserved:** no. These are valid YAML 1.2 files that Python reads and checks correctly. In Go the file loses type, title, description and tags (`list --where 'type = Concept'` no longer selects it) and `check` exits 4. The `\/` escape written by JSON-style tools is the most likely case; the workaround is to rewrite the text (`/` without backslash, plain anchor names, no empty keys).
- **Owner:** Go core and read side (F: OKFT-daut)
- **Reproduce:** `mk; put c 'title: "a\\/b"'`
  `okf --root $R check`
- **PO decision:**

#### D-27 NEL (U+0085), LS (U+2028) and PS (U+2029) in frontmatter
- **Cases:**   - `<c>` is U+0085, U+2028 or U+2029; every context below was run with all three (`check`, `list`)
  - Go refuses the block, Python reads it: `title:<c> T`; a line holding only `<c>`; `m: &a<c>b 1`
  - Python refuses the block, Go reads it: `title: T # x<c>y`; own-line comment `# x<c>y`; `description: |` with `x<c>y`; `description: >` with `x<c>y`
  - both read, the text differs: `title: a<c>b` (NEL only); `title: ab<c>`; `title: <c>ab`; `title: "a<c>b"` (NEL only); `title: 'a<c>b'` (NEL only); `tags: [al<c>pha, beta]` (NEL only); `description: x<c>  y`; `type: Concept<c>`
  - identical in both: `title: a<c>b` (LS, PS only); `title: "a<c>b"` (LS, PS only); `title: 'a<c>b'` (LS, PS only); `tags: [al<c>pha, beta]` (LS, PS only); key `k<c>x: 1`; both refuse: -
- **Channel:** exit code, stdout
- **Difference:** ruamel treats the three characters as line breaks; Go treats them as ordinary characters (it swaps them for private-use characters before parsing). So Python reads blocks that Go refuses, and Go reads blocks that Python refuses. A trailing NEL or LS on `type: Concept` is trimmed by Python and kept by Go, so `list --where 'type = Concept'` misses that file in Go.
```text
Python (exit 0):
  OK — 0 violations
Go (exit 4):
  ERROR    okf/frontmatter/parseable b/c.md  (no parseable frontmatter: could not find expected ':' (line 6, column 1))
  1 VIOLATIONS
```
- **Reason:** Go: `breaks.go` in go/internal/frontmatter swaps NEL, LS and PS for placeholders before `parseBlock`, on the premise that YAML 1.2 treats them as ordinary characters. Python: ruamel's scanner (`_THE_END`, `scan_line_break`) and reader count all three as line ends.
- **Capability preserved:** no. Python reads and checks the blocks with the character after `key:`, alone on a line or inside an anchor name (`check` exit 0); Go refuses the whole block there (exit 4). The characters appear after copy-paste only; the workaround is to delete them.
- **Owner:** Go core and read side (F: OKFT-daut)
- **Reproduce:** `mk; put c 'title:\xc2\x85 T'`
  `okf --root $R check`
- **PO decision:**

#### D-28 TOML integer above int64 aborts every command that reads the config
- **Cases:**   - `<R>/.okf.toml` with `build_serial = 18446744073709551616` (2^64): `check`, `find C`, `build-index`, `migrate`
  - boundary, `check`: `9223372036854775808` (2^63) fails; `9223372036854775807` and `-9223372036854775808` pass
  - user config `$XDG_CONFIG_HOME/okf/config.toml` with `big = 99999999999999999999`: every run without `--root` (`list`)
- **Channel:** exit code, stderr
- **Difference:** Python reads the file and goes on. Go refuses it with exit 2 although no okf key uses the number.
```text
Python (exit 0):
  OK — 0 violations
Go (exit 2):
  ERROR: <R>/.okf.toml is not valid TOML: 18446744073709551616 is out of range for int64 (at line 1, column 16)
```
- **Reason:** Go: `catalogue.ReadTOML` (go/internal/catalogue/root.go) decodes with BurntSushi/toml v1.6.0, which parses integers with `strconv.ParseInt(…, 0, 64)`. Python: `tomllib` has arbitrary-precision integers.
- **Capability preserved:** no. A config that holds any integer above int64 is valid TOML. Python works; Go refuses `check`, `find`, `build-index`, `migrate` and every run that reads the user config. No okf key takes such a number, so this is rare; the workaround is to remove the number.
- **Owner:** Go core and read side (F: OKFT-daut)
- **Reproduce:** `mk; put c 'title: T'; printf 'build_serial = 18446744073709551616\n' > $R/.okf.toml`
  `okf --root $R check`
- **PO decision:**

#### D-29 Load-time checks of ruamel that Go skips (equal duplicate keys, invalid tag values, merge-key misuse)
- **Cases:**   - duplicate keys that are equal after typing: `1: a` + `01: b`, `1` + `0x1`, `true` + `True`, `null` + `~`; also `1` + `1.0` (Python refuses although YAML 1.2 has two keys): `check`, `list`
  - explicit tags with invalid values: `title: !!int abc`, `!!float abc`, `!!timestamp foo`, `!!seq abc`, `!!map abc`, `!!omap {a: 1}`: `check`, `list`
  - merge-key misuse: `<<: 5`, `<<: foo`, `<<:` (empty), `<<: [1, 2]`, two `<<` keys in one mapping: `check`, `list`
  - Python then sees the file without frontmatter in `list`, `find`, `index`; Go reads it
- **Channel:** exit code, stdout
- **Difference:** Python refuses these blocks with `okf/frontmatter/parseable` (`check` exit 4). Go reads them (`check` exit 0, `list` shows the title). The three files below hold `1: a` with `01: b`, `n: !!int abc` and `<<: 5`.
```text
Python (exit 4):
  ERROR    okf/frontmatter/parseable b/dup.md  (no parseable frontmatter: found duplicate key "1" with value "b" (original value: "a") (line 7, column 1))
  ERROR    okf/frontmatter/parseable b/merge.md  (no parseable frontmatter: expected a mapping or list of mappings for merging, but found scalar (line 7, column 5))
  ERROR    okf/frontmatter/parseable b/tag.md  (no parseable frontmatter: invalid literal for int() with base 10: 'abc')
  3 VIOLATIONS
Go (exit 0):
  OK — 0 violations
```
- **Reason:** Go: `duplicateKey` (go/internal/frontmatter/frontmatter.go) compares keys by their written text and skips `<<`; yaml.v3 builds a node tree and constructs no typed values. Python: ruamel builds typed keys and values, so equal keys, `int('abc')` and a non-mapping merge value raise, and `read_frontmatter` reports the exception as the parse error.
- **Capability preserved:** no. No data is lost and Go reads the file, but `check` no longer flags input that is invalid YAML (a key spelled two ways, `!!int abc`, a non-mapping merge). Python also over-reports `1` vs `1.0` (two keys in YAML 1.2). The PO decides whether `check` has to keep flagging these.
- **Owner:** Go core and read side (F: OKFT-daut)
- **Reproduce:** `mk; put dup '1: a\n01: b\ntitle: T'; put tag 'title: T\nn: !!int abc'; put merge 'title: T\n<<: 5'`
  `okf --root $R check`
- **PO decision:**

#### D-30 Impossible dates and out-of-range timestamps in a custom key (`2026-02-30`, `T24:00:00Z`)
- **Cases:**   - plain scalar under a custom key: `some_date: 2026-02-30`, `2026-13-45`, `2026-05-29T24:00:00Z`, `2026-05-29T10:00:00+24:00`: `check` (Python 4, Go 0), `list --where 'type = Concept'`, `list --where 'some_date = 2026-02-30'`, `find`, `reindex`
  - OKF keys: `generated.at: 2026-02-30T10:00:00Z`, `verified[0].at: 2026-13-01T00:00:00Z`: `check` (both exit 4, different rule), `list --where 'tier = human-reviewed'`
  - quoted `"2026-02-30"` is a string in both (identical)
- **Channel:** exit code, stdout, file-tree effect
- **Difference:** Python reads neither a string nor a datetime: ruamel raises `ValueError` while building the timestamp, so the whole frontmatter block of the file fails to load (`check` exit 4, the file loses type, title and tags in every command). Go keeps the scalar a string and reads the file (`check` exit 0).
```text
Python (exit 4):
  ERROR    okf/frontmatter/parseable b/feb30.md  (no parseable frontmatter: day 30 must be in range 1..28 for month 2 in year 2026)
  ERROR    okf/frontmatter/parseable b/h24.md  (no parseable frontmatter: hour must be in 0..23, not 24)
  2 VIOLATIONS
Go (exit 0):
  OK — 0 violations
```
- **Reason:** Python: ruamel's constructor builds `datetime` objects and raises `ValueError` for an impossible field; `read_frontmatter` returns it as the parse error. Go: `spec.yamlTimestamp` (go/internal/spec/yamltime.go) recognises the same shape, but `frontmatter.Read` never refuses the block for it, so the value stays text.
- **Capability preserved:** no. Changed from yes in my first report, for the same reason as the load-time checks entry. Go reads the rest of the file, which Python loses, but Go no longer flags an unquoted impossible date in a non-OKF key (exit 4 becomes 0). Go still flags the OKF timestamp keys (`okf/format/timestamp`, exit 4). The PO decides whether the custom-key finding is required.
- **Owner:** Go core and read side (F: OKFT-daut)
- **Reproduce:** `mk; put feb30 'title: T\nsome_date: 2026-02-30'; put h24 'title: T\nsome_date: 2026-05-29T24:00:00Z'`
  `okf --root $R check`
- **PO decision:**

#### D-31 Timestamp text: the author's text (Go) against ruamel's re-render (Python)
- **Cases:**   - `check` messages (`okf/lifecycle/stale-after`, `okf/format/timestamp`): `stale_after: 2026-05-29T18:32:00.5Z`, `2026-05-29t18:32:00Z`, `2026-05-29T18:32:00.9999995+00:00`, `2026-05-29 18:32:00.250 +02:00`; naive or date-only `generated.at`, `verified[].at`, `usage_window.from`
  - `check` drift message (`okf/trust/drift`, git repo): `generated.at: 2020-01-01T00:00:00.5Z`, `2020-01-01 00:00:00.25 +02:00`, `2020-01-01T00:00:00.1234567Z`
  - `title: 2026-05-29T18:32:00.5Z`, `description: 2026-05-29 18:32:00.25 +02:00`: `list`, `find --breakdown`, `index`, `reindex`
  - `plain_ts: 2026-05-29T18:32:00.5Z`: `list --where 'plain_ts = 2026-05-29T18:32:00.500000Z'` matches in Python, `... = 2026-05-29T18:32:00.5Z` in Go; `~ 18:32:00.5` in both
  - not affected: `read`, `read --json`, `--where` on the instant keys
- **Channel:** stdout, file-tree effect
- **Difference:** Go prints the timestamp as the author wrote it; Python prints ruamel's re-render (fraction padded to six digits and rounded, `t` and `z` upper-cased, zone text normalised). It shows wherever title, description or a message is printed or matched as text.
```text
Python (exit 0):
  title: 2026-05-29T18:32:00.500000Z
Go (exit 0):
  title: 2026-05-29T18:32:00.5Z
```
- **Reason:** Python: `scalar_text` (cli/okf/catalogue.py) dumps every non-string value through ruamel's round-trip dumper, which re-renders a timestamp from the parsed `datetime`. Go: `frontmatter.ScalarText` (go/internal/frontmatter/access.go) returns the node text as written.
- **Capability preserved:** yes. The instant is the same; only the spelling differs. A user selects the same concepts with the matching literal (Python needs `.500000Z`, Go the written `.5Z`; `~ 18:32:00.5` matches in both). A script that pastes Python's re-rendered literal into `--where` on a non-instant key would stop matching in Go.
- **Owner:** Go core and read side (F: OKFT-daut)
- **Reproduce:** `mk; put c 'title: 2026-05-29T18:32:00.5Z'`
  `okf --root $R list --where 'path ~ b/'`
- **PO decision:**

#### D-32 Anchor and explicit-tag prefix: Python adds it to scalars, Go adds it to collections
- **Cases:**   - scalars, Python prints the prefix: `title: &a 5`, `description: &b 6`, `title: !!str 123`, `title: !t foo`, `type: !!str Concept`, `k: &a 5`
  - collections, Go prints the prefix: `title: &a [x, y]`, `title: &a {x: 1}`, anchored block list, `!!seq [a, b]`, `!!map {a: 1}`, `description: !!set {a, b}`, `!!omap [a: 1]`
  - commands: `list`, `list --where 'k = 5'`, `index nb --json`, `read b/a --follow 1 --max-tokens 1`, `toc`, `visualize` (`viz.html`), `check`
  - `check`: `type: !!str Concept` (Python reports it unregistered, Go accepts it); `status: !!str draft` (message text differs)
- **Channel:** stdout, file-tree effect, exit code
- **Difference:** Python prints `&a` or the explicit tag in front of an anchored or tagged scalar; Go prints the plain value. For collections it is the other way round: Go prints `&a [x, y]`, Python prints `[x, y]`.
```text
Python (exit 0):
  title: &a 5
  path: b/a
  title: [x, y]
  path: b/b
Go (exit 0):
  title: &a [x, y]
  path: b/b
  title: 5
  path: b/a
```
- **Reason:** Python: `scalar_text` returns a `str` as is but dumps ints, floats, bools and tagged scalars through the round-trip dumper (`&a`, `!!str`); the first dump line of a collection carries no anchor or tag. Go: `frontmatter.ScalarText` returns the scalar text without prefix and the first `yaml.Marshal` line for a collection (`&a [x, y]`, `!!seq [a, b]`).
- **Capability preserved:** yes. The value is the same; only the printed prefix differs. `--where 'k = 5'` selects an anchored `k: &a 5` in Go; Python needs `'&a 5'`. Go accepts `type: !!str Concept` (a valid string); Python wrongly reports it unregistered.
- **Owner:** Go core and read side (F: OKFT-daut)
- **Reproduce:** `mk; put a 'title: &a 5'; put b 'title: &a [x, y]'`
  `okf --root $R list --where 'path ~ b/'`
- **PO decision:**

#### D-33 Number text: ruamel re-renders floats with exponent or underscores and negative hex/binary ints
- **Cases:**   - `title`/`description`/`k` set to `1_0.5`, `-0b11`, `-0x1F`, `1e400`, `.5e+3`, `1_0e3`, `0e3`, `1e-0`, `12e308`: `list --json`, `list --where 'k = <spelling>'`
  - sweep of 732 numeric forms (sign x mantissa x exponent, plus signed hex/binary/octal): 310 identical, 364 differ in spelling only, 19 are garbled by Python, 39 crash Python (see the crash entry); no numeric value changes
  - forms that read identically: `1e3`, `1E3`, `1_000`, `.5`, `5.`, `+1`, `0o17`, `017`, `0x1F`, `0b11`, `.inf`, `.nan`
- **Channel:** stdout, file-tree effect
- **Difference:** Go prints the number as written. Python prints ruamel's re-rendered form: `1_0.5` becomes `010.5`, `-0x1F` becomes `!!int '0x-1F'`, `1e400` becomes `.inf` (so `k = .inf` matches both `1e400` and `12e308`).
```text
Python (exit 0):
  title: !!int '0x-1F'
  path: b/b
  title: 010.5
  path: b/a
Go (exit 0):
  title: -0x1F
  path: b/b
  title: 1_0.5
  path: b/a
```
- **Reason:** Python: ruamel keeps floats and non-decimal ints as `ScalarFloat`/`HexInt`/`BinaryInt` and its dumper (`represent_scalar_float`, representer.py) rebuilds the text from parts; `scalar_text` prints that. Go: `frontmatter.ScalarText` keeps the written text.
- **Capability preserved:** yes. No numeric value changes. Go prints exactly what the author wrote; Python prints a re-spelled or garbled form. `--where 'k = v'` selects the same concepts when the literal matches the printed form of the implementation.
- **Owner:** Go core and read side (F: OKFT-daut)
- **Reproduce:** `mk; put a 'title: 1_0.5'; put b 'title: -0x1F'`
  `okf --root $R list --where 'path ~ b/'`
- **PO decision:**

#### D-34 Python crashes (exit 1) on frontmatter values that Go reads or refuses cleanly
- **Cases:**   - `title: -0e0` and 39 of the 732 numeric forms (floats that are zero or underflow to zero, written with an exponent and a sign or a trailing dot, e.g. `-0e0`, `-0e3`, `-0E3`, `-0e+3`, `-0.e3`, `+0.e0`, `-1e-400`, `+5.e-400`): any command that reads the file (`list`, `find`, `index`, `check`)
  - `k: !!bool maybe`: `check`, `list`
  - `title: "\ud83d\ude00 smile"` (JSON-style surrogate-pair escapes): `list`, `check`; Go answers with an `okf/frontmatter/parseable` finding (exit 4)
- **Channel:** exit code, stderr, stdout
- **Difference:** As soon as one concept holds such a value, Python aborts the whole command with exit 1 (a traceback; `kind: internal` in `--json`). Go reads the value or reports a parse finding.
```text
Python (exit 1):
  ValueError: not enough values to unpack (expected 2, got 1)
Go (exit 0):
  title: -0e0
```
- **Reason:** Python: `scalar_text` calls ruamel's `represent_scalar_float`, which raises `ValueError`; `construct_yaml_bool` raises `KeyError`, which `read_frontmatter` (it catches `YAMLError` and `ValueError`) does not catch; surrogate escapes give a string that cannot be printed. Go: no typed dump, `!!bool maybe` is text, surrogate escapes are a parse finding.
- **Capability preserved:** yes. Go works where Python aborts the command for the whole catalogue. For the surrogate escapes the input is not valid YAML (a surrogate half is no character; `\U0001F600` is the valid spelling) and Go reports a finding instead of crashing.
- **Owner:** Go core and read side (F: OKFT-daut)
- **Reproduce:** `mk; put c 'title: -0e0'`
  `okf --root $R list --where 'path ~ b/'`
- **PO decision:**

#### D-35 TAB as separation whitespace: ruamel refuses the block, Go reads it
- **Cases:**   - Python refuses, Go reads: `status:<TAB>todo`, `type:<TAB>Concept`, `title:<TAB>Tabbed`, `description:<TAB><TAB>d2`, `description: <TAB>d3`, `description: d4<TAB>`, `description: a<TAB>b`, `title: T<TAB># c`, `k<TAB>: 1`, `title:<TAB>"Quoted"`, `status:<TAB>[draft]`, `stale_after:<TAB>2026-01-01T00:00:00Z`, `description:<TAB>` followed by a continuation line
  - both read: a TAB inside a flow list `[alpha,<TAB>beta]`, inside a flow map `{a:<TAB>1}`, inside quoted scalars, block scalars and comments
  - both refuse (wording differs): a TAB as indentation of a nested key or list item, after a block dash `-<TAB>alpha`, a line holding only a TAB
  - commands: `check`, `list --where 'status = todo'`, `list --where 'type = Concept'`, `find`, `index`, `reindex`
- **Further cases (second sweep, same cause: `verify` writes where Python's loader refuses):**   - `hz/date-bad.md` with `generated: {at: 2026-13-45, by: x}`, then `verify hz/date-bad --by human:x`
  - `hz/tabs.md` with `type:` followed by a tab and `Concept`, then `verify hz/tabs --by human:x`
  - `hz/timestamps.md` with `stale_after: 0000-00-00` and an impossible date in `verified`, then `verify hz/timestamps --by human:x`
- **Channel:** exit code, stdout, file-tree effect
- **Difference:** A TAB after a colon is separation whitespace in YAML. Python refuses the whole block (`check` exit 4, the file loses all its keys in every command); Go reads it. Both refuse a TAB as indentation.
```text
Python (exit 4):
  ERROR    okf/frontmatter/parseable b/c.md  (no parseable frontmatter: found character '\t' that cannot start any token (line 7, column 8))
  1 VIOLATIONS
Go (exit 0):
  OK — 0 violations
```
- **Reason:** Python: ruamel's scanner rejects a TAB wherever a block token may start. Go: `frontmatter.parseBlock` hands the block to yaml.v3 (libyaml rules), which accepts a TAB as separation space and rejects it only as indentation.
- **Capability preserved:** yes. Python then reads nothing of such a file (type, title, description, tags, status missing; `type = Concept` misses it; `reindex` lists it by file name); Go reads it. For `status:<TAB>todo` both exit 4 for different rules (Python: parseable; Go: `okf/lifecycle/status`, because `todo` is no valid status).
- **Owner:** Go core and read side (F: OKFT-daut)
- **Reproduce:** `mk; put c 'title: T\nstatus:\tstable'`
  `okf --root $R check`
- **PO decision:**

#### D-36 Typed `title` / `description` (and `type`, `tags`) as index and list link text
- **Cases:**   - 15 of 44 title/description forms differ (the quoted key is the one that differs): `title: &a⏎  - x⏎  - y; description: &b⏎  - z`, `title: &a 5; description: &b 6`, `title: &a [x, y]; description: &b [z]`, `title: &a {x: 1}; description: &b {z: 2}`, `title: ? [a, b]⏎  : c`, `description: 1e400`, `title: - a⏎  - b; description: - c⏎  - d`, `title: - a⏎- b; description: - c`, `title: - a: 1⏎    b: 2⏎  - c`, `title: !t foo; description: !t 5`, `title: !!seq [a, b]; description: !!set {a, b}`, `title: !!map {a: 1}; description: !!omap [a: 1]`, `title: !!str 5; description: !!str true`, `title: 2026-05-29 18:32:00 +02:00`, `description: 2026-05-29T18:32:00.5Z`
  - identical in both (29 forms, the title shown): `*anc`, `&a foo`, `>⏎  line1⏎  line2`, `|⏎  line1⏎  line2`, `true`, `yes`, `"a [b] (c) *d* `e`"`, `2026-05-29`, `T`, `""`, `0.1`, `1e3`, `.inf`, `.5`, `.NaN`, `42`, `0x1F`, `0o7`, `+5`, `1_000`, `[]`, `[a, b]`, `a: 1⏎  b: 2`, `{}`, `{a: 1, b: 2}`, `first⏎  second`, `~`, `"   "`, `"42"`
  - commands: `index <bundle>` (no index.md), `index <bundle> --json`, `index --full <bundle>`, `index --json`, `reindex <bundle>`, `list --json`
  - typed `type`/`tags` (`type: &a 5`, `type: !!str Note`, `tags: [&t 7, !!str x, 2026-05-29T18:32:00.5Z, 0o7, 1e3]`): `index --full`, `tags`
  - order: Python sorts by `casefold()` and its order for equal titles is not file-name order; Go sorts with `x/text` case folding and keeps file-name order for ties (U+3000 sorts before U+13A0 in Go, after it in Python)
- **Channel:** stdout, file-tree effect
- **Difference:** A `title` or `description` that is not a plain string prints differently: Python shows ruamel's re-render (`  - a` for a block list, no tag or anchor on collections), Go shows the written text (`- a`, `!!seq [a, b]`). The same text appears in `index`, `index --full`, `reindex` and `list --json`.
```text
Python (exit 0):
  * [  - a](list_block.md) [Concept] - d
  * [[a, b]](tag_list.md) [Concept] - d
  * [2026-05-29T18:32:00.500000Z](ts_z.md) [Concept] - d
Go (exit 0):
  * [- a](list_block.md) [Concept] - d
  * [!!seq [a, b]](tag_list.md) [Concept] - d
  * [2026-05-29T18:32:00.5Z](ts_z.md) [Concept] - d
```
- **Reason:** Python: `list_dir_concepts` and `fm_meta` (cli/okf/catalogue.py) take title and description from `scalar_text` and sort by `casefold()`. Go: `catalogue/indexblock.go` with `frontmatter.ScalarText` (written text for scalars, first `yaml.Marshal` line for collections) and `pytext.Casefold` (x/text `cases.Fold`).
- **Capability preserved:** yes. Every concept is still listed with link, type and description; only the spelling of the link text and, for ties and rare Unicode titles, the line order differ. The forms named in the seed (`1e3`, `.inf`, `0.1`, `1_000`, `0o7`, bool, `~`, date) print identically.
- **Owner:** Go navigation commands (F: OKFT-se5f) + Go core and read side (F: OKFT-daut)
- **Reproduce:** `mk; put list_block 'title:\n  - a\n  - b'; put tag_list 'title: !!seq [a, b]'; put ts_z 'title: 2026-05-29T18:32:00.5Z'`
  `okf --root $R index b`
- **PO decision:**

#### D-37 TOML parse-error wording and date/time repr (different TOML libraries)
- **Cases:**   - `<R>/.okf.toml` syntax errors, `check` (the same text for `find`, `build-index`, `migrate`): `registry_format = `; `kc_root = "abc`; `[a ⏎ b = 1`; `a = 1 ⏎ a = 2`; `a = 1 b = 2`; `a = "\q"`; `a b = 1`; `a = 2026-13-45`; `[a] ⏎ x = 1 ⏎ [a] ⏎ y = 2`; `a = 1 ⏎ [a] ⏎ y = 2`; `a = "x<0x01>y"`; `a = 1<0x00>`; `just text`; `a = 1__0`; `a = 012`; `a = 1.`; `a = True`; `a = 'x ⏎ y'`; `[[a]] ⏎ x=1 ⏎ [a] ⏎ y=2`; `a = 1<0x0d>b = 2`; `a = "\ud800"`
  - user config `$XDG_CONFIG_HOME/okf/config.toml` (`root = "/x` and a duplicate `root` key), any run without `--root`
  - date/time values in the config-type note of `check`: `ignore_rules = 2026-05-29`, `07:32:00`, `2026-05-29T07:32:00`, `2026-05-29T07:32:00Z`
- **Further cases (second sweep, same cause: invalid TOML in `.okf.toml` / `config.toml`):**   - `.okf.toml` = `[unclosed`, then `check`, `find bread`, `migrate`, `tags --register zz "a tag"`
  - `~/.config/okf/config.toml` = `root = ` (invalid), then `--global info` and `--global list --where "type = Concept"`
- **Channel:** stderr
- **Difference:** Both print `ERROR: <path> is not valid TOML: <reason> (at line L, column C)` and exit 2, but the reason text differs in 21 of 21 samples (and often the column). Date and time values in the note print as `datetime.date(2026, 5, 29)` in Python and `2026-05-29 00:00:00 +0200 date-local` in Go.
```text
Python (exit 2):
  ERROR: <R>/.okf.toml is not valid TOML: Cannot overwrite a value (at line 2, column 6)
Go (exit 2):
  ERROR: <R>/.okf.toml is not valid TOML: Key 'a' has already been defined. (at line 2, column 7)
```
- **Reason:** Go: `catalogue.ReadTOML` (go/internal/catalogue/root.go) uses BurntSushi/toml v1.6.0 and prints its message plus `(at line L, column C)`. Python: `tomllib` (TOML 1.0) messages; date values are printed with `repr`.
- **Capability preserved:** yes. Same frame, same exit code 2, same commands fail; only the reason text, the column and the repr of date values differ.
- **Owner:** Go core and read side (F: OKFT-daut)
- **Reproduce:** `mk; put c 'title: T'; printf 'a = 1\na = 2\n' > $R/.okf.toml`
  `okf --root $R check`
- **PO decision:**

#### D-38 TOML inputs that only one reader accepts (Go accepts TOML 1.1 syntax and a BOM; Python crashes on invalid UTF-8)
- **Cases:**   - Python refuses (exit 2), Go reads (exit 0), `check` with `<R>/.okf.toml`: inline table over two lines `a = {x = 1,⏎ y = 2}`; `"\x41"` escape; `"\e"` escape; `t = 12:30`; `t = 2026-05-29T12:30Z`; `a = {x = 1,}`; a UTF-8 BOM before `a = 1`; `a.b = 1` then `a = 2`
  - invalid UTF-8 byte in `<R>/.okf.toml` (`a = "\xff"`): Python exit 1 with a traceback, Go exit 2
  - identical in both: arrays of mixed types, `inf`/`nan`, CRLF, empty file, comment-only file, unicode keys
- **Channel:** exit code, stderr
- **Difference:** Go accepts every config that Python accepts and also TOML 1.1 syntax, a BOM and a dotted-key conflict that Python's TOML 1.0 parser refuses with exit 2. A byte that is not valid UTF-8 gives a Python traceback instead of an error message.
```text
Python (exit 2):
  ERROR: <R>/.okf.toml is not valid TOML: Invalid initial character for a key part (at line 1, column 12)
Go (exit 0):
  OK — 0 violations
```
- **Reason:** Go: BurntSushi/toml v1.6.0 (`catalogue.ReadTOML`) accepts TOML 1.1 syntax, skips a BOM and does not reject the dotted-key conflict. Python: `tomllib` is strict TOML 1.0; invalid UTF-8 raises `UnicodeDecodeError` outside its error handling.
- **Capability preserved:** yes. Nothing a Python user can do is blocked: Go reads every file Python reads. A file that only Go accepts is not a valid config for the Python CLI. The Python traceback on invalid UTF-8 is a Python defect.
- **Owner:** Go core and read side (F: OKFT-daut)
- **Reproduce:** `mk; put c 'title: T'; printf 'a = {x = 1,}\n' > $R/.okf.toml`
  `okf --root $R check`
- **PO decision:**

#### D-39 YAML parse-error wording and position, inputs other than handbook/broken-yaml.md
- **Cases:**   - 48 blocks are refused by both; 5 have identical text, 43 differ in wording, and 27 of those differ in (line, column) as well; `check`, `list`
  - unclosed or extra brackets and quotes: `tags: [a, b`, `m: {a: 1`, `tags: [a]]`, `title: "unclosed`, `title: 'unclosed`
  - structure: a key indented under another key, `title: a: b`, `title T` (no colon), `- a` after a mapping, mixed sequence and mapping, `key:value`-style lines
  - scalars: undefined alias `*x`, `@foo`, a backtick, `%foo`, bad escapes `\q`, `\xZZ`, `\u12G4`, block scalar with bad header or indentation
  - control characters (NUL, BEL, ESC, DEL, U+FFFE), bad tags (`!<bad`), `%YAML 9.9`, a TAB as indentation or after a block dash
- **Channel:** stdout
- **Difference:** Both refuse the same files with the same rule and exit code, but Python quotes ruamel's scanner text and Go quotes libyaml's text, and the position differs for part of the inputs. Control characters give Python no line and column at all.
```text
Python (exit 4):
  ERROR    okf/frontmatter/parseable b/c.md  (no parseable frontmatter: mapping values are not allowed here (line 6, column 9))
Go (exit 4):
  ERROR    okf/frontmatter/parseable b/c.md  (no parseable frontmatter: mapping values are not allowed in this context (line 6, column 9))
```
- **Reason:** Python: `_yaml_reason` (cli/okf/catalogue.py) formats ruamel's problem and its `problem_mark` line and column. Go: `failurePosition` (go/internal/frontmatter/reason.go) takes yaml.v3's message and finds the column by re-parsing prefixes of the block. This is the same cause as the known golden entry.
- **Capability preserved:** yes. Both refuse the same files with the same rule (`okf/frontmatter/parseable`) and exit code 4; only the explanation text and, for part of the inputs, the position differ.
- **Owner:** Go core and read side (F: OKFT-daut)
- **Reproduce:** `mk; put c 'title: a: b'`
  `okf --root $R check`
- **PO decision:**

#### D-40 `ReusedAnchorWarning` on Python stderr, nothing in Go
- **Cases:**   - `a: &x 1` and `b: &x 2` (the same anchor name defined twice) in one file: any command that reads the file (`list`, `check`)
- **Channel:** stderr
- **Difference:** Python prints a `ReusedAnchorWarning` on stderr each time it reads such a file; Go prints nothing. Exit code and stdout are identical.
```text
Python (exit 0):
  <site-packages>/ruamel/yaml/composer.py:227: ReusedAnchorWarning: 
  found duplicate anchor 'x'
  first occurrence   in "<unicode string>", line 7, column 4:
  second occurrence   in "<unicode string>", line 8, column 4:
Go (exit 0):
  (no output)
```
- **Reason:** Python: ruamel's composer calls `warnings.warn(ReusedAnchorWarning)` when an anchor name is redefined (composer.py). Go: yaml.v3 redefines the anchor silently.
- **Capability preserved:** yes. Noise only. A redefined anchor is valid YAML.
- **Owner:** Go core and read side (F: OKFT-daut)
- **Reproduce:** `mk; put c 'title: T\na: &x 1\nb: &x 2'`
  `okf --root $R list --where 'path ~ b/'`
- **PO decision:**

### Area D. Process, I/O, ordering, completion and display

**Errors, ordering, shell completion: acceptance entries (work package K)**

Fixture: tests/golden/catalogue; `<ROOT>` in an excerpt stands for the working copy of the catalogue. `okf` means the Python CLI or the Go binary on the same input, both without network.

#### D-41 Go reports success when stdout cannot be written
- **Cases:**   - Closed stdout: `okf read handbook/glossary >&-` (run with `read`; every text-mode command prints through the same unchecked writes, not run separately)
  - Full device: `okf read handbook/glossary >/dev/full`
- **Channel:** exit code, stderr
- **Difference:** Python fails when its stdout flush fails (traceback, exit 1 on a closed stdout, exit 120 on a full device). Go ignores the failed write and exits 0 without a message.
```text
Python (exit 1): >&-       stderr ends: AttributeError: 'NoneType' object has no attribute 'flush'
Python (exit 120): >/dev/full stderr ends: OSError: [Errno 28] No space left on device
Go (exit 0): >&-       (stderr empty)
Go (exit 0): >/dev/full (stderr empty)
```
- **Reason:** Python: `main` in `cli/okf-cli.py` flushes stdout inside its `try`, and the interpreter flushes again at exit. Go: `run` in `go/cmd/okf/main.go` and `envelope.Run` print with `fmt.Print` and `fmt.Fprintln(os.Stdout, ...)` and never check the returned error (the other text-mode handlers were not all read).
- **Capability preserved:** yes, since `bfaf900` (K's run: no). K's finding, kept: A caller that writes to a full disk or a failing device gets exit 0 and lost output from Go, while Python reports the failure. Python's closed-stdout crash is not good behaviour either, but Go's silent success hides the lost output. There is no workaround except checking the output file afterwards. Closed stdout is the one case that stays at exit 0 (see Fixed in).
- **Fixed in `bfaf900` (2026-10-16):** all text of every command now goes through the new package `stdio` (`fmt.Print*` and `os.Stdout` replaced in every command package, in `envelope.Run` and in `main`): the first failed write is kept, the command runs on, and `main` ends with `stdio.Exit`,
  which writes one line to stderr and ends with status 120, the one CPython ends with when the flush of stdout fails at exit. Fixture: copy of tests/golden/catalogue. `okf --root . read handbook/glossary >/dev/full`: before exit 0, stderr empty; after exit 120, stderr `ERROR: cannot write to stdout: no space left on device`
  (Python: exit 120, `OSError: [Errno 28] No space left on device`); with `--json` the same in both. For a large answer (`handbook/big`, 400000 lines) Go gives 120 and Python 1 (its status depends on whether the error surfaces in `print` or in the final flush). A failing command that writes nothing keeps its own
  status in Python and Go (`read handbook/nonexistent >/dev/full`: 3). Closed stdout (`>&-`) is not fixed, and cannot be: since Go 1.22 the runtime opens `/dev/null` read-write on a closed descriptor 0 to 2 before `main` (`runtime/fds_unix.go`), so every write succeeds, and that is the descriptor that
  `subprocess.DEVNULL` (Python 3.14.6) and Node's `stdio: 'ignore'` hand to a child (checked: `/dev/null` with `O_RDWR`; a shell `>/dev/null` gives `O_WRONLY`). Treating it as closed would fail detached hook runs. No output is lost there, since no channel exists; Go exits 0 where Python crashes with exit 1 (`AttributeError`), the one difference left in this entry.
- **Owner:** Go core and read side (F: OKFT-daut)
- **Reproduce:** In a copy of tests/golden/catalogue: `okf --root . read handbook/glossary >/dev/full; echo $?` and `okf --root . read handbook/glossary >&-; echo $?`.
- **PO decision:**

#### D-42 Go is killed by SIGPIPE when the reader of a pipe exits early
- **Cases:**   - `okf read handbook/big | head -c 100`, with handbook/big.md holding 400000 body lines (about 6.8 MB)
  - The same pipeline under `set -o pipefail`
- **Channel:** exit code
- **Difference:** Python catches the broken pipe and exits 0; Go is ended by SIGPIPE, which the shell shows as 141. The bytes that `head` receives are the same.
```text
Python (exit 0): PIPESTATUS=0 0
Python (exit 0): pipefail rc=0
Go (exit 141): PIPESTATUS=141 0
Go (exit 141): pipefail rc=141
```
- **Reason:** Python: the entry point in `cli/okf-cli.py` catches `BrokenPipeError`, calls `_silence_broken_pipe_streams()` and exits 0. Go: `go/cmd/okf/main.go` has no SIGPIPE or EPIPE handling, so the Go runtime ends the process when stdout closes.
- **Capability preserved:** yes, since `bfaf900` (K's run: no). K's finding, kept: A script that checks the status of `okf` inside a pipeline (`set -o pipefail`, `PIPESTATUS`) sees success from Python and 141 from Go for `okf read x | head -1`. Without pipefail the pipeline status is the one of `head` and nothing differs.
- **Fixed in `bfaf900` (2026-10-16):** `stdio.Init` (the first call of `main`) replaces `os.Stdout` and `os.Stderr` by files on duplicates of the descriptors 1 and 2: the `os` package raises SIGPIPE on an EPIPE write for the numbers 1 and 2 only, so on the duplicates a broken pipe is an error of the write. `stdio.Exit` treats it as
  no failure, as Python's caught `BrokenPipeError`, and keeps the status of the command. Same pipelines as above: before `PIPESTATUS=141 0` and `pipefail rc=141`; after `PIPESTATUS=0 0` and `pipefail rc=0` (Python the same). Also 0 (before 141) for a small answer (`read handbook/glossary | true`), for `read handbook/big --json | head -c 100` and for stderr
  (`find zzzunknown 2>&1 | true`). A failing command keeps its own status through a closed pipe (`read handbook/nonexistent | true`: 3 before and after, Python 3); only `--json` differs there: Python ends with 120 and a flush warning, Go keeps the status of the command (3). No cost at startup: 300 runs of
  `read handbook/glossary` take 1.26 to 1.27 ms each with the fix against 1.41 to 1.43 ms before (three rounds, devt).
- **Owner:** Go core and read side (F: OKFT-daut)
- **Reproduce:** Create a concept with 400000 body lines in a copy of tests/golden/catalogue, then: `bash -c 'set -o pipefail; okf --root . read handbook/big | head -c 100 >/dev/null; echo "${PIPESTATUS[*]} $?"'`
- **PO decision:**

#### D-43 Go aborts normalize-tags and verify on a non-scalar frontmatter key
- **Cases:**   - `normalize-tags` (dry run) in a catalogue that holds `handbook/ck.md` with the frontmatter keys `? [a, b]` / `: v`, `type`, `title`, `tags: [t1]`
  - `normalize-tags --apply`, same catalogue
  - `verify handbook/ck --by human:x`
- **Channel:** exit code, stdout, stderr, file-tree effect
- **Difference:** With one such file present, Go stops the whole run with exit 2 and changes nothing. Python rewrites every file that needs it; for `verify` it also respells the key as `[a, b]: v`.
```text
Python (exit 0): normalize-tags --apply, stdout starts: --- a/handbook/ck.md
Python (exit 0): normalize-tags --apply, file-tree effect: M handbook/ck.md
Python (exit 0): verify, file-tree effect: -? [a, b]
Python (exit 0): verify, file-tree effect: -: v
Python (exit 0): verify, file-tree effect: +[a, b]: v
Go (exit 2): normalize-tags --apply: handbook/ck.md: a key of the frontmatter is not a scalar
Go (exit 2): verify: a key of the frontmatter is not a scalar
Go (exit 2): file-tree effect: (no file changed)
```
- **Reason:** Go: `go/internal/yamlpatch/yamlpatch.go:246` rejects a key that is not a scalar and the command stops for all files. Python: `cmd_normalize_tags` (`cli/okf/tags.py`) and the verify command (`cli/okf/verify.py`) use the ruamel round trip, which handles the key.
- **Capability preserved:** no. With one such file in the catalogue Go cannot normalize any file and cannot verify that file. Workaround: for `normalize-tags` a `--where` expression that excludes the file; none for `verify` of that file. Python's respelling of the key is the same YAML, so it is not corruption.
- **Owner:** Go frontmatter writer (F: OKFT-5lq2)
- **Reproduce:** Add handbook/ck.md = `---`, `? [a, b]`, `: v`, `type: Concept`, `title: ComplexKey`, `tags: [t1]`, `---`, `body`; run `okf --root . normalize-tags --apply` and `okf --root . verify handbook/ck --by human:x`.
- **PO decision:**

#### D-44 Python tracebacks become one-line errors in Go (S8, all triggers)
- **Cases:**   - Dangling symlink (`ln -s /nonexistent/target.md handbook/dangling.md`): `list --where "type = Concept"`, `find glossary`, `check`, `tags`, `wikilinks`
  - Directory where the file is expected (`mkdir -p handbook/xdir && mkdir handbook/xdir/index.md`): `read handbook/xdir`, `toc handbook/xdir`
  - Unreadable file (`chmod 000 handbook/glossary.md`): `read handbook/glossary`, `list --where "type = Concept"`, `find glossary`, `check`, `toc handbook/glossary`, `refs handbook/glossary.md`, `tags`, `wikilinks`, `verify handbook/glossary --by human:x`
  - Unwritable target: `chmod 555 handbook` then `rename handbook/overview.md handbook/overview2.md --apply`, `archive handbook/overview --apply`; `chmod 555 _ctx` then `ctx create newslug handbook/overview`; `chmod 444 handbook/overview.md` then `verify handbook/overview --by human:x`; `chmod 444 recipes/overview.md` then `merge-tags food --into meal --apply`; `chmod 444 TAGS.md` then `tags --register newtag "a new tag"`
  - Unreadable directory (`chmod 000 handbook/ops`): `reindex handbook --check` (`read`/`toc` of that directory are the next entry)
  - Unreadable user config (`chmod 000 ~/.config/okf/config.toml`): `--global info`
  - The same triggers with `--json` (`list --where "type = Concept" --json`, `verify ... --json`): the envelope has kind `internal`, exit 1, and only the message text differs
- **Channel:** stderr (exit code 1 and empty stdout are equal)
- **Difference:** Python prints a traceback ending in the exception line; Go prints one line from the error text. In `--json` mode both print the envelope and exit 1, the message reads `PermissionError: [Errno 13] ...` in Python and `*fs.PathError: open ...` in Go. `<ROOT>` stands for the catalogue copy.
```text
Python (exit 1): FileNotFoundError: [Errno 2] No such file or directory: '<ROOT>/handbook/dangling.md'
Go (exit 1): open <ROOT>/handbook/dangling.md: no such file or directory
Python (exit 1): IsADirectoryError: [Errno 21] Is a directory: '<ROOT>/handbook/xdir/index.md'
Go (exit 1): read <ROOT>/handbook/xdir/index.md: is a directory
Python (exit 1): PermissionError: [Errno 13] Permission denied: '<ROOT>/handbook/glossary.md'
Go (exit 1): open <ROOT>/handbook/glossary.md: permission denied
Python (exit 1): PermissionError: [Errno 13] Permission denied: '<ROOT>/handbook/overview.md' -> '<ROOT>/handbook/overview2.md'
Go (exit 1): rename <ROOT>/handbook/overview.md <ROOT>/handbook/overview2.md: permission denied
```
- **Reason:** Python: `main` in `cli/okf-cli.py` catches only `OkfError`; any other exception ends in a traceback, and `run_envelope` in `okf/output.py` prints it. Go: `run` in `go/cmd/okf/main.go` turns an unclassified error into kind `internal` through `okferr.As`, and `envelope.Run` prints `%T: %v`.
- **Capability preserved:** yes. Each input fails with exit 1 in both, with no output and no file written; only the failure text differs, and a caller that keys on exit 1 sees no change.
- **Owner:** Go core and read side (F: OKFT-daut)
- **Reproduce:** In a copy of tests/golden/catalogue as a non-root user (or with `setpriv --bounding-set -dac_override,-dac_read_search`): `chmod 000 handbook/glossary.md; okf --root . read handbook/glossary; echo $?` and `ln -s /nonexistent/target.md handbook/dangling.md; okf --root . check; echo $?`
- **PO decision:**

#### D-45 Unreadable directory used as a concept reference: Python exit 1, Go exit 3
- **Cases:**   - `chmod 000 handbook/ops`, then `read handbook/ops`
  - `chmod 000 handbook/ops`, then `toc handbook/ops`
- **Channel:** exit code, stderr
- **Difference:** Python lists the directory to find its index.md and fails with a permission traceback (exit 1). Go hides the error and reports not_found (exit 3) with a message that blames a missing index.md.
```text
Python (exit 1): PermissionError: [Errno 13] Permission denied: '<ROOT>/handbook/ops'
Go (exit 3): not found: handbook/ops is a directory without an index.md
```
- **Reason:** Python: `resolve_concept` in `cli/okf/catalogue.py` calls `os.listdir`, which raises `PermissionError`. Go: `ResolveConcept` in `go/internal/catalogue/bundles.go` ignores the `ListDir` error and falls through to the not_found message.
- **Capability preserved:** yes. Neither implementation can read the directory, so no result for valid input is lost. Go changes the exit class from 1 to 3 and the text no longer names the permission problem.
- **Owner:** Go core and read side (F: OKFT-daut)
- **Reproduce:** In a copy of tests/golden/catalogue as a non-root user: `chmod 000 handbook/ops; okf --root . read handbook/ops; echo $?`
- **PO decision:**

#### D-46 Deeply nested YAML frontmatter: Python RecursionError, Go succeeds
- **Cases:**   - `handbook/deep.md` with `tags:` followed by N nested `[` ... `]` (N = 250, 1000, 20000): `read handbook/deep --frontmatter-only`, `list --where "type = Concept"`, `check handbook`, `tags`
  - The same with nested maps `x: {a: {a: ... 1}}` (N = 250, 1000, 20000)
  - `hz/deep-nest.md` (N = 300): `read`, `toc`, `verify --by human:x`, `reindex hz --check`
  - N = 50 and N = 150 are identical in both (Python's limit lies between 150 and 250)
- **Channel:** exit code, stdout, stderr
- **Difference:** Python fails with a RecursionError traceback (exit 1, `check`: exit 1 instead of 4) once the nesting passes its recursion limit. Go parses the file and answers normally, tested up to N = 20000.
```text
Python (exit 1): RecursionError: maximum recursion depth exceeded
Go (exit 0): ---
Go (exit 0): type: Concept
Python (exit 1): check handbook: RecursionError: maximum recursion depth exceeded
Go (exit 4): check handbook: ERROR    okf/frontmatter/parseable handbook/broken-yaml.md  (no parseable frontmatter: did not find expected ',' or ']' (line 3, column 9))
```
- **Reason:** Python: `read_frontmatter` in `cli/okf/catalogue.py` runs ruamel.yaml, which recurses per nesting level. Go: the frontmatter reader under `go/internal/frontmatter` has no such limit (library not read; shown by runs).
- **Capability preserved:** yes. Go does everything Python does and also answers where Python crashes, so no user loses anything.
- **Owner:** Go core and read side (F: OKFT-daut)
- **Reproduce:** In a copy of tests/golden/catalogue: `python3 -c "open('handbook/deep.md','w').write('---\ntype: Concept\ntitle: Deep\ntags: '+'['*250+']'*250+'\n---\nbody\n')"` then `okf --root . read handbook/deep --frontmatter-only; echo $?`
- **PO decision:**

#### D-47 Tied titles and case-variant index files follow os.listdir in Python, name order in Go (S9)
- **Cases:**   - `reindex tb --check`, `reindex tb`, `reindex tb --init`: bundle `tb` with `index.md` (empty `<!-- okf:index -->` block), then `alpha.md`, `mid.md`, `zeta.md` all titled `Same Title`, created in that order
  - `read tb2` and `toc tb2`: directory `tb2` holding `Index.md` (created first, `# UPPER index`) and `index.md` (created second, `# lower index`)
  - Checked identical with such ties: `recent`, `list`, `find` (substring and FTS), `visualize`, `refs`, `tags`, `prime`, `index`, `check`
- **Channel:** stdout, file-tree effect
- **Difference:** The order of tied titles in the generated index block, and the choice between `Index.md` and `index.md` for a directory reference, differ. Python's `os.listdir` after creating zeta, mid, alpha, beta, omega gives ['omega.md', 'beta.md', 'alpha.md', 'mid.md', 'zeta.md'] on tmpfs and ['zeta.md', 'mid.md', 'alpha.md', 'beta.md', 'omega.md'] on btrfs, so Python's own output depends on the filesystem; Go's order is always by name.
```text
Python (exit 0): reindex tb on tmpfs: +* [Same Title](/tb/zeta.md) - d-zeta
Python (exit 0): reindex tb on tmpfs: +* [Same Title](/tb/mid.md) - d-mid
Python (exit 0): reindex tb on tmpfs: +* [Same Title](/tb/alpha.md) - d-alpha
Python (exit 0): reindex tb on btrfs: +* [Same Title](/tb/alpha.md) - d-alpha
Python (exit 0): reindex tb on btrfs: +* [Same Title](/tb/mid.md) - d-mid
Python (exit 0): reindex tb on btrfs: +* [Same Title](/tb/zeta.md) - d-zeta
Go (exit 0): reindex tb: +* [Same Title](/tb/alpha.md) - d-alpha
Go (exit 0): reindex tb: +* [Same Title](/tb/mid.md) - d-mid
Go (exit 0): reindex tb: +* [Same Title](/tb/zeta.md) - d-zeta
Python (exit 0): read tb2 (tmpfs): description: lower
Go (exit 0): read tb2: description: upper
```
- **Reason:** Python: `list_dir_concepts` in `cli/okf/catalogue.py` iterates unsorted `os.listdir` before a stable title sort, and `resolve_concept` picks the first case-insensitive `index.md` in directory order. Go: `RealFS.ListDir` (`go/internal/catalogue/files.go`) is `os.ReadDir`, which is sorted; it feeds `go/internal/catalogue/indexblock.go` and `ResolveConcept`.
- **Capability preserved:** yes. The same entries are written with the same data; only the order of tied titles and the rare `Index.md` versus `index.md` pick differ, and Go's order is reproducible on every filesystem while Python's is not. Python sorts explicitly for `recent`, `list`, `find` and the others, so they do not differ.
- **Owner:** Go core and read side (F: OKFT-daut) + Go link rewriting writes (F: OKFT-cm5o)
- **Reproduce:** Create `tb/index.md` with an empty index block and `alpha.md`, `mid.md`, `zeta.md` (same `title`) in this order on tmpfs, then `okf --root . reindex tb` and `git diff`; for the second shape create `tb2/Index.md`, then `tb2/index.md`, then `okf --root . read tb2`.
- **PO decision:**

#### D-48 A Python completer that raises aborts the whole completion; Go does not (S10a)
- **Cases:**   - `sync-export nothere/x <TAB>` and `sync-export /kc-gov/ownership <TAB>` (the concept does not resolve)
  - `sync-insert recipes/soup nothere/x <TAB>`
  - With a dangling symlink `handbook/dangling.md` among the concepts: `tags --validate <TAB>`, `merge-tags <TAB>`, `remove-tags <TAB>`, `sync-status --source <TAB>`, `sync-status --block <TAB>`, `sync-update --source <TAB>`, `sync-update --block <TAB>`
  - With `chmod 000 _ctx/cooking.md`: `ctx show <TAB>`
  - Not a case: `read nothere/ <TAB>` is identical in both (the same 9 option candidates)
- **Channel:** exit code, stderr, candidates
- **Difference:** When a completer raises, Python prints a traceback on stderr, exits 1 and writes no candidate. Go exits 0 and offers what it can compute, here the option candidates of the line. The zsh and bash glue discard completer stderr, so the user sees nothing (Python) or the option list (Go).
```text
Python (exit 1): sync-export nothere/x <TAB>: okf.errors.OkfError: not found: nothere/x
Python (exit 1): candidates written: none
Python (exit 1): merge-tags <TAB> with the dangling symlink: FileNotFoundError: [Errno 2] No such file or directory: '<ROOT>/handbook/dangling.md'
Python (exit 1): candidates written: none
Go (exit 0): sync-export nothere/x <TAB>: -h:show this help message and exit
Go (exit 0): sync-export nothere/x <TAB>: --help:show this help message and exit
Go (exit 0): sync-export nothere/x <TAB>: --json:print one JSON envelope {command, ok, data, warnings, error}
Go (exit 0): merge-tags <TAB> with the dangling symlink: 6 candidates, first: -h:show this help message and exit
```
- **Reason:** Python: `_complete_block_ids` in `cli/okf/sync.py` (via `resolve_concept`), `_complete_tags` in `cli/okf/parser_support.py`, `_complete_canon_sources` and `_complete_canon_block_ids` and `_complete_ctx_slugs` in `cli/okf/ctx.py` raise inside argcomplete, which has no handler. Go: `CompleteBlockIDs` in `go/internal/wikisync/completers.go`, `Tags` and `CtxSlugs` in `go/internal/complete/generic.go` return nothing on error and `complete.Run` still exits 0.
- **Capability preserved:** yes. Nothing Python offers is missing in Go: where Python offers no candidates because it crashed, Go offers options or the candidates it could read.
- **Owner:** Go shell completion (F: OKFT-50ly) + Go wikilinks and sync blocks (F: OKFT-ca1y)
- **Reproduce:** `_ARGCOMPLETE=1 _ARGCOMPLETE_SHELL=zsh COMP_LINE='okf --root . sync-export nothere/x ' COMP_POINT=35 _ARGCOMPLETE_STDOUT_FILENAME=/tmp/out okf; echo $?; cat /tmp/out` with the Python CLI and with the Go binary.
- **PO decision:**

#### D-49 The Files completer lists candidates in random order in Python, in a fixed order in Go (S10b)
- **Cases:**   - `visualize handbook --out <TAB>`
  - `check --types <TAB>`
  - `ctx create zz --import <TAB>`
  - Same completer in Python, not run separately: `ctx drop slug <TAB>`, `ctx move slug <TAB>`, `ctx list --for <TAB>`
- **Channel:** stdout (candidate order; the candidate set is equal)
- **Difference:** Python builds the file list from a set, so the order changes with every process (8 different orders in 8 runs). Go keeps the order of bash's `compgen`, the same on every run.
```text
Python (exit 0): PYTHONHASHSEED=1: .okf.toml TYPES.md SPEC.md TAGS.md PROPERTIES.md
Python (exit 0): PYTHONHASHSEED=2: SPEC.md PROPERTIES.md .okf.toml TYPES.md TAGS.md
Python (exit 0): PYTHONHASHSEED=3: TAGS.md TYPES.md .okf.toml PROPERTIES.md SPEC.md
Python (exit 0): PYTHONHASHSEED=4: .okf.toml TYPES.md PROPERTIES.md SPEC.md TAGS.md
Go (exit 0): run 0: .okf.toml PROPERTIES.md SPEC.md TAGS.md TYPES.md
Go (exit 0): run 1: .okf.toml PROPERTIES.md SPEC.md TAGS.md TYPES.md
```
- **Reason:** Python: `FilesCompleter.__call__` in argcomplete ends with `list(set(completion) - set(anticomp))`. Go: `Files` in `go/internal/complete/generic.go` keeps the `compgen` order and appends the directories.
- **Capability preserved:** yes. The same candidates are offered; only the order differs, and zsh shows the order it is given. Users get a stable order from Go.
- **Owner:** Go shell completion (F: OKFT-50ly)
- **Reproduce:** `_ARGCOMPLETE=1 _ARGCOMPLETE_SHELL=zsh COMP_LINE='okf --root . visualize handbook --out ' COMP_POINT=38 _ARGCOMPLETE_STDOUT_FILENAME=/tmp/out okf; tr '\013' '\n' < /tmp/out` several times, for the Python CLI and the Go binary.
- **PO decision:**

#### D-50 visualize with a non-UTF-8 file name: the node id differs
- **Cases:**   - `printf -- '---\ntitle: Cafe\ntype: Concept\ntags: [a]\n---\nbody\n' > $'handbook/caf\xe9.md'`, then `visualize handbook --out viz.html`
  - Identical on that file: `list`, `list --json`, `find`, `check`, `index`, `tags`, `recent`, `wikilinks`, `reindex --check` (both print the raw byte)
- **Channel:** file-tree effect (viz.html)
- **Difference:** Python writes the undecodable byte into the node id as the escape `\udce9`; Go writes the replacement character `\ufffd`. The graph is produced either way.
```text
Python (exit 0): viz.html: ... {"id": "caf\udce9", "title": "Cafe", "type": "Concept", "body": "\nbody\n"}
Go (exit 0): viz.html: ... {"id": "caf\ufffd", "title": "Cafe", "type": "Concept", "body": "\nbody\n"}
```
- **Reason:** Python: `visualize` in `cli/okf/navigation.py` dumps the surrogate-escaped name with `json.dumps`. Go: `go/internal/navigation/visualize.go` decodes names with replacement characters (exact line not read).
- **Capability preserved:** yes. A user still gets the full concept graph; only the spelling of one node id with an invalid byte differs.
- **Owner:** Go navigation commands (F: OKFT-se5f)
- **Reproduce:** In a copy of tests/golden/catalogue: `printf -- '---\ntitle: Cafe\ntype: Concept\n---\nbody\n' > $'handbook/caf\xe9.md'; okf --root . visualize handbook --out viz.html; grep -o '"id": "caf[^"]*"' viz.html`
- **PO decision:**

#### D-51 Completion protocol with an invalid environment: Go panics on a negative COMP_POINT
- **Cases:**   - `COMP_POINT=-3`
  - `COMP_POINT=abc`; missing `COMP_POINT`; missing `COMP_LINE`
  - `_ARGCOMPLETE_STDOUT_FILENAME` empty or inside a missing directory
  - `_ARGCOMPLETE=0` (Python offers no candidate, Go 10); `_ARC_DEBUG=1` (Python writes debug lines to stderr, Go none)
- **Channel:** exit code, stderr, candidates
- **Difference:** A negative COMP_POINT makes Go panic (exit 2, goroutine dump) where Python slices from the end and answers (exit 0). For the other invalid values both exit 1, Python with a traceback and Go silently. The shell glue never sends these values.
```text
Python (exit 0): COMP_POINT=-3: 37 candidates, stderr empty
Go (exit 2): COMP_POINT=-3: panic: runtime error: slice bounds out of range [:-3]
Go (exit 2): COMP_POINT=-3: goroutine 1 [running]:
Python (exit 1): COMP_POINT=abc: ValueError: invalid literal for int() with base 10: 'abc'
Go (exit 1): COMP_POINT=abc: (stderr empty)
```
- **Reason:** Go: `splitLine` in `go/internal/complete/shlex.go` (line 158) slices the line at COMP_POINT without a bound check, and text mode has no recover. Python: `argcomplete` slices `comp_line[:comp_point]`, where a negative value is valid.
- **Capability preserved:** yes. No caller reaches this: zsh, bash and fish pass a non-negative COMP_POINT. The only change is the failure class (panic with exit 2 instead of a normal answer).
- **Owner:** Go shell completion (F: OKFT-50ly)
- **Reproduce:** `_ARGCOMPLETE=1 COMP_LINE='okf --root . read hand' COMP_POINT=-3 _ARGCOMPLETE_STDOUT_FILENAME=/tmp/out okf; echo $?` with the Python CLI and with the Go binary.
- **PO decision:**

#### D-52 `recent` prints UTC instead of local time when `TZ` is a POSIX rule string
- **Cases:**   - `TZ=CET-1CEST okf recent --limit 12` and `... recent --limit 5 --json`
  - the same two commands with `TZ=CET-1CEST,M3.5.0,M10.5.0/3`, `TZ='<+0530>-5:30'`, `TZ=UTC+3`, `TZ=UTC-3` (10 runs)
  - identical in both: the 29 other `TZ` values tried (IANA names such as `Europe/Berlin`, `America/New_York`, `Asia/Kolkata`, `Pacific/Chatham`; absolute zoneinfo paths; `EST5EDT`; empty; invalid names; `UTC0`; `+03`)
- **Channel:** stdout (clock time in text mode, the `created` offset in `--json`; `created_ts` is equal)
- **Difference:** With a POSIX rule string in `TZ`, Python prints the creation time in that rule's local time and Go prints UTC without saying so. In `--json` the same shift shows as `"created": "2026-08-08T10:08:08+02:00"` (Python) against `"created": "2026-08-08T08:08:08+00:00"` (Go).
```text
Python (exit 0): 2026-02-11 01:00  Recipe  recipes/stew
Python (exit 0): 2026-02-10 01:00  Recipe  recipes/soup
Go (exit 0): 2026-02-11 00:00  Recipe  recipes/stew
Go (exit 0): 2026-02-10 00:00  Recipe  recipes/soup
```
- **Reason:** Python `recent.format_created` and `iso_created` call `datetime.fromtimestamp(ts, None)`, which uses libc local time and understands POSIX rules. Go `navigation/recent.go` `formatCreated` and the JSON branch use `time.Unix(ts, 0)` in `time.Local`; for all five rule strings Go printed UTC, for every zone name it matched Python.
- **Capability preserved:** no. A user whose `TZ` is a POSIX rule string gets local creation times from Python and UTC times from Go. The instant (`created_ts`) and the order are the same, and every IANA zone name or an unset `TZ` gives identical output.
- **Owner:** Go navigation commands (F: OKFT-se5f)
- **Reproduce:** golden fixture catalogue: `TZ=CET-1CEST okf --root <fixture> recent --limit 3`; control `TZ=Europe/Berlin` prints identical lines in both.
- **PO decision:**

#### D-53 `recent` with a commit time beyond year 9999: Python crashes, Go prints the year
- **Cases:**   - commit date 253402300800 (10000-01-01T00:00:00Z), `recent` text, `TZ=UTC`
  - commit date 253402300799 (9999-12-31T23:59:59Z): `recent` text with `TZ` east of UTC (`Europe/Berlin`, `Asia/Kolkata`, `Pacific/Chatham`); `recent --json` with every `TZ` tried (`UTC`, `Europe/Berlin`, `America/New_York`, `Asia/Kolkata`, `Pacific/Chatham`)
  - commit dates 1099511627776 (year 36812) and 9223372036854775807 (the largest 64-bit value): `recent` text and `--json`, every `TZ` tried; `recent --limit 1`, `3`, `5`, `8`, `12` on that repository
  - 23 of 25 runs differ; identical: year-9999 commits in text mode with `TZ=UTC` and `TZ=America/New_York`
- **Channel:** exit code, stdout, stderr
- **Difference:** Python raises on the first commit time it cannot represent (exit 1; with `--json` the error envelope on stdout and the traceback on stderr). Go prints the date with its real year and exits 0.
```text
Python (exit 1): ValueError: year must be in 1..9999, not 10000
Go (exit 0): 10000-01-01 00:00  Note    handbook/far
Python (exit 1): OSError: [Errno 75] Value too large for defined data type
Go (exit 0): 292277026596-12-04 15:30  Note  b/c13
Python (exit 1): ValueError: year must be in 1..9999, not 10000
Go (exit 0): {"command": "recent", "ok": true, "data": [{"created": "9999-12-31T23:59:59+00:00", "created_ts": 253402300799
```
- **Reason:** Python `recent.format_created` and `iso_created` use `datetime.fromtimestamp(ts, tz)`, which accepts years 1..9999 only, and nothing catches the error; in `--json` mode it already fails for 9999-12-31T23:59:59Z. Go `navigation/recent.go` formats with `time.Unix(ts, 0).Format(...)`, which has no year limit.
- **Capability preserved:** yes. Go reports the dates Python cannot represent; for every year up to 9999 the text output is identical. Such history is absurd input and neither command writes data.
- **Owner:** Go navigation commands (F: OKFT-se5f)
- **Reproduce:** golden fixture catalogue, git identity set: `printf -- '---\ntype: Note\ntitle: Far\ndescription: d\ntags: [a]\n---\n\n# Far\n' > handbook/far.md; git add handbook/far.md; GIT_AUTHOR_DATE='@253402300800 +0000' GIT_COMMITTER_DATE='@253402300800 +0000' git commit -qm far`; then `TZ=UTC okf --root <fixture> recent --limit 3`.
- **PO decision:**

#### D-54 Python colours help, usage errors and `prime` on a terminal; Go prints plain text
- **Cases:**   - on a pseudo-terminal with `TERM=xterm-256color`, with `TERM` unset, and with `FORCE_COLOR=1`: `okf` (no arguments), `--help`, `list --help`, `check --help`, `ctx --help`, `find --help`, `prime --help`, `read --help`, `tags --help`, `bogus`, `list --bogus`, `read` (missing path), `prime`, `prime --compact`, `prime --full`; widths 20, 40, 80, 100, 200 (93 of 307 terminal runs)
  - `PYTHON_COLORS=1` on a pipe: `--help`, `list --help`, `list --bogus`, `prime` (4 runs)
  - identical: `NO_COLOR=1` or `TERM=dumb` (0 of 38 command lines differ in each case) and every other command on a terminal (`list`, `read` page, `toc`, `tags`, `ctx`, `check`, `find`, `index`, `info`, ...)
- **Channel:** stdout (help, `prime`) and stderr (usage errors)
- **Difference:** Python 3.14 argparse emits ANSI colour codes on a terminal; Go never does. With the `ESC[...m` sequences removed the text is identical in all 93 runs (same wrapping, same exit codes). `\x1b` below stands for the ESC byte.
```text
Python (exit 0): \x1b[1;34musage: \x1b[0m\x1b[1;35mokf list\x1b[0m [\x1b[32m-h\x1b[0m] [\x1b[36m--where \x1b[33mEXPR\x1b[0m] [\x1b[36m--json\x1b[0m]
Python (exit 0): \x1b[1;34moptions:\x1b[0m
Python (exit 0):   \x1b[1;32m-h\x1b[0m, \x1b[1;36m--help\x1b[0m    show this help message and exit
Go (exit 0): usage: okf list [-h] [--where EXPR] [--json]
Go (exit 0): options:
Go (exit 0):   -h, --help    show this help message and exit
```
- **Reason:** Python `argparse` (3.14) colours help and error text when the stream is a terminal, `NO_COLOR` is unset and `TERM` is not `dumb`, or when `PYTHON_COLORS=1` is set; `prime` embeds the rendered subcommand help. Go `internal/cli/format.go` renders usage and help without colour (no ANSI byte in any of the 307 Go runs).
- **Capability preserved:** yes. Only colour differs; text, wrapping and exit codes are the same, and Go's output equals what Python prints with `NO_COLOR=1` or on a pipe.
- **Owner:** Go core and read side (F: OKFT-daut) + Go navigation commands (F: OKFT-se5f)
- **Reproduce:** in an interactive terminal: `okf list --help`; control `NO_COLOR=1 okf list --help` is identical in both.
- **PO decision:**

#### D-55 Python crashes when stdout cannot encode the text; Go always writes UTF-8
- **Cases:**   - `PYTHONIOENCODING=ascii okf list --where 'path ~ /'` and the same with `PYTHONIOENCODING=latin-1` (a title contains U+2014)
  - `LC_ALL=C PYTHONUTF8=0 okf read version-control-git/index` (the page contains `ü`)
  - golden fixture: `PYTHONIOENCODING=ascii okf read handbook/ops/setup`, and `PYTHONIOENCODING=latin-1 okf read handbook/ops/setup --json`
  - identical: `LC_ALL=C`, `LANG=C`, `LC_ALL=de_DE.UTF-8` without `PYTHONIOENCODING`
- **Channel:** exit code, stdout, stderr
- **Difference:** Python exits 1 with a `UnicodeEncodeError` at the first character the stream encoding cannot hold; for `list` it has already printed the `------` line. Go exits 0 and prints the complete UTF-8 text.
```text
Python (exit 1): UnicodeEncodeError: 'ascii' codec can't encode character '\u2014' in position 307: ordinal not in range(128)
Go (exit 0): ---
Go (exit 0): type: Runbook
Go (exit 0): title: Setup
```
- **Reason:** Python `navigation.cmd_read` (line 217, `print(out, end=end)`) and `cmd_list` print through a stream with the configured encoding, and `okf-cli.py:main` handles only `OkfError`. Go writes UTF-8 bytes and does not read `PYTHONIOENCODING`, `PYTHONUTF8` or the locale.
- **Capability preserved:** yes. In that environment Go does the work Python aborts on; with a UTF-8 stdout both outputs are identical.
- **Owner:** Go core and read side (F: OKFT-daut)
- **Reproduce:** golden fixture catalogue: `PYTHONIOENCODING=ascii okf --root <fixture> read handbook/ops/setup`.
- **PO decision:**

#### D-56 `--where` with about 990 or more flat `and`/`or` terms: Python RecursionError, Go answers
- **Cases:**   - `list --where 'type = Runbook and type = Runbook and ...'` with 990, 995, 998, 999, 1000, 1001, 2000, 5000 terms
  - the same with `or`, and with `type = Runbook or type = SOP or ...` (24 runs)
  - identical: 10 to 800 terms (both answer); the parse-time limits for nested parentheses and `not` (exit 2 in both)
- **Channel:** exit code, stdout, stderr
- **Difference:** Python fails while evaluating the long chain (exit 1, traceback); Go evaluates it and lists the matches (exit 0).
```text
Python (exit 1): RecursionError: maximum recursion depth exceeded
Go (exit 0): ------
Go (exit 0): title: Deploy
Go (exit 0): type: Runbook
```
- **Reason:** Python `find_filters._evaluate` recurses once per `and`/`or` term of the left-deep tree, and only `parse_where` is wrapped in `except RecursionError`. Go `internal/where/eval.go:evaluate` has no depth limit; `parse.go` copies Python's limit at parse time only (`frameLimit = 995`).
- **Capability preserved:** yes. Go answers a query Python aborts; both agree on every expression Python can evaluate.
- **Owner:** Go core and read side (F: OKFT-daut)
- **Reproduce:** golden fixture catalogue: `okf --root <fixture> list --where "$(python3 -c "print(' and '.join(['type = Runbook']*990))")"`.
- **PO decision:**

#### D-57 Out-of-range integer option values: Go saturates or accepts, Python echoes or refuses
- **Cases:**   - `toc <id> --level N` with N = 9999999999999999999, 99999999999999999999, 25 nines, 9223372036854775808, -9223372036854775808, -9223372036854775809, 10^30, 100 nines, 1000 nines
  - `toc <id> --level <5000 nines>` (3 runs) and `recent --limit <5000 nines>`
  - identical: every value up to 999999999999999999 (18 digits); for `recent --limit`, `tags --limit`, `ctx toc --depth` and `read --max-tokens` the values 2^31, 2^32, 2^63 and 10^30, including negative ones (the number is not echoed there)
- **Channel:** stdout (`toc` prints the level it got), exit code and stderr (5,000-digit values)
- **Difference:** Python echoes the number at any size; Go saturates at the int64 limit (the minimum prints as -9223372036854775807). With 5,000 digits Python refuses (`invalid int value`, exit 2) and Go accepts (exit 0).
```text
Python (exit 0): (no h99999999999999999999 headings)
Python (exit 0): (no h-9223372036854775808 headings)
Go (exit 0): (no h9223372036854775807 headings)
Go (exit 0): (no h-9223372036854775807 headings)
```
- **Reason:** Python `argparse` `type=int` has arbitrary precision (and `int()` refuses more than 4300 digits), and `toc` prints the value as given. Go `internal/cli/types.go` `Int`/`parseInt` saturates at `math.MaxInt64` (its comment: "A value beyond the range of int saturates").
- **Capability preserved:** yes. No valid level or limit gives a different result; only absurd values do.
- **Owner:** Go core and read side (F: OKFT-daut)
- **Reproduce:** golden fixture catalogue: `okf --root <fixture> toc handbook/index --level 99999999999999999999`.
- **PO decision:**

#### D-58 `visualize --out` with a bare file name, `--out` on a directory, and `visualize .`
- **Cases:**   - `visualize <bundle> --out rel-viz.html` (no directory part): bundles `_ctx` (Knowledge-Catalogue), `architecture-and-features` (sproutling-okf), `assets` (home-lab-wiki)
  - `visualize <bundle> --out <existing directory>` with the same three bundles (both exit 1)
  - `--root <bundle without catalogue marker> visualize .` (dev-okf)
  - identical: `--out` with a directory part (`handbook/../x/viz.html`), the default output path of a named bundle, and the written HTML in all other runs
- **Channel:** exit code, stdout, stderr, file-tree effect (bare file name: Go creates `rel-viz.html`, Python writes nothing)
- **Difference:** A bare file name makes Python fail and Go write the file. For a directory both refuse with exit 1 and different wording. For `.` Python prints `<root>/./assets/viz.html` and Go `<root>/assets/viz.html`; the same file is written.
```text
Python (exit 1): FileNotFoundError: [Errno 2] No such file or directory: ''
Go (exit 0): wrote rel-viz.html (10 nodes, 7 edges)
Python (exit 1): IsADirectoryError: [Errno 21] Is a directory: '<ROOT>'
Go (exit 1): open <ROOT>: is a directory
Python (exit 0): wrote <ROOT>/handbook/./assets/viz.html (10 nodes, 6 edges)
Go (exit 0): wrote <ROOT>/handbook/assets/viz.html (10 nodes, 6 edges)
```
- **Reason:** Python `navigation.cmd_visualize` (line 294) runs `os.makedirs(os.path.dirname(out))`, which raises for the empty directory name of a bare file name, and builds the default path with `os.path.join` (keeps `./`). Go `navigation/visualize.go:runVisualize` uses `os.MkdirAll(filepath.Dir(out))` (`.` is fine) and `filepath.Join`, which cleans the path.
- **Capability preserved:** yes. Go writes the file Python cannot; for a directory both fail with exit 1 and name the path.
- **Owner:** Go navigation commands (F: OKFT-se5f)
- **Reproduce:** golden fixture catalogue: `okf --root <fixture> visualize handbook --out rel-viz.html` and `okf --root <fixture>/handbook visualize .`.
- **PO decision:**

### Area E. Embedding clients and Unicode tables

**Go vs Python: Unicode text handling and embedding clients (work package K, areas S14 and S15)**

Versions: Python 3.14.6 (Unicode 16.0.0), Go 1.27.0 binary (Unicode 17.0.0, x/text v0.43.0). Every call ran in a private network namespace; Ollama and Voyage were replaced by a local stub server. `{ROOT}` in excerpts stands for the catalogue root. Entries with "no" first, then "yes".

#### D-59 Cherokee letters: Go case folding is not idempotent, so a heading typed in the other case is not found
- **Cases:** catalogue with `docs/d.md` (heading `## Ꭰ` U+13A0 and one text line) and `docs/t1..t5.md` titled `Ꭰ cherokee`, `あ kana`, `한 hangul`, `Zebra`, `apple`.
  - `okf read docs/d --section ꭰ` (U+AB70, small letter) and `okf read docs/d --section 'doc > ꭰ'`
  - `okf list --where 'type = Note' --json` (title order: Cherokee after kana in Go)
  - `okf reindex docs` (entry order in `docs/index.md`)
  - scope: the 86 capitals U+13A0..U+13F5 with their small letters U+AB70..U+ABBF and U+13F8..U+13FD; the same function is used by `ctx add`, `tags --register`, `migrate` [INFERENCE: not run]
- **Channel:** exit code, stderr (read); stdout order (list); file-tree effect (reindex writes `docs/index.md`)
- **Difference:** Python finds the heading with the small letter, Go does not. Python orders Cherokee titles before kana, Go after kana.
```text
$ okf read docs/d --section ꭰ
Python (exit 0): ## Ꭰ
Python (exit 0): cherokee section text
Go (exit 3): section not found: ꭰ
$ okf reindex docs   (lines added to docs/index.md)
Python (exit 0): +* [Ꭰ cherokee](/docs/t1.md) - d
Python (exit 0): +* [あ kana](/docs/t2.md) - d
Go (exit 0): +* [あ kana](/docs/t2.md) - d
Go (exit 0): +* [Ꭰ cherokee](/docs/t1.md) - d
```
- **Reason:** `go/internal/pytext/pytext.go` `Casefold` is `cases.Fold().String(s)`; x/text folds U+13A0 to U+AB70 and U+AB70 to U+13A0, so the two spellings stay unequal. Python `str.casefold` folds both to U+13A0.
- **Capability preserved:** no. Python matches a Cherokee heading in either letter case, Go cannot; the same-case spelling (`--section Ꭰ`) works in both. `list` and `reindex` still work, only the order differs.
- **Owner:** Go core and read side (F: OKFT-daut)
- **Reproduce:** `okf --root <cat> read docs/d --section ꭰ` on the catalogue above; `okf --root <cat> reindex docs` with an empty `<!-- okf:index -->` block in `docs/index.md`.
- **PO decision:**

#### D-60 Timeouts: Python limits each socket wait, Go limits the whole request
- **Cases:** stub sends the HTTP headers at once, then the 10.8 KB JSON body in 4 pieces 4 s apart (16 s in total, never idle longer than 4 s).
  - `okf find zzzunknown --breakdown` with a prebuilt `.tagvec` cache (query embedding timeout 10 s) [run]
  - Voyage document batches in `okf build-semantic-index` and `build-tagvec` (timeout 60 s) and Ollama tag embedding in `tags --register`, `build-tagvec` (timeout 300 s): same code path [INFERENCE: not run with a slow body]
- **Channel:** stdout, stderr, duration
- **Difference:** Python waits for the slow answer and ranks with the semantic arm; Go gives up at the timeout and falls back to lexical results.
```text
$ okf find zzzunknown --breakdown
Python (exit 0): rank: 1
Python (exit 0): title: Concept 4 salad
Python (exit 0): [stderr] note: semantic arm owns this ranking (lexical top-1 lacked a clear margin)
Python elapsed: 16.1 s
Go (exit 0): (no matches for: zzzunknown)
Go (exit 0): [stderr] note: semantic arm skipped (embedding backend unavailable: timeout after 10s) — lexical results only
Go elapsed: 10.0 s
```
- **Reason:** Python `urllib.request.urlopen(req, timeout=10)` (`cli/okf/semantic.py:_embed_query_voyage`; `cli/embeddings/build_tagvec.py:embed_voyage` 60 s, `embed_bge_m3` 300 s) sets a per-operation socket timeout. Go `go/internal/tagvec/embed.go:post` uses `http.Client{Timeout: timeout}`, which bounds connect, headers and the whole body read.
- **Capability preserved:** no, only where a slow backend or link delivers the answer in more than the timeout in total but never goes idle that long: Python accepts it, Go aborts it (the retry ladder then fails the same way and `build-semantic-index` reports "incomplete"). A server that stalls fails in both (Python "The read operation timed out", Go "timeout after 10s"). Normal fast backends behave the same.
- **Owner:** Go find and FTS index (F: OKFT-y1zl)
- **Reproduce:** stub server that answers `/v1/embeddings` with the headers at once and the 1024-float JSON body in four writes 4 s apart; `VOYAGE_API_KEY=stub-key okf --root <cat> find zzzunknown --breakdown` with a prebuilt `.tagvec` cache.
- **PO decision:**

#### D-61 A JSON `null` vector element is stored as 0.0 by Go and refused by Python
- **Cases:** stub answers HTTP 200 with a valid body whose first vector has `null` at element [3].
  - `okf tags --register newone "first new tag" --register newtwo "second new tag"` (Ollama): Python warns `auto-embed skipped ... (error: required argument is not a float)`, Go prints `auto-embedded 2 new tag(s) (bge-m3)`
  - `okf build-semantic-index` (Voyage; text and `--json`)
  - `build_tagvec.py --produce --target both` against `okf build-tagvec --produce --target both`
  - `okf find zzzunknown` (the query vector holds the null)
- **Channel:** exit code, stdout, stderr, file-tree effect (stored vector)
- **Difference:** Python reports an error and writes nothing (`build_tagvec.py` exits 1, `find` ends with a Traceback). Go stores 0.0 for the null element, reports success and prints no message.
```text
$ okf build-semantic-index
Python (exit 0): [stderr] note: semantic index build failed (error: required argument is not a float) -- lexical arm unaffected
Go (exit 0): embedded 3 concept(s) -> {ROOT}/.tagvec/tag_vectors.sqlite
$ build_tagvec.py --produce --target both   /   okf build-tagvec --produce --target both
Python (exit 1): struct.error: required argument is not a float
Go (exit 0): voyage-3-large: wrote 3/3 concept row(s)
$ okf find zzzunknown
Python (exit 1): TypeError: unsupported operand type(s) for *: 'NoneType' and 'float'
Go (exit 0): [stderr] note: semantic arm owns this ranking (lexical top-1 lacked a clear margin)
Go stored vector of docs/c0, elements [0..5]: [0.554424, 0.793278, 0.238983, 0.0, 0.769076, 0.379168]
```
- **Reason:** Go decodes the embeddings as `[]float64` in `go/internal/tagvec/embed.go` (`post`, `narrow`), so JSON `null` becomes 0.0 without an error. Python `json.loads` yields `None` and `struct.pack("<f", ...)` raises (`build_tagvec.py`, `semantic.py`, `tags.py:auto_embed_new_tags`); `find` raises in the cosine loop.
- **Capability preserved:** yes, since `0bbdcac` (K's run: no). K's finding, kept: A malformed backend answer changes a stored vector silently in Go, where Python refuses it; I use `no` by the rule that silent data change is `no`, and found no reason to keep `yes`. Well-formed answers are identical in both. Python's `find` crash is a separate Python defect.
- **Fixed in `0bbdcac` (2026-10-16):** the embed decode (`tagvec` `EmbedBGEM3`, `EmbedVoyage`, `EmbedVoyageQuery`) reads the elements as `*float64`, keeps a null and refuses it with a `tagvec.Exception` that carries the class and text of the Python exception: `error: required argument is not a float` (`pack_vec`) for the document vectors,
  `TypeError: unsupported operand type(s) for *: 'NoneType' and 'float'` (the cosine) for the query vector. `EmbedResilient` returns it at once without a retry, as Python raises after `embed_resilient`, and the consumers end like Python's. Stub as in Reproduce (null at element [3] of the first vector), Go before, then after (Python in brackets):
  `tags --register newone ... --register newtwo ...`: `auto-embedded 2 new tag(s) (bge-m3)` and 2 stored rows, then `warning: auto-embed skipped for new tag(s) (error: required argument is not a float) ...` and no store (text identical to Python); `build-semantic-index`: `embedded 24 concept(s)` and 24 stored rows, then
  `note: semantic index build failed (error: required argument is not a float) -- lexical arm unaffected`, exit 0, no store, in text and `--json` (identical to Python); `build-tagvec --produce --target both`: exit 0 and `wrote 13/13 tag row(s)`, then exit 1, `error: required argument is not a float` (Python `struct.error: ...`) and no stored row;
  `find zzzunknown` and `find zzzunknown --expand-tags` on a built cache: exit 0, then exit 1 with `TypeError: unsupported operand type(s) for *: 'NoneType' and 'float'` (identical to Python). Well-formed answers and the HTTP 500 retry ladder give byte-identical output before and after (tags, 24 concepts, `find`).
- **Owner:** Go find and FTS index (F: OKFT-y1zl) + Go tag and frontmatter writes (F: OKFT-dkdu)
- **Reproduce:** stub that answers 200 with a normal body but `null` at `data[0].embedding[3]` (Voyage) or `embeddings[0][3]` (Ollama); `VOYAGE_API_KEY=stub-key okf --root <cat> build-semantic-index`.
- **PO decision:**

#### D-62 Unicode 17 tables in Go against Unicode 16 tables in Python: `find` query split, `--where`, `--limit`, `ctx` positions, `rewrite-path`, `repr`
- **Cases:** only code points that Python 3.14.6 does not know differ (assigned in Unicode 17). `\w` and `isalnum` (Go: letter or number): 4657 code points: U+088F, U+0C5C, U+0CDC, U+A7CE..U+A7CF, U+A7D2, U+A7D4, U+A7F1, U+10940..U+10959, U+10EC5..U+10EC7, U+11DB0..U+11DDB, U+11DE0..U+11DE9 (new digits), U+16EA0..U+16EB8, U+16EBB..U+16ED3, U+16FF2..U+16FF6, U+187F8..U+187FF, U+18D09..U+18D1E, U+18D80..U+18DF2, U+1E6C0..U+1E6DE, U+1E6E0..U+1E6E2, U+1E6E4..U+1E6E5, U+1E6E7..U+1E6ED, U+1E6F0..U+1E6F4, U+1E6FE..U+1E6FF, U+2B73A..U+2B73F, U+2CEA2..U+2CEAD, U+323B0..U+33479 (4298 CJK Extension J).
  - `lower`/`casefold` (Go changes, Python keeps), 28: U+A7CE, U+A7D2, U+A7D4, U+16EA0..U+16EB8. `repr`/`isprintable` (Go prints, Python escapes), 4803 in 47 ranges: U+088F, U+0C5C, U+0CDC, U+1ACF..U+1ADD, U+1AE0..U+1AEB, U+20C1, U+2B96, U+A7CE..U+A7CF, U+A7D2, U+A7D4, U+A7F1, U+FBC3..U+FBD2, U+FD90..U+FD91, U+FDC8..U+FDCE, U+10940..U+10959, U+10EC5..U+10EC7, U+10ED0..U+10ED8, U+10EFA..U+10EFB, U+11B60..U+11B67, U+11DB0..U+11DDB, U+11DE0..U+11DE9, U+16EA0..U+16EB8, U+16EBB..U+16ED3, U+16FF2..U+16FF6, U+187F8..U+187FF, U+18D09..U+18D1E, U+18D80..U+18DF2, U+1CCFA..U+1CCFC, U+1CEBA..U+1CED0, U+1CEE0..U+1CEF0, U+1E6C0..U+1E6DE, U+1E6E0..U+1E6F5, U+1E6FE..U+1E6FF, U+1F6D8, U+1F777..U+1F77A, U+1F8D0..U+1F8D8, U+1FA54..U+1FA57, U+1FA8A, U+1FA8E, U+1FAC8, U+1FACD, U+1FAEA, U+1FAEF, U+1FBFA, U+2B73A..U+2B73F, U+2CEA2..U+2CEAD, U+323B0..U+33479. No difference: `isspace`/`\s`, NFC/NFD; NFKC/NFKD differ only for U+A7F1.
  - `okf find 'abc꟎def'` (with and without index; U+A7CE), `okf find '꟎'`, `okf find '𲎰abc'` (U+323B0), `okf find '꟎def'` and `okf find '𲎰'` against bodies `abc꟎def`, `漢𲎰字`
  - `okf find abc --where 'type = Note꟎'`, `okf find abc --limit 𑷡` (U+11DE1), `okf find abc --limit 🫈` (U+1FAC8: the error text shows `'\U0001fac8'` in Python, `'🫈'` in Go)
  - `okf ctx check` with a `pos` cell `𑷡`; `okf rewrite-path docs/old/page.md docs/new/page.md --check` on text `docs/old/page.md꟎x` and `𲎰docs/old/page.md`
- **Channel:** stdout, stderr, exit code, file-tree effect (`rewrite-path` without `--check`)
- **Difference:** Go treats the new characters as letters or digits, Python as separators: `find` keeps `abc꟎def` as one token (Python splits it); `find '꟎'` gives "(empty query)" in Python and "(no matches ...)" in Go; `--limit 𑷡` is refused in Python and read as 1 in Go; `rewrite-path` in Go skips the occurrences next to these characters.
```text
$ okf find 'abc꟎def'   (index built)
Python (exit 0): title: Beta
Python (exit 0): title: Gamma
Python (exit 0): title: Alpha
Go (exit 0): (no matches for: abc꟎def)
$ okf find abc --where 'type = Note꟎'
Python (exit 2): --where: unexpected character '꟎' at position 12
Go (exit 0): (no matches for: abc)
$ okf ctx check   (pos cell 𑷡, second row pos ٣)
Python (exit 4): ERROR    kc/ctx/row-format    _ctx/cook.md  (row 1: pos "𑷡" is neither an integer nor -)
Go (exit 4): ERROR    kc/ctx/required-positions _ctx/cook.md  (required positions are not 1..2 in table order: 1, 3)
```
- **Reason:** Go uses `unicode.IsLetter || unicode.IsNumber`, `unicode.IsPrint` and `\p{L}\p{N}` (Unicode 17) in `go/internal/rank/rank.go:Tokenize`, `where/parse.go:isAlnum`, `cli/types.go:digitValue`, `ctxfile/parse.go:decimalValue`, `rewrite/rewritepath.go:blocksPath`, `pytext/regexp.go`, `pytext/repr.go:ReprStr`; Python uses `re` `\w`, `str.isalnum`, `int()`, `repr`, `tokenize` in `cli/okf/fts.py` (Unicode 16). SQLite's FTS index splits these characters like Go does (same 1,102,763 terms in both).
- **Capability preserved:** yes. Valid input gives the same result; the differences only appear for characters that Python 3.14.6 does not know yet, and Go matches how the index splits the text. Python will behave like Go once it ships Unicode 17 [INFERENCE].
- **Owner:** Go core and read side (F: OKFT-daut) + Go find and FTS index (F: OKFT-y1zl)
- **Reproduce:** catalogue with `docs/a.md` body `xx abc yy`, `docs/b.md` `abc def`, `docs/c.md` `def ghi` (titles Alpha, Beta, Gamma) and `docs/n.md` body `abc꟎def`; `okf --root <cat> build-index`, then `okf --root <cat> find 'abc꟎def'`.
- **PO decision:**

#### D-63 Final sigma: `lower()` of Σ next to a few modifier letters differs (substring search without index only)
- **Cases:** bodies `x ʕΣ end` (Alpha, U+0295 U+03A3), `y ʰΣ end` (Beta, U+02B0 U+03A3), `z ΑΣ end` (Gamma); `okf find` with `'ʕς'`, `'ʕσ'`, `'ʕΣ'`, `'ʰς'`, `'ʰσ'`, `'ʰΣ'`, `'ας'`, `'ασ'` without an index (with an index all 8 queries are identical; without index only the four with ς or σ after ʕ or ʰ differ).
  - `lower("<c>Σ")` gives ς in Python and σ in Go for U+0295; σ in Python and ς in Go for U+0345 and 266 Lm code points: U+037A, U+02B0..U+02B8, U+02C0..U+02C1, U+02E0..U+02E4, U+10FC, U+1D2C..U+1D6A, U+1D78, U+1D9B..U+1DBF, U+2071, U+207F, U+2090..U+209C, U+2C7C..U+2C7D, U+A69C..U+A69D, U+A770, U+A7F2..U+A7F4, U+A7F8..U+A7F9, U+AB5C..U+AB5F, U+AB69, U+10780, U+10783..U+10785, U+10787..U+107B0, U+107B2..U+107BA, U+1E030..U+1E06D; plus 55 Unicode-17 code points from E2.
- **Channel:** stdout (hit set)
- **Difference:** The substring fallback lowercases query and body with the same function in each implementation, so the same words are found, but a query typed with lowercase ς or σ next to these letters matches different concepts.
```text
$ okf find 'ʕς'   (no index)
Python (exit 0): title: Alpha
Go (exit 0): (no matches for: ʕς)
$ okf find 'ʕσ'
Python (exit 0): (no matches for: ʕσ)
Go (exit 0): title: Alpha
$ okf find 'ʰσ'
Python (exit 0): title: Beta
Go (exit 0): (no matches for: ʰσ)
```
- **Reason:** Python `handle_capital_sigma` (CPython `Objects/unicodeobject.c`) skips Case_Ignorable characters first and then tests Cased. Go `pytext.Lower` is `cases.Lower(language.Und)`; x/text (`golang.org/x/text/cases/map.go`: `undLowerCaser.Transform`, `finalSigmaBody`) tests Cased first and its table does not mark U+0295 as Cased [INFERENCE: effect measured, table not traced].
- **Capability preserved:** yes. The default FTS arm is identical (SQLite folds ς and σ); only the no-index fallback differs, and only for these neighbours; a query typed with capital Σ finds the concept in both.
- **Owner:** Go core and read side (F: OKFT-daut) + Go find and FTS index (F: OKFT-y1zl)
- **Reproduce:** catalogue without `.fts`, concept body `x ʕΣ end` (U+0295 U+03A3); `okf --root <cat> find 'ʕς'`.
- **PO decision:**

#### D-64 Vector count differs from text count: Python writes partial rows and reports success, Go refuses the batch
- **Cases:** stub answers HTTP 200 with the wrong number of vectors (`short` = one fewer, `long` = one more, `zero` = none).
  - `okf tags --register newone "first new tag" --register newtwo "second new tag"` (1 / 3 / 0 vectors for 2 texts)
  - `okf build-semantic-index` on 3 concepts (2 / 4 / 0 vectors); also first answer short, retry answer correct
  - `build_tagvec.py --produce --target both` against `okf build-tagvec --produce --target both` (short, long)
- **Channel:** stdout, stderr, file-tree effect (stored rows), duration (Go retry ladder 2+4+8 s = about 14 s)
- **Difference:** Python pairs texts and vectors with `zip()`, writes the shorter list and reports the written count. Go rejects the whole response, retries, then skips and writes nothing; if a retry answer is complete Go writes all rows (3 rows against 2 in Python).
```text
$ okf tags --register newone "first new tag" --register newtwo "second new tag"   (1 vector for 2 texts)
Python (exit 0): [stderr] auto-embedded 1 new tag(s) (bge-m3)
Go (exit 0): [stderr] warning: auto-embed skipped for new tag(s) (response holds 1 embeddings for 2 texts) — run cli/embeddings/build_tagvec.py --produce manually later
$ okf build-semantic-index   (2 vectors for 3 texts)
Python (exit 0): embedded 2 concept(s) -> {ROOT}/.tagvec/tag_vectors.sqlite
Go (exit 0):     retry 1 (3 texts) voyage concepts docs/c0..: response holds 2 embeddings for 3 texts
Go (exit 0):     SKIPPED voyage concepts docs/c0.. — 3 text(s) left unembedded
Go (exit 0): [stderr] note: semantic index build incomplete -- 3 concept(s) left unembedded after retries; rerun to pick up the rest
```
- **Reason:** Python `zip(batch, vectors)` in `cli/okf/semantic.py:cmd_build_semantic_index`, `cli/embeddings/build_tagvec.py:main`, `cli/okf/tags.py:auto_embed_new_tags` never compares the counts. Go `go/internal/tagvec/embed.go:narrow` returns `response holds %d embeddings for %d texts`, which `EmbedResilient` and `tagwrite/tags.go:autoEmbedNewTags` treat like any other failure.
- **Capability preserved:** yes. A valid response has one vector per text. With a short response Python may attach vectors to the wrong tags or concepts and still says "embedded N", so Go's refusal keeps correct behaviour; a transient short answer is recovered by Go's retry. Cost: no partial progress, and 14 s when the backend keeps answering short.
- **Owner:** Go find and FTS index (F: OKFT-y1zl) + Go tag and frontmatter writes (F: OKFT-dkdu)
- **Reproduce:** stub that answers 200 with one embedding fewer than inputs; `VOYAGE_API_KEY=stub-key okf --root <cat> build-semantic-index` on a catalogue with 3 concepts.
- **PO decision:**

#### D-65 NaN and numeric-string vector elements: Go refuses, Python stores or crashes
- **Cases:** stub answers HTTP 200 with element [3] of the first vector set to the JSON literal `NaN` or to the string `"0.5"`; the same four commands as in E5a (`tags --register`, `build-semantic-index`, `build_tagvec.py` against `build-tagvec`, `find`).
- **Channel:** stderr, stdout, exit code, file-tree effect
- **Difference:** Go reports `malformed response` for both and writes nothing. Python stores NaN without a message (`tags --register`, `build-semantic-index`), refuses the string with an error text, and crashes `find` with a Traceback (rc=1) for NaN.
```text
$ okf tags --register newone "first new tag" --register newtwo "second new tag"   (element [3] = NaN)
Python (exit 0): [stderr] auto-embedded 2 new tag(s) (bge-m3)
Go (exit 0): [stderr] warning: auto-embed skipped for new tag(s) (malformed response) — run cli/embeddings/build_tagvec.py --produce manually later
$ okf build-semantic-index   (element [3] = NaN)
Python (exit 0): embedded 3 concept(s) -> {ROOT}/.tagvec/tag_vectors.sqlite
Go (exit 0):     retry 1 (3 texts) voyage concepts docs/c0..: malformed response
$ okf tags --register newone "first new tag" --register newtwo "second new tag"   (element [3] = "0.5")
Python (exit 0): [stderr] warning: auto-embed skipped for new tag(s) (error: required argument is not a float) — run cli/embeddings/build_tagvec.py --produce manually later
Go (exit 0): [stderr] warning: auto-embed skipped for new tag(s) (malformed response) — run cli/embeddings/build_tagvec.py --produce manually later
```
- **Reason:** `go/internal/tagvec/embed.go` decodes `[]float64`; a string or the non-standard `NaN` literal is a decode error. Python `json.loads` accepts `NaN` and passes it to `struct.pack("<f", ...)`, which stores nan; `find` raises outside its `try`.
- **Capability preserved:** yes. Valid vectors are identical in both; refusing a malformed vector is the correct result, and a stored NaN would poison the cosine ranking.
- **Owner:** Go find and FTS index (F: OKFT-y1zl) + Go tag and frontmatter writes (F: OKFT-dkdu)
- **Reproduce:** stub that answers 200 with `NaN` (or `"0.5"`) at `embeddings[0][3]`; `okf --root <cat> tags --register newone "first new tag"`.
- **PO decision:**

#### D-66 HTTP 2xx other than 200: Python accepts, Go rejects
- **Cases:** stub answers HTTP 201 with a correct body: `okf tags --register ...`, `okf build-semantic-index`, `okf find zzzunknown` (prebuilt cache). Status 400, 401, 404, 429, 500 are errors in both (not a deviation).
- **Channel:** stdout, stderr, file-tree effect
- **Difference:** Python uses the vectors, Go treats the answer as a failed backend (warning, retries and skip, lexical fallback).
```text
$ okf tags --register newone "first new tag" --register newtwo "second new tag"   (HTTP 201)
Python (exit 0): [stderr] auto-embedded 2 new tag(s) (bge-m3)
Go (exit 0): [stderr] warning: auto-embed skipped for new tag(s) (HTTP 201 Created) — run cli/embeddings/build_tagvec.py --produce manually later
$ okf find zzzunknown   (HTTP 201)
Python (exit 0): [stderr] note: semantic arm owns this ranking (lexical top-1 lacked a clear margin)
Go (exit 0): [stderr] note: semantic arm skipped (embedding backend unavailable: HTTP 201 Created) — lexical results only
```
- **Reason:** Go `go/internal/tagvec/embed.go:post` requires `StatusCode == 200`; Python `urllib` treats every 2xx as success.
- **Capability preserved:** yes. Ollama and Voyage answer 200; a 2xx other than 200 does not occur from them, and Go degrades like for any backend error.
- **Owner:** Go find and FTS index (F: OKFT-y1zl) + Go tag and frontmatter writes (F: OKFT-dkdu)
- **Reproduce:** stub that answers 201 with a normal body; `VOYAGE_API_KEY=stub-key okf --root <cat> find zzzunknown` with a prebuilt `.tagvec` cache.
- **PO decision:**

#### D-67 Embedding error texts: Go uses fixed neutral words, Python prints the exception text
- **Cases:** each condition at `tags --register` (stderr warning; Python puts the exception class in front, for example `URLError: `), `build-semantic-index` and `build-tagvec` (retry lines on stdout) and `find` (stderr note): connection refused; DNS failure; timeout; HTTP 500, 429, 401, 400, 404; 200 with a body that is not JSON, empty or HTML; 200 JSON without the expected key (`KeyError 'embeddings'` or `'data'` against `malformed response`); connection closed (`Remote end closed connection without response` against `connection closed`); connection reset; `find` with 0 vectors in the answer (`list index out of range` against `malformed response`). In the acceptance sandbox (`unshare -rn`) Voyage gives `<urlopen error [Errno 101] Network is unreachable>` in Python and `unknown host` in Go.
- **Channel:** stderr, stdout (retry lines); exit codes are identical
- **Difference:** Same structure and exit code, different wording (condition in brackets, `find` note shown with Voyage answering 500).
```text
Python (exit 0): [refused] <urlopen error [Errno 111] Connection refused>
Python (exit 0): [DNS] <urlopen error [Errno -2] Name or service not known>
Python (exit 0): [timeout] The read operation timed out
Python (exit 0): [HTTP 500] HTTP Error 500: Internal Server Error
Python (exit 0): [body not JSON] Expecting value: line 1 column 1 (char 0)
Python (exit 0): [reset] [Errno 104] Connection reset by peer
Go (exit 0): [refused] connection refused
Go (exit 0): [DNS] unknown host
Go (exit 0): [timeout] timeout after 10s
Go (exit 0): [HTTP 500] HTTP 500 Internal Server Error
Go (exit 0): [body not JSON] malformed response
Go (exit 0): [reset] connection reset
```
- **Reason:** Go `go/internal/tagvec/embed.go` (`post`, `transportError`) maps errors to fixed lower-case words; Python prints `str(exc)` (plus `type(exc).__name__` in `cli/okf/tags.py:auto_embed_new_tags`).
- **Capability preserved:** yes. The retry, warning and fallback behaviour and the exit codes are the same; Go's text is coarser (status codes and refused, DNS and timeout stay distinguishable; errno and JSON position do not). In `unshare -rn` Go's `unknown host` for Voyage is misleading.
- **Owner:** Go find and FTS index (F: OKFT-y1zl) + Go tag and frontmatter writes (F: OKFT-dkdu)
- **Reproduce:** stub that answers with each condition (for example `HTTP 500`); `VOYAGE_API_KEY=stub-key okf --root <cat> find zzzunknown` with a prebuilt `.tagvec` cache.
- **PO decision:**

#### D-68 `build-semantic-index --json`: retry lines go to stdout in Python and to stderr in Go
- **Cases:** `okf build-semantic-index --json` with Voyage failing (HTTP 500, bad JSON, empty body and others). Text mode (no `--json`) is identical in both: retry lines on stdout, note on stderr; `build-tagvec` has no JSON mode and prints retry lines on stdout in both.
- **Channel:** stdout, stderr
- **Difference:** Python's stdout is the retry lines followed by the JSON envelope, which is not valid JSON; Go's stdout is the single envelope and the retry lines are on stderr.
```text
$ okf build-semantic-index --json   (Voyage answers HTTP 500 every time)
Python (exit 0): [stdout]     retry 1 (3 texts) voyage concepts docs/c0..: HTTP Error 500: Internal Server Error
Python (exit 0): [stdout]     SKIPPED voyage concepts docs/c0.. — 3 text(s) left unembedded
Python (exit 0): [stdout] {"command": "build-semantic-index", "ok": true, "data": {"applied": false, "embedded": 0, "path": "{ROOT}/.tagvec/tag_vectors.sqlite"}, "warnings": ["semantic index build incomplete -- 3 concept(s) left unembedded after retries; rerun to pick up the rest"], "error": null}
Python: json.loads(stdout) -> JSONDecodeError: Expecting value: line 1 column 5 (char 4)
Go (exit 0): [stdout] {"command": "build-semantic-index", "ok": true, "data": {"applied": false, "embedded": 0, "path": "{ROOT}/.tagvec/tag_vectors.sqlite"}, "warnings": ["semantic index build incomplete -- 3 concept(s) left unembedded after retries; rerun to pick up the rest"], "error": null}
Go (exit 0): [stderr]     retry 1 (3 texts) voyage concepts docs/c0..: HTTP 500 Internal Server Error
Go (exit 0): [stderr]     SKIPPED voyage concepts docs/c0.. — 3 text(s) left unembedded
Go: json.loads(stdout) -> valid
```
- **Reason:** Python `embed_resilient` (`cli/embeddings/build_tagvec.py`) uses `print(...)` and `cmd_build_semantic_index` does not redirect it; Go `go/internal/semantic/semantic.go:build` hands `os.Stderr` to `EmbedResilient` when `--json` is set.
- **Capability preserved:** yes. Go's stdout is the one JSON envelope the flag promises; Python's stdout cannot be parsed whenever a retry happens.
- **Owner:** Go find and FTS index (F: OKFT-y1zl)
- **Reproduce:** stub that answers every Voyage request with HTTP 500; `VOYAGE_API_KEY=stub-key okf --root <cat> build-semantic-index --json`, then parse stdout as JSON.
- **PO decision:**

#### D-69 Proxy variables: Python sends localhost requests through `http_proxy`, Go never does
- **Cases:** `http_proxy=http://127.0.0.1:3999 HTTP_PROXY=http://127.0.0.1:3999 okf tags --register newone "first new tag"` (stub Ollama answers on localhost:11434, nothing listens on 3999); `https_proxy` and `HTTPS_PROXY` set with `okf build-semantic-index` (Voyage; both implementations go through the dead proxy: Python `<urlopen error [Errno 111] Connection refused>`, Go `connection refused`).
- **Channel:** stderr, file-tree effect (embedding row written or not)
- **Difference:** Python's request to the local Ollama goes to the proxy and fails; Go's goes straight to localhost and the tag is embedded.
```text
$ okf tags --register newone "first new tag"   (http_proxy=http://127.0.0.1:3999)
Python (exit 0): [stderr] warning: auto-embed skipped for new tag(s) (URLError: <urlopen error [Errno 111] Connection refused>) — run cli/embeddings/build_tagvec.py --produce manually later
Go (exit 0): [stderr] auto-embedded 1 new tag(s) (bge-m3)
```
- **Reason:** Go `net/http.ProxyFromEnvironment` never proxies `localhost`; Python `urllib` proxies every host not listed in `no_proxy`.
- **Capability preserved:** yes. Go reaches the local Ollama where Python cannot behind a proxy variable; HTTPS to Voyage honours the proxy in both.
- **Owner:** Go find and FTS index (F: OKFT-y1zl)
- **Reproduce:** `http_proxy=http://127.0.0.1:3999 okf --root <cat> tags --register newone "first new tag"` with a stub Ollama on 127.0.0.1:11434.
- **PO decision:**

#### D-70 Store write errors in the tag-vector writers: error text and class name differ
- **Cases:** `.tagvec/tag_vectors.sqlite` holds garbage bytes: `okf tags --register`, `build_tagvec.py` against `okf build-tagvec` (both exit 1), `okf build-semantic-index` (text identical in both). `.tagvec` is a regular file: `okf tags --register`, `okf build-semantic-index`, `build_tagvec.py` against `okf build-tagvec` (both exit 1).
- **Channel:** stderr, exit code (same in both)
- **Difference:** Both refuse and write nothing; the error wording and the Python class name differ.
```text
$ okf tags --register newone "first new tag"   (tag_vectors.sqlite holds garbage)
Python (exit 0): [stderr] warning: auto-embed skipped for new tag(s) (DatabaseError: file is not a database) — run cli/embeddings/build_tagvec.py --produce manually later
Go (exit 0): [stderr] warning: auto-embed skipped for new tag(s) (file is not a database (26)) — run cli/embeddings/build_tagvec.py --produce manually later
$ okf build-semantic-index   (.tagvec is a regular file)
Python (exit 0): [stderr] note: semantic index build failed (FileExistsError: [Errno 17] File exists: '{ROOT}/.tagvec') -- lexical arm unaffected
Go (exit 0): [stderr] note: semantic index build failed (Error: mkdir {ROOT}/.tagvec: not a directory) -- lexical arm unaffected
```
- **Reason:** Go `go/internal/tagwrite/tags.go:autoEmbedNewTags` and the `buildtagvec` package print the raw driver error; `go/internal/semantic/semantic.go:build` maps SQLite errors to Python class names (`sqlstore.PyError`) and uses `Error: <go text>` for the rest.
- **Capability preserved:** yes. Same exit codes and nothing written in both.
- **Owner:** Go find and FTS index (F: OKFT-y1zl) + Go tag and frontmatter writes (F: OKFT-dkdu)
- **Reproduce:** write garbage bytes to `<cat>/.tagvec/tag_vectors.sqlite` (or create `.tagvec` as a file); stub Ollama answering normally; `okf --root <cat> tags --register newone "first new tag"`.
- **PO decision:**

### Area F. Python-side bugs and damage that Go avoids

**PythonBugsFixed: write verbs, sync blocks and tag verbs**

Python = the Python CLI, Go = the Go binary. Every command ran on identical fresh copies of the golden fixture catalogue (`<fixture>`), without network. `^M` marks a CR; every other line end is LF. `<ROOT>` stands for the catalogue root inside a message, `<NOW>` for a run timestamp. The causes that would answer capability `no` in this area are on the overlap list and appear only under "Extra cases for entries covered elsewhere". The YAML parse-error wording of the golden set also shows up outside it (for example in the `unparseable handbook/broken-yaml.md ...` line of `merge-tags` and `remove-tags` dry-runs: 4 of 118 error-path runs); it is not repeated.

#### D-71 sync-update corrupts a consumer that has a CR before or inside a sync block (S4a)
- **Cases:**   - CRLF consumer with one stale block, LF owner: `sed -i 's/$/\r/' kc-gov/naming.md`, then `sync-update --apply`
  - CRLF consumer with two stale blocks, `sync-update --apply`: the second block is cut further back and its end marker is doubled
  - the same two-block file, dry-run `sync-update` and `sync-update --json`: in Python the plan already holds the doubled `<!-- /okf:sync --><!-- /okf:sync -->`
  - LF file with one `\r\n` line before the block, or a `\r\n` inside the payload: `sync-update --apply` (same damage)
  - controls, identical in both: `sync-insert` on CRLF consumers; `sync-update` with an LF consumer and a CRLF owner
- **Channel:** file-tree effect, stdout
- **Difference:** Python splices at LF-only offsets into the CRLF text: it deletes as many characters in front of the block as there are CRs before it (6 here) and leaves as many characters of the old end marker behind as there are CRs up to that marker (10 here). It still exits 0 with a normal summary, and in the two-block run `sync-status` afterwards reports `3 synced` and `check kc-gov` reports 0 violations. Go replaces exactly the block, whose own lines are LF, so the file ends up with mixed line endings; file lines from `Refer to` on:
```text
Python (exit 0): Refer to [ownership](/kc-gov/ownership.md<!-- okf:sync id=naming-rule source=/kc-gov/ownership.md hash=5f1068e89974 -->
Python (exit 0): > [!quote] Synchronisiert aus `/kc-gov/ownership.md` — Canon-Owner, hier nicht bearbeiten.
Python (exit 0): <!-- okf:sync-body -->
Python (exit 0): Names are lowercase, hyphenated, stable and unique.
Python (exit 0): <!-- /okf:sync -->f:sync -->^M
Go (exit 0): Refer to [ownership](/kc-gov/ownership.md).^M
Go (exit 0): ^M
Go (exit 0): <!-- okf:sync id=naming-rule source=/kc-gov/ownership.md hash=5f1068e89974 -->
Go (exit 0): > [!quote] Synchronisiert aus `/kc-gov/ownership.md` — Canon-Owner, hier nicht bearbeiten.
Go (exit 0): <!-- okf:sync-body -->
Go (exit 0): Names are lowercase, hyphenated, stable and unique.
Go (exit 0): <!-- /okf:sync -->^M
```
- **Reason:** Python `sync.py` `scan_sync_blocks` parses `read_frontmatter(read_file(ap)).body` (universal newlines, so the spans count LF only) and `cmd_sync_update` slices the verbatim text with those spans. Go `tagwrite/syncwrite.go` `spliceSyncBlocks` re-parses the stored text and uses the scan only to pair blocks.
- **Capability preserved:** yes. Python writes wrong data on valid input (deleted prose, orphan marker text) and nothing reports it; Go writes the intended file and refuses nothing.
- **Owner:** Go tag and frontmatter writes (F: OKFT-dkdu)
- **Reproduce:** in `<fixture>`: `sed -i 's/$/\r/' kc-gov/naming.md`, then `okf --root <fixture> sync-update --apply` (block `naming-rule` is stale).
- **PO decision:**

#### D-72 merge-tags writes tags that start with `?` or `:` unquoted into a flow list (S4b)
- **Cases:** (all `merge-tags soup --into V --apply` on `recipes/soup.md`, which holds `tags: [food, soup]`)
  - V = `? q`, `?q`, `?-`: Python writes them plain and they read back as a mapping (`{'q': None}`, `{'-': None}`)
  - V = `??` and `: x`: Python writes a file that no longer parses
  - V = `a`, U+0085, `b` (`a\x85b`): Python folds the character in flow and block lists and it reads back as `a b`
  - existing items `tags: [a, ? q]` with `merge-tags a --into z`, `remove-tags a`, `normalize-tags`: same data in both; only the formatting differs (Python `[z, q: null]`, `[q: null]`, `- {q: null}`; Go `[z, ? q]`, `[? q]`, `- ? q`)
  - the other 44 of the 50 values of the first sweep (`a, b`, `}`, `[x]`, `a #b`, `&a`, `true`, `1e3`, `2026-01-01`) give the same data in both; `-x` fails the same way in both
- **Channel:** file-tree effect
- **Difference:** Python writes the new tag as a plain scalar, which YAML reads as a key marker, so the tag turns into a mapping or the file stops parsing. Go quotes the tag; both results below were read back with the Python reader.
```text
Python (exit 0): tags: [food, ? q]   reads back as ['food', {'q': None}]
Python (exit 0): tags: [food, ??]    reads back as UNPARSEABLE: expected the node content, but found '?' (line 5, column 15)
Python (exit 0): tags: [food, : x]   reads back as UNPARSEABLE: expected the node content, but found ':' (line 5, column 14)
Go (exit 0): tags: [food, '? q']     reads back as ['food', '? q']
Go (exit 0): tags: [food, '??']      reads back as ['food', '??']
Go (exit 0): tags: [food, ': x']     reads back as ['food', ': x']
```
- **Reason:** Python `tags.py` `_retag` stores a plain string and ruamel `analyze_scalar` (`emitter.py` line 1095, marked `# ToDo`) treats a leading `?` or `:` as a flow indicator only for a one-character scalar. Go `yamlpatch/quote.go` `plainOK` writes plain only when a probe `k: [<s>]` reads back as the same string.
- **Capability preserved:** yes. Python writes an unparseable file or silently a different tag; Go writes the tag as typed, and all other values give equal data.
- **Owner:** Go frontmatter writer (F: OKFT-5lq2) + Go tag and frontmatter writes (F: OKFT-dkdu)
- **Reproduce:** `okf --root <fixture> merge-tags soup --into '? q' --apply`, then read `recipes/soup.md` (`--into '??'` gives the unparseable file).
- **PO decision:**

#### D-73 verify writes invalid YAML when `verified` is a single mapping with a comment on its key line (S4d)
- **Cases:** (each as `handbook/zz.md`, command `verify handbook/zz --by human:x`)
  - stress fixture 21: `verified: { by: human:a, at: 2026-01-01T00:00:00Z }  # who`
  - the same without the inner spaces, and the same flow mapping as the last key of the block
  - block mapping with the comment on the key line: `verified:   # who`, then `by:` and `at:` lines
  - controls with equal data in both: flow or block mapping without a comment, block list, flow list (stress files 17-20); stress files 22 and 23 are refused by both with the same text
- **Channel:** file-tree effect (stdout and exit code are equal)
- **Difference:** With a comment on the key line of a single `verified` mapping, Python repeats the comment and joins the old entry's keys on one line (`by: human:x at: ...`), exits 0, and its own `check` then reports the file as unparseable. Go keeps the flow mapping and the comment and appends a valid entry; every other key stays unchanged.
```text
Python (exit 0): verified:                                            # who
Python (exit 0):   - {by: human:a, at: 2026-01-01T00:00:00Z}          # who
Python (exit 0):   - by: human:x at: 2026-10-16T15:34:15Z
Python (exit 4): okf check finding okf/frontmatter/parseable (error): no parseable frontmatter: mapping values are not allowed here (line 6, column 19)
Go (exit 0): verified:
Go (exit 0):   - { by: human:a, at: 2026-01-01T00:00:00Z }  # who
Go (exit 0):   - by: human:x
Go (exit 0):     at: 2026-10-16T15:34:15Z
Go (exit 4): okf check finds nothing for the file (exit 4 comes from the fixture's handbook/broken-yaml.md)
```
- **Reason:** Python `verify.py` `cmd_verify` (line 49) wraps the single mapping as `CommentedSeq([data["verified"], entry])`, and ruamel re-emits the key-line comment twice (mechanism inferred, output exact). Go `yamlpatch/ops.go` `flowMapToList` and `mapToList` patch the lines and the self-check reads the result back.
- **Capability preserved:** yes. Python reports success and writes a file that the Python CLI itself cannot parse; Go writes valid YAML with the same data plus the new entry.
- **Owner:** Go check and verify (F: OKFT-agws) + Go frontmatter writer (F: OKFT-5lq2)
- **Reproduce:** write `go/internal/yamlpatch/testdata/stress/21-verified-single-map-flow.md` as `handbook/zz.md` in `<fixture>`, then `okf --root <fixture> verify handbook/zz --by human:x` and `okf --root <fixture> check handbook --json`.
- **PO decision:**

#### D-74 CRLF concepts: Python mixes or converts line endings, Go keeps CRLF (S4c)
- **Cases:**   - `sed -i 's/$/\r/' recipes/bread.md recipes/soup.md`, then `migrate recipes --apply`: Python frontmatter LF and body CRLF (CR on 7 of 18 lines in bread.md, 11 of 17 in soup.md), Go CR on every line
  - dry-run `migrate recipes` on the same files: Python's hunk is `@@ -1,12 +1,14 @@` (whole frontmatter replaced), Go's is `@@ -5,8 +5,10 @@`
  - whole fixture CRLF, `migrate --apply`: bread, pasta and soup are mixed in Python (CR on 7/18, 8/22 and 11/17 lines)
  - CRLF concept with `tags: [a, b]`: `merge-tags a --into z --apply`, `remove-tags a --apply`, `normalize-tags --apply`, `verify handbook/zz --by human:x`: Python converts the whole file to LF
  - identical in both on CRLF files: fix-crosslinks, fix-xml-tags, reindex, rename, archive, rewrite-path, sync-insert, `tags --register`, `registry convert`
- **Channel:** file-tree effect, stdout (dry-run diff)
- **Difference:** After CRLF-to-LF normalisation every pair of result files is byte-equal, so only the line endings differ. `migrate` leaves an LF frontmatter and a CRLF body in Python; the tag verbs and `verify` turn the whole file into LF; Go keeps the file's own endings. The first ten lines are lines 1, 2, 10, 11 and 12 of `recipes/bread.md` after `migrate --apply`; the last two are the whole CRLF concept after `merge-tags` (Python bytes):
```text
Python (exit 0): ---
Python (exit 0): type: Recipe
Python (exit 0):   at: '2026-01-29T00:00:00+00:00'
Python (exit 0): status: draft
Python (exit 0): ---^M
Go (exit 0): ---^M
Go (exit 0): type: Recipe^M
Go (exit 0):   at: '2026-01-29T00:00:00+00:00'^M
Go (exit 0): status: draft^M
Go (exit 0): ---^M
Python (exit 0): b'---\ntype: Concept\ndescription: d\ntags: [z, b]\n---\n# T\n\nbody line\n'
Go (exit 0): b'---\r\ntype: Concept\r\ndescription: d\r\ntags: [z, b]\r\n---\r\n# T\r\n\r\nbody line\r\n'
```
- **Reason:** Python `catalogue.py` `render_frontmatter` (line 530) writes the delimiters and the dump with LF in front of `fm.body`; `migrate.py` passes the verbatim text, so the body keeps CRLF, while `tags.py` `_selected_concepts` and `verify.py` `cmd_verify` read with `read_file` (universal newlines) and write the LF text. Go `yamlpatch/yamlpatch.go` `newPatcher` patches the lines in place and keeps the file's line ending.
- **Capability preserved:** yes. Same data; the endings are kept (Go) instead of normalised (Python).
- **Owner:** Go tag and frontmatter writes (F: OKFT-dkdu) + Go check and verify (F: OKFT-agws)
- **Reproduce:** `sed -i 's/$/\r/' recipes/bread.md recipes/soup.md` in `<fixture>`, then `okf --root <fixture> migrate recipes --apply` and `cat -A recipes/bread.md`.
- **PO decision:**

#### D-75 argument with invalid UTF-8: Python empties the target file, Go refuses first
- **Cases:** (argument bytes `\xff`, written as bash `$'...'`)
  - `tags --register $'bad\xfftag' desc` and `tags --register goodtag $'de\xffsc'`: Python empties `TAGS.md` (480 to 0 bytes)
  - `rewrite-path old-host.example.org $'new\xffhost.example.org'`: Python empties the first matching file `handbook/ops/setup.md` (438 to 0 bytes)
  - `rename handbook/ops/retired-tool.md $'handbook/ops/legacy\xfftool.md' --apply`: Python moves the file and empties `_ctx/legacy.md` (441 to 0 bytes)
  - `merge-tags soup --into $'bad\xffname' --apply`: Python exit 0 writes `tags: [food, "bad\uDCFFname"]` into 2 files; Go exit 2 `recipes/soup.md: a new string is not valid UTF-8`, nothing written
  - `verify handbook/ops/setup --by $'human:bad\xff'`: Python exit 0 writes the entry; Go exit 2 `a new string is not valid UTF-8`
- **Channel:** file-tree effect, exit code, stderr
- **Difference:** Python opens the target for writing, which empties it, and only then fails to encode the argument; Go checks the text first and leaves every file as it was. `tags --register` also differs in exit code (Python 2, Go 1).
```text
Python (exit 2): ERROR: 'utf-8' codec can't encode character '\udcff' in position 129: surrogates not allowed
Go (exit 1): write <ROOT>/TAGS.md: text is not valid UTF-8
Python (exit 1): UnicodeEncodeError: 'utf-8' codec can't encode character '\udcff' in position 128: surrogates not allowed
Go (exit 1): write <ROOT>/handbook/ops/setup.md: text is not valid UTF-8
Python (exit 1): UnicodeEncodeError: 'utf-8' codec can't encode character '\udcff' in position 122: surrogates not allowed
Go (exit 2): the stored text is not valid UTF-8
```
- **Reason:** Python `catalogue.py` `write_file` (line 735) and `write_file_verbatim` (line 1252) open with `"w"` and then write the surrogate-escaped text. Go `diffs/plan.go` `WriteFileVerbatim` checks `utf8.ValidString` before opening (its comment names this).
- **Capability preserved:** yes. Python destroys TAGS.md, a concept or a ctx file for a malformed argument; Go refuses before touching anything. The exit class of `tags --register` (2 vs 1) is the only visible difference.
- **Owner:** Go tag and frontmatter writes (F: OKFT-dkdu) + Go link rewriting writes (F: OKFT-cm5o)
- **Reproduce:** in `<fixture>` (bash): `okf --root <fixture> tags --register $'bad\xfftag' desc; wc -c TAGS.md` (480 bytes before).
- **PO decision:**

#### D-76 mid-run write failure (S16): same exit code and files, different message
- **Cases:** (the file is read-only through a bind mount, so root in a user namespace fails too)
  - `normalize-tags --apply` (3 files to write, the 2nd read-only) and `migrate --apply` (3 files, the 2nd read-only)
  - `merge-tags misc x-experimental --into security --apply` with the first, or the last, of its 2 files read-only
  - `sync-update --apply` (3 consumers, the 2nd read-only), `sync-insert --apply`, `verify` (target read-only)
  - `tags --register` and `registry convert TAGS.md --to block --apply` (`TAGS.md` read-only)
  - `rename --apply` (an inbound-link file read-only), `fix-crosslinks`, `fix-xml-tags`
  - `normalize-tags --apply --json` and `verify --json`
- **Channel:** stderr; stdout of the `--json` envelope
- **Difference:** In all 14 runs both exit 1, the files written before the failing one stay written, and the failing and later files are untouched (same file sets; `normalize-tags` wrote `handbook/glossary.md` only). Text-mode stdout is empty in both, except `sync-insert`, which prints the same 409-byte diff before the failing write; only the error message differs.
```text
Python (exit 1): OSError: [Errno 30] Read-only file system: '<ROOT>/recipes/overview.md'
Python (exit 1): {"command": "normalize-tags", "ok": false, "data": null, "warnings": [], "error": {"kind": "internal", "code": 1, "message": "OSError: [Errno 30] Read-only file system: '<ROOT>/recipes/overview.md'"}}
Go (exit 1): open <ROOT>/recipes/overview.md: read-only file system
Go (exit 1): {"command": "normalize-tags", "ok": false, "data": null, "warnings": [], "error": {"kind": "internal", "code": 1, "message": "*fs.PathError: open <ROOT>/recipes/overview.md: read-only file system"}}
```
- **Reason:** Python lets the `OSError` escape: stderr is a 22-line traceback ending in the line above, and `output.py` `run_envelope` wraps it as kind `internal`. Go `diffs/plan.go` `WritePlan` (documented as Python `write_plan`) stops at the first failed write and returns the `*fs.PathError`, also kind `internal`.
- **Capability preserved:** yes. Exit code, written files and failure point are identical; only the message wording differs.
- **Owner:** Go core and read side (F: OKFT-daut) + Go frontmatter writer (F: OKFT-5lq2)
- **Reproduce:** in the `<fixture>` root: `unshare -rnm bash -c 'mount --bind recipes/overview.md recipes/overview.md && mount -o remount,bind,ro recipes/overview.md recipes/overview.md && exec okf --root . normalize-tags --apply'`
- **PO decision:**

#### D-77 text of non-string tag items in `tags` and `check`
- **Cases:** (each shape in its own concept with `tags: [a, X]`; commands `okf tags` and `okf check handbook`)
  - X = `? q`, `?q`: a mapping item with a null value; Python `{q: null}`, Go `{q: ''}`; X = `{a: }`: Python `{a: null}`, Go `{a: ''}`
  - X = `!!str 5`, `!!float 1`, `!custom x`: Python keeps the tag text (`!!str 5`, `!!float '1'`, `!custom x`); Go prints the bare value (`5`, `1`, `x`)
  - X = `{[x]: y}` (complex key): Python `{[x]: y}`; Go `{? [x] : y}`
  - X = `2026-01-01T00:00:00.5Z`, `2026-01-01T00:00:00.123456789Z`, `2026-01-01 00:00:00.5`: Python pads or rounds to six digits (`.500000Z`, `.123457Z`, `.500000`); Go prints as written
  - the other 33 of 39 item shapes tried (numbers, bools, dates, nested lists, anchors, quoted strings) print the same; `[a, - a]` is invalid YAML in both and differs only in the parse-error wording
- **Channel:** stdout
- **Difference:** Only the printed form of malformed or typed tags differs; nothing is written. `tags` exits 0 in both, and `check` exits 4 in both because of `handbook/broken-yaml.md` in the fixture.
```text
Python (exit 0): tags: [a, ? q]  ->  `  {q: null}       1`
Python (exit 4): same file, okf check  ->  WARNING  kc/tag/registered    handbook/zz.md  (tag `{q: null}` not registered in TAGS.md)
Python (exit 0): tags: [a, !!str 5]  ->  `  !!str 5         1`
Python (exit 0): tags: [a, {[x]: y}]  ->  `  {[x]: y}        1`
Python (exit 0): tags: [a, 2026-01-01T00:00:00.5Z]  ->  `  2026-01-01T00:00:00.500000Z  1`
Go (exit 0): tags: [a, ? q]  ->  `  {q: ''}         1`
Go (exit 4): same file, okf check  ->  WARNING  kc/tag/registered    handbook/zz.md  (tag `{q: ''}` not registered in TAGS.md)
Go (exit 0): tags: [a, !!str 5]  ->  `  5               1`
Go (exit 0): tags: [a, {[x]: y}]  ->  `  {? [x] : y}     1`
Go (exit 0): tags: [a, 2026-01-01T00:00:00.5Z]  ->  `  2026-01-01T00:00:00.5Z  1`
```
- **Reason:** Python `catalogue.py` `scalar_text` (line 576) dumps non-string values through ruamel and keeps the first line. Go `frontmatter/access.go` `ScalarText` says in its comment that Python also dumps explicitly tagged scalars with their tag and pads fractional seconds to six digits, and that neither is reproduced; a mapping is printed from its YAML form.
- **Capability preserved:** yes. Only the printed form of malformed or typed tags differs; exit codes and counts are equal.
- **Owner:** Go core and read side (F: OKFT-daut)
- **Reproduce:** in `<fixture>` give `handbook/zz.md` (`type: Concept`, `description: d`) the line `tags: [a, ? q]`, then `okf --root <fixture> tags` and `okf --root <fixture> check handbook`.
- **PO decision:**

### 2.3 Match against the deviation list of OKFT-5lq2 (criterion 5)

The list of OKFT-5lq2 (leaf, Constraints, D02 bullet, `updated_at` 2026-10-16T13:20:08Z, `to-review`) names four deliberate deviations that no golden case pins. Each one was run directly against the Python CLI:

| Deviation of OKFT-5lq2 | Entry | Run result |
|---|---|---|
| `render_ctx` over an existing ctx file whose frontmatter does not parse, or that the writer rejects, returns the rejection instead of starting a new block | D-17 (writer rejects), D-19 (does not parse) | confirmed: Go exit 2 and no write; Python rewrites the file |
| a stored text that is not valid UTF-8 is rejected instead of written with replacement characters | D-10 | confirmed: Go exit 2, file unchanged; Python writes U+FFFD |
| an edit on an anchored, aliased or tagged value is rejected instead of changing every alias | D-05 | confirmed: Go exit 2; Python writes |
| a CRLF file keeps CRLF in its frontmatter where ruamel writes LF | D-11 | confirmed |
| (non-goal line of the leaf, not a deviation) byte equality with ruamel where ruamel normalises untouched text: re-indented lists, fractional seconds, a new item behind comments | D-11 to D-15 | formatting kept by Go, data equal; the corpus run (§3) measures minimal diff, not byte equality |

Deviations of the same area that the OKFT-5lq2 list does not name (found by the sweeps): flow-mapping root D-04, lone CR D-02 D-03, comment inside a flow list D-06, other unpatchable shapes D-07, the first refused file ending the whole run D-08 D-09, non-scalar keys D-43, a ctx `pos` beyond int64 D-18 (named in a code comment of `ctxfile/parse.go` only).

### 2.4 Coverage of the suspected deviations handed over with the assignment

| Seed | Where |
|---|---|
| 1 parse-error wording (frontmatter, TOML) | D-01 (21 goldens); other YAML inputs D-39; TOML wording D-37 D-38 |
| 2 writer refusals (flow root, anchors/aliases/tags, comment in flow list, invalid UTF-8, lone CR, one refused file blocks the run, ctx files with unparseable frontmatter) | D-04 D-05 D-06 D-10 D-03 D-02 D-08 D-09 D-19 D-17 |
| 3 formatting kept (CRLF, spacing, quote style, trailing comments) | D-11 D-12 D-13 D-14 D-15 |
| 4 Go fixes Python bugs (CRLF sync-update, flow tag `? q`, migrate CRLF, verify fixture 21) | D-71 D-72 D-74 D-73; the `sync-insert` half of the CRLF seed is identical in both |
| 5 scalar text (timestamps, `&x`/tag prefix, impossible dates, NEL) | D-31 D-32 D-30 D-27 |
| 6 ctx `pos` beyond int64, NUL in a ctx path | D-18 D-20 |
| 7 tab after the colon | D-35 |
| 8 Python tracebacks become one-line errors | D-44 D-22 |
| 9 listing-order ties | D-47 |
| 10 completion (completer abort, Files order) | D-48 D-49 |
| 11 typed title/description as index link text | D-36 |
| 12 `source=` of sync blocks after rename | identical in both (§2.6, PythonBugsFixed block) |
| 13 ctx description quoting | D-21 (15 strings, not 5) |
| 14 Unicode 17 against 16 | D-62 |
| 15 embed count mismatch, non-200, error texts, `--json` retry lines | D-64 D-66 D-67 D-68 (and D-61, D-65, D-60 found on the way) |
| 16 mid-run write failure | D-76 (same exit code and written files; message wording differs) |

### 2.5 Golden assets unchanged (criterion 8)

`git diff --stat 5b5e05a HEAD -- tests/golden tests/okf_golden.py` is empty (`5b5e05a` = `feat(OKFT-ks1t): OS-level network block in golden harness`, the final commit of OKFT-ks1t; its merge into the line is `e4976d5`). `git log 5b5e05a..HEAD -- tests/golden tests/okf_golden.py` is empty. `tests/golden/cases.txt` holds 314 cases and `tests/golden/expected` 314 files at `5b5e05a`, at `e4976d5` and at HEAD: no case was added, so there is no added case to prove against the Python CLI (the Python run over all 314 cases is green). This report's commit touches neither path. The Go test files of the line are 13, in `yamlpatch` (5), `linkscan` (4), `rank` (3) and `fts` (1, `ranking_test.go`, FTS ranking tests of OKFT-y1zl; see §6).

### 2.6 Differential sweeps: matrices and what was identical

The entries above come from eight sweeps (each a Python CLI against the Go binary, golden-fixture catalogues and copies of the production catalogues, `unshare -rn`). Their matrices and the lists of what came out identical follow, so the PO can see where nothing was found.

#### Sweep `ReadSweep`

**Matrix table**

Production-data set (m1: the four production catalogues; every concept and md file, every option of every command, `--json` variants). `visualize` has no m1 rows (its runs compare the written file and are in the fixture block).

| command | invocations | SAME | DIFF |
|---|---:|---:|---:|
| list | 7,383 | 7,383 | 0 |
| read | 4,315 | 4,315 | 0 |
| toc | 2,981 | 2,981 | 0 |
| refs | 2,892 | 2,784 | 108 |
| recent | 507 | 507 | 0 |
| prime | 70 | 70 | 0 |
| tags | 1,004 | 1,004 | 0 |
| wikilinks | 330 | 330 | 0 |
| info | 12 | 12 | 0 |
| sync-status | 364 | 364 | 0 |
| sync-export | 184 | 184 | 0 |
| ctx | 306 | 306 | 0 |
| misc (root resolution, global options) | 32 | 31 | 1 |
| **total m1** | **20,380** | **20,271** | **109** |

Fixture sets (crafted catalogues, git states, TZ/PATH/locale/colour variants, pseudo-terminal and pipe runs, parser and help runs; not the golden fixture itself):

| command | invocations | SAME | DIFF |
|---|---:|---:|---:|
| list | 3,415 | 2,760 | 655 |
| read | 2,756 | 2,608 | 148 |
| toc | 1,026 | 1,008 | 18 |
| refs | 1,066 | 369 | 697 |
| recent | 229 | 195 | 34 |
| prime | 248 | 245 | 3 |
| tags | 2,504 | 2,455 | 49 |
| wikilinks | 146 | 129 | 17 |
| info | 67 | 67 | 0 |
| visualize | 154 | 140 | 14 |
| sync-status | 141 | 67 | 74 |
| sync-export | 169 | 167 | 2 |
| ctx | 59 | 59 | 0 |
| index | 9 | 9 | 0 |
| build-index | 11 | 11 | 0 |
| check | 8 | 6 | 2 |
| find | 31 | 29 | 2 |
| misc (root resolution, global options, help) | 612 | 582 | 30 |
| parser (abbreviations, `--`, repeats, help at several widths, env) | 741 | 732 | 9 |
| tty (pseudo-terminal runs) | 307 | 214 | 93 |
| pipe (reader closes the pipe) | 15 | 7 | 8 |
| **total fixtures** | **13,714** | **11,859** | **1,855** |

All sets: 34,094 invocations, 32,130 SAME, 1,964 DIFF.

**Extra cases for entries covered elsewhere**

(a) Broken pipe, Go exit 141 (ErrorsOrderCompletion)
- Exit status of okf in `okf ... | head -c 100`: Python 0, Go 141 for `list --where 'path ~ /'`, the same with `--json`, `tags`, `read version-control-git/index --follow 3`, `recent --limit 500`, `ctx read git-canon`, `find git --limit 50`, `index` (8 of 15 commands probed, production catalogue).
- Same status in both for the other 7: `wikilinks`, `prime --full`, `info`, `toc version-control-git/index --level 0`, `refs TAGS.md`, `sync-status` (0) and `check` (4).
- stdout and stderr are identical in all 15; only the exit status differs.

(b) Python traceback against Go one-line message for OS errors (ErrorsOrderCompletion, CtxDeviations); exit 1 in both, `--json` runs differ the same way
- `refs <md> --scan-root <path>`: 108 runs on the production catalogues (Knowledge-Catalogue 82, home-lab-wiki 13, sproutling-okf 11, dev-okf 2). Nonexistent directory (107): `FileNotFoundError: [Errno 2] No such file or directory: '<COPY>/nonexistent'` against `open <COPY>/nonexistent: no such file or directory`. A file instead of a directory (1): `NotADirectoryError: [Errno 20] Not a directory: '<path>'` against `open <path>: not a directory`.
- Dangling symlink inside a bundle: 13 runs (`wikilinks` 3, `list` 2, `read` 2, `refs` 2, `sync-status` 2, `tags` 1, `visualize` 1) and 4 runs of `refs TAGS.md --scan-root ..` over a tree that holds such a link: `FileNotFoundError: ... '<root>/fs/dangling.md'` against `open <root>/fs/dangling.md: no such file or directory`.
- Unreadable file (`chmod 000`, DAC capabilities dropped): 40 runs (`read` 6, `refs` 6, `wikilinks` 6, `list` 4, `sync-status` 4, `tags` 4, `toc` 2, `visualize` 2, `check` 2, `find` 2, `sync-export` 2): `PermissionError: [Errno 13] Permission denied: '<root>/fs/secret.md'` against `open <root>/fs/secret.md: permission denied`.
- `--root '~root'` (unreadable `/root`), 4 runs: `PermissionError: [Errno 13] Permission denied: '/root'` against `open /root: permission denied`.
- Identical in both: unreadable or read-only directory, file and directory symlinks, symlink loop, invalid-UTF-8 file names.

(c) `ReusedAnchorWarning` (ScalarSemantics)
- 1,511 runs differ only by the extra Python stderr warning (stdout and exit code equal): `refs` 685, `list` 561, `read` 140, `sync-status` 68, `tags` 41, `wikilinks` 8, `toc` 4, `prime` 2, `visualize` 2.
- Trigger: any run that parses a catalogue holding a frontmatter with a repeated anchor (`a: &x 1`, `b: &x 2`, `c: *x`). No production-data run printed the warning.

(d) Tagged and anchored scalar text (ScalarSemantics, CtxDeviations)
- 68 runs: `list` 64 (60 on a catalogue with 87 exotic scalars each in `title`, `type`, `description` and a tag; 4 on the crafted edge catalogue), `tags` 3, `prime` 1.
- `t: !!python/object:os.system x`: `t = x` matches only in Go; `t > 2025-12-31` also lists it in Go only. `s: !!set {a, b}`: `s ~ a` and `s ~ set` match only in Python. `a: &x 1`: `a = 1` matches only in Go.
- `d6: 2026-01-01T00:00:00.5+02:00`: `d6 ~ .500000` and `d6 = '2026-01-01T00:00:00.500000+02:00'` match only in Python; `d6 = '2026-01-01T00:00:00.5+02:00'` only in Go.
- Identical: `t ~ x`, `s = a`, `d6 ~ .5`, `d1 = 2026-01-01`, `d2 = 2026-01-01T00:00:00Z`, alias values (`base.k = v`), and all 7,383 production-data `list` runs.

(e) TOML wording and BOM (ScalarSemantics, ErrorsOrderCompletion)
- 25 runs with a user `config.toml` (`--global info`, `--global list`, fallback from a directory without marker, `$HOME/.config/okf/config.toml`, relative and empty `XDG_CONFIG_HOME`, `--global` inside the catalogue).
- `root = [unterminated` (9 runs, one of them in the production-data set) and a duplicate `root` key (8 runs): exit 2 and the same `ERROR: <path> is not valid TOML:` prefix; reason text differs (`Invalid value (at line 1, column 9)` against `expected value but found "unterminated" instead (at line 1, column 9)`; `Cannot overwrite a value (at line 2, column 56)` against `Key 'root' has already been defined. (at line 2, column 57)`).
- UTF-8 BOM before `root = "..."` (8 runs): Python exit 2 `... is not valid TOML: Invalid statement (at line 1, column 1)`, Go exit 0 and answers. Identical: the other 20 config spellings (absolute, `~`, relative, CRLF, single-quoted, multi-line, unicode, spaces, missing, file as root, wrong type, empty).

(f) `visualize` with a non-UTF-8 file name (ErrorsOrderCompletion)
- 2 runs (`visualize fs --out <file>` text and `--json`) on a bundle with `bad\xffname.md` and `bad\xfedir/inner.md`: stdout and exit code equal; the written HTML differs only in the JS node ids: Python `"bad\udcffname"` and `"bad\udcfedir/inner"`, Go `"bad\ufffdname"` and `"bad\ufffddir/inner"`.
- Every other `visualize` run wrote byte-identical HTML, including NFD/NFC names, emoji, CJK, spaces, CRLF and BOM files.

**Identical in both / did not reproduce**

- `list` (7,383 production runs, 1,480 with `--json`): every `--where` family (type, tag, path, status, tier, stale, archived, generated.by, verified.by, instants in about 30 spellings, `in (...)`, and/or/not, quoted values) and 1,315 syntax-error expressions (same exit 2 and text).
- `read` (4,315): every md file of the four roots, whole page, `--json`, `--frontmatter-only`, `--body-only`, `--section` (first, middle and last heading, upper and lower case, nested `A > B`), `--follow 1..3`, `--inbound`, `--max-tokens`; `toc` (2,981, levels 0..7 and invalid values); `refs` (2,784 of 2,892; the 108 are in (b)).
- `prime` (70), `info` (12), `wikilinks` (330), `sync-status` (364), `sync-export` (184), `ctx` (306: every slug through list, show, read, toc, outbound, inbound, check), `tags` (1,004), `recent` (507): no difference on production data.
- Archived concepts (all of them in three catalogues; 227 runs) and 198 runs with `.fts`/`.tagvec` present, stale, corrupt, empty, a directory or foreign: identical.
- `tags` on fixtures: 2,504 runs, 2,455 identical (mutated production tags, word pairs, unicode queries, `--validate`, 14 registry variants: table, block, mixed, CRLF, BOM, empty, missing, prose only, odd rows, `types_source`); the 49 differences are covered by (b), (c) and (d).
- Crafted read-side catalogue: CRLF, BOM, lone CR, NEL/LS/PS/VT/FF/FS/GS/RS in headings, setext and fenced headings, 15 invalid-YAML frontmatters, 99 link and 64 wikilink spellings, a 300 KB line, NUL and Latin-1 bytes, empty files, file and directory symlinks, symlink loop, invalid-UTF-8 names: identical except as listed in (b), (c), (d) and (f).
- `recent` git states: untracked, staged, modified, deleted and re-added, renamed, three commits in one second, paths starting with `@`, non-ASCII names, bundle symlinked into another repository or into no repository, non-git root, empty repository, `PATH` without git, `GIT_DIR`, locale and 29 TZ values: identical.
- Root resolution: trailing slash, `//`, `..`, relative and `~` roots, hull layout, 23 config spellings, HOME and `XDG_CONFIG_HOME` variants; 231 option shapes and 38 global-option placements; help of all 33 commands and 14 ctx verbs at several `COLUMNS` values: identical except entries 3 and 4 and (e).
- `visualize`: all runs except entry 7 and (f) wrote byte-identical HTML.

**Harness artefacts**

- `refs TAGS.md --scan-root=. --json` (1 run): the JSON `target` is relative to the cwd, so it differs only because the two copies sit in directories with different names.
- Config `root = "~"` (2 runs): the root expands to the whole real HOME; Python hit the 60 s timeout, Go answered quickly. Duration, not behaviour.
- `read <id> --follow 99999999999999999999`: both implementations loop for ever; removed from the matrix.
- The temporary directory ran out of inodes once; per-run files were replaced by one JSONL file per set. No effect on results.
- Both copies are unchanged after all runs (sha256 manifests before and after are equal), except the `visualize` output files, which were removed.

#### Sweep `WriteSweep`

**Scenario table**

Cause tags used in the cells (full entries elsewhere):
(a) Go refuses anchored/aliased/tagged values and the first refused file ends the whole run. (b) Go keeps formatting: `{ by: x }` spacing, CRLF, trailing spaces, indentation, comments. (c) `sync-update` on a CRLF consumer corrupts the file in Python. (d) Equal-title ties follow `os.listdir` in Python. (e) Python traceback vs one-line Go error for unreadable paths. (f) `tags --register` auto-embed warning text. (g) YAML parse-error wording.

"files changed": `N*` = files written, as the command's own summary line reports (the scenario starts from a mutated copy); otherwise files that differ from the frozen catalogue after the scenario (modified, new, deleted), equal in both implementations unless two numbers are given. "n/a" = the command has no dry-run; "not run" = only the apply form was run. `[--x]` = run with and without the option.

| scenario | command line | files changed | dry-run output | apply output | resulting trees |
|---|---|---|---|---|---|
| normalize-all | `normalize-tags [--json] [--where "path ~ home-lab-wiki/"] [--apply]`, apply twice; 600 block-tag files first turned into inline lists (8 styles) | 582* | (b) in 2 of 3 dry-run steps | (b) | (b) 22 files |
| merge-go-tui | `merge-tags bubbletea golang --into go-tui [--json] [--apply]`, apply twice | 66 | identical | identical | identical |
| merge-adr | `merge-tags adr --into architecture-decision [--apply]`, apply twice | 43 | identical | identical | identical |
| merge-filtered | `merge-tags testing --into testing-quality --where "path ~ sproutling-okf/"`; `merge-tags devdash devdashboard --into dev-dashboard`; `merge-tags self-hosted-service home-lab --into homelab --where "type = Runbook or type = Decision"` | 29 | identical | identical | identical |
| merge-edge-cases | unknown tag; `golang --into golang`; `bubbletea golang --into golang`; no `--into` (rc 2); bad `--where` (rc 2); tag with a space | 65 | identical | identical | identical |
| merge-doc-sites | `merge-tags starlight --into starlight-site [--apply]` | 11 | (b) | (b) | (b) 11 files |
| remove-emptied | `remove-tags context-engineering [--json] [--apply]`, apply twice | 28 (3 lose `tags:`) | identical | identical | identical |
| remove-multi | `remove-tags bubbletea golang adr [--apply]`; `remove-tags testing --where "type = Decision" --apply` | 109 | identical | identical | identical |
| remove-doc-sites | `remove-tags starlight [--apply]` | 11 | (b) | (b) | (b) 11 files |
| fix-crosslinks-whole | `fix-crosslinks [--check] [--json] [--include-reserved]`, write twice | 3 (4 with `--include-reserved`) | identical | identical | identical |
| fix-crosslinks-targets | `fix-crosslinks [--check] <target>` for 8 targets (bundles, subdir, symlinked bundles, `_ctx`, 2 missing: rc 3); write on 2 | 1 | identical | identical | identical |
| fix-xml-tags-whole | `fix-xml-tags [--check] [--json]`, write twice | 3 (4 chains) | identical | identical | identical |
| fix-xml-tags-targets | `fix-xml-tags [--check] <target>` for 6 targets (2 missing: rc 3); write on 2 | 0 | identical | identical | identical |
| fix-links-tricky | `fix-xml-tags` and `fix-crosslinks [--check] [--json] [--include-reserved]`, write twice; 65 concepts (every 10th) carry 20 link/placeholder forms | 68* wrapped (590 chains), 68* rewritten (179 unresolved) | identical | identical | identical |
| reindex-fresh | `reindex [--check] [--json] <bundle>` for 19 bundles; no target (rc 2); missing bundle (rc 3); subdir | 0 | identical | identical | identical |
| reindex-stale | `reindex [--check] [--json] <bundle>` for 11 bundles, `--init [--check]`, `--init --force`; about 90 concepts edited, 16 removed, 54 added, an unlisted subtree, flat / multi-section / prose indexes | 48* index files updated | identical | identical | identical |
| migrate-whole | `migrate [--json] [--apply]`, apply twice | 56* migrated, 1 unresolved | identical | identical | identical |
| migrate-targets | `migrate <target>` for 8 targets (2 missing: rc 3); `--apply` on one subdir | 15* | identical | identical | identical |
| migrate-citations | `migrate [--json] [--apply]`, apply twice; 71 concepts got a citation section of 12 shapes | 79* migrated, 48 unresolved | (b) | (b) | (b) 2 files |
| migrate-git-history | `migrate [--json] [--apply]` on 20 concepts with a crafted git history (offsets +00:00, +05:30, -03:30, +14:00, committer date -12:00, 4 author spellings, frontmatter-only commit, rename, merge, untracked) and 5 `.okf.toml` `git_authors` variants | 18* migrated, 2 unresolved | (b) in 2 of 8 dry-run steps | (b) | (b) 1 file (CRLF); `generated` by/at equal in all 20 |
| verify-sample | `verify --by human:erik` (also `process:ci-check`, `claude-code/claude-sonnet-5-5`) on 3 concepts `[--json]`; second `--by`; bad actor (rc 2); missing concept / bundle (rc 3); `.md` suffix; `index`; archived | 5 | n/a | identical (16 steps, time masked) | (b) 1 file |
| verify-all | `verify --by human:erik <concept>` once for each of the 641 concepts | 641 | n/a | identical in 641 of 641 (rc 0, stdout, stderr; time masked) | (b) 24 files |
| archive-restore | `archive [--json] [--apply] knowledge-management/project-documentations-canon`, again; `archive --restore [--json] [--apply] _archive/knowledge-management/project-documentations-canon` | 6 mod, 1 new, 1 del after archive; 0 after restore | identical | identical | identical |
| archive-edge-cases | symlinked bundle, `dev-okf`, reserved `index`, `.md` suffix, missing concept (rc 3), missing bundle, already archived, `--restore` of a non-archived path, restore collision, `--force` | 11 mod, 3 new, 3 del | identical | identical | identical |
| rename-same-bundle | `rename [--json] [--apply] knowledge-management/project-documentations-canon.md knowledge-management/projekt-docs-canon.md`, again (rc 3), back; without `.md` (rc 2) | 6 mod, 1 new, 1 del (8 inbound links in 6 files, 1 ctx bundle); 0 after renaming back | identical | identical | identical |
| rename-cross-bundle | `rename [--apply] version-control-git/worktrees.md development-tooling/worktrees.md`; `rename [--apply] knowledge-management/code-system-t-d-b-i-q.md dev-okf/code-system-t-d-b-i-q.md` (into a symlinked bundle) | 17 mod, 2 new, 2 del | identical | identical | identical |
| rename-symlinked-bundles | `rename [--apply]` inside `sproutling-okf` and `home-lab-wiki` (symlinked bundles) | 7 mod, 2 new, 2 del | identical | identical | identical |
| rename-edge-cases | collision (+ `--apply --force`), ambiguous basename (+ `--apply`, `--force`), reserved `index.md` (rc 2), missing source (rc 3), same path (rc 2), absolute old path, target outside the root (rc 2), non-`.md` target (rc 2), new bundle | 22 mod, 2 new, 3 del | identical | identical | identical |
| rename-links-canon-owners | `rename [--json] [--apply]` of a concept referenced by 15 wikilink / markdown-link / text variants plus a fenced block in 5 files and 2 frontmatter keys; a move to another bundle; renames of the canon owners `DEPLOYMENT.md` and `GLOSSARY.md` (consumer `source=` follows); `wikilinks`, `sync-status`, `check` | 41 mod, 4 new, 4 del (6 prepared) | identical | identical | identical |
| rename-special-names | `rename --apply` of 26 files with special names (space, `()`, `[]`, `#`, `?`, `%20`, NFD umlaut, emoji, CJK, backslash, tab, ...), each with 5 link spellings; 6 renames onto special names; 6 `archive --apply`; `check` | 28 new | identical | identical | identical |
| rewrite-path-synthetic | `rewrite-path [--check] [--json] --scan-root <dir> docs/foo docs/bar` and 7 more patterns (regex specials, `$1\1${x}` in NEW, overlapping `aaa`, NFC, NFD, empty OLD, OLD = NEW) on 39 boundary lines, CRLF/BOM/no-EOL, non-UTF-8, dot dirs, `node_modules`, symlinks | 12* + 1* written | identical | identical | identical |
| rewrite-path-dangling-root | the same commands with a dangling symlink inside the scan root | 0 (both abort, rc 1/1) | (e) | (e) | n/a (nothing written) |
| rewrite-path-real | `rewrite-path [--check] [--json] CLAUDE.md AGENTS.md`; `justfile build-recipes`; a catalogue path; `--scan-root` whole copy / relative / subdir (full copy incl. `.obsidian`) | 51* for CLAUDE.md, 66 after all steps | identical | identical | identical |
| rewrite-path-long-diffs | `rewrite-path [--check] [--json] --scan-root <dir> docs/foo docs/bar` and variants on 12 repetitive files (250-1,200 lines) | 12* | identical | identical | identical |
| registry-convert-real | `registry convert --to block` and `--to table [--json] [--apply] TAGS.md` and `TYPES.md`, again; `PROPERTIES.md` (rc 2) | 1 (533 TAGS.md entries) | identical | identical | identical |
| registry-convert-shapes | `registry convert --to block` / `--to table [--apply] TAGS.md` and `tags --register zz-reg "..."` on 22 synthetic TAGS.md shapes (escaped pipes, 2 tables, prose, extra column, no EOL, duplicates, tabs, block form, fenced table, ...) | 22 shapes, 1 file each | identical | identical for the converts; (f) in the 22 `--register` steps | identical (TAGS.md bytes equal per shape) |
| tags-register | `tags --register <tag> "<description>"` 17 calls (two tags, again, 151 chars: rc 2, upper case, space, pipe, newline, unicode, padded, duplicates, `--json`, block form); `tags --validate` 3 calls | 1 (TAGS.md) | n/a | (f) in 11 of 17 calls (stderr only) | identical |
| sync-drift-matrix | `sync-status [--json] [--source] [--block]`, `sync-export`, `sync-update [--json] [--force] [--apply]`, `sync-insert [--json] [--apply]`, `check`; canon edits first (source changed, consumer modified, both changed, source marker removed) | 7 (4 prepared); `sync-update --apply`: 2 updated, 2 refused, 1 unresolvable; `--apply --force`: 2 updated | identical | identical | identical |
| sync-insert-shapes | `sync-insert --apply <consumer> sproutling-okf/releases-and-deployment/DEPLOYMENT tier-chain` into 9 consumer shapes (empty body, no EOL, ends in fence, no frontmatter, unclosed fence / comment, tabs), reserved file, `.md` suffix, second block; `sync-update --apply`; `sync-status`; `check` | 10 new (prepared) | not run | identical | identical |
| ctx-all-verbs | `ctx create [--import] [--description]`, `add [--pos] [--mode] [--comment]`, `move`, `drop`, `rename` (inbound links follow), `edit` (`EDITOR=true`), `check [--stale]`, `list`, `show`, `read`, `toc`, `outbound`, `inbound`, `remove`; error cases (rc 2/3/4) on the real `_ctx` | 2 mod, 2 new | n/a | identical | identical |
| build-index | `build-index [--json] [--if-stale] [--include-topics]`; `find` | 1 (`.fts/fts.sqlite`: 668 concepts, 7 tables row for row equal) | n/a | identical | identical |
| visualize | `visualize <bundle> [--json]` for 7 targets (1 missing: rc 3) | 6 new (`assets/viz.html`) | n/a | identical | identical (the 6 files are byte-equal) |
| exotic-normalize | `normalize-tags [--apply]` on the normalize-all copy plus 41 concepts re-encoded (CRLF, BOM, BOM + CRLF, no final newline, `---` + trailing spaces, trailing spaces in frontmatter); run twice | 570* | (b) | (b) | (b) 40 files (all collapse under CRLF / trailing-space / flow-map normalisation); `git status` differs in 3 lines |
| exotic-merge | `merge-tags bubbletea golang --into go-tui [--apply]` on the 41 re-encoded concepts | 66* | (b) | (b) | (b) 2 files |
| exotic-remove | `remove-tags golang [--apply]` on the same | 66* | (b) | (b) | (b) 2 files |
| exotic-migrate | `migrate [--apply]` on the same | 55* | (b) | (b) | (b) 3 files |
| exotic-fix-links | `fix-xml-tags` and `fix-crosslinks` after the 20-form block and the 41 re-encodings | 68* wrapped, 68* rewritten (190 unresolved) | identical | identical | identical |
| exotic-rewrite-path | `rewrite-path [--check] CLAUDE.md AGENTS.md` on the same | 51* | identical | identical | identical |
| exotic-reindex | `reindex [--check] <bundle>` for 11 bundles, `--init`, `--init --force`, every 2nd reserved file CRLF | 58* index files updated | identical | identical | identical |
| exotic-registry | `registry convert` and `tags --register` with CRLF TAGS.md and TYPES.md | 2 (533 entries) | identical | identical; (f) in the 2 `--register` steps | identical |
| exotic-ctx | `ctx create`, `add`, `move`, `drop`, `rename`, `check`, `edit` with 5 CRLF ctx files | 4 mod, 2 new, 1 del (5 prepared) | n/a | (e) for `ctx edit` (no editor installed, rc 1/1); rest identical | identical |
| exotic-rename-archive | `rename --apply` twice, `archive --apply`, `archive --restore --apply` after the 41 re-encodings | 61 mod, 2 new, 2 del (41 prepared) | not run | identical | identical |
| exotic-sync | `sync-update [--apply --force]`, `sync-insert --apply` with CRLF consumers `04-bewaehrung-fahren.md`, `06-release-fahren.md` and CRLF source | 4* updated | (c) | (c) | (c) 2 files |
| sync-update-crlf-consumer | `sync-update [--apply]` after a canon edit, consumer `06-release-fahren.md` is CRLF; `sync-status`, `check` | 6 (prepared incl.); 2 updated | (c) | (c) | (c) 1 file |
| sync-update-crlf-source | the same with the canon owner `DEPLOYMENT.md` CRLF | 6 (prepared incl.) | identical | identical | identical |
| sync-update-crlf-both | the same with owner and consumer CRLF | 6 (prepared incl.) | (c) | (c) | (c) 1 file |
| sync-insert-crlf-consumer | `sync-insert [--apply] <consumer> <owner> tier-chain`, `sync-status`, `check`; consumer CRLF | 5 | identical | identical | identical |
| sync-insert-crlf-source | the same, canon owner CRLF | 5 | identical | identical | identical |
| sync-insert-crlf-both | the same, both CRLF | 5 | identical | identical | identical |
| sync-update-force-crlf | `sync-update --apply --force` with CRLF `06-release-fahren.md` and `07-hotfix.md` | 6 (prepared incl.) | not run | (c) | (c) 2 files |
| odd-file-binary | 15 steps: `normalize-tags`, `merge-tags okf --into okf2`, `remove-tags okf` (dry-run forms), `fix-crosslinks --check`, `fix-xml-tags --check`, `reindex [--check]`, `migrate`, `rewrite-path --check foo bar`, `check`, `sync-status`, `wikilinks`, `build-index`, `list`, `tags`; a concept whose body is not UTF-8 | 1 mod, 1 new | identical | identical | identical |
| odd-file-dangling-dirlink | the same 15 steps; symlink to a missing directory | 1 new | identical | identical | identical |
| odd-file-dangling-md | the same steps plus `verify`, `archive`, `rename`, `ctx create`; dangling `.md` symlink | 1 new | (e) in 7 of 10 dry-run steps and in 5 read steps (`check`, `sync-status`, `wikilinks`, `list`, `tags`), all rc 1/1 | identical (`reindex` rc 0/0; `verify`, `archive`, `rename`, `ctx create` of the dangling path rc 3/3); (e) for `build-index` | identical |
| odd-file-directory-named-md | the same 15 steps; a directory named `x.md` | 0 | identical | identical | identical |
| odd-file-empty | the same 15 steps; empty `.md` | 1 mod, 1 new | identical | identical | identical |
| odd-file-symlink-same-title | the same 15 steps; symlink to a file with the same title | 1 mod, 1 new | (d) `reindex --check` | (d) `reindex` | (d) 1 file |
| odd-file-symlink-loop | the same 15 steps; symlink loop | 1 mod, 1 new | identical | identical | identical |
| odd-file-dangling-detail | dangling symlink: `normalize-tags [--json]`, `fix-crosslinks --check`, `tags --json`, `list --json`, `reindex`, `verify`, `ctx create`, `archive`, `rename` | 1 new | (e) in 3 of 4 dry-run steps, and the 2 read steps | identical | identical |
| title-sort-keys | `reindex [--check]`, `index [--json]`, `list`, `recent` for 64 titles with casefold-equal groups and 6 sub-folders | 7* index files updated (77 new) | (d) | (d) | (d) 1 file |
| verify-frontmatter-shapes | `verify --by human:erik <concept>` over 30 frontmatter shapes (null / flow / scalar `verified`, no frontmatter, CRLF, anchors, tabs, duplicate key, ...), repeats | 30 new (prepared) | n/a | (g) in 2 of 33 steps; rest identical | (b) 7 files |
| tag-verbs-shapes-merge | `merge-tags okf --into okf2 [--apply] --where "path ~ <test bundle>/"` over 44 frontmatter shapes | Python 30 (5 unparseable), Go 0 (rc 2) | (a) | (a) | (a) 30 files |
| tag-verbs-shapes-remove | `remove-tags okf cli [--apply] --where ...` on the same shapes | Python 30 (27 emptied, 5 unparseable), Go 0 (rc 2) | (a) | (a) | (a) 30 files |
| tag-verbs-shapes-normalize | `normalize-tags [--apply] --where ...` on the same shapes | Python 5 (3 unparseable), Go 0 (rc 2) | (a) | (a) | (a) 5 files |
| migrate-shapes | `migrate [--apply] <test bundle>` over the same 44 shapes | 1* migrated, 1 unresolved | identical | identical | identical |
| modes-and-symlinks | `merge-tags okf --into okf2 --apply`, `verify`, `fix-crosslinks`, `fix-xml-tags`, `rename --apply` (a symlink), `archive --apply`, `reindex`, `rewrite-path` on files with modes 600/755/444/000/666/4644, a file symlink and a directory symlink | 8* tag rewrites; modes equal after every step | n/a | (e) in 2 steps: `archive` and `rewrite-path` abort in both (rc 1/1) after `archive` of a symlink's target left a dangling link; rest identical | identical (modes and link-ness equal) |
| anchored-tags-production | `merge-tags bubbletea golang --into go-tui [--apply]` after one real concept got `tags: &tg` plus an alias; rerun with `--where "path != <that concept>" --apply`; `verify` | Python 66, Go 0 (rc 2); after the rerun Go 65 | (a) | (a) | (a) 66 files; after the rerun 1 file (that concept) |
| git-state-unstaged-edit | `rename --apply version-control-git/tags.md version-control-git/tags-new.md`; `archive --apply version-control-git/worktrees`; `rename --json --apply version-control-git/branches.md version-control-git/branches-new.md` with an unstaged edit in the source files | 17 mod, 3 new, 3 del | not run | identical | identical (incl. `git status` of 4 repos) |
| git-state-staged-edit | the same three commands, staged edit | 17 mod, 3 new, 3 del | not run | identical | identical |
| git-state-index-lock | the same, `.git/index.lock` present | 17 mod, 3 new, 3 del | not run | identical | identical |
| git-state-no-git | the same, no `.git` | 17 mod, 3 new, 3 del | not run | identical | identical |
| git-state-fresh-init | the same, fresh `git init` without commits | 17 mod, 3 new, 3 del | not run | identical | identical |
| git-state-detached-head | the same, detached HEAD | 17 mod, 3 new, 3 del | not run | identical | identical |
| git-state-ignored-file | the same, source file listed in `.git/info/exclude` | 17 mod, 3 new, 3 del | not run | identical | identical |
| git-state-assume-unchanged | the same, `assume-unchanged` on the source file | 17 mod, 3 new, 3 del | not run | identical | identical |
| git-state-skip-worktree | the same, `skip-worktree` on the source file | 17 mod, 3 new, 3 del | not run | identical | identical |
| git-state-case-conflict | the same, destination exists with different letter case | 17 mod, 4 new, 3 del | not run | identical | identical |
| git-state-dest-is-dir | the same, destination is a directory (first rename refused, rc 2 in both) | 16 mod, 2 new, 2 del | not run | identical | identical |
| git-state-dest-parent-file | the same, parent of the destination is a file | 17 mod, 4 new, 3 del | not run | identical | identical |
| argparse-abbreviations | 31 calls on write verbs: `--ap`, `--app`, `--wh`, `--in`, `--chec`, `--rest`, `--for`, `--js`, `-h`, `--`, `=` forms, intermixed, duplicates, empty / unicode tag, `registry conv --to bl`, `tags --reg` | 2 | identical | identical except (f) in 1 step (`tags --reg`) | identical |
| repro-anchor | one-bundle catalogue: `merge-tags a --into c [--apply] [--where "path != b/x"]`; `x.md` has `tags: &t` | Python 3, Go 0 (rc 2); with `--where` Go 2 | (a) | (a) | (a) |
| repro-flow-map | one file: `normalize-tags --apply` with `tags: [a, b]` and `generated: { by: ..., at: ... }` | 1 | not run | (b) | (b) |
| repro-trailing-spaces | one file: `normalize-tags --apply` with `type: Note   ` and `tags: [a, b]   ` | 1 | not run | (b) | (b) |
| repro-crlf | one CRLF file: `normalize-tags --apply` | 1 | not run | (b) | (b) |
| repro-delimiter-spaces | one file with `---   ` as opening delimiter: `normalize-tags --apply` | 1 | not run | (b) | (b) |
| repro-verify-shapes | `verify --by human:erik <concept>` on zero-indent list, 4-space nesting, `~` / `null`, comment-only frontmatter, CRLF | 5 | n/a | identical | (b) 5 files |
| repro-register | `tags --register zz-new "A new tag"` | 1 | n/a | (f) | identical |
| repro-sync-crlf | `sync-update [--apply]` with CRLF consumer, canon edited | 2 updated | (c) | (c) | (c) |
| repro-tie-order | `reindex b`, `index b` with three concepts titled "Same title" | 1 | not run | (d) | (d) |
| repro-dangling | `normalize-tags [--json]`, `reindex b`, `verify` with a dangling `.md` symlink | 1 new | (e) | identical | identical |
| repro-ctx-edit | `ctx create zz b/x`; `ctx edit zz` with `EDITOR=no-such-editor-xyz` | 1 new | n/a | (e) | identical |

**Production-scale numbers**

- Data: 4 git trees, 641 concept files reachable from the catalogue root, 19 bundles, 668 documents indexed by `build-index`, 533 entries in TAGS.md.
- `verify --by human:erik` on all 641 concepts, one call each: 641 of 641 identical in rc 0, stdout and stderr (time masked); 641 files written in both; 617 byte-equal apart from the time; 24 differ only in `generated: { by: ..., at: ... }` spacing (23 under `documentation-sites/`, 1 `software-delivery/item-summary-feeds-release-notes.md`), plain data equal.
- Those 24 files are the only variant of (b) in unmutated production data. On unmutated data the only other difference is the (f) stderr text of `tags --register`. No Go refusal of a file (rc 2 "anchor, alias or explicit tag") and no Python traceback occurred in any run on unmutated production data.
- `normalize-tags` (600 of 675 block-tag files first turned inline): 582 files rewritten in both; trees identical except 22 files, all `{ by: x }` spacing.
- `merge-tags bubbletea golang --into go-tui` 66 files, `adr` into `architecture-decision` 43, `remove-tags bubbletea golang adr` 109, `remove-tags context-engineering` 28 (3 lose `tags:`): trees identical. `merge-tags starlight` and `remove-tags starlight`: 11 files each, all 11 differ in (b) only.
- Anchored file at production scale: one real concept given `tags: &tg` plus an alias; `merge-tags bubbletea golang --into go-tui --apply`: Python wrote 66 files, Go wrote 0 (rc 2). Rerun with `--where "path != <that concept>"`: Go wrote 65; the trees then differ in that one file only (a).
- `migrate`: whole catalogue 56 files, 1 unresolved, identical. With 71 injected citation sections: 79 files, 48 unresolved, 2 files differ in (b). Crafted git history: 18 files migrated; `generated` by/at equal in all 20 files; only the CRLF file differs.
- `reindex`: 19 fresh bundles 0 files to update in both; after the mutation 48 index files updated, trees identical.
- `rename` of a concept with 8 inbound links in 6 files and 1 ctx bundle, `archive` and `archive --restore`: identical; renaming back or restoring leaves 0 files different from the frozen catalogue in both.
- `fix-crosslinks` 3 files (1 unresolved link), `fix-xml-tags` 3 files (4 chains), `rewrite-path CLAUDE.md AGENTS.md` 51 files, `sync-update --apply` 2 updated, 2 refused, 1 unresolvable (`--force`: 2 updated): identical.
- `build-index`: 668 documents; `.fts/fts.sqlite` equal table by table (7 tables; `docs` 668 rows).
- Volume: 947 logged paired steps plus 641 `verify` writes = 1,588 paired runs (lower bound).

**Extra cases for entries covered elsewhere**

(a) Anchored, aliased or tagged values:
- Production scale: `merge-tags bubbletea golang --into go-tui [--apply]` after `software-patterns/tui-architecture-design/lazy-cache-and-optimistic-merge` got `tags: &tg` and `related_tags: *tg`: dry-run Python rc 0 (66 files), Go rc 2, stdout empty; apply: Python 66 files written, Go 0; rerun with `--where "path != software-patterns/tui-architecture-design/lazy-cache-and-optimistic-merge"`: Go rc 0, 65 files.
- One-bundle repro: `merge-tags a --into c [--apply]` with `b/x.md` = `tags: &t` and two plain files: Python rc 0 `merge-tags: 3 file(s) would rewrite, 0 unparseable — a -> c`; Go rc 2, stdout empty, stderr `b/x.md: the value of a key carries an anchor, an alias or an explicit tag`; with `--where "path != b/x"` Go rc 0 `2 file(s) rewrote`.
- 44 frontmatter shapes in one test bundle (one is `tags: &t`): `merge-tags okf --into okf2` Python 30 files (5 unparseable) / Go 0; `remove-tags okf cli` Python 30 (27 emptied, 5 unparseable) / Go 0; `normalize-tags` Python 5 (3 unparseable) / Go 0; Go rc 2 in all three, no file written.
- `migrate` over the same 44 shapes: identical (the anchored file needs no change, so Go does not refuse).

(b) Formatting kept by Go:
- `{ by: x }` spacing, `generated: {by: claude-code/claude-sonnet-5-5, at: 2026-10-16T08:54:24Z}` (Python) vs `generated: { by: claude-code/claude-sonnet-5-5, at: 2026-10-16T08:54:24Z }` (Go): 24 production files; hit by `normalize-tags` (22 files in the mutated run), `merge-tags starlight` (11), `remove-tags starlight` (11), `migrate` (2 in the citation run), `verify` (24 of 641). Python's dry-run diff shows that line as changed in every such file (hunk `@@ -4,9 +4,9 @@`), Go as untouched context (`@@ -4,7 +4,7 @@`).
- One-file repros: trailing space `type: Note   ` kept by Go; CRLF file: Python writes LF throughout, Go keeps CRLF on every line; opening delimiter `---   ` kept by Go (Python `---`); zero-indent `tags:` list `- a` kept by Go (Python `  - a`); 4-space nesting kept by Go (Python 2); `null1: ~` / `null2: null` kept by Go (Python `null1:` / `null2:`); comment-only frontmatter `# only a comment` dropped by Python, kept by Go.
- `migrate` on a CRLF concept: Python writes the frontmatter with LF and leaves the body CRLF (151 bytes, 4 CR), Go keeps CRLF everywhere (160 bytes, 13 CR); `generated` by/at equal.
- 41 re-encoded concepts (CRLF, BOM, BOM + CRLF, no final newline, `---` + trailing spaces, trailing spaces in frontmatter): `normalize-tags` 40 differing files (all collapse under CRLF / trailing-space / flow-map normalisation), `merge-tags` 2, `remove-tags` 2, `migrate` 3. A file that starts with a BOM is not read as frontmatter by either implementation: `normalize-tags`, `merge-tags`, `remove-tags`, `migrate` leave it untouched (0 files, same in both); `fix-crosslinks` and `fix-xml-tags` rewrite its text and `verify` prepends a new frontmatter block in front of the BOM, identical in both (a BOM + CRLF file differs per (b): Python LF, Go CRLF).

(c) `sync-update` on a CRLF consumer: canon `tier-chain` in `DEPLOYMENT.md` edited (one extra line), consumer `sproutling-okf/processes/core/06-release-fahren.md` CRLF, `sync-update --apply`:
- Python dry-run hunk `@@ -70,24 +70,22 @@` deletes the list line ``- Kundentext, Deckungs-Audit, DE nach EN: `skill:spf-release-notes`.`` outside the block; Go hunk `@@ -74,20 +74,21 @@` replaces the block (hash `332598d12aa7` to `ba88bf8b9b29`).
- After apply the Python file ends `Zusatzsatz im Canon-Block fuer den Sweep.$` / ``<!-- /okf:sync -->oduction` geht, ist bitidentisch mit dem, was auf `beta` lief.^M$`` / `<!-- /okf:sync -->^M$`; Go ends `Zusatzsatz ...$` / `<!-- /okf:sync -->^M$`. LF-normalised diff against the file before the run: Python 8 changed lines, Go 3. Sizes 7055 B before, 7097 B Python, 7081 B Go; Go writes the new lines with LF inside the CRLF file.
- Variants: canon owner also CRLF: same; `sync-update --apply --force` with two CRLF consumers: 2 files differ; three CRLF files (04, 06, owner) with `--force`: 2 files differ; CRLF owner only: identical; `sync-insert` with CRLF consumer, owner or both: identical.

(d) Equal-title ties:
- Three concepts titled "Same title" (`a-first`, `m-middle`, `z-last`, created in that order): `reindex b` lists Python z-last, m-middle, a-first (directory order) and Go a-first, m-middle, z-last; `index b` the same.
- A symlink to `tags.md` (same title) in `version-control-git`: `reindex --check` rc 5/5 and `reindex` rc 0/0, stdout differs, `index.md` is the one differing file.
- 64 titles with casefold-equal groups (`Straße/Strasse/STRASSE/strasse`, `ΑΣ/ας`, `Ø/ø`, `ꜳ/Ꜳ`, `Ñandú/ñandú`, `NAÏVE/naïve`): `reindex` updates 7 index files in both, the order differs only inside the groups; `index` shows the same.
- Code reading only: `rename` and `archive` plan their reindex over sorted names (Python `PlannedFs.listdir`), so ties there already follow the file name like Go; no tie case was run through them.

(e) Traceback vs one-line error:
- Dangling `.md` symlink in a bundle: 13 steps abort rc 1/1 in both with different stderr: `normalize-tags`, `merge-tags okf --into okf2`, `remove-tags okf`, `fix-crosslinks --check`, `fix-xml-tags --check`, `migrate`, `rewrite-path --check foo bar`, `check`, `sync-status`, `wikilinks`, `build-index`, `list --where "type = Note"`, `tags`. Identical: `reindex` (rc 0), `verify` / `archive` / `rename` / `ctx create` of the dangling path (rc 3).
- Python `FileNotFoundError: [Errno 2] No such file or directory: '<path>'`, Go `open <path>: no such file or directory`; with `--json` `error.message` `FileNotFoundError: ...` vs `*fs.PathError: open <path>: no such file or directory`, kind `internal`, code 1 in both.
- Natural trigger: `archive` of a concept that a symlink points at leaves a dangling link; the next `archive` or `rewrite-path` aborts in both (rc 1/1). `rewrite-path` with a dangling symlink in the scan root: 10 of 12 steps abort rc 1/1 in both.
- `ctx edit` with a missing editor: Python `FileNotFoundError: [Errno 2] No such file or directory: 'no-such-editor-xyz'`, Go `exec: "no-such-editor-xyz": executable file not found in $PATH`, rc 1/1 (also without any editor installed).

(f) `tags --register` warning:
- Every call that registers a tag with the network unreachable: 11 of 17 `--register` calls in the variant run, 22 after `registry convert` on 22 synthetic TAGS.md shapes, 2 with CRLF TAGS.md, 1 with `tags --reg zz-a desc`.
- stdout, rc 0/0, resulting TAGS.md and `.tagvec/tag_vectors.sqlite` (sha1 `84e8a8fdc2` before and after) equal in both.
- Python `(URLError: <urlopen error [Errno 101] Network is unreachable>)`, Go `(connection failed)`; the rest of the line `— run cli/embeddings/build_tagvec.py --produce manually later` is equal.

(g) YAML parse-error wording (`verify --by human:erik <concept>`, rc 2 in both, file untouched):
- Duplicate key `title`: Python `frontmatter does not parse: found duplicate key "title" with value "dup" (original value: "v16") (line 4, column 1)`, Go `frontmatter does not parse: found duplicate key "title" (line 4, column 1)`.
- Tab indentation: Python `found character '\t' that cannot start any token (line 5, column 1)`, Go `found character that cannot start any token (line 5, column 1)`.

No cause beyond (a)-(g) turned up, so there is no full entry.

**Identical in both**

- `normalize-tags`, `merge-tags`, `remove-tags`: same files selected, same rewrite counts, same de-duplication and emptied-`tags` handling, same `--json` envelope (apart from (a), (b)).
- `fix-crosslinks` and `fix-xml-tags`: whole catalogue, bundle and subdir targets, `--include-reserved`, 65 files with 20 link/placeholder forms each, also on CRLF/BOM/no-EOL variants.
- `reindex` incl. `--init` and `--init --force`: stale/uncovered reports, refusals, odd titles and file names (apart from (d) ties).
- `migrate`: git-derived `generated.at` for offsets +00:00, +05:30, -03:30, +14:00 and a -12:00 committer date; author mapping (mapped, unmapped, other case, empty local part, umlaut); frontmatter-only commits skipped; rename followed; merge; untracked; all `git_authors` variants and their error exits.
- `verify`: all actor forms, `--json`, 641 concepts, 30 frontmatter shapes (apart from (b), (g)).
- `archive`, `archive --restore`, `rename`, `--force`: link, wikilink and sync-`source=` rewriting, `git mv` outcome in all four repositories, 12 git states, 26 special file names, symlinked bundles.
- `rewrite-path`: Unicode word boundaries, literal `$1` / `\1` in NEW, regex specials in OLD, dot-dir pruning incl. `.obsidian`, symlinks, non-UTF-8 skip, long diffs.
- `registry convert` (real files and 22 shapes), `sync-status/-export/-update/-insert` (drift matrix, 9 consumer shapes), all `ctx` verbs on the real `_ctx`, `build-index` (7 tables row for row), `visualize` (6 byte-equal `viz.html`).
- Exit codes and `--json` envelopes of all of these, error cases included (rc 2, 3, 4, 5).
- File modes (600, 755, 444, 000, 4644) and write-through of symlinked files after every write verb.
- Option abbreviations (`--ap`, `--wh`, `--in`, `--chec`), `=` forms and `--`.
- A file that starts with a BOM is not read as frontmatter by either implementation: the tag verbs and `migrate` skip it, `fix-crosslinks` / `fix-xml-tags` rewrite its text and `verify` prepends a frontmatter block, the same in both (LF file byte-identical).

**Not run or not checked**

- `build-semantic-index` (needs network) and `install`: not run.
- `tags --register` with a reachable embedding service: not run; only the offline warning path.
- Only frozen copies were used; the live catalogues were out of reach. The copies lacked `.obsidian`, `.fts`, `.tagvec` except where a scenario needs them (`rewrite-path` on real data, `tags --register`, `build-index`).
- The mutations (inline tags, CRLF/BOM, link forms, citation sections, canon drift, git history) reach code paths that unmutated production data does not; results on them are marked by the scenario names and the "prepared" notes.
- Compared by eye, not by script: broken pipe under `| head`, `ctx create --import /dev/stdin` and `-`, relative `--root`, trailing slash.
- Per-step outputs of the CRLF `sync-update` variants were kept for the single-consumer repro only; the variants' trees and step status were compared by script.

#### Sweep `WriterRefusals`

**Refusal table**

All refusals are exit 2, error class `invalid_input`, and leave the file byte-identical (sha256 checked). Tag verbs and `migrate` prefix the reason with the catalogue-relative path (`w/x.md: <reason>`); `verify` prints the bare reason. With `--json` the same text is `error.message` in the envelope on stdout.

| Go reason (exit 2, invalid_input) | input shape | what Python does |
|---|---|---|
| the frontmatter is a flow mapping | root `{type: Concept, tags: [a, b]}`; also `--- {}`, `{ }`, `{}  # c`, `{type: Concept}` | writes (non-empty flow root keeps its flow style; empty roots become a block mapping) |
| the patched frontmatter does not read: mapping values are not allowed in this context (line 3, column 9) | root `~` (verify) | writes (null becomes a mapping) |
| the value of a key carries an anchor, an alias or an explicit tag | anchored, aliased or `!!seq`-tagged `tags`; anchor or alias on a tags item; anchored `verified`, `status`, `timestamp` | writes; a tags item `- !!str a` is ignored (exit 0, nothing written) |
| a comment sits inside a flow list | `tags: [a, # c` newline `b]` | writes and drops the comment (`normalize-tags` keeps it) |
| the frontmatter holds a carriage return that does not end a line | lone CR between keys of an LF file | writes, the CR becomes LF |
| the key "tags" is not in the frontmatter | CR-only file, or CR in front of the closing `---` (tag verbs) | writes, file converted to LF (`verify` on such a file: entry 1) |
| the stored text is not valid UTF-8 | invalid byte anywhere in the file (verify) | writes U+FFFD over the byte |
| list item N does not start behind its dash | null item `-`, or item value on the line after the dash (merge-tags, remove-tags) | writes |
| the last list item does not start behind its dash | last `verified` item with its value on the next line (verify) | writes |
| item N of "tags" is not a plain or quoted scalar | folded or literal block scalar as tags item (merge-tags) | writes |
| the flow list of "tags" does not start on its key line | `? tags` complex key; list on the line after `tags:` (normalize-tags) | writes |
| an item of the flow list of "tags" spans several lines | quoted flow item over two lines (normalize-tags) | writes |
| the key "tags" is written in a form that is not patched | `? tags` block form when the last item goes (remove-tags) | writes |
| a flow mapping over several lines cannot become a list | `verified: {by: …,` newline `at: …}` (verify) | writes |
| `verified` is neither a mapping nor a list of mappings; fix it by hand before verifying | `verified:` null, a scalar, a list of scalars (verify) | same text, exit 2 (identical) |
| frontmatter does not parse: <reader reason> (line L, column C) | invalid YAML, e.g. duplicate key (verify; tag verbs list the file as `unparseable`, migrate skips it) | same refusal; the YAML parser wording differs (the known golden entry) |

16 distinct reasons were seen; a first count of 17 was a miscount.

**Production-data census**

- Source: frozen production copies (snapshot 20261016T144645Z), `.md` and `.toml` files only; every run on its own copy per implementation.
- 779 `.md` files, 720 with a frontmatter block. Refused by Go in any verb below: 0 files. No anchor, alias or explicit tag, no CR, CRLF, BOM or non-UTF-8 file, no comment inside a flow list.
- Flow-mapping root: 2 files (`HLO_home_lab_ops/home-lab-wiki/tools/index.md`, `.../services/index.md`), both reserved `index.md` files that no write verb reaches. Flow `tags` list: 1 file (reserved `SPF_sproutling/sproutling-okf/README.md`); block `tags` list: 675 files.
- `remove-tags <all 317 registered tags> --apply`: both exit 0, same 654 files rewritten (645 emptied), Go refused 0; 628 results byte-identical, 26 differ in bytes, 0 differ in data.
- The 26 byte differences: 24 files with `generated: { by: …, at: … }` (ruamel closes the spaces, Go keeps them) and 2 files (`sleep-data-logging-shape.md`, `sleep-recommendations-implementation.md`) with a blank line before the closing `---` (ruamel drops it, Go keeps it).
- `merge-tags <all 317 tags> --into zzz-merged --apply`: the same figures (654 files, 628 identical, 26 byte differences, 0 data differences, 0 refused).
- `normalize-tags --apply`: both exit 0 and rewrite 0 files (no flow `tags` list in a concept).
- `verify` on each of the 663 concepts: 663 times exit 0 in both; 639 byte-identical apart from the time in `at`, 24 differ only by the `{ by: … }` spacing; 0 data differences; Go refused 0.
- `migrate` dry-run on the full copy with git history: stdout byte-identical (682 lines, last line `migrate: would migrate 56 file(s), 1 unresolved; dry-run: re-run with --apply`), both exit 0.

**Identical in both / did not reproduce**

- S2b example `description: &x text`: no write verb sets `description` of a concept (`ctx add` keeps the stored value): identical, nothing to refuse.
- `migrate` on `status: !!str todo`: same outcome in both (unresolved); only the text of the status-mapping line differs (Python prints its ruamel object repr, Go prints `'todo'`).
- Non-UTF-8 file under `merge-tags`, `remove-tags`, `normalize-tags`, `migrate`: both skip it. `fix-xml-tags` and `fix-crosslinks` (they do not use the frontmatter writer): identical on non-UTF-8, NUL, BOM, CRLF, all-CR and lone-CR files (10 cases).
- A lone CR in the body only is not a refusal: both write, Python turns the CR into LF (entry 9a). A CR inside a plain value makes the file unparseable in both. `migrate` on an all-CR file, with a CR before the closing delimiter or in the body: identical.
- Identical in both: `{}` and `  {}` roots; list and scalar roots (`block is not a mapping`); `tags` as `a, b`, null, `[]`, nested, mapping or literal items; `verified` null, scalar or list of scalars; quote style of the new item and trailing comments of list lines (s3a to s3c, s4a to s4e).
- 20 probes of `tags --register` and `registry convert` (CRLF, BOM, no final newline, non-UTF-8, odd descriptions): identical apart from the known network-error text.
- 396 `merge-tags --into <value>` and 1 488 `verify --by <value>` runs: both refuse the same 8 and 78 runs; Go wrote the intended data in every other run (entry 10).
- Outside the writer area, for the owners: `ctx add` on a ctx file whose frontmatter does not parse: Python replaces the block (`description: ''`), Go exits 2 (documented deviation D02; Go ctx bundles (F: OKFT-82n3)).
- Outside the writer area: `migrate` on `status: todo` followed by a TAB and `# c`: Python's reader rejects the tab and skips the file, Go reads it and writes `status: draft` (reader difference, Go core and read side (F: OKFT-daut); Go's data is right).

#### Sweep `CtxDeviations`

**Identical in both / did not reproduce**

- Seed S13 said 5 strings; the 282-string sweep found 15 (entry 5). Seeds S2g, AC5a, S6a, S6b reproduce (entries 1 to 4).
- Identical for 13 to 26 commands each: missing, empty or extra frontmatter keys, comments, quoted, multi-line, null or numeric description, wrong or missing type in block style, CRLF ctx file (both write LF), unclosed frontmatter, flow root with `type: Context`, anchors, bare CR.
- Identical: duplicate entries, dead entries, upper-case or invalid modes, position gaps, Unicode digits, wrong cell counts, `~` and absolute entries, every link form, `|` and unicode in comments, header variants, two tables, no table, BOM, CRLF or lone-CR tables, invalid UTF-8.
- Identical: ctx members that are CRLF, multibyte, latin-1, empty, NFC/NFD names, non-md, directories (74 commands); symlinked bundles, HOME paths, link loops (114); 176 root spellings; `--stale` float rounding; file mode, inode and symlink kept on ctx writes.
- Identical: 260 argument variants of create/add/drop/move/rename/shorthand and every import-file line separator; `ctx --help` and verb help are byte-identical.
- Identical: rename/archive with a missing `_ctx` or index, a concept in 3 ctx files, ctx files moved in or out of `_ctx`, a self-listed ctx, unreadable rows, BOM, CRLF (28 cases).
- A frontmatter without a closing `---` counts as no frontmatter and is identical (both start a new block).
- Two production rename cases that differed (GLOSSARY, 02-container-fahren) were harness artefacts (Python had already moved the file in the sibling repository), not deviations.
- Not testable here: permission-denied cases (`unshare -r` makes the user root).

#### Sweep `ScalarSemantics`

**Identical in both / did not reproduce**

- `read`, `read --json`, `read --frontmatter-only` print the file's own text: identical. The seed on timestamps shows only where text is derived (entry 6).
- `--where` on instant keys: `stale_after` with 60 stored forms in 116 files x 4 predicates and 51 literal forms, and `verified.at` with merged mappings, give the same matches and exit codes (the 8 instant keys: `generated.at`, `verified.at`, `stale_after`, `usage_window.from|to`, `sources.last_modified`, `sources.usage_window.from|to`).
- Typed scalars in `list --where 'k = v'`, `--json`, `read`: 44 values x 157 predicates identical (`yes no on off ~ null true True 0o17 017 0x1F 0x1f 1_000 .5 5. 1e3 1E3 +1 -1 0b11 1:30 = 007 -0 +0 0.10 1.0 .inf -.inf .nan 08 1_0`, quoted numbers, dates, an empty value).
- Valid merge keys (`<<: *a`, `<<: [*a, *b]`, inline map, own key overriding a merged key, merge into `verified`/`generated`/`tags`): identical in `list`, `--where`, `check`.
- Plain duplicate keys, empty values, a 209-character string, long flow lists and maps: both refuse or read alike; only the wording of the refusal differs (entry 14).
- `okf_version` as `"0.2"`, `'0.2'`, `0.2`, `!!str 0.2`, `&a "0.2"`, `[0.2]`, block scalars: the same 5 forms declare 0.2 in both.
- `generated.by` and `verified[].by` with 38 Unicode-whitespace and control-character variants: `check` and `--where 'tier = ...'` identical.
- `check` rules on typed `status`, `type`, `tags`, `generated`, `verified`, `stale_after`, `usage_window`, `sources`, `superseded_by`, `runtime` (112 concepts): findings identical except the entries 6, 7, 14.
- Frontmatter layout: UTF-8 BOM before `---`, CRLF, CR-only, `---  `, `----`, no closing delimiter, empty block, `tags: []`, flow tags with alias, anchor, tag, comment: identical apart from the wording of one parse reason. A TAB inside quoted scalars, block scalars, comments, flow collections and NEL as a YAML escape (`"\u0085"`, `\N`, `\L`, `\P`): identical.

#### Sweep `ErrorsOrderCompletion`

**Identical in both**

- Usage errors (R-08): 48 of 48 cases give the same exit code (2) and byte-equal stderr starting `usage: okf`: no command, unknown command, unknown flag, missing or extra positional, missing option value, bad int or choice, option abbreviations (also ambiguous), `--opt=value`, `--`, negative numbers, `--limit 0/-1/huge/+2/1_0/0x10`, mutually exclusive options, `-h`, `--version`, `--global` with `--root`, `--root` without value, empty command.
- `COLUMNS` variants (0, 1 to 10, -1, abc, empty, unicode digits, 99999) on `--help`, `read --help`, `find --help` and a usage error: 96 of 96 identical.
- Bad `--where` expressions (empty, unbalanced, bad operators, bad timestamps, 600 levels of nesting, 3000-item `in`, plus `find`, `recent`, `merge-tags`, `normalize-tags`, `--json`, missing `--where`): 83 of 83 identical in exit code and text.
- Completion points (commands, options, concept ids, bundles, scopes, ctx slugs, tags, canon sources and ids, `_archive` refs, files, dirs; zsh, bash and raw protocol; quotes, backslashes, `$`, `:`, `=`, `;`, `&`, `*`, `~`, multibyte names, `--opt=`, `--`, `~` roots): 172 of 198 points identical in candidates, order, stderr and exit code; the others are entries 9, 10 and 13.
- Root problems (`--root` a file, a missing directory, a directory without marker, empty value, no catalogue above cwd and no config): same exit 3 or 0 and same text.
- Concept as FIFO (`read` exit 3; `list`, `find`, `check`, `tags` block in both), 300-character names, NUL bytes inside concepts, TYPES.md, TAGS.md, ctx files and `--types` or `--import` files, symlink loops inside a bundle: identical. NUL cannot be passed in argv.
- Non-UTF-8 bytes in a concept body: `read`, `find`, `list`, `check`, `toc`, `index`, `tags`, `recent`, `wikilinks`, `refs`, `info` identical (Python replaces, no traceback); only `verify` differs (entry 7).
- Ties in `recent`, `list`, `find` (substring and FTS), `visualize`, `refs`, `tags`, `prime`, `index`, `check` on tmpfs with creation order different from name order: identical (Python sorts explicitly, Go uses stable sorts).

**Gaps**

- The user-config battery (118 cases: config.toml variants and many `--root` spellings) stopped at case 94 because my test driver died on one case; of the 94 run, 60 are identical and the others are covered by entries 4 and 11, a test-harness path inside a note, and `--root /` where Python walked the whole disk into my 60 s limit.
- Entries 1 and 2 were run with `read` only; that every Go text-mode handler ignores write errors is inferred from the shared print calls, not read in every handler.
- Only tmpfs and btrfs exist on the test host; the ext4 and APFS `os.listdir` orders were not measured.
- Deep nesting was measured up to 20000 levels; the 200000-level runs did not finish before the run was stopped.
- The hostile-frontmatter sweep also showed scalar and alias differences in `list`, `find`, `tags` and `index --full` (anchors, billion-laughs `tags`, dates); they belong to the scalar-semantics area and were not analysed here.
- `ctx drop`, `ctx move` and `ctx list --for` use the Files completer; only `ctx create --import` was run.
- Count correction: my earlier chat summary said 270 of 280 completion points were identical; the logged count is 172 of 198 (entry-9, 10 and 13 points are the differing ones).

#### Sweep `TextUnicodeEmbed`

**Identical in both / did not reproduce**

- Characters named in the S14 seed (ß, İ, ǅ, ſ, K U+212A, Greek words with an ordinary final sigma, composed and decomposed accents, CJK, Hangul, kana, emoji, U+0085, U+200B, U+FEFF, U+00A0, U+2028, U+180E, U+001C, U+3000) did not reproduce a difference: 45 queries as text and `--json`, with and without index, 0 differences apart from E3.
- `isspace`/`\s`, NFC/NFD (all code points) and `str.splitlines` give the same results; `make_snippet` output is the same for length-changing lowercasing (İ), emoji, combining marks and the space characters above.
- The SQLite FTS index vocabulary for `x<c>y` over all code points is the same in both: 1,102,763 terms, 0 only in Python, 0 only in Go; only the query pre-split differs (E2).
- `find` on 545 production concepts: 153 queries, as `--json --breakdown` with and without index: 0 differences. Zero-hit suggestions (`difflib`) and `okf tags <query>` fuzzy matching: 0 differences in 150+ queries each.
- Embedding clients against the stub, happy path: hit order and cosine values, `--expand-tags`, `build-tagvec` rows, batch cuts (32 items or 90000 characters), halving ladder on oversized texts, tie order, `intvec`, `dim:512`, multi-batch with one failing batch: same stdout, stderr, exit code and database rows.
- Request payloads carry the same model, `input`, `input_type` and `Authorization` header (headers `Accept-Encoding` and `User-Agent` differ, no effect). A missing `VOYAGE_API_KEY` gives the same text and the same 14 s retry ladder in both.
- `build-tagvec` dry run with `--concept-limit 2/-1/0`, `--concept-path-prefix`, `--target`, `--model`: same output (only the usage line differs). Retry delays 2, 4, 8 s: 194.3 s in Python against 194.1 s in Go for three 60 s timeouts.

#### Sweep `PythonBugsFixed`

**Extra cases for entries covered elsewhere**

**(a) Go refuses frontmatter shapes that Python rewrites**
- `normalize-tags` on a flow-mapping root: Python exit 0 (`normalize-tags: 0 file(s) would rewrite, 0 unparseable`, with `--apply` `normalize-tags: 0 file(s) rewrote, 0 unparseable`); Go exit 2 `handbook/zz.md: the frontmatter is a flow mapping` in both modes.
- `migrate --apply` (files committed in git) on `timestamp: &t 2026-01-01T00:00:00Z`; `base: &s active` with `status: *s`; `timestamp: !!str 2026-01-01T00:00:00Z`; a flow-mapping root: Go exit 2 (`mg/zz.md: the value of a key carries an anchor, an alias or an explicit tag`, or `...: the frontmatter is a flow mapping`), file unchanged; Python exit 0 and valid YAML for all four.
- `verify` on `verified: &v [{...}]` and `verified: !!seq [{...}]`: Go exit 2 (anchor/alias/tag text); on a flow list with `# c` inside: Go exit 2 `a comment sits inside a flow list`; on a multi-line flow mapping: Go exit 2 `a flow mapping over several lines cannot become a list`. Python writes valid YAML in all four and drops the anchor, the tag and the comment.
- `normalize-tags` on `tags: [&x a, *x]` and `tags: [!!str 1, a]`: Go exit 2 (anchor/alias/tag text), Python writes a block list that keeps `- &x a`, `- *x`, `- !!str 1`; on `tags: [a, ?q]`: Go exit 2 `the patched frontmatter does not read back as intended`, Python writes `- {q: null}`.
- a comment inside a flow list (`tags: [a, # c` + newline + `  b]`): Go exit 2 `a comment sits inside a flow list` for merge-tags, remove-tags and normalize-tags; Python `merge-tags a --into z` writes `tags: [z, b]` (comment lost), `normalize-tags` moves the comment.

**(b) lone-CR files**
- CR-only concept `---\rtype: Concept\rdescription: d\rtags: [a, b]\r---\r# T\rbody\r`: `merge-tags`, `remove-tags`, `normalize-tags` exit 2 in Go with `handbook/zz.md: the key "tags" is not in the frontmatter`; Python exit 0 rewrites the file as LF (`merge-tags a --into z`: `---\ntype: Concept\ndescription: d\ntags: [z, b]\n---\n# T\nbody\n`).
- `verify` on it: Python exit 0 writes `---\ntype: Concept\ndescription: d\ntags: [a, b]\nverified:\n  - by: human:x\n    at: <NOW>\n---\n# T\nbody\n`; Go exit 0 writes `---\nverified:\n  - by: human:x\n    at: <NOW>\n---\n---\rtype: Concept\rdescription: d\rtags: [a, b]\r---\r# T\rbody\r`.
- `migrate --apply` on the same file (with `timestamp` and `status`): exit 0, file unchanged in both.
- a stray bare CR in the body of an LF file: Python turns it into LF on `merge-tags` and `verify` (`# T\nstray\nbody\n`), Go keeps it (`# T\rstray\nbody\n`); here Go is the better one.
- a stray CR inside the frontmatter (`description: d` + CR + `more`), `verify`: both exit 2 `frontmatter does not parse: could not find expected ':' (line N, column 1)`; N is 5 in Python and 4 in Go.

**(c) one refused file aborts the whole run**
- 60 stress files (`go/internal/yamlpatch/testdata/stress`) copied into a bundle `st/`, `--where "path ~ st/"`: `merge-tags a --into z --apply`: Python exit 0 wrote 15 files, Go exit 2 wrote 0 (`st/15-anchors-aliases.md: the value of a key carries an anchor, an alias or an explicit tag`); `remove-tags a --apply`: 15 vs 0; `normalize-tags --apply`: 14 vs 0.
- With `st/15` taken out, Go still refuses `st/48-flow-tags-inline-comment.md` (`a comment sits inside a flow list`) and `st/51-flow-mapping-root.md` (`the frontmatter is a flow mapping`): 3 refused files for normalize-tags, merge-tags and remove-tags.
- `migrate mg --apply` with `a-ok.md`, `b-refused.md` (`timestamp: &t ...`), `c-ok.md`: Python exit 0, `migrate: migrated 3 file(s), 0 unresolved`, 3 files written; Go exit 2 `mg/b-refused.md: the value of a key carries an anchor, an alias or an explicit tag`, 0 files written.
- Python only skips and lists files it cannot parse (`unparseable    handbook/broken-yaml.md  (... — skipped)`) and carries on.
- None of the four production catalogues triggered a refusal (`verify` over 450 concepts, `merge-tags`, `remove-tags`, `migrate`: no exit other than 0).

**(d) `verify` on non-UTF-8 stored text**
- Concept with `# T \xff\xfe` and a trailing `\xc3`, `verify handbook/zz --by human:x`: Python exit 0 `verified handbook/zz by human:x at <ts>`, the file tail becomes `# T \xef\xbf\xbd\xef\xbf\xbd\n\nSee [a](b.md) and <size> here. \xef\xbf\xbd\n`; Go exit 2 `the stored text is not valid UTF-8`, file unchanged.
- `sync-insert` with such a consumer: exit 4 `not valid UTF-8: handbook/zz.md` in both.
- merge-tags, remove-tags, normalize-tags, migrate, fix-xml-tags, fix-crosslinks, reindex, rename and archive leave such a file unchanged in both.

**(e) formatting kept by Go where ruamel normalises**
- Production copies, `verify` on all 450 concepts: 426 byte-equal, 24 differ; the 24 are exactly the files whose frontmatter has an inline `generated: { by: ..., at: ... }` (24 files, counted separately). Example: Python `generated: {by: claude-code/claude-opus-5-5, at: 2026-10-13T19:04:51+02:00}`, Go `generated: { by: claude-code/claude-opus-5-5, at: 2026-10-13T19:04:51+02:00 }`.
- `verify` on stress 18 (`verified:` then `- by: human:a` and `  at: 2026-01-01T00:00:00Z` at column 0): Go keeps column 0 (`- by: human:x` / `  at: <NOW>`), Python re-indents to `  - by: human:a` / `    at: ...`.
- `migrate` on `timestamp: 2026-10-06` followed by `  # indented comment under the key`: Go keeps the comment (under `  at: ...`), Python drops it; on `generated: { by: human:a, at: 2026-10-06T00:00:00Z }` Go keeps the spacing, Python writes `{by: human:a, at: 2026-10-06T00:00:00Z}`.
- `normalize-tags` on a list holding `null` (`[1, true, null, 2026-01-01, 1.5, 0x1f, .inf, ~, yes, No]`): Go `- null`, Python `- ` (empty); on `["\u00e9", "\U0001F600", x]`: Go keeps the escapes, Python writes `- "é"` and `- "😀"`; on `[<U+FEFF>a]`: Go writes the raw character, Python `- "\uFEFFa"`; on `[a,\r\n b]` in a CRLF file: Go keeps CRLF, Python writes LF.

**(f) tab after the colon and TOML wording**
- `verify` on a frontmatter line `note:` + TAB + `x`: Python exit 2 `frontmatter does not parse: found character '\t' that cannot start any token (line 3, column 6)`; Go exit 0 and writes the `verified` entry; afterwards Python's `check` flags the file with the same text, Go's does not.
- `migrate recipes` with `.okf.toml` = `git_authors = [`: both exit 2; Python `ERROR: <ROOT>/.okf.toml is not valid TOML: Invalid value (at end of document)`, Go `ERROR: <ROOT>/.okf.toml is not valid TOML: unexpected EOF; expected value (at line 1, column 16)`.

**Identical in both**

- S12, the `source=` of sync blocks after `rename` or `archive` of the owner: the absolute marker is rewritten in both (`source=/kc-gov/ownership-renamed.md`, `source=/_archive/kc-gov/ownership.md`), the visible callout line is not; relative, bare, `../` and no-`.md` `source=` values stay `malformed` or `source-missing` before and after and are never rewritten; `sync-status`, `sync-update`, `check` and CRLF consumers behave the same afterwards.
- S4a `sync-insert` on CRLF consumers (LF or CRLF owner; tails `\r\n\r\n\r\n`, lone `\r`, `\r\r\n`, CRLF without final newline): byte-equal, mixed endings in both (`...md).\r\n\n<!-- okf:sync id=ownership-rule ...`).
- `sync-insert` edge cases (24: no final newline, no frontmatter, empty file, BOM, broken YAML, reserved, archive and ctx consumers, absolute and `..` paths, self owner, duplicate ids, `--json`): identical including exit code and stderr.
- Canon payload shapes (14: blank lines, tabs, empty, injected markers, unicode, CR, CRLF, NUL, a 20 kB line, table, code fence) through sync-export, sync-insert, sync-status, sync-update and `--json`, and 36 Unicode whitespace code points at the payload edges: identical.
- `sync-status` and `sync-update`: 34 marker shapes x 7 commands, 18 target forms x 3 commands and 32 duplicate and position cases are identical except the CRLF-inside-LF case of entry 1.
- 118 error-path runs of sync-*, verify, migrate, merge-tags, remove-tags and normalize-tags: 114 identical, 4 differ only in the YAML parse-error wording line of `handbook/broken-yaml.md`.
- `migrate`: 60 citation-section shapes (dry-run JSON), no git, untracked file, bad `git_authors`, target forms: identical; 30 frontmatter shapes and the 60 stress files are byte-equal or formatting-only apart from the refusals under (a); 58 of the 60 stress files are byte-equal.
- `tags` and registry: 38 `tags --register` and listing cases and 64 `registry convert` runs (both directions, dry-run and apply, 16 TAGS.md shapes) are identical apart from the network-error text pinned by the golden; `verify --by` with 39 awkward actor strings writes a valid file whose new entry carries the string unchanged.
- Production copies (own copy of the frozen data): `normalize-tags`, `migrate`, `sync-status`, `sync-update` as `--json` are byte-equal; `migrate --apply` (1 file), `merge-tags` (66 and 65 files) and `remove-tags` (66 files) give byte-equal trees; `normalize-tags --apply` and `sync-update --apply` have nothing to write in both; none of the four catalogues holds a CRLF or lone-CR concept.

## 3. Block 2: corpus minimal-diff run of the production frontmatter writer (criteria 9 to 13)

Method of `SPIKE-yaml-roundtrip.md` (ops op0 to op4, the ruamel-independent `intended()` data check, the line-range `min` measure, the self-test that damages accepted outputs), applied to the production writer of OKFT-5lq2 instead of the spike's strategy (c): the corpus driver `go/internal/yamlpatch/corpus` (shipped by OKFT-5lq2, `yamlpatch.SpikeOp` over the production edit set) writes `out/surgical/<op>/<rel>` and `status.json`, `ref.py measure --strategies surgical` measures them. The spike assets were used unchanged (71 files identical on the Mac and on devt; workspace commit `ef9b96d`, `git status` clean): `ref.py` sha256 `37b3cdde445dc6b2266a288e23ac2d141205ea604d0a091302bd4a4db6c6adfc`, `corpus-real.tar.gz` `945568ce5b4502e17614b41c0ba039ed9a9db60f40edf7d30b659b9a49a36152`, `run.sh` `78e3a8a34bfec4b8d5783e2b3c666ad008f3b9f00c130c4735f349285724e69c`. Only the writer under test changed; `--strategies surgical` only selects which `out/` directory is measured. The pass criterion is `minimal`; ruamel byte equality is shown for comparison and decides nothing. `ref.py report` cannot print its stress matrix without the two spike strategies, so the tables below come from `results.json` with the spike's layout. The `snapshot` step ran with `HOME` pointing at a scratch directory whose `Obsidian/Knowledge-Catalogue` is the frozen copy (`ref.py` hard-codes that path for the history corpus); the history bound is `HIST_HEAD` 71b54d06ed207e5e4881628577ddf53fa86dfe05 (774 commits, present in the frozen copy).

Snapshot counts (`corpus.json` of the run): `real` 674 with frontmatter (729 `.md`, 55 without), `hist` 8,655 blobs of which 567 equal a current file, 1,138 without frontmatter, 6,950 with (86 refused by ruamel, 6,864 usable), `stress` 60 (54 parseable). 7,538 usable files (674 + 6,864) enter the 100 % criterion; the 54 stress files are measured too.

Corpus as snapshotted (`corpus.json`):

- `hist`: bytes=37381367, identical_to_real=567, md_blobs=8655, no_frontmatter=1138, with_frontmatter=6950
- `real`: bytes=5710498, files_kc=674, md_total=729, no_frontmatter=55, with_frontmatter=674
- `stress`: with_frontmatter=60
- pins: `{"kc_git_head": "71b54d06ed207e5e4881628577ddf53fa86dfe05", "real": "frozen: corpus-real.tar.gz"}`

Parser agreement (files; `both_ok` = ruamel and the Go reader accept the file, `both_fail` = both refuse it, a one-sided result would be `go_fails_ruamel_ok` or `ruamel_fails_go_ok`):

| Set | ruamel (reference) | Go reader of the production writer |
|---|---|---|
| `real` | both_ok 674 | both_ok 674 |
| `hist` | both_fail 86, both_ok 6864 | both_fail 86, both_ok 6864 |
| `stress` | both_fail 6, both_ok 54 | both_fail 6, both_ok 54 |

### `real`: 674 files of the current catalogue (frozen `corpus-real.tar.gz`)

`n` = files on which the op applies according to ruamel. `ruamel min` = how often ruamel itself changes only the intended lines (comparison value). `byte` = output byte-equal to ruamel's. `min` = **minimal diff** (data as intended and diff confined to the lines of the op; the pass criterion). Percentages follow the numbers.

| Op | n | ruamel min | production writer byte | production writer min | declined | n/a | error | not minimal |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| op0 | 674 | 674 (100 %) | 674 (100 %) | **674 (100 %)** | 0 | 0 | 0 | 0 |
| op1 | 640 | 640 (100 %) | 638 (99.7 %) | **640 (100 %)** | 0 | 0 | 0 | 0 |
| op2a | 623 | 623 (100 %) | 623 (100 %) | **623 (100 %)** | 0 | 0 | 0 | 0 |
| op2b | 674 | 674 (100 %) | 674 (100 %) | **674 (100 %)** | 0 | 0 | 0 | 0 |
| op3 | 674 | 674 (100 %) | 674 (100 %) | **674 (100 %)** | 0 | 0 | 0 | 0 |
| op4 | 43 | 43 (100 %) | 43 (100 %) | **43 (100 %)** | 0 | 0 | 0 | 0 |

### `hist`: 6,864 historical versions (blobs of the catalogue history up to `HIST_HEAD` 71b54d06)

`n` = files on which the op applies according to ruamel. `ruamel min` = how often ruamel itself changes only the intended lines (comparison value). `byte` = output byte-equal to ruamel's. `min` = **minimal diff** (data as intended and diff confined to the lines of the op; the pass criterion). Percentages follow the numbers.

| Op | n | ruamel min | production writer byte | production writer min | declined | n/a | error | not minimal |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| op0 | 6864 | 4650 (67.7 %) | 4650 (67.7 %) | **6864 (100 %)** | 0 | 0 | 0 | 0 |
| op1 | 6655 | 4456 (67.0 %) | 4456 (67.0 %) | **6655 (100 %)** | 0 | 0 | 0 | 0 |
| op2a | 6427 | 4416 (68.7 %) | 4416 (68.7 %) | **6427 (100 %)** | 0 | 0 | 0 | 0 |
| op2b | 6864 | 4650 (67.7 %) | 4650 (67.7 %) | **6864 (100 %)** | 0 | 0 | 0 | 0 |
| op3 | 6864 | 4650 (67.7 %) | 4650 (67.7 %) | **6864 (100 %)** | 0 | 0 | 0 | 0 |
| op4 | 5525 | 4598 (83.2 %) | 4598 (83.2 %) | **5525 (100 %)** | 0 | 0 | 0 | 0 |

### `stress`: 54 parseable special cases (information only, rejection path is OKFT-5lq2's R-04)

`n` = files on which the op applies according to ruamel. `ruamel min` = how often ruamel itself changes only the intended lines (comparison value). `byte` = output byte-equal to ruamel's. `min` = **minimal diff** (data as intended and diff confined to the lines of the op; the pass criterion). Percentages follow the numbers.

| Op | n | ruamel min | production writer byte | production writer min | declined | n/a | error | not minimal |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| op0 | 54 | 37 (68.5 %) | 37 (68.5 %) | **54 (100 %)** | 0 | 0 | 0 | 0 |
| op1 | 27 | 20 (74.1 %) | 13 (48.1 %) | **24 (88.9 %)** | 3 | 0 | 0 | 0 |
| op2a | 48 | 35 (72.9 %) | 32 (66.7 %) | **46 (95.8 %)** | 2 | 0 | 0 | 0 |
| op2b | 54 | 38 (70.4 %) | 37 (68.5 %) | **53 (98.1 %)** | 1 | 0 | 0 | 0 |
| op3 | 52 | 36 (69.2 %) | 35 (67.3 %) | **51 (98.1 %)** | 1 | 0 | 0 | 0 |
| op4 | 5 | 3 (60.0 %) | 3 (60.0 %) | **5 (100 %)** | 0 | 0 | 0 | 0 |

File × op over `real` and `hist`: 42527, minimal: 42527 (100 %).


**Not-minimal files (criterion 11): 0.** No file, op or diff to list; no blocking finding for OKFT-5lq2 from this block. On `real` and `hist` the production writer declined, failed or skipped nothing (columns `declined`, `n/a`, `error` are 0). On `stress` (not part of criteria 9 and 10) it declined 7 op cells on shapes it refuses by design (R-04; op1 3, op2a 2, op2b 1, op3 1); a declined cell is not a minimal diff and not an error, and no stress cell is wrong or invalid (`not minimal` is 0 there too). The refusals of the production writer on such shapes are the subject of the entries D-02 to D-09.

**Self-test (criterion 12):** `ref.py selftest` damaged the accepted outputs of the production writer and the measure saw every damage: `750 accepted outputs; damage seen: Leerzeichen an fremder Zeile 745/745, falscher Wert 750/750, fremde Zeile entfernt 745/745, keine Änderung 750/750`.

Commands (devt, `OKFT_SOURCE` = the worktree, `WORK` = scratch): `ref.py snapshot WORK` (HOME trick above), `ref.py expected WORK`, `go run ./internal/yamlpatch/corpus -corpus WORK/corpus -out WORK/out` (from `go/`), `ref.py measure WORK --strategies surgical`, `ref.py selftest WORK`, all through `uv run --no-project --with-requirements cli/okf-cli.py python ref.py ...`.

## 4. Block 3: catalogue parity on frozen copies (criteria 14 to 17)

### 4.1 Setup

Copies per §1; `build-index` ran once per copy with its own implementation (Python on `py/`, Go on `go/`), then every case ran once per implementation on its own copy, under `unshare -rn`, `VOYAGE_API_KEY` unset, `LC_ALL=C.UTF-8 TZ=UTC COLUMNS=100 NO_COLOR=1`, copy path normalised to `<COPY>` in the output. Compared per case: exit code, stdout, stderr. Roots: `--root` = the Knowledge-Catalogue copy (668 concepts indexed; the mounted bundles `dev-okf`, `sproutling-okf`, `home-lab-wiki` are followed), the `sproutling-okf` copy (85 concepts indexed) and the `dev-okf` copy as a root of its own. With `dev-okf` as root its three files sit at the root, not in a bundle, so the index holds 0 concepts and every `find` has no hits (identical in both); the two `dev-okf` concepts are reached through the Knowledge-Catalogue (`find ... --where "path ~ dev-okf/"`, `check dev-okf`, `index dev-okf`). The semantic arm degrades the same way in both: `note: semantic arm skipped (embedding backend unavailable: VOYAGE_API_KEY not set) — lexical results only`.

### 4.2 Results

148 of 148 cases identical (exit code, stdout, stderr), 0 differences, so no parity entry (criterion 16). `check` exits 4 on the Knowledge-Catalogue copy (`1 VIOLATIONS`) and on `sproutling-okf` (`9 VIOLATIONS`), 0 on `dev-okf` (`OK — 0 violations`), the same in both. The two FTS databases hold the same rows: `docs` (668 / 85 / 0 rows) and `fts_meta` tables and the schema are equal. Cross-read: each implementation answered all 62 `find` cases on the index built by the other one, identically. The two copies were compared with the master after the run (`.fts/` and the three re-pointed symlinks excluded): no file differs, so the read commands wrote nothing but `.fts/`.

| Catalogue root | build-index | check | index | find | identical | different |
|---|---:|---:|---:|---:|---:|---:|
| KC | 1 | 9 | 42 | 32 | 84 | 0 |
| sproutling-okf | 1 | 4 | 20 | 18 | 43 | 0 |
| dev-okf | 1 | 4 | 4 | 12 | 21 | 0 |
| **total** | 3 | 17 | 66 | 62 | **148** | **0** |

**find queries on `KC`** (32; `--where` filter in the rows marked w):

| # | query / options | hits | exit |
|---|---|---:|---:|
| 01 | `okf --root <KC> find git` | 10 | 0 |
| 02 | `okf --root <KC> find worktree` | 10 | 0 |
| 03 | `okf --root <KC> find 'yaml frontmatter'` | 10 | 0 |
| 04 | `okf --root <KC> find okf` | 10 | 0 |
| 05 | `okf --root <KC> find tpic --limit 25` | 25 | 0 |
| 06 | `okf --root <KC> find 'docker compose'` | 10 | 0 |
| 07 | `okf --root <KC> find testing` | 10 | 0 |
| 08 | `okf --root <KC> find ruamel` | 0 | 0 |
| 09 | `okf --root <KC> find 'reverse proxy'` | 10 | 0 |
| 10 | `okf --root <KC> find Überblick` | 10 | 0 |
| 11 | `okf --root <KC> find '"git worktree"'` | 10 | 0 |
| 12 | `okf --root <KC> find 'git OR worktree'` | 10 | 0 |
| 13 | `okf --root <KC> find 'NOT git'` | 10 | 0 |
| 14 | `okf --root <KC> find c++` | 10 | 0 |
| 15 | `okf --root <KC> find dev-okf` | 10 | 0 |
| 16 | `okf --root <KC> find skills --breakdown` | 10 | 0 |
| 17 | `okf --root <KC> find git --json` | 10 | 0 |
| 18 | `okf --root <KC> find okf --include-topics` | 10 | 0 |
| 19 | `okf --root <KC> find okf --where 'type = SOP'` w | 10 | 0 |
| 20 | `okf --root <KC> find git --where 'path ~ version-control-git/'` w | 10 | 0 |
| 21 | `okf --root <KC> find worktree --where 'tag = git or tag = worktree'` w | 10 | 0 |
| 22 | `okf --root <KC> find testing --where 'type in (Convention, LessonLearned) and status = stable'` w | 10 | 0 |
| 23 | `okf --root <KC> find okf --where 'archived = true'` w | 2 | 0 |
| 24 | `okf --root <KC> find okf --where 'tier = unverified' --limit 5` w | 5 | 0 |
| 25 | `okf --root <KC> find git --where 'stale = false' --limit 5` w | 5 | 0 |
| 26 | `okf --root <KC> find claude --where 'generated.by ~ claude' --limit 5` w | 5 | 0 |
| 27 | `okf --root <KC> find just --where 'path ~ dev-okf/'` w | 1 | 0 |
| 28 | `okf --root <KC> find workspace --where 'path ~ dev-okf/'` w | 2 | 0 |
| 29 | `okf --root <KC> find Hüllen-Struktur --where 'path ~ dev-okf/'` w | 0 | 0 |
| 30 | `okf --root <KC> find release --where 'path ~ sproutling-okf/'` w | 10 | 0 |
| 31 | `okf --root <KC> find deployment --where 'path ~ sproutling-okf/ and type = SOP'` w | 10 | 0 |
| 32 | `okf --root <KC> find docker --where 'path ~ home-lab-wiki/'` w | 10 | 0 |

**find queries on `sproutling-okf`** (18; `--where` filter in the rows marked w):

| # | query / options | hits | exit |
|---|---|---:|---:|
| 01 | `okf --root <sproutling-okf> find release` | 10 | 0 |
| 02 | `okf --root <sproutling-okf> find deployment` | 10 | 0 |
| 03 | `okf --root <sproutling-okf> find 'canary beta'` | 10 | 0 |
| 04 | `okf --root <sproutling-okf> find migration` | 10 | 0 |
| 05 | `okf --root <sproutling-okf> find alembic` | 10 | 0 |
| 06 | `okf --root <sproutling-okf> find tenant` | 6 | 0 |
| 07 | `okf --root <sproutling-okf> find workflow` | 10 | 0 |
| 08 | `okf --root <sproutling-okf> find security` | 10 | 0 |
| 09 | `okf --root <sproutling-okf> find DSGVO` | 3 | 0 |
| 10 | `okf --root <sproutling-okf> find 'feature container'` | 10 | 0 |
| 11 | `okf --root <sproutling-okf> find Ezra` | 1 | 0 |
| 12 | `okf --root <sproutling-okf> find gate --limit 3` | 3 | 0 |
| 13 | `okf --root <sproutling-okf> find zzzqqq` | 0 | 0 |
| 14 | `okf --root <sproutling-okf> find release --json` | 10 | 0 |
| 15 | `okf --root <sproutling-okf> find deployment --breakdown` | 10 | 0 |
| 16 | `okf --root <sproutling-okf> find release --where 'type = Convention'` w | 6 | 0 |
| 17 | `okf --root <sproutling-okf> find gate --where 'path ~ workflows-and-procedures/'` w | 10 | 0 |
| 18 | `okf --root <sproutling-okf> find sicherheit --where 'path ~ security-and-compliance/ and archived = false'` w | 8 | 0 |

**find queries on `dev-okf`** (12; `--where` filter in the rows marked w):

| # | query / options | hits | exit |
|---|---|---:|---:|
| 01 | `okf --root <dev-okf> find konventionen` | 0 | 0 |
| 02 | `okf --root <dev-okf> find workspace` | 0 | 0 |
| 03 | `okf --root <dev-okf> find project.toml` | 0 | 0 |
| 04 | `okf --root <dev-okf> find just` | 0 | 0 |
| 05 | `okf --root <dev-okf> find referenz` | 0 | 0 |
| 06 | `okf --root <dev-okf> find repo` | 0 | 0 |
| 07 | `okf --root <dev-okf> find worktrees` | 0 | 0 |
| 08 | `okf --root <dev-okf> find beans` | 0 | 0 |
| 09 | `okf --root <dev-okf> find zzzqqq` | 0 | 0 |
| 10 | `okf --root <dev-okf> find index` | 0 | 0 |
| 11 | `okf --root <dev-okf> find konventionen --json` | 0 | 0 |
| 12 | `okf --root <dev-okf> find workspace --where 'type = Convention'` w | 0 | 0 |

check/index cases per catalogue (all identical in stdout, stderr and exit code):

- `KC`: `build-index`, `check`, `check-json`, `check-strict`, `index`, `index-json`, `index-full`, `index-full-json`; plus 44 per-bundle/mounted-bundle cases (`index[:--full] <bundle>`, `check[ --json] <mounted bundle>`)
- `sproutling-okf`: `build-index`, `check`, `check-json`, `check-strict`, `check-types-kc`, `index`, `index-json`, `index-full`, `index-full-json`; plus 16 per-bundle/mounted-bundle cases (`index[:--full] <bundle>`, `check[ --json] <mounted bundle>`)
- `dev-okf`: `build-index`, `check`, `check-json`, `check-strict`, `check-types-kc`, `index`, `index-json`, `index-full`, `index-full-json`

exit codes of check: KC/check rc=4, sproutling-okf/check rc=4, dev-okf/check rc=0
cross-read: 62 of 62 find cases identical on the other implementation's index
fts: {"KC": {"tables_equal": {"docs": true, "fts_meta": true}, "schema_equal": true, "rows": {"docs": 668, "fts_meta": 4}}, "sproutling-okf": {"tables_equal": {"docs": true, "fts_meta": true}, "schema_equal": true, "rows": {"docs": 85, "fts_meta": 4}}, "dev-okf": {"tables_equal": {"docs": true, "fts_meta": true}, "schema_equal": true, "rows": {"docs": 0, "fts_meta": 4}}}


### 4.3 Live trees untouched (criterion 17)

Checksum manifest (sha256 of every file, symlink targets, over the three catalogues, `home-lab-wiki` and the parent `.git` dirs: 8,252 files, 3 symlinks, 224,038,905 bytes) taken at 2026-10-16T14:46:45Z before the copy and again at 2026-10-16T16:15:28Z after all runs: the two manifest files are identical (sha256 `1883579f8dea9ce628164e6cac6751f40e1c246d76ed460d0d8b66dde0e3b296`). The live trees were only read (rsync source, manifest); no git command touched them.

## 5. Block 4: startup (criteria 18 to 20)

### 5.1 No Python on PATH (criterion 18)

`env -i PATH=<dir without python or uv> go/bin/okf --root <Knowledge-Catalogue copy> find git`: exit 0, 81 stdout lines, 10 hits, stderr `note: semantic arm skipped (embedding backend unavailable: VOYAGE_API_KEY not set) — lexical results only`; the same with an empty directory as PATH and under `unshare -rn` (stdout identical). The PATH directory holds symlinks to the `/usr/bin` tools and no `python*` and no `uv*` entry; `env -i PATH=<that dir> sh -c 'command -v python python3 uv'` finds none of them.

### 5.2 Medians (criteria 19 and 20)

Method: `hyperfine 2.0.0` (installed with mise, run through its binary path; see §6), `-N` (no shell), 3 warmup runs, 30 runs per command, two rounds, `VOYAGE_API_KEY` unset, inside `unshare -rn`. Knowledge-Catalogue copy `time/` made from the master, FTS index built with the Python CLI (the Go binary reads it identically, §4.2), the 26 MB `.tagvec/tag_vectors.sqlite` of the production catalogue kept. Exit code of every run 0. Idle machine (§1). Cell: median (min–max).

| Command | Round | Runs | Go binary | Python direct | Python `uv run --script` | median Go ≤ Python |
|---|---|---|---|---|---|---|
| `okf --help` | 1 | 30 | 1.32 ms (1.21 ms–1.54 ms) | 46.9 ms (44.5 ms–49.7 ms) | 49.8 ms (48.6 ms–52.6 ms) | yes (36× / 38×) |
| `okf --help` | 2 | 30 | 1.40 ms (1.27 ms–1.72 ms) | 46.9 ms (44.9 ms–49.6 ms) | 50.3 ms (49.0 ms–53.6 ms) | yes (33× / 36×) |
| `okf --root <KC copy> find git` | 1 | 30 | 17.1 ms (16.1 ms–17.8 ms) | 145.5 ms (143.0 ms–149.8 ms) | 150.2 ms (146.6 ms–154.6 ms) | yes (9× / 9×) |
| `okf --root <KC copy> find git` | 2 | 30 | 17.1 ms (15.4 ms–18.1 ms) | 145.5 ms (142.8 ms–156.9 ms) | 149.8 ms (147.5 ms–152.3 ms) | yes (9× / 9×) |

Command lines: Go `go/bin/okf`; Python direct `/tmp/k-ev/pyenv/bin/python cli/okf-cli.py` (Python 3.14.6); Python uv `uv run --script cli/okf-cli.py` (uv 0.12.10). Peak memory (median, round 1) of `find git`: Go 55 MiB, Python 212 MiB.

Early number of OKFT-y1zl (commit `95b67b2`, hyperfine, 2 warmups + 10 runs, Knowledge-Catalogue copy in `/tmp` with FTS index built, `VOYAGE_API_KEY` unset, host devt), quoted: `find git` go 3.7 ms, python `uv run --script` 61.9 ms, python wrapper 67.7 ms; `--help` go 1.3 ms, uv 53.5 ms, wrapper 64.9 ms. Reference of D10 (Mac, 2026-10-12): `--help` 0.07 s, `find` 0.87 s.

Why the final `find` numbers are higher than the early ones, measured: the final copy is the production Knowledge-Catalogue with its 26 MB `.tagvec/tag_vectors.sqlite`. With `.tagvec` moved aside in the scratch copy (30 runs, same method, third block of the log) the medians come close to the early values: Go 3.9 ms, Python direct 54.7 ms, Python uv 60.1 ms (early: 3.7 ms Go, 61.9 ms uv, 67.7 ms wrapper; the early Python values were measured through the uv and wrapper launchers). The extra time with `.tagvec` is therefore the handling of that file, in both implementations. The binary stays faster than Python in every case: `--help` by a factor of 35 to 38, `find git` by a factor of 8.5 to 8.8 (with `.tagvec`) and 14 to 15.5 (without).

## 6. Observations outside the criteria

1. **Argument order in R-01 and criterion 18.** `okf find git --root <catalogue>` (the literal text of R-01 and AC 18) exits 2 with `unrecognized arguments: --root ...` in the Python CLI and in the Go binary alike: `--root` is a global option and goes before the command (`okf --root <catalogue> find git`, as `just go-find-smoke` does). The evidence uses that order. The requirement text should say the same.
2. **hyperfine.** The leaf says hyperfine is not installed; devt has `hyperfine 2.0.0` under mise (`mise exec hyperfine@2.0.0 -- hyperfine`, not activated by default), so hyperfine was used instead of `time`.
3. **Go test files.** R-05 allows test files for YAML patch, ranking and link scan; the line also carries `go/internal/fts/ranking_test.go` (FTS ranking tests, OKFT-y1zl) beside `yamlpatch`, `linkscan` and `rank`. K added none.
4. **`dev-okf` as a root.** Its three files sit at the root and not in a bundle, so `okf --root dev-okf` indexes 0 concepts in both implementations (§4.1).
5. **Production catalogues have findings.** `check` exits 4 on the Knowledge-Catalogue and on `sproutling-okf` in both implementations; the findings (and their exit code) are identical.
6. **Harness artefacts of the sweeps** (a shared sibling directory of two copies once made a `rename` link count differ; with isolated copies, as in the final runs, Python and Go print `rewrote 19 inbound link(s) in 15 file(s)` alike) are listed in the sweep blocks of §2.6 and are not deviations.
7. **Not run:** `build-semantic-index` and `install` against real services (network and agents), the MCP server, Homebrew and zsh completion (proven by OKFT-qg0o and siblings, not repeated, as the leaf says).

## 7. Reproduction

```text
# build and golden (worktree of the chore line; Python baseline, Go, Go with a python-free child PATH)
just go-build
just golden
just golden --cmd go/bin/okf
just golden --cmd "env PATH=<dir with symlinks to /usr/bin tools except python*, uv*, pip*> $PWD/go/bin/okf"

# corpus (devt; spike assets unchanged, OKFT_SOURCE = the worktree, WORK = scratch dir)
uv run --no-project --with-requirements cli/okf-cli.py python ref.py snapshot WORK     # HOME=<dir holding Obsidian/Knowledge-Catalogue = frozen copy>
uv run --no-project --with-requirements cli/okf-cli.py python ref.py expected WORK
(cd go && go run ./internal/yamlpatch/corpus -corpus WORK/corpus -out WORK/out)
uv run --no-project --with-requirements cli/okf-cli.py python ref.py measure WORK --strategies surgical
uv run --no-project --with-requirements cli/okf-cli.py python ref.py selftest WORK

# parity: frozen copies per implementation, then per case
env -u VOYAGE_API_KEY unshare -rn okf --root <copy> build-index | check | index | find <query> [--where ...]

# startup
env -u VOYAGE_API_KEY unshare -rn hyperfine -N --warmup 3 --runs 30 "go/bin/okf --help" "<python direct> --help" "uv run --script cli/okf-cli.py --help"
env -u VOYAGE_API_KEY unshare -rn hyperfine -N --warmup 3 --runs 30 "go/bin/okf --root <copy> find git" "<python direct> --root <copy> find git" "uv run --script cli/okf-cli.py --root <copy> find git"
```
