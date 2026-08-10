# retrieval-architecture

Hybrid-Retrieval-Architektur des Katalogs (lexikaler FTS5-Arm + semantischer
voyage-3-large-Arm, bedingte Übergabe) — Think-Session 2026-07-25/26, Epic
`okf-cli-cskz`/`okf-cli-5uog`.

## Contents

<!-- okf:index -->
* [Filter gelten für die Antwort, nicht für einen Arm](/okf-tools-okf/retrieval-architecture/filters-constrain-the-answer.md) - Entwurfsregel für Retrieval mit bedingter Übergabe — wer das Ranking besitzt, wird zur Laufzeit entschieden, also muss jeder Arm dieselben Filter durchsetzen; mit dem Residual-Rückgabewert als Durchsetzungsmechanismus und dem Testschnitt, der ihn bewacht.
* [Hybrid retrieval architecture — decisions](/okf-tools-okf/retrieval-architecture/hybrid-retrieval-decisions.md) - Decision log (D01-D17) for okf-cli's hybrid lexical/semantic retrieval — conditional handover fusion, voyage-3-large as the production embedding model, chunking rejected.
* [Hybrid retrieval architecture — target design and findings](/okf-tools-okf/retrieval-architecture/hybrid-retrieval-design.md) - Target retrieval architecture for okf-cli — FTS5/BM25 lexical arm plus voyage-3-large semantic arm, conditional-handover fusion — with the measured findings that rule out chunking, an absolute cosine floor, and RRF.
* [The .tagvec producer runs offline and is not a runtime dependency](/okf-tools-okf/retrieval-architecture/tagvec-producer.md) - build_tagvec.py regenerates the tag-similarity cache that find's semantic backstop reads at query time; the pass is offline, batched, resumable, and embeds slugs only because title/description enrichment made independent tags look similar.
<!-- /okf:index -->
