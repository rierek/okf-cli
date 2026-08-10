# okf-tools

1. Testläufe und Smoke-Proben schreiben nie nach `~/Obsidian/Knowledge-Catalogue`; das Wegwerf-Layout entsteht unter einem eigenen tmpdir.
2. Vor einem Commit an einem Konzept im Knowledge-Catalogue das reale Repo des Bundles auflösen — `git -C <pfad> rev-parse --show-toplevel`, die Bundles sind Symlinks — und dort ausschließlich explizite Dateipfade stagen.
3. `just test` läuft vollständig grün durch, bevor eine Änderung an `cli/` oder `mcp/` committet wird.
