# Contributing to okf

Issues and pull requests are welcome.

- **Bugs and ideas:** open an issue with the command, the catalogue layout (or a minimal one) and the output.
- **Pull requests:** run `just test` first; it must be green. Tests never write into a real catalogue and use their own tmpdir. Keep the CLI stdlib-only.
- **Commits:** `<type>(<scope>): <subject>`, at most 72 bytes.

Changes to the OKF format itself belong upstream: [GoogleCloudPlatform/open-knowledge-format](https://github.com/GoogleCloudPlatform/open-knowledge-format) (see its CONTRIBUTING.md). `okf` only implements tooling around the spec.
