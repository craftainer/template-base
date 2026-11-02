#!/usr/bin/env bash
# Runs `claude -p` for one moderation stage, inside the devcontainer (see
# ../workflows/README.md's "Issue moderation" section). Shared by all four
# Claude-invoking moderation workflows so the model/effort/output-format
# pinning, the git identity and the permission hardening stay in one place.
#
# The workflow copies this file from a trusted snapshot of the default branch
# to .moderation-tools/run_claude.sh before it starts (moderate_prepare.sh); it
# never runs the copy that sits in the checked-out tree.
#
# The Anthropic API key arrives ONLY in the environment of this process
# (devcontainers/ci's `env:` input -> `devcontainer exec --remote-env`). It is
# never written to a file in the workspace.
set -euo pipefail

prompt_file="$1"
allowed_tools="$2"
max_turns="$3"
timeout_seconds="$4"

if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "::error::ANTHROPIC_API_KEY is not set in the environment of run_claude.sh" >&2
  exit 1
fi
[[ "$max_turns" =~ ^[0-9]+$ && "$timeout_seconds" =~ ^[0-9]+$ ]] || {
  echo "::error::max turns and timeout must be integers" >&2
  exit 1
}

# An instance's optional extra tools (the MODERATION_EXTRA_TOOLS repository
# variable) arrive as data in the environment, never spliced into a command.
if [ -n "${MODERATION_EXTRA_TOOLS:-}" ]; then
  allowed_tools="$allowed_tools,$MODERATION_EXTRA_TOOLS"
fi

# Every commit this pipeline makes carries this identity, distinct from the
# github-actions[bot] identity ../scripts/template_sync.py uses, so a
# Claude-authored commit is visibly attributable to this pipeline. Set through
# the environment, not `git config`, so nothing is written to .git/config.
export GIT_AUTHOR_NAME="claude-moderator[bot]"
export GIT_COMMITTER_NAME="claude-moderator[bot]"
export GIT_AUTHOR_EMAIL="claude-moderator[bot]@users.noreply.github.com"
export GIT_COMMITTER_EMAIL="claude-moderator[bot]@users.noreply.github.com"

# Strip credentials from the environment of everything Claude starts (Bash
# commands, hooks, MCP servers); only claude itself keeps the key.
export CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1

# Deny rules outrank every allow rule. They keep the file tools away from the
# process environment (/proc/<pid>/environ holds the key), from this tooling
# directory and from .git. `--settings` is the command-line level of Claude
# Code's settings precedence, above the project's own .claude/settings*.json,
# and is passed inline so there is no file for the agent to edit mid-run.
settings='{"permissions":{"deny":["Read(//proc/**)","Read(//sys/**)","Read(~/.claude/**)","Read(~/.config/gh/**)","Edit(./.moderation-tools/**)","Edit(./.git/**)"]}}'

timeout "${timeout_seconds}s" claude -p "$(cat "$prompt_file")" \
  --model claude-sonnet-5 \
  --effort medium \
  --output-format json \
  --max-turns "$max_turns" \
  --settings "$settings" \
  --allowedTools "$allowed_tools"
