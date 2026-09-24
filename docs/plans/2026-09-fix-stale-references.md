# Fix stale references inherited from template-fastapi

## Status

Draft

## Goal

`template-base` was seeded from `template-fastapi` (commit `e1e71a7`).
Several comments and docs still point at files, services, and settings
that exist only there, or nowhere at all. This plan rewrites them to
describe `template-base` as it is. Every file touched is in the
`replace` tier of `.github/template-sync-manifest.yml`, so these edits
overwrite every instance's copy on its next template sync. That means
the new wording has to hold for *any* instance: `template-fastapi`,
`template-react`, `template-axum`. Don't name an instance-specific
service, file, or tool.

## Approach

Only comment and documentation text changes. Don't change any YAML key,
command, or JSON value. Before editing, read every `README.md` on each
file's path, per `CLAUDE.md`'s "Before writing anything" (for
`.github/`, the directory doc is `CONTENTS.md`). For each edit below,
replace the quoted old text with the new text exactly. If the old text
isn't found verbatim, stop and report back. Don't guess at a nearby
match.

This plan is independent of `2026-09-sync-devcontainer-lockfile.md`.
The two touch different lines, so they can run in either order.

### 1. `.github/workflows/checks.yml`: cache-warming comment

There's no `api` service here. The dev service is `app`, and instances
may name theirs differently, so don't name it at all. The linked plan
file doesn't exist in any craftainer repo.

Old:
```yaml
      # Warms the Buildx layer cache for the devcontainer image (the
      # `develop` stage below) before devcontainers/ci builds it via
      # `docker compose build`. Same context/target/Dockerfile as
      # .devcontainer/compose.yml's `api` service, so cache keys line up;
      # no push/load since this step only needs to populate the cache, not
      # produce a usable image. See docs/plans/2026-09-speed-up-checks-devcontainer-build.md.
```

New:
```yaml
      # Warms the Buildx layer cache for the devcontainer image (the
      # `develop` stage below) before devcontainers/ci builds it via
      # `docker compose build`. Same context/target/Dockerfile as the dev
      # service in .devcontainer/compose.yml, so cache keys line up; no
      # push/load since this step only needs to populate the cache, not
      # produce a usable image.
```

### 2. `.github/workflows/checks.yml`: teardown comment

The teardown command selects the stack by project name (`-p`) alone and
passes no compose file list. So there's no list to "keep in sync", and
`.devcontainer/stack/README.md` doesn't exist in `template-base`.

Old:
```yaml
      # devcontainers/ci starts the full compose stack (see
      # .devcontainer/devcontainer.json's dockerComposeFile) but never
      # tears it down -- that's fine for a throwaway CI VM, but this repo
      # wants a clean, explicit teardown regardless. Keep this file list
      # in sync with dockerComposeFile (see .devcontainer/stack/README.md's
      # "Devcontainer stack pattern").
```

New:
```yaml
      # devcontainers/ci starts the full compose stack (see
      # .devcontainer/devcontainer.json's dockerComposeFile) but never
      # tears it down -- that's fine for a throwaway CI VM, but this repo
      # wants a clean, explicit teardown regardless. Selecting the stack
      # by project name alone (no -f list) also covers any services an
      # instance adds through compose.yml's `include:`.
```

### 3. `.devcontainer/compose.yml`: ports comment

`devcontainer.json` has no `forwardPorts`, and the root `README.md` has
no "Don't" section. The rule lives in `.devcontainer/README.md`'s
"Don't".

Old:
```yaml
    # No ports: mapping and no networks: block — see the root README's
    # "Don't". Host access comes from devcontainer.json's forwardPorts;
    # an instance with backing services reaches them by name on the
    # default network compose generates for this project.
```

New:
```yaml
    # No ports: mapping and no networks: block — see .devcontainer/
    # README.md's "Don't". An instance that needs host access adds
    # forwardPorts to devcontainer.json; one with backing services
    # reaches them by name on the default network compose generates for
    # this project.
```

This edit only touches a comment, so it takes effect without a
devcontainer rebuild. Mention that to the user anyway, per `CLAUDE.md`.

### 4. `.devcontainer/README.md`: `devcontainer.json` bullet

`devcontainer.json` configures no forwarded ports. It does configure
mounts (the SSH agent socket).

Old:
```markdown
  (features, forwarded ports, editor settings).
```

New:
```markdown
  (features, mounts, editor settings).
```

### 5. `.github/scripts/README.md`: delete the tests rule

`template-base` has no `tests/` directory, and no instance tests these
scripts. The user decided to delete the rule outright, without a
replacement. Delete exactly this line from the `## Do` list:

```markdown
- Add a test in `../../tests/` for any new logic here that isn't trivial.
```

The `## Do` list keeps its other bullet ("Keep scripts here
dependency-free ..."), so leave the heading in place.

### 6. Verify

Show the actual output of each command in your report.

1. None of the stale references remain:
   ```sh
   grep -rnE '`api` service|speed-up-checks|\.devcontainer/stack/README\.md|root README|forwarded ports|\.\./\.\./tests/' .github .devcontainer
   ```
   Expected: no output. (`.devcontainer/README.md` still says
   `` `stack/README.md`'s ... once an instance adds one ``. That wording
   is correct, conditional phrasing, and the pattern deliberately
   doesn't match it.)
2. Only comments and prose changed:
   ```sh
   git diff --stat
   git diff -U0 -- '*.yml' | grep -E '^[+-][^+-]' | grep -vE '^[+-]\s*#'
   ```
   Expected: `--stat` lists exactly the four files above, and the second
   command prints nothing (no non-comment YAML line changed).
3. Full suite passes:
   ```sh
   prek run --all-files --hook-stage manual
   ```

If a check fails, fix the root cause (see `CLAUDE.md`'s "Address root
causes").

### 7. Hand off

- Delete this plan file. Nothing here needs an ADR.
- Don't commit. Give the user this commit message:
  ```
  docs: fix stale references inherited from template-fastapi

  - checks.yml: drop nonexistent `api` service, plan link, and stack/README pointer
  - compose.yml: point the ports rule at .devcontainer/README.md, not a nonexistent forwardPorts
  - .devcontainer/README.md: devcontainer.json configures mounts, not forwarded ports
  - .github/scripts/README.md: drop the rule requiring tests in a nonexistent tests/
  ```
- Tell the user that `template-fastapi`'s `checks.yml` has the same
  dangling plan link, and that template sync will fix it there.
