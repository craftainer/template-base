# scripts/

- `develop.sh` — the Dockerfile's `develop`-stage setup: installs `prek`,
  the Claude Code CLI, and `snip`, the only tooling this template requires
  regardless of instance language. An instance adds its own language
  runtime/tooling install on top, either by extending this script or
  copying its shape into a second one invoked from the instance's own
  `Dockerfile` layer. Prefer the hook below over either.
- `post-create.sh` — the devcontainer's `postCreateCommand`: git
  `safe.directory`, `prek install`, then every `post-create.d/*.sh`.
- `develop.d/`, `post-create.d/` — instance hook directories, empty apart
  from their own `README.md`; see `docs/TEMPLATE.md`'s "Instance extension
  points".

## Do

- Keep this script's own tools pinned to an exact version (a `# renovate:`
  ARG in the Dockerfile) and checksum-verified where the upstream project
  publishes checksums, matching the pattern each install step here already
  follows.

## Don't

- Add a language runtime or stack-specific tool here — that belongs in the
  instance's own layer (`develop.d/`), not the base template's.
