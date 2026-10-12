# Copy of the tap formula (xRiErOS/homebrew-tap, Formula/okf-cli.rb) for rel-0-2-3. At the next release: set url, version and sha256, then copy to the tap.
class OkfCli < Formula
  include Language::Python::Virtualenv

  desc "CLI and MCP server for Open Knowledge Format (OKF) catalogues"
  homepage "https://github.com/xRiErOS/okf-cli"
  url "https://github.com/xRiErOS/okf-cli/archive/refs/tags/rel-0-2-3.tar.gz"
  sha256 "8cfddc7b8862870709e2e5d988af1d4242746957eb13b1aba26fe9e2dfe89b14"
  version "0.2.3"
  license "Apache-2.0"

  depends_on "python@3.14"
  depends_on "uv" # the MCP server runs as `uv run --with "mcp<2"`

  resource "argcomplete" do
    url "https://files.pythonhosted.org/packages/87/6f/5a73f04007ca950701765949209f068da628bd11f9c2da287278ce91e0ee/argcomplete-3.7.2.tar.gz"
    sha256 "aad8b69a0b9969edb62db0d1752354c0d50717b10e0cbb00e2a958381b9fc6b9"
  end

  resource "ruamel.yaml" do
    url "https://files.pythonhosted.org/packages/c7/3b/ebda527b56beb90cb7652cb1c7e4f91f48649fbcd8d2eb2fb6e77cd3329b/ruamel_yaml-0.19.1.tar.gz"
    sha256 "53eb66cd27849eff968ebf8f0bf61f46cdac2da1d1f3576dd4ccee9b25c31993"
  end

  def install
    # Same artifact as `pipx install` / `uv tool install`: the wheel layout of pyproject.toml.
    venv = virtualenv_create(libexec, "python3.14")
    venv.pip_install resources
    venv.pip_install_and_link buildpath
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
    system bin/"okf", "install", "--json", "--only", "claude"
  end
end
