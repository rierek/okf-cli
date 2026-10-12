# Template of the Homebrew tap formula (xRiErOS/homebrew-tap, Formula/okf-cli.rb). At release: set url to the tag tarball
# and sha256 to its digest. Verified through a local tap with a git-archive tarball: brew install, brew test, uninstall.
class OkfCli < Formula
  include Language::Python::Virtualenv

  desc "CLI and MCP server for Open Knowledge Format (OKF) catalogues"
  homepage "https://github.com/xRiErOS/okf-cli"
  url "https://github.com/xRiErOS/okf-cli/archive/refs/tags/v0.1.0.tar.gz"
  sha256 "RELEASE_TARBALL_SHA256"
  license "Apache-2.0"

  depends_on "python@3.14"
  depends_on "uv" # the MCP server runs as `uv run --with "mcp<2"`

  def install
    # Same artifact as `pipx install` / `uv tool install`: the wheel layout of pyproject.toml.
    venv = virtualenv_create(libexec, "python3.14")
    venv.pip_install_and_link buildpath
  end

  def caveats
    <<~EOS
      Wire okf-cli into your coding agents and shells (previews first, changes nothing):
        okf-cli install
      Then perform it:
        okf-cli install --apply
    EOS
  end

  test do
    assert_match "usage:", shell_output("#{bin}/okf-cli --help")
    system bin/"okf-cli", "install", "--json", "--only", "claude"
  end
end
