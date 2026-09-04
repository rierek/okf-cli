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
