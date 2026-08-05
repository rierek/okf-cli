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
