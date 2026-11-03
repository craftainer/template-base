# 0001. Harden the issue-moderation workflows

## Status

Proposed

## Context

`moderate-bug-triage.yml`, `moderate-feature-triage.yml`,
`moderate-bug-fix.yml` and `moderate-feature-build.yml` run the `claude`
CLI against GitHub issue text (title, body, every comment) on a runner that
holds a repository secret (`ANTHROPIC_API_KEY`) and a `GITHUB_TOKEN`. Issue
text is attacker-controlled: an outsider's issue carrying `claude:ok`, or an
issue edited or commented on after a maintainer labelled it, is a prompt
injection that Claude reads as it works. The 2026-11 OWASP review of this
repository (findings High 1, High 2 and Medium 4 of the template-base
report; High 1 of the `.github` report for the same pattern in an older
copy) found that the existing controls did not hold:

- **The key sat in the workspace.** Each job wrote it to
  `.secrets/claude.txt`, a file Claude's own `Read` tool can open, and
  `--allowedTools` is not a sandbox: `Bash(git *)` allows
  `git -c alias.x='!cmd' x` and `git push <any url>`; `Bash(prek run *)`
  runs hooks from a config Claude can `Edit`; `Write`/`Edit` can change any
  script the job runs afterwards. An injected run could exfiltrate the key.
  The workflows README claimed the jobs were "limited to git, gh, file tools
  and prek run", which was wrong.
- **Triage held write scopes.** The triage jobs ran Claude with `contents:
  write`, `issues: write` and `pull-requests: write`; the fix/build jobs had
  already been split into a read-only Claude job and a privileged `apply`
  job, triage had not. An injected triage run could push over branches and
  tags, or edit other issues and PRs.
- **The Claude job ran its own tree.** Fix/build executed
  `moderate_package_result.sh` and `run_claude.sh` from the checkout Claude
  had just edited, and built the devcontainer from the repro/plan branch,
  which Claude had written during triage.
- **`apply` trusted its input.** `base_sha` from the artifact went unchecked
  to `git fetch`, and the patch could change any path, including
  `.github/scripts/`, `Makefile`, `.devcontainer/` and the hook config.
- **Forwarding of the environment was unverified.** The moderation steps set
  `GH_TOKEN` in the `devcontainers/ci` step's `env:` but not in `with: env:`.
  The action's source (below) confirms only `with: env:` (and `inheritEnv`)
  reach the command, so `gh` inside the container had no token. No run had
  ever reached that step to show it, because the repository has no key.

User decision (2026-11-02): harden all four jobs, not only the Claude-writes
ones.

### Sources

- Anthropic, claude-code-action, "Security"
  (<https://github.com/anthropics/claude-code-action/blob/main/docs/security.md>):
  limit allowed tools to the minimum, with the caveat that restricting them
  "reduces the rate of recovery but may not eliminate the risk"; prefer the
  workflow `GITHUB_TOKEN` scoped to the job's declared permissions; treat
  comments from non-write users as untrusted, and note the action scrubs
  secrets from subprocess environments by default
  (`CLAUDE_CODE_SUBPROCESS_ENV_SCRUB`).
- Anthropic, Claude Code docs: "Configure permissions"
  (<https://code.claude.com/docs/en/permissions.md>: Bash rules match whole
  commands and are split on `&&`, `||`, `;`, `|`; `Read`/`Edit` deny rules
  cover the file tools and recognised file commands but "not ... arbitrary
  subprocesses"), "Settings files and precedence"
  (<https://code.claude.com/docs/en/settings.md>: `--settings` sits above
  project settings), and the environment variables reference
  (<https://code.claude.com/docs/en/env-vars.md>:
  `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB`, which leaves GitHub tokens in place).
- GitHub, "Security hardening for GitHub Actions"
  (<https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions>):
  "Good practices for mitigating script injection attacks" (pass untrusted
  or secret values through an intermediate `env:` variable, not into the
  script text), "Use secrets for sensitive information" (least privilege,
  default read-only `GITHUB_TOKEN`, raise it per job).
- `devcontainers/ci` at the pinned v0.3.1900000450
  (`action.yml`: `env` "Specify environment variables to pass to the docker
  run command", `inheritEnv`; `github-action/dist/index.js`: `populateDefaults`
  builds the list from `env`/`inheritEnv` and `devContainerExec` turns each
  entry into `--remote-env`; nothing else of the step's environment is
  forwarded).
- Anthropic, Claude Code docs, "Sandboxing"
  (<https://code.claude.com/docs/en/sandboxing.md>): `sandbox.enabled`,
  `failIfUnavailable` (fail closed), `allowUnsandboxedCommands`,
  `autoAllowBashIfSandboxed` (default true), `network.allowedDomains` /
  `strictAllowlist`, `filesystem.denyRead` / `allowWrite`,
  `credentials.envVars` (`deny` unsets a variable in every sandboxed
  command), Linux dependencies `bubblewrap` and `socat`, and that in an
  unprivileged container bubblewrap cannot mount a fresh `/proc` unless
  `enableWeakerNestedSandbox` bind-mounts the container's own, "which
  exposes process information"; the sandbox covers Bash and its children,
  not the Read/Edit/Write tools.
- The OWASP review reports (`OW-template-base`, `OW-.github`, 2026-11-01).

## Decision

We will treat the Claude process as compromised by the issue text it reads
and make sure that nothing it can reach is worth taking and nothing it can
change is acted on without a check.

1. **Read-only Claude, privileged apply, for all four workflows.** The
   `triage`, `fix` and `build` jobs hold `contents: read` (triage also
   `issues: read`). They emit a `moderation-result` artifact. The `apply`
   job runs no Claude and no untrusted code, validates the artifact and does
   every write. Triage's comment, label and repro/plan-branch push move into
   a new `apply` job (`moderate_apply_triage.sh`), driven by a closed set of
   actions mapped to fixed labels.
2. **The key exists only in one process's environment.** No file. The
   step lists `ANTHROPIC_API_KEY` under `devcontainers/ci`'s `with: env:`,
   so it reaches `devcontainer exec --remote-env` for the one
   `run_claude.sh` command. `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1` keeps it
   out of Bash, hooks and MCP children, and an inline `--settings` deny
   list blocks `Read(//proc/**)` (and `/sys`, `~/.claude`, `~/.config/gh`).
   The same `with: env:` fix gives triage its read-only `GH_TOKEN`.
   Claude Code's built-in sandbox wraps every Bash command and what it
   starts (prek hooks, tests, code the agent wrote): filesystem
   isolation, a network allow-list (`github.com` and, for triage,
   `api.github.com`, plus an optional repository variable), the key unset in
   every sandboxed command. `failIfUnavailable: true` and
   `allowUnsandboxedCommands: false` make it fail closed, and
   `enableWeakerNestedSandbox` is not set (it would expose the container's
   `/proc`). The image gains `bubblewrap` and `socat`.
3. **Narrow tool allow-list.** `Bash(git *)` becomes the local subcommands
   Claude needs (`status`, `diff`, `log`, `show`, `add`, `commit`, `restore`,
   `rm`, `mv`, `ls-files`, `rev-parse`, and for triage `checkout -b` /
   `switch -c`): no `-c`, `config`, `push`, `remote`, `fetch`. `gh` is only
   `issue view` and `repo view`, and only in triage. Pushes happen only in
   `apply`. `Bash(prek run *)` becomes `prek run --config
   .moderation-tools/pre-commit-config.yaml *`, a copy of the default
   branch's config placed outside the tree Claude edits (and denied to its
   edit tools). Only the config is trusted: hooks that call repository
   scripts run the copies in the tree Claude edits, and the sandbox
   (see the sandbox decision above) is the mitigation. `MODERATION_EXTRA_TOOLS` is passed as an environment
   variable, not spliced into the command line.
4. **Claude never runs from its own tree.** Each Claude job snapshots the
   default branch with `git archive` into `$RUNNER_TEMP/trusted`, outside
   the devcontainer's bind mount. The launcher, prompts and hook config
   are installed from the snapshot; the packaging script runs from it and
   reads the agent's commits through a fresh bare repository and its result
   files only when they are regular, non-symlink files under
   `.moderation-out/`. Fix/build also refuse to start Claude when the
   repro/plan branch differs from its merge base with the default branch in
   a denied path, since the devcontainer and image build are read from the
   branch. The snapshot is the default branch's latest commit (`github.sha`
   on an `issues` event).
5. **`apply` validates.** `base_sha` must match `^[0-9a-f]{40}$`, follow a
   `--`, and be an ancestor of the default branch or (fix/build) of the bot
   branch's tip, checked through the compare API (this also removes the old
   100-commit limit). The commits the patch makes are checked against
   `moderate_check_paths.sh`: no change under `.github/`, `.devcontainer/`,
   `.claude/`, `.vscode/`, to `.mcp.json`, `.pre-commit-config.yaml`,
   `.gitattributes`, `.gitmodules`, a `Makefile` or `*.mk`, a `Dockerfile*`
   or `compose*.y*ml`, `scripts/release*`, `scripts/develop.sh`,
   `scripts/post-create.sh` (and their `.d/` directories), and no symlink
   or submodule. The artifact's issue number must equal the run's, patches
   are capped at 2 MiB, text is capped and has `@` broken. The PR base is
   the repository's default branch.

## Consequences

- A prompt-injected Claude run can no longer push, comment, label or open a
  PR. Its reachable credentials are a spend-limited API key and a read-only
  token on a public repository's contents and issues. Its output is
  checked before it touches the repository.
- **Sandbox, unverified until a real run.** The residual risk of agent-run
  code reading the claude process's environment is addressed by the sandbox
  (user decision 2026-11-02, over a key-less second step or a separate uid).
  Nothing here has run: the repository has no key, and the docs do not say
  whether bubblewrap works inside the privileged devcontainer on a
  GitHub-hosted runner, nor spell out the PID-namespace behaviour that would
  hide `/proc/<claude pid>/environ`. If bubblewrap cannot start, every
  Claude step fails and the issue becomes `needs-human`; the pipeline then
  stays unusable until the sandbox works rather than run without it. The
  scratch-repo procedure in the pull request checks both properties. The
  sandbox does not cover the file tools (the `permissions.deny` rules do),
  hooks or MCP servers. `github.com` stays reachable, so data sent there is
  not blocked, but without a write token in the fix/build jobs and with a
  read-only one in triage, nobody can retrieve it.
- Accepted residual risks: the devcontainer build for fix/build reads the
  branch's own `.devcontainer/`, verified equal to the default branch only at
  the merge base, not at its tip (an older, formerly trusted version may
  build); the live issue text is read at run time, so text edited after a
  maintainer's review is still seen (the confirm label pins the branch tip,
  not the issue text).
- Some legitimate fixes become `needs-human` notes: any change to CI,
  Makefiles, Dockerfiles, compose files, release or devcontainer scripts. The
  list is intentionally larger than the three named in the review; shrinking
  it is a one-line change in `moderate_check_paths.sh`.
- The wide deny-list is a deliberate decision (user, 2026-11-02).
- The base for a fix is the repro tip, which is not an ancestor of the
  default branch. The review asked for an ancestor-of-default check; `apply`
  applies it to triage and to a fix whose bot branch has been deleted, and
  checks "ancestor of the bot branch's tip" otherwise.
- Instances inherit all of it through the replace-tier `.github/scripts/`
  and the moderation workflows. An instance that set `MODERATION_EXTRA_TOOLS`
  keeps working; one that edited a moderation workflow resolves a merge by
  hand. None of this has been run end to end: the repository has no
  `ANTHROPIC_API_KEY`, and the workflows are exercised by CI only through
  the script tests and zizmor.
