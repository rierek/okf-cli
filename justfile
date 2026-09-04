set shell := ["bash", "-uc"]

# Verzeichnis der Test- und Quelldateien
cli_dir := "cli"
# Catalogue-Root fuer Smoke-Laeufe gegen einen echten Store
catalogue := env_var("HOME") + "/Obsidian/Knowledge-Catalogue"

# Alle Rezepte auflisten
default:
    @just --list

# Testsuite (unittest discovery ueber cli/test_*.py)
test *ARGS:
    cd {{cli_dir}} && python3 -m unittest {{ if ARGS == "" { "discover -p 'test_*.py'" } else { ARGS } }}

# Konformitaets-Scan des Catalogue (§9 + lokale Invarianten)
check root=catalogue:
    python3 {{cli_dir}}/okf-cli.py --root {{root}} check

# Agent-Onboarding gegen den echten Catalogue ausgeben
prime root=catalogue:
    python3 {{cli_dir}}/okf-cli.py --root {{root}} prime

# spec_dir wird per scripts/spec-dir.sh abgeleitet (D-siyu-07), nicht als
# Modul-Variable -- die wuerde `just` bei JEDEM Rezept eager auswerten und
# bei Fehlschlag auch test/check/prime mitreissen, nicht nur dieses.

# EARS-Konformitaet der Rewrite-SPEC pruefen (Abgabekriterium je SPEC-Datei)
spec-check *FILES:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ -z "{{FILES}}" ]; then dir="$(scripts/spec-dir.sh)"; set -- "$dir"/*.md; else set -- {{FILES}}; fi
    exec node scripts/ears-table-check.js "$@"

# Fixtures der scripts/-Tests gehoeren in einen eigenen tmpdir, nie ins
# SPEC-Verzeichnis -- der Glob von spec-check fischt dort jede *.md ein
# (CLAUDE.md Regel 1 gilt sinngemaess).

# Tests der scripts/-Werkzeuge (node built-in runner, gefiltert je Datei)
test-scripts *FILES:
    #!/usr/bin/env bash
    set -euo pipefail
    shopt -s nullglob
    if [ -z "{{FILES}}" ]; then set -- scripts/*.test.js; else set -- {{FILES}}; fi
    [ "$#" -gt 0 ] || { echo 'test-scripts: no test file matched scripts/*.test.js -- nothing was checked' >&2; exit 1; }
    exec node --test "$@"
