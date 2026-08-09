---
type: ADR
title: "Rust-Rewrite — Scope-Entscheidungen D05-D07"
description: "Erweiterungen werden Config-Profile statt Plugins, das Binary kennt Bundle und Catalogue als Store-Modelle, MCP bleibt stdio-only in v1."
tags:
  - okf-cli
  - rust
  - architecture
---

# Rust-Rewrite — Scope-Entscheidungen D05-D07

Grilling-Session 2026-08-09, Fortsetzung des Nummernraums aus [AUDIT.md](./AUDIT.md) (D01-D04 dort vergeben). Löst die dortigen Q02 und Q03 auf.

## Decision-Log

| Code | Decision | Status | Rationale |
|---|---|---|---|
| D05 | Erweiterungen gegenüber OKF v0.1 werden über ein **Config-Profil in `.okf.toml`** geschaltet, nicht über ein Plugin-System. `plugin/` entfällt. | 🟢 | Die Erweiterungen sind eine bekannte, endliche Menge und gehören fest ins Binary. Ein echtes Plugin-System hieße in Rust dynamisch geladener Code — kein stabiles ABI, Cross-Compilation-Bruch, und es zerstört die Single-Binary-Distribution, die das Ziel des Rewrites ist. Der Mechanismus ist im eigenen Code bereits erprobt (`wikilink_checked_bundles`, bundle-granulares Opt-in). Nutzer entscheiden selbst, was sie aktivieren. |
| D06 | Das Binary kennt **beide Store-Modelle**. Erkennung über die Umkehrung der Beweislast: **Marker gefunden → Catalogue, kein Marker → Bundle.** Marker bleibt `.okf.toml` bzw. `SPEC.md`+`TYPES.md`. | 🟢 | Ein verteilbares Binary, das nur ein privates Catalogue-Layout kennt, löst das Distributionsproblem der Runtime und behält das des Datenmodells. OKF §2 nennt das Bundle „the unit of distribution". Die Umkehrung ist robust, weil die Norm-Form markerlos bleibt und die Erweiterung sich ausweist. |
| D07 | Der MCP-Server spricht in v1 **ausschließlich stdio** (`okf mcp serve`). | 🟢 | Der Store ist ein lokales Dateisystem-Artefakt mit Symlinks in Projekt-Repos, die über HTTP ins Leere zeigen; Synchronisation ist git, nicht HTTP. Bei `rmcp` ist der Transport von den Tool-Definitionen getrennt (`serve(transport)`), ein HTTP-Transport später ist additiv statt Umbau. |
| D08 | Die `--full`-Dualität von `index` (I08) wird aufgelöst, indem die Bundle-Variante das eigene Flag **`--summary`** bekommt. | 🟡 | Vorschlag aus dem Fan-out, **nicht vom PO bestätigt**. I08 verlangt die Auftrennung, benennt aber kein Flag; ein unbenanntes Flag macht INDEX-7 als Audit-Zelle unprüfbar. Der Name ist die einzige erfundene Bezeichnung in 26 Dateien und steht hier, damit sie sichtbar ist statt in einer Requirement-Zeile zu verschwinden. |

## Verworfene Alternativen

| Code | Verworfen | Grund |
|---|---|---|
| D05.alt1 | Echtes Plugin-System via `.so`/`.dylib` | Nur sinnvoll für Erweiterungen Dritter, die man nicht kennt. Tauscht die Python-Abhängigkeit gegen ABI-Kompatibilität. |
| D05.alt2 | Cargo-Features statt Runtime-Config | Schaltet zur Compile-Zeit; bräuchte zwei Binaries und könnte nicht pro Store variieren. |
| D05.alt3 | WASM-Plugins | Hält die Distribution intakt, ist aber ein eigenes Projekt und für eine endliche Menge bekannter Regeln überdimensioniert. |
| D06.alt1 | Catalogue-only wie heute, aber ein Bundle sauber ablehnen statt fehlinterpretieren | YAGNI-korrekt bei reiner Eigennutzung, verfehlt aber das Distributionsmotiv. |
| D06.alt2 | `okf_version` in `index.md` als Bundle-Marker | **Faktisch widerlegt**: SPEC §11 sagt „Bundles **MAY** declare", und §3 listet `index.md` selbst als optional. Ein normkonformes Bundle ohne beides ist legal, der Marker erkennt nur eine Minderheit. `okf_version` bleibt als Versions-Hinweis nützlich, taugt aber nicht als Existenz-Marker. |
| D07.alt1 | stdio + HTTP gleich mitbauen | Verlangt vorher eine Antwort auf die Symlink-Mounts; ohne die macht der Transport den Store nicht remote-fähig. |
| D07.alt2 | `--port`-Flag als wirkungsloser Platzhalter | Zusage im Interface ohne Deckung. |

## Befunde, die die Entscheidungen tragen

**Der Catalogue ist nicht eine Schicht über dem Bundle — er ist die einzige Form, die die CLI kennt.** Verifiziert gegen ein Bundle nach SPEC Anhang A: Auto-Detect scheitert (kein `.okf.toml`, kein `SPEC.md`+`TYPES.md`), und mit erzwungenem `--root` meldet `index` „bundle: tables, concepts: 1" — `tables/` ist aber ein Concept-Verzeichnis innerhalb des Bundles, kein Bundle. Die Bundle-Ebene wurde nie implementiert.

**Mindestens sechs der elf `check`-Regeln sind OKF-Abweichungen, nicht OKF-Norm** (`cli/okf-cli.py:3394` ff., hartcodierte `per_file_checks`-Liste):

| Check | weicht ab von |
|---|---|
| `crosslink-format` | §5.1 — Links sind bundle-relativ, dieser Catalogue schreibt catalogue-root-absolut |
| `type-registered` | §1 — „no schema registry, no central authority" |
| `tag-registered` | TAGS.md closed-vocabulary, der SPEC unbekannt |
| `tags-block-form` | im eigenen Docstring als „local convention" markiert |
| `english-keys` | D16 Hybrid-Sprache |
| `RESERVED` | §3.1 reserviert nur `index.md`/`log.md`; lokal um `readme.md`/`index-map.md` erweitert |

Dazu die Catalogue-Ebene selbst und der semantische Arm. Der Knowledge-Catalogue dokumentiert in `okf-meta-wiki/extensions/` bereits **15 Erweiterungen** gegenüber OKF v0.1 — die Profil-Definition kann sich daran entlanghangeln.

**`run_checks` heißt im Docstring bereits „pluggable conformance scan"**, ist aber eine feste Liste mit fester Severity. `wikilink-resolvable` ist die einzige Regel mit Opt-in, und zwar bundle-granular über `.okf.toml`, mit der Begründung „ships silent and is switched on per bundle, so introducing it cannot bury a clean catalogue in warnings". Das ist D05 im Kleinen, bereits gebaut.

## Folge-Tasks

| Code | Task | Outcome |
|---|---|---|
| T06 | Profil-Definition erarbeiten: welche der 15 dokumentierten Erweiterungen werden einzeln schaltbar, welche gehören zum Profil `catalogue`, was gilt im Profil `okf`. | Eine Tabelle Erweiterung → Schalter → Profil-Zugehörigkeit, abgeglichen gegen `okf-meta-wiki/extensions/`. |
| T07 | Store-Abstraktion in der SPEC verankern: welche Kommandos verhalten sich im Bundle-Modus anders, wie adressieren `target`/`--scope` dort. | Pro Kommando eine Aussage zum Bundle-Modus in der EARS-SPEC. |
| T08 | `check --profile okf` als Portabilitäts-Gate spezifizieren — beantwortet „hält dieses Bundle ohne den Catalogue". | Ein Kommando, das ein Bundle gegen die reine Norm prüft. |
| T09 | `plugin/` löschen und die Zeile aus `docs/docs-index-map.md` streichen. | Ordner weg, index-map beschreibt keinen Skeleton mehr, der nie existierte. |
