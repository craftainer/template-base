#!/usr/bin/env bash
# Sets up the `develop` stage on top of Microsoft's generic base
# devcontainer image (which already provides the `vscode` user, git, sudo,
# and curl). Installs only the language-agnostic AI-assisted-workflow
# tooling this template requires everywhere; an instance's own
# scripts/develop.sh (or an addition to this one) installs its language
# runtime and any stack-specific CLI on top -- see docs/TEMPLATE.md.
set -euo pipefail

prek_version=$1
claude_code_version=$2
snip_version=$3

# prek (https://prek.j178.dev/) is installed as a standalone tool, not a
# project dependency of any particular language's package manager -- every
# instance, regardless of language, is expected to run
# `prek run --all-files --hook-stage manual` (see checks.yml).
curl -LsSf "https://github.com/j178/prek/releases/download/v${prek_version}/prek-installer.sh" \
    | sudo -u vscode env HOME=/home/vscode INSTALLER_NO_MODIFY_PATH=1 sh
ln -s /home/vscode/.local/bin/prek /usr/local/bin/prek

curl -fsSL https://claude.ai/install.sh \
    | sudo -u vscode env HOME=/home/vscode bash -s "$claude_code_version"
ln -s /home/vscode/.local/bin/claude /usr/local/bin/claude

# For the snip Claude Code PreToolUse hook -- see .claude/README.md. Not on
# PyPI/npm, so fetched as a release tarball and checksum-verified against
# the project's own published checksums.txt instead of trusting a
# curl-pipe-to-sh installer.
snip_arch="$(dpkg --print-architecture)"
snip_asset="snip_${snip_version}_linux_${snip_arch}.tar.gz"
snip_tmpdir="$(mktemp -d)"
sudo chmod a+rwx "$snip_tmpdir"
curl -LsSf -o "${snip_tmpdir}/${snip_asset}" \
    "https://github.com/edouard-claude/snip/releases/download/v${snip_version}/${snip_asset}"
curl -LsSf -o "${snip_tmpdir}/checksums.txt" \
    "https://github.com/edouard-claude/snip/releases/download/v${snip_version}/checksums.txt"
(cd "$snip_tmpdir" && grep " ${snip_asset}\$" checksums.txt | sha256sum -c -)
tar -xzf "${snip_tmpdir}/${snip_asset}" -C "$snip_tmpdir" snip
sudo -u vscode install -Dm755 "${snip_tmpdir}/snip" /home/vscode/.local/bin/snip
rm -rf "$snip_tmpdir"
ln -s /home/vscode/.local/bin/snip /usr/local/bin/snip
