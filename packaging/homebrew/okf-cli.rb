# Repo copy of the tap formula (xRiErOS/homebrew-tap, Formula/okf-cli.rb) for the Go binary (OKFT-jyvt).
# It builds `okf` from source with `just go-build`, the one build command of the Go module (go/).
# No release carries the Go sources yet (D11): until one does, the formula has only `head`.
# At the release that ships the port: add url, version and sha256 of that rel-* tag, then copy to the tap.
# Local check without the tap: scripts/brew-local-check.sh.
class OkfCli < Formula
  desc "CLI and MCP server for Open Knowledge Format (OKF) catalogues"
  homepage "https://github.com/xRiErOS/okf-cli"
  head "https://github.com/xRiErOS/okf-cli.git", branch: "main"
  license "Apache-2.0"

  depends_on "go" => :build
  depends_on "just" => :build
  depends_on "uv" # the MCP server runs as `uv run --with "mcp<2"`; the binary itself never calls uv

  def install
    system "just", "go-build"
    # `okf install` finds its package root as the nearest ancestor of the binary that holds
    # skills/okf/SKILL.md and mcp/okf_mcp.py; here that is the keg prefix, next to bin/okf.
    bin.install "go/bin/okf"
    (prefix/"skills").install "skills/okf"
    (prefix/"mcp").install "mcp/okf_mcp.py"
  end

  def caveats
    <<~EOS
      Wire okf into your coding agents and shells (previews first, changes nothing):
        okf install
      Then perform it:
        okf install --apply
    EOS
  end

  test do
    assert_match "usage:", shell_output("#{bin}/okf --help")
    plan = shell_output("#{bin}/okf install --json --only claude")
    assert_match "#{opt_prefix}/mcp/okf_mcp.py", plan
    assert_path_exists prefix/"skills/okf/SKILL.md"
    assert_path_exists prefix/"mcp/okf_mcp.py"
  end
end
