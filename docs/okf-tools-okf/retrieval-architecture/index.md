# retrieval-architecture

Hybrid-Retrieval-Architektur des Katalogs (lexikaler FTS5-Arm + semantischer
voyage-3-large-Arm, bedingte Übergabe) — Think-Session 2026-07-25/26, Epic
`okf-cli-cskz`/`okf-cli-5uog`.

## Contents

<!-- okf:index -->
* [Hybrid retrieval architecture — decisions](/okf-tools-okf/retrieval-architecture/hybrid-retrieval-decisions.md) - Decision log (D01-D17) for okf-cli's hybrid lexical/semantic retrieval — conditional handover fusion, voyage-3-large as the production embedding model, chunking rejected.
* [Hybrid retrieval architecture — target design and findings](/okf-tools-okf/retrieval-architecture/hybrid-retrieval-design.md) - Target retrieval architecture for okf-cli — FTS5/BM25 lexical arm plus voyage-3-large semantic arm, conditional-handover fusion — with the measured findings that rule out chunking, an absolute cosine floor, and RRF.
<!-- /okf:index -->
