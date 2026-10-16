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
# Verzeichnis des Go-Moduls (go.mod liegt dort) und Ausgabe des Builds relativ dazu; der Pfad
# {{go_dir}}/{{go_out}} ist der eine Binary-Pfad fuer `just golden --cmd`
go_dir := "go"
go_out := "bin/okf"

# Alle Rezepte auflisten
default:
    @just --list

# Testsuite (unittest discovery ueber tests/test_*.py). Die Laufzeit-Abhaengigkeiten kommen aus dem
# PEP-723-Header von cli/okf-cli.py; mcp ist ein reines Test-Extra. UV_PYTHON waehlt den Interpreter.
test *ARGS:
    uv run --no-project --with-requirements {{cli_dir}}/okf-cli.py --with mcp python -m unittest {{ if ARGS == "" { "discover -s tests -t . -p 'test_*.py'" } else { ARGS } }}

# Golden-Output-Vergleich (tests/okf_golden.py): --update schreibt die Goldens neu, --cmd prueft eine
# andere Implementierung (z.B. ein Port-Binary), --only <text> waehlt Faelle per Namensteil.
# Jeder Fall laeuft hinter einem Netzwerk-Block (macOS sandbox-exec, Linux seccomp), auch Loopback;
# greift er nicht, bricht der Lauf vor dem ersten Fall ab.
[positional-arguments]
golden *ARGS:
    uv run --no-project --with-requirements {{cli_dir}}/okf-cli.py python tests/okf_golden.py "$@"

# Go-Binary bauen (statisch, ohne cgo) nach go/bin/okf; Abnahme: just golden --cmd go/bin/okf
go-build:
    CGO_ENABLED=0 go build -C {{go_dir}} -o {{go_out}} ./cmd/okf

# Die Completion-Skripte des Go-Binarys (go/internal/complete/okf.*) aus cli/_okf und argcomplete 3.7.2
# neu schreiben; --check vergleicht nur und bricht bei Abweichung ab
go-completion-scripts *ARGS:
    uv run --no-project --with argcomplete==3.7.2 python scripts/go_completion_scripts.py {{ARGS}}

# Wheel und sdist nach dist/ bauen (uv build, Backend hatchling laut pyproject.toml)
build:
    uv build

# Korrektheits-Lint (Syntaxfehler, pyflakes) ueber cli/ und mcp/; Regeln in pyproject.toml [tool.ruff.lint]
lint:
    uvx ruff@{{ruff_version}} check cli mcp

# Paket pruefen: bauen, twine check --strict, Wheel in leerer venv installieren, okf --help
pack-check:
    scripts/pack-check.sh

# Offline Eval-Gate: lexikalische Messung auf Wegwerf-Catalogue gegen die eingefrorene Baseline, nur S1-literal-Guard (OKFT-cuj7)
eval-gate:
    scripts/eval-gate.sh

# Skill-Evals mit headless omp-Agenten (kostet Tokens): just skill-eval --only write- --models small=claude-haiku-4-5
skill-eval *ARGS:
    python3 scripts/skill-eval.py {{ARGS}}

# Release-Note-Entwurf aus den Beans eines Release-Meilensteins: just release-notes OKFT-xxxx > releases/RELEASE-x.y.z.md
release-notes MILESTONE:
    python3 scripts/release-notes.py {{MILESTONE}}

# Gate A (EARS-Form der Acceptance Criteria) gegen rohe .beans/-Dateien, z.B. `just gate-a ../.beans/OKFT-xxxx--slug.md`. Exit 0 = sauber, 1 = Befund, 2 = Fehlaufruf.
gate-a *ARGS:
    @test -n "{{ARGS}}" || { echo "just gate-a <bean-datei>... — kein Bean genannt" >&2; exit 2; }
    @cd "{{invocation_directory()}}" && ahm gate-a {{ARGS}}

# okf bei Agents und Shells einrichten: zeigt den Plan, `just setup --apply` fuehrt ihn aus (--uninstall, --only: siehe `okf install --help`)
setup *ARGS:
    uv run --script {{cli_dir}}/okf-cli.py install {{ARGS}}

# Verpackungs-Smoke: Wheel bauen, in Wegwerf-venv installieren, CLI + MCP-stdio gegen die installierte Kopie pruefen
smoke-pack:
    scripts/pack-smoke.sh

# Konformitaets-Scan des Catalogue (§9 + lokale Invarianten)
check root=catalogue:
    uv run --script {{cli_dir}}/okf-cli.py --root {{root}} check

# Agent-Onboarding gegen den echten Catalogue ausgeben
prime root=catalogue:
    uv run --script {{cli_dir}}/okf-cli.py --root {{root}} prime
