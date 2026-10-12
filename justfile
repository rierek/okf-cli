set shell := ["bash", "-uc"]
# Container-Lebenszyklus just wt start|merge|finish -- eine Quelle in den dotfiles.
# mod?: fehlt die Datei (CI, andere Rechner), entfaellt nur das Modul.
mod? wt '~/.config/just/wt.just'

# Verzeichnis der Test- und Quelldateien
cli_dir := "cli"
# Catalogue-Root fuer Smoke-Laeufe gegen einen echten Store
catalogue := env_var("HOME") + "/Obsidian/Knowledge-Catalogue"
# Ruff-Version fuer den Lint-Gate (eine Quelle; Regelsatz steht in pyproject.toml)
ruff_version := "0.17.0"

# Alle Rezepte auflisten
default:
    @just --list

# Testsuite (unittest discovery ueber tests/test_*.py). Die Laufzeit-Abhaengigkeiten kommen aus dem
# PEP-723-Header von cli/okf-cli.py; mcp ist ein reines Test-Extra. UV_PYTHON waehlt den Interpreter.
test *ARGS:
    uv run --no-project --with-requirements {{cli_dir}}/okf-cli.py --with mcp python -m unittest {{ if ARGS == "" { "discover -s tests -t . -p 'test_*.py'" } else { ARGS } }}

# Wheel und sdist nach dist/ bauen (uv build, Backend hatchling laut pyproject.toml)
build:
    uv build

# Korrektheits-Lint (Syntaxfehler, pyflakes) ueber cli/ und mcp/; Regeln in pyproject.toml [tool.ruff.lint]
lint:
    uvx ruff@{{ruff_version}} check cli mcp

# Paket pruefen: bauen, twine check --strict, Wheel in leerer venv installieren, okf-cli --help
pack-check:
    scripts/pack-check.sh

# Offline Eval-Gate: lexikalische Messung auf Wegwerf-Catalogue gegen die eingefrorene Baseline, nur S1-literal-Guard (OKFT-cuj7)
eval-gate:
    scripts/eval-gate.sh

# okf-cli bei Agents und Shells einrichten: zeigt den Plan, `just setup --apply` fuehrt ihn aus (--uninstall, --only: siehe `okf-cli.py install --help`)
setup *ARGS:
    uv run --script {{cli_dir}}/okf-cli.py install {{ARGS}}

# Konformitaets-Scan des Catalogue (§9 + lokale Invarianten)
check root=catalogue:
    uv run --script {{cli_dir}}/okf-cli.py --root {{root}} check

# Agent-Onboarding gegen den echten Catalogue ausgeben
prime root=catalogue:
    uv run --script {{cli_dir}}/okf-cli.py --root {{root}} prime
