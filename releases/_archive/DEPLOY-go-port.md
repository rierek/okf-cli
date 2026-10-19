# Deploy steps of the Go release (internal)

Moved out of `RELEASE-DRAFT-go-port.md`: the draft becomes public release text, these steps do not.

## Deploy steps after PO approval

1. In `repo/` on `main`: merge the integration line `--no-ff`, check the diff against the line, run `just test` and `just golden-go`, then `git push origin main`.
2. Tag the merge commit `rel-<x-y-z>` and push the tag. The release workflow builds the four binaries, the wheel and the sdist and attaches the provenance; verify the provenance with `slsa-verifier`.
3. In `packaging/homebrew/okf-cli.rb` add `url`, `version` and `sha256` of that tag, then copy the formula to the tap (`xRiErOS/homebrew-tap`, `Formula/okf-cli.rb`). Check it first with `just brew-local-check`.
