package cli

// topDescription is the text above the option list of okf --help: the module docstring of
// cli/okf-cli.py.
const topDescription = "okf — navigation, search and maintenance for an OKF Knowledge Catalogue.\n" +
	"\n" +
	"Catalogue-aware fork inspired by Cole Medin's single-bundle okf-cli.py.\n" +
	"A *catalogue* is a directory whose immediate subdirectories (not starting with\n" +
	"'.' or '_') are OKF *bundles*. The runtime dependencies are declared as PEP 723\n" +
	"metadata in the header of this file; `uv run --script okf-cli.py` installs them\n" +
	"on first use.\n" +
	"\n" +
	"Run `okf --help` for the command directory (flat + grouped by purpose),\n" +
	"and `okf <command> --help` for one command's options. Both are generated\n" +
	"from the parser — this file documents no command list by hand.\n" +
	"\n" +
	"Catalogue root: --root (a `~` is expanded), else the nearest catalogue above cwd (.okf.toml,\n" +
	"or SPEC.md plus TYPES.md, also in a docs/ child), else `root` in $XDG_CONFIG_HOME/okf/config.toml\n" +
	"(default ~/.config/okf/config.toml). --global takes that configured root and skips the search\n" +
	"above cwd; it excludes --root.\n"
