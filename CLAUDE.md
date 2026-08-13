# okf-tools

1. Testläufe und Smoke-Proben schreiben nie nach `~/Obsidian/Knowledge-Catalogue`; das Wegwerf-Layout entsteht unter einem eigenen tmpdir.
2. Vor einem Commit an einem Konzept im Knowledge-Catalogue das reale Repo des Bundles auflösen — `git -C <pfad> rev-parse --show-toplevel`, die Bundles sind Symlinks — und dort ausschließlich explizite Dateipfade stagen.
3. `just test` läuft ohne neue Fehler durch, bevor eine Änderung an `cli/` oder `mcp/` committet wird. Vollständig grün ist die Suite derzeit nicht: drei Tests in `cli/test_eval_runner.py::RunnerAgainstRealCatalogueTest` sind vorbestehend rot, weil sie gegen den echten Knowledge-Catalogue messen (`test_runner_scores_literal_s1_top1`, `test_metadata_hit_and_miss_rows_scored_correct`, `test_index_walk_row_present_with_rank_no_dedicated_metric`). Sie gehören zu OKFT-5c2c und werden weder repariert noch angepasst. Das Gate lautet deshalb: genau diese drei rot, kein vierter.
4. Nach jedem abgeschlossenen Epos-Abschnitt nach `origin/main` pushen — stehende Freigabe von Erik, 2026-08-13. Ohne sie lag die Arbeit dieses Repos ausschließlich lokal.
