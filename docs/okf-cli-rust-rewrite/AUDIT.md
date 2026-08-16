---
type: Analysis
title: "okf-cli + okf-MCP — Reifegrad-Audit vor dem Rust-Rewrite"
description: "Prüfkatalog in 11 Achsen und Bewertung von CLI und MCP-Oberfläche, plus Portierungsanalyse Python→Rust unter der Direktive Capability-Gleichheit statt Byte-Gleichheit."
tags:
  - okf-cli
  - rust
  - audit
---

# okf-cli + okf-MCP — Reifegrad-Audit vor dem Rust-Rewrite

Gegenstand: `cli/okf-cli.py` (4280 LOC, 23 Kommandos), `mcp/okf_mcp.py` (219 LOC, 14 Tools), `cli/embeddings/build_tagvec.py` (431 LOC). Stand `1eea173`, Testsuite 548 Tests grün (55.9 s).

## Zwei Rahmensetzungen des PO (2026-08-09)

**R1 — Der MCP-Server ist Teil des Lieferumfangs.** Er ist die agentenseitige Oberfläche und wird üblicherweise mitausgeliefert. Damit ist er Prüfgegenstand (Achse A11), nicht bloß Konsument der CLI — und er darf nicht in Python zurückbleiben, sonst löst der Rewrite das Distributionsproblem nur zur Hälfte.

**R2 — Verhaltensgleichheit auf Capability-Ebene, keine sklavische Portierung.** Maßgabe ist, dass eine Fähigkeit im Rust-Binary erhalten bleibt, nicht dass eine Ausgabe Byte für Byte identisch ist. Wo Rust eine bessere Lösung hat, wird sie genommen.

## Prüfkatalog

Elf Achsen, an denen ein Werkzeug gemessen wird, das von Menschen **und** Agenten benutzt wird. Jede Achse hat ein Kriterium, das im Rewrite als Akzeptanzkriterium taugt.

| # | Achse | Kriterium |
|---|---|---|
| A1 | Verb-Grammatik | Jedes Kommando ist `<verb>` oder `<verb>-<objekt>`; kein Kommando trägt mehr als einen Modus; Objekte mit mehreren Verben sind Subkommando-Gruppen. |
| A2 | Scope-Mechanik | Der Geltungsbereich wird über **genau einen** Mechanismus ausgedrückt, nicht über vier. |
| A3 | Mutations-Polarität | Alle schreibenden Kommandos haben dieselbe Default-Richtung und dasselbe Flag-Paar dafür — in CLI **und** MCP. |
| A4 | Flag-Vokabular | Gleicher Name = gleiche Bedeutung über alle Kommandos; Kurzformen für die frequenten Flags; einheitliche Defaults. |
| A5 | Exit-Code-Kontrakt | Nutzungsfehler, Sachbefund und interner Fehler haben unterscheidbare Codes; dokumentiert und getestet. |
| A6 | Stream-Disziplin | Nutzdaten auf stdout, Diagnose auf stderr, ausnahmslos; JSON-Modus hält stdout parse-rein. |
| A7 | Maschinenlesbarkeit | Jedes lesende Kommando kann `--json`; alle Antworten teilen einen versionierten Envelope; Exit-Code und JSON widersprechen sich nie. |
| A8 | Selbstdokumentation | Kommandoliste, Flag-Hilfen und Onboarding werden aus dem Parser gerendert; ein undokumentiertes Kommando ist nicht mergebar. |
| A9 | Fehler- und Erfolgsmeldungen | Einheitliches Präfix-Schema; jede Meldung nennt Ursache **und** Remedy; jeder Dry-run nennt den Befehl, der ihn ausführt. |
| A10 | Nebenwirkungsfreiheit im Fehlerfall | Ein Tippfehler erzeugt niemals Dateien, Verzeichnisse oder Netzwerkverkehr. |
| A11 | MCP-Oberfläche | Deklariertes Tool-Schema entspricht dem tatsächlichen Rückgabewert; das Lese-Set der CLI ist vollständig exponiert; Mutations-Polarität und Degradationssignale kommen strukturiert, nicht als Fließtext. |

## Bewertung

| Achse | Urteil | Belege |
|---|---|---|
| A1 | 🟡 teilweise | Grammatik überwiegend sauber. Ausreißer: `tags` trägt vier Modi (Volldump, Fuzzy-Suche, `--register`, `--validate`). |
| A2 | 🔴 verletzt | Vier Mechanismen: Positional `target` (check, fix-crosslinks, fix-xml-tags, reindex, wikilinks), Positional `bundle` (index, log, visualize), Flag `--scope` (find, list, recent, merge-tags, normalize-tags, remove-tags), Flag `--scan-root` (refs, rewrite-path). |
| A3 | 🔴 verletzt | Drei Polaritäten: `--apply` schreibt (merge-tags, normalize-tags, remove-tags, rename), `--check` liest nur (fix-crosslinks, fix-xml-tags, reindex, rewrite-path), `tags --register` schreibt sofort und ungefragt. Setzt sich in den MCP fort: `okf_rename` hat `apply=False`, `okf_reindex` schreibt ohne Vorschau. |
| A4 | 🟡 teilweise | Keine einzige Kurzform in 23 Kommandos. `--limit` default 10 (find, recent) vs. 8 (tags). `--full` bedeutet bei `index` je nach Anwesenheit von `bundle` zwei verschiedene Dinge. `--force` bedeutet bei `reindex` „Multi-Section flatten", bei `rename` „Ziel überschreiben + Ambiguität akzeptieren". |
| A5 | 🔴 verletzt | Exit 1 trägt drei Bedeutungen: Nutzungsfehler (`list` ohne Filter), Sachbefund (`check`, `tags --validate`), Nichtgefunden (`read`, `toc`). `refs` weicht als einziges auf Exit 2 aus. `find ""` und `index <nichtexistent>` liefern Exit 0. |
| A6 | 🟢 erfüllt | Konsequent umgesetzt und im MCP dokumentiert ausgenutzt (`mcp/okf_mcp.py:73-98`). Eine der stärksten Eigenschaften. |
| A7 | 🔴 verletzt | `--json` nur bei 6 von 23 (check, index, list, recent, refs, wikilinks). Fehlt bei `find` — dem Kommando, das ein Agent am häufigsten ruft. Kein Envelope: `list`/`recent` liefern bares Array, die anderen vier je ein eigenes Objekt-Schema. Keine `schema_version`. |
| A8 | 🟢 erfüllt | Vorbildlich. `_sub()` (`cli/okf-cli.py:4031`) erzwingt Summary und Purpose-Group als Pflicht-Positionals, die Summary erreicht beide Hilfeebenen, der gruppierte Überblick wird aus den registrierten Parsern gerendert (Z. 4045), `CommandHelpConformance` (`test_okf_cli.py:3380`) macht ein undokumentiertes Kommando unmergebar. |
| A9 | 🔴 verletzt | Fünf Präfix-Stile: `ERROR: `, `not found: `, `not a directory: `, `refs: target not found: `, `(error: …)`. Nur `rename` nennt den Folgebefehl (Z. 3950). Programmname mal `okf-cli`, mal `okf-cli.py`. |
| A10 | 🔴 verletzt | `visualize <tippfehler>` legt `<root>/<tippfehler>/assets/viz.html` an — verifiziert. `tags --register` mutiert TAGS.md ohne Bestätigung und löst einen Ollama-Call aus — verifiziert. |
| A11 | 🔴 verletzt | `okf_find` deklariert `-> list`, liefert `str` — verifiziert. `recent` ist als einziges Lese-Kommando nicht exponiert. Degradationen kommen bei Nicht-JSON-Tools als Fließtext vor die Nutzdaten geklebt (`run_okf`, Z. 96-97) statt als Feld. `_FLAGS`/`_BOOL_FLAGS` sind global über alle Kommandos geteilt, mit einem im Code dokumentierten Kollisionsrisiko (Z. 40-48). |

Gesamtbild: **innen reif, außen uneinheitlich**. Retrieval-Architektur, Degradationsdisziplin, Selbstdokumentation und Testabdeckung liegen deutlich über dem Üblichen. Die Verstöße sitzen vollständig in der Oberfläche — also in genau dem Teil, den der Rewrite ohnehin neu schreibt.

## 1. Bugs

| Bxx | Schwere | Beschreibung | Empfehlung | Status |
|---|---|---|---|---|
| B01 | medium | `index <nichtexistentes-bundle>` gibt `# <name>` aus, Exit 0 — ein Tippfehler sieht aus wie ein leeres Bundle. `cmd_check` hat den Fix bereits (`cli/okf-cli.py:3446`), `cmd_index` nicht. | Bundle-Existenz vor der Ausgabe prüfen, Exit ≠ 0. | 🟣 |
| B02 | medium | `visualize <nichtexistentes-bundle>` **erzeugt** `<root>/<name>/assets/` und schreibt `viz.html (0 nodes, 0 edges)`. Ein Tippfehler mutiert den Katalog. | Existenz als Vorbedingung; kein `makedirs` auf unvalidierten Pfad. | 🟣 |
| B03 | medium | `okf_find` deklariert im Tool-Schema `-> list`, liefert tatsächlich `str` (`find` hat `supports_json=False`, `run_okf` gibt Text zurück). Der Agent bekommt ein Schema, das eine Liste verspricht, und Fließtext geliefert. | Fällt mit I04 + I12 weg: `find` bekommt strukturierte Ausgabe, das Tool-Schema wird aus dem Typ generiert statt handdeklariert. | 🟣 |
| B04 | low | `find ""` gibt `(empty query)` auf **stdout**, Exit 0. Nutzungsfehler nicht von „nichts gefunden" unterscheidbar. | stderr + Exit-Code. | 🟣 |
| B05 | low | `tags --register X --validate Y` führt `--register` aus und ignoriert `--validate` still, Exit 0. Kein Mutual-Exclusion-Gate zwischen den vier Modi. | Modi als echte Subkommandos trennen (I01). | 🟣 |
| B06 | low | `recent` ist das einzige reine Lese-Kommando der CLI, das der MCP nicht exponiert. Die acht anderen Nicht-Exponierten sind Mutationen bzw. `log`/`visualize` und damit erklärbar CLI-only. | Als Tool ergänzen. | 🟣 |

## 2. Improvements

| Ixx | Beschreibung | Nutzen | Empfehlung | Status |
|---|---|---|---|---|
| I01 | `tags` in `tags list` / `tags find` / `tags register` / `tags validate` auftrennen. | Beseitigt B05 strukturell, macht `--singletons`/`--limit` eindeutig zuordenbar, macht `register` als Mutation sichtbar. | clap-Subkommando-Gruppe. | 🟣 |
| I02 | Scope auf **einen** Mechanismus vereinheitlichen: durchgängig optionales Positional `[TARGET]`. | A2. Wer `check okf` kann, kann dann auch `find … okf`. | `--scope`/`--scan-root` nicht mitportieren. | 🟣 |
| I03 | Eine Mutations-Polarität in CLI und MCP: dry-run by default, `--apply`/`apply=true` schreibt. | A3. Heute schreibt die gefährlichere Hälfte (`fix-*`, `reindex`, `rewrite-path`, `tags --register`, `okf_reindex`) ungefragt. | Einheitlich, ohne Ausnahme. | 🟣 |
| I04 | Globales `--json` statt sechs Einzelflags, gemeinsamer Envelope `{schema_version, command, data, notes[]}`. | A7 + A11. Ein Agent parst eine Form statt sechs. `find --json` wird möglich. `notes[]` nimmt die Degradationen auf, die heute als Fließtext vorgeklebt werden. | Envelope-Version ab `1`. | 🟣 |
| I05 | Kurzformen für die frequenten Flags: `-l/--limit`, `-t/--type`, `-T/--tag`, `-n/--dry-run`, `-j/--json`, `-r/--root`, `-v/--verbose`. | A4. Interaktive Nutzung. | Nur wo global eindeutig. | 🟣 |
| I06 | Fehler-Präfixe vereinheitlichen: `okf: error: <ursache>` + Zeile `hint: <remedy>`. | A9. Ein Agent kann Fehlerklassen mustern. | Ein Konstruktor für alle Ausgänge. | 🟣 |
| I07 | Jeder Dry-run endet mit der Zeile, die ihn ausführt (`rename` macht das bereits, Z. 3950). | A9. | Gemeinsame Renderfunktion. | 🟣 |
| I08 | `--limit`-Default vereinheitlichen (10 statt 10/10/8); `--full` bei `index` in zwei benannte Flags auftrennen. | A4. Kontextabhängige Flag-Bedeutung ist in `--help` nicht darstellbar. | — | 🟣 |
| I09 | Exit-Code-Kontrakt festschreiben und testen: `0` Erfolg, `1` Sachbefund, `2` Nutzungsfehler, `3` interner Fehler. | A5. Macht die CLI in Skripten und CI verwendbar. | Ein Test pro Code. | 🟣 |
| I10 | Programmname konsequent `okf` in allen Meldungen und Hilfetexten, aus einer Konstante. | Sonst geben Fehlermeldungen nicht-ausführbare Befehle aus. | — | 🟣 |
| I11 | `fzf` als Laufzeitabhängigkeit entfernen (`cli/okf-cli.py:345`). | Genau das Distributionsproblem, das der Rewrite löst. | Fällt in Rust ohnehin weg (`nucleo-matcher` in-process). | 🟣 |
| I12 | **MCP als Subkommando desselben Binaries** (`okf mcp serve`), gegen die interne API statt gegen einen Subprozess. | Der größte struktureller Gewinn des Rewrites. Streicht `build_argv`/`run_okf` samt Argument-Marshalling, dem dokumentierten `_FLAGS`-Kollisionsrisiko (Z. 40-48), dem Textparsing der Rückgabe und dem `python3`-Subprozess pro Tool-Call. Ein Artefakt statt zwei, eine Installation statt zwei. | `rmcp` (offizielles Rust-SDK) mit `#[tool_router]`/`#[tool]`. | 🟣 |
| I13 | Tool-Schemata aus Rust-Typen generieren (`schemars::JsonSchema`) statt handdeklarieren. | Beseitigt B03 als Klasse: ein falscher Rückgabetyp wird zum Compile-Fehler statt zu einem irreführenden Schema. Derselbe Single-Source-Trick, den `_sub()` heute für die CLI-Hilfe leistet — dann auch für den MCP. | — | 🟣 |
| I14 | `MAX_OUTPUT_CHARS` (120 k) vor der Serialisierung greifen lassen, nicht danach, und statt eines Fehlers eine gekürzte Antwort mit `truncated: true` und Restzahl liefern. | Heute wird die volle Arbeit geleistet und dann verworfen; der Agent bekommt gar nichts. In-Process ist die Trefferzahl vorher bekannt. | — | 🟣 |

## 3. Questions

| Qxx | Hintergrund | Relevanz | Frage | Status |
|---|---|---|---|---|
| Q01 | Unter R2 ist die Verifikationsfrage schärfer, nicht lockerer: eine Suite, die auf konkrete Ausgaben assertiert, taugt als Fixpunkt nur, solange Byte-Gleichheit gilt. Genau die wurde aufgegeben. | Entscheidet, ob der Rewrite verifizierbar ist oder ein Vertrauensvorschuss. Die 548 Tests sind heute die eigentliche Spec — Rust erbt sie nicht. | Wie wird Capability-Gleichheit **geprüft**? Vorschlag: pro Kommando ein Capability-Kontrakt in der SPEC (was muss wahr sein, nicht wie sieht es aus) und eine sprachneutrale Suite, die beide Binaries als Subprozess fährt. | 🟣 |
| Q02 | Der `plugin/`-Ordner. Faktisch leer (0 Bytes, nie in git); die index-map behauptet ein TypeScript-Skeleton. Ursprungszweck laut PO: Schaltbarkeit der Erweiterungen gegenüber OKF v0.1. | Wäre eine dritte Konsumentenschicht neben CLI und MCP. | Im Scope des Rewrites, oder vorher klären/löschen? | 🟢 → [D05/D06](./DECISIONS.md): Config-Profil in `.okf.toml` statt Plugin-System; `plugin/` entfällt (T09). Das Binary kennt zusätzlich beide Store-Modelle. |
| Q03 | Der MCP wird mitausgeliefert (R1). Heute `stdio` via `uv run --with mcp<2`. | Bestimmt Packaging und Konfigurationsformat der `.mcp.json`-Einträge. | Bleibt `stdio` der einzige Transport, oder soll das Binary auch HTTP/SSE können? | 🟢 → [D07](./DECISIONS.md): stdio-only in v1; bei `rmcp` ist der Transport von den Tool-Definitionen getrennt, HTTP später additiv. |

## 4. Tasks

| Txx | Prio | Aufgabe | Status |
|---|---|---|---|
| T01 | hoch | B01 und B02 **in Python** fixen, bevor der Rewrite startet — Verhaltensfehler, keine Oberflächenfragen, würden sonst mitportiert. | 🟣 |
| T02 | hoch | Oberflächen-SPEC schreiben, die I01–I14 zu **einer** Kommando- und Tool-Grammatik zusammenzieht, CLI und MCP gemeinsam. Das ist der Fixpunkt des Rewrites, nicht die Python-Datei. | 🟣 |
| T03 | hoch | Q01 beantworten und die Verifikationsstrategie aufsetzen, bevor die erste Rust-Zeile entsteht. | 🟣 |
| T04 | mittel | Capability-Kontrakte aus der bestehenden Suite destillieren: die 548 Tests sagen, *was* garantiert ist — das gehört in die SPEC, bevor der Code, der es beweist, ersetzt wird. | 🟣 |
| T05 | niedrig | Die drei Regex-Stellen mit Lookaround/Backreference (Z. 1837, 2717, 3008) als isolierte Portierungseinheiten behandeln. Unter R2 entschärft: freie Wahl zwischen `fancy-regex` und Handscanner. | 🟣 |

## 5. Decisions

| Dxx | Hintergrund | Entscheidung | Empfehlung | Status |
|---|---|---|---|---|
| D01 | Ob der semantische Arm Python braucht. | **Nein.** Kein Modell läuft je im Prozess; beide Embedding-Pfade sind HTTP-Clients. Siehe Portierungsanalyse. | Rust-Rewrite ohne jeden Python-Anteil. | 🟢 |
| D02 | Der Rewrite kann die heutige Oberfläche spiegeln oder auf die neue Grammatik ziehen. | Offen. | Grammatik ziehen. Sie wird ohnehin neu geschrieben; zweimal anfassen kostet doppelt. | 🟣 |
| D03 | Ob der MCP-Server in Python bleiben kann. **Revidiert** — die frühere Empfehlung „in Python belassen" hielt den MCP für einen lokalen Hilfsprozess. Unter R1 ist er Teil des Lieferumfangs. | Er muss mit nach Rust. Ein Python-MCP-Server im Lieferumfang bedeutet, dass Python **doch** mitausgeliefert werden muss — das Problem, das der Rewrite löst, wäre nur zur Hälfte gelöst. | Als Subkommando `okf mcp serve` im selben Binary (I12), via `rmcp`. Ein Artefakt, eine Installation, kein Subprozess pro Tool-Call. | 🟣 |
| D04 | R2 gibt die Freiheit, Rust-native Lösungen zu nehmen. | Fuzzy-Ranking (`difflib`-Ratio) darf durch einen Rust-Matcher ersetzt werden; Frontmatter darf mit einem echten YAML-Parser gelesen werden statt mit dem Regex-Parser; die Regex-Sonderfälle dürfen als Handscanner entstehen. | Beim Frontmatter mit Bedacht: `serde_yaml` akzeptiert **mehr** als der heutige Parser. Dateien, die heute stillschweigend als „kein Tag-Feld" durchgehen, werden dann geparst — Verhalten ändert sich in Richtung korrekter, aber es ändert sich. `check` sollte diese Fälle vor der Umstellung sichtbar machen. | 🟣 |

## Portierungsanalyse Python → Rust

### Der semantische Arm braucht kein Python

Kein Modell läuft je im Prozess:

- **Query-Embedding**: HTTP POST gegen `https://api.voyageai.com/v1/embeddings` mit `input_type: "query"` (`cli/okf-cli.py:1150-1174`), reine `urllib.request`-Nutzung.
- **Dokument-Embedding**: `cli/embeddings/build_tagvec.py:53-62` — beide Modelle sind Endpunkte. `voyage-3-large` über HTTPS, `bge-m3` über **Ollama** auf `http://localhost:11434/api/embed`.
- **Vektor-Speicher**: SQLite-Tabellen `emb` und `concept_emb`, Little-Endian-Float32-Blobs (`struct.unpack("<{}f")`, Z. 1132) → `f32::from_le_bytes`.
- **Ähnlichkeit**: `_cosine` (Z. 1177), ein Dreizeiler ohne numpy.

Die CLI importiert **ausschließlich Standardbibliothek**. Keine externe Python-Abhängigkeit erzwingt einen Python-Anteil. Externe Prozesse sind nur `fzf` (I11) und `git`.

### Abbildung

| Python | Rust | Risiko unter R2 |
|---|---|---|
| `argparse` + `_sub()`-Registrierung | `clap` (derive), Purpose-Groups über `help_heading` | gering — clap trägt A8 nativ |
| `mcp.server.fastmcp` / FastMCP | `rmcp`, offizielles Rust-SDK, `#[tool_router]`/`#[tool]`, Schema aus `schemars::JsonSchema` | gering — Deklarationsmodell entspricht dem Decorator-Ansatz, und das generierte Schema beseitigt B03 als Klasse |
| `sqlite3` mit FTS5, Tokenizer `porter unicode61 remove_diacritics 2`, `bm25()` mit `0,0,3,2,1` | `rusqlite`, Feature `bundled-full` | gering — FTS5 und `bm25()` sind SQLite-, nicht Python-Features; Gewichte gehen unverändert mit |
| `urllib.request` → Voyage / Ollama | `ureq` oder `reqwest` | gering |
| `struct.unpack("<Nf")` | `f32::from_le_bytes` | gering |
| `tomllib` | `toml` | gering |
| `subprocess` → `git` | `std::process::Command` | gering |
| `re` (Standardfälle) | `regex` | gering |
| `re` mit Lookbehind/Backreference (Z. 1837, 2717, 3008) | `fancy-regex` oder Handscanner | gering–mittel — unter R2 freie Wahl; die Stellen sitzen im Wikilink-Dead-Zone-Masking, dem dichtest getesteten Teil, also gilt T04 hier besonders |
| `difflib.get_close_matches` | `nucleo-matcher` / `strsim` | gering — unter R2 kein Nachbau nötig, Capability ist „ähnliche Tags finden", nicht „dieses Ranking" |
| `fzf`-Subprozess | in-process | gering, entfernt eine Laufzeitabhängigkeit |
| Frontmatter-Regexparser | `serde_yaml` | mittel — nicht technisch, sondern semantisch: der neue Parser akzeptiert mehr (D04) |
| `build_argv`/`run_okf`-Marshalling (`mcp/okf_mcp.py:31-98`) | entfällt | — Gewinn, nicht Aufwand: MCP ruft die interne API direkt |

### Aufwand und Reihenfolge

4280 LOC Python, davon gut die Hälfte Kommentare mit hoher Informationsdichte — sie tragen die Entscheidungsgeschichte (D-Nummern, Messwerte, „do not simplify it back"-Warnungen) und müssen mitwandern. Der Logikanteil ist überschaubar. Unter R2 sinkt das Portierungsrisiko deutlich; was bleibt, ist die Verifikationsfrage (Q01), und die wird durch R2 eher größer.

Reihenfolge: **T01 → T02 → T03 → Rewrite**. Erst die zwei Verhaltensbugs in Python fixen, dann CLI- und MCP-Grammatik gemeinsam als SPEC festschreiben, dann die Verifikationsstrategie aufsetzen. Ein Rewrite, der gleichzeitig die Grammatik erfindet und die Prüfbarkeit aufgibt, hat keinen Fixpunkt.
