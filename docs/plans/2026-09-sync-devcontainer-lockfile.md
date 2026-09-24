# Keep the devcontainer lockfile in sync with devcontainer.json

## Status

Draft

## Goal

Renovate PR #4 (commit `4e0e1c3`) bumped the `docker-in-docker` feature
from `4.1.0` to `4.1.1` in `.devcontainer/devcontainer.json`, but Renovate
never regenerates `.devcontainer/devcontainer-lock.json`. The PR
automerged with CI green, so `main` still has a lockfile pinning `4.1.0`.
This plan commits the corrected lockfile and adds a prek hook so any
future mismatch fails Checks. A failing check also stops Renovate from
automerging.

## Approach

Do the steps in order. Each step names the exact files to touch; don't
edit anything else. Before editing any file, read every `README.md` on
its path, per `CLAUDE.md`'s "Before writing anything" (for
`.github/`, the directory doc is `CONTENTS.md`).

### 1. Commit the already-regenerated lockfile

The working tree already has the correct lockfile: a devcontainer rebuild
regenerated it. Confirm before relying on it:

```sh
git diff .devcontainer/devcontainer-lock.json
```

Expected: the only change is the key/`version` going from
`docker-in-docker:4.1.0` to `docker-in-docker:4.1.1`, plus a new
`resolved`/`integrity` digest
(`sha256:2b44bcb32e75d5a3c028479f7f957cf7d5e42d81761373025a8d501dd3748f88`).
If the diff shows anything else, or no diff at all, stop and report back
instead of continuing. Don't hand-edit the digest.

Don't commit yet. The whole plan ships as one change (see step 6).

### 2. Add the check script

Create `.github/scripts/check_devcontainer_lock.py` with exactly this
content. It follows `template_sync_manifest.py`'s style (stdlib only,
`::error::` lines, `main()` returning an exit code):

```python
#!/usr/bin/env python3
"""Check that ``.devcontainer/devcontainer-lock.json`` matches ``devcontainer.json``.

Renovate bumps a feature's version tag in ``devcontainer.json`` but never
regenerates the lockfile, so without this check a feature bump can
automerge with the lockfile still pinning the old version and digest.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEVCONTAINER_DIR = Path(__file__).parent.parent.parent / ".devcontainer"


def remote_features(config: dict) -> set[str]:
    """Return ``config``'s feature references, minus local ``./`` ones (never locked)."""
    return {ref for ref in config.get("features", {}) if not ref.startswith(("./", "../"))}


def check(config_path: Path, lock_path: Path) -> list[str]:
    """Return one error message per feature reference present in only one of the files."""
    wanted = remote_features(json.loads(config_path.read_text()))
    locked: set[str] = set()
    if lock_path.exists():
        locked = set(json.loads(lock_path.read_text()).get("features", {}))
    errors = [f"{ref}: in {config_path} but not in {lock_path}" for ref in sorted(wanted - locked)]
    errors += [f"{ref}: in {lock_path} but not in {config_path}" for ref in sorted(locked - wanted)]
    return errors


def main() -> int:
    """Run the lockfile-consistency check and print any errors."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEVCONTAINER_DIR / "devcontainer.json")
    parser.add_argument("--lock", type=Path, default=DEVCONTAINER_DIR / "devcontainer-lock.json")
    args = parser.parse_args()

    errors = check(args.config, args.lock)
    if errors:
        for error in errors:
            print(f"::error::{error}", file=sys.stderr)
        print(
            f"{args.lock} is out of date -- regenerate it with "
            "`npx @devcontainers/cli upgrade --workspace-folder .` (or by "
            "rebuilding the devcontainer) and commit the result.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Make it executable to match its sibling: `chmod +x
.github/scripts/check_devcontainer_lock.py`.

`.github/template-sync-manifest.yml` needs no change, because
`.github/scripts/` is already covered by the `replace` tier. The
`template-sync-manifest` hook in step 5 confirms this.

### 3. Register the hook

In `.pre-commit-config.yaml`, append a second hook to the existing
`- repo: local` block's `hooks:` list, after `template-sync-manifest`:

```yaml
      - id: devcontainer-lock
        name: devcontainer-lock (lockfile matches devcontainer.json features)
        entry: python3 .github/scripts/check_devcontainer_lock.py
        language: system
        files: ^\.devcontainer/devcontainer(-lock)?\.json$
        pass_filenames: false
        stages: [pre-commit, manual]
```

`.github/workflows/checks.yml` needs no change, because it already runs
every `manual`-stage hook.

### 4. Document it

Keep each edit to the wording given here. Don't expand it.

- `.github/scripts/README.md`: add a bullet after the
  `template_sync_manifest.py` one:
  > - `check_devcontainer_lock.py` — checks that every remote feature in
  >   `../../.devcontainer/devcontainer.json` has a matching entry in
  >   `devcontainer-lock.json` and vice versa; backs the
  >   `devcontainer-lock` prek hook.
- `.devcontainer/README.md`: add a bullet at the end of the `## Do`
  list:
  > - Commit `devcontainer-lock.json` in the same change as any feature
  >   edit in `devcontainer.json`. Regenerate it with
  >   `npx @devcontainers/cli upgrade --workspace-folder .`, or by
  >   rebuilding the devcontainer. Renovate bumps feature versions but
  >   never regenerates this file, so its feature-bump PRs fail the
  >   `devcontainer-lock` check (and don't automerge) until someone
  >   pushes the regenerated lockfile to the Renovate branch.
- `.github/CONTENTS.md`: at the end of the `renovate.json` bullet,
  append one sentence:
  > Devcontainer feature bumps are the exception: they need a manual
  > lockfile regeneration first (see `../.devcontainer/README.md`).
- `docs/TEMPLATE.md`, `## Checks` section, first paragraph: change
  "and the `template-sync-manifest` completeness check." to
  "the `template-sync-manifest` completeness check, and the
  `devcontainer-lock` lockfile-consistency check."

### 5. Verify

Show the actual output of each command in your report.

1. Full suite passes, with the lockfile from step 1 in place:
   ```sh
   prek run --all-files --hook-stage manual
   ```
   Expected: every hook `Passed` (or `Skipped`), including
   `devcontainer-lock` and `template-sync-manifest`.
2. The check catches the original bug. Run it against the stale
   lockfile still on `HEAD`:
   ```sh
   git show HEAD:.devcontainer/devcontainer-lock.json > "$TMPDIR/stale-lock.json"
   python3 .github/scripts/check_devcontainer_lock.py --lock "$TMPDIR/stale-lock.json"; echo "exit=$?"
   ```
   Use your scratchpad directory for `$TMPDIR`. Expected: two
   `::error::` lines (`...:4.1.1: in ... but not in ...` and
   `...:4.1.0: in ... but not in ...`), the regenerate hint, and
   `exit=1`.
3. Confirm the hint's command is real (the CLI isn't installed in the
   devcontainer, so `npx` downloads it):
   ```sh
   npx --yes @devcontainers/cli upgrade --help
   ```
   If `upgrade` isn't a valid subcommand, stop and report back rather
   than changing the wording on your own.

If anything fails, fix the root cause. Don't weaken the check or skip a
hook (see `CLAUDE.md`'s "Address root causes").

### 6. Hand off

- Delete this plan file. It records no decision worth an ADR (see
  `README.md` in this directory).
- Don't commit. Give the user this commit message:
  ```
  fix(devcontainer): sync lockfile and check it against devcontainer.json

  - Commit devcontainer-lock.json regenerated for docker-in-docker 4.1.1
    (Renovate #4 bumped devcontainer.json only)
  - Add devcontainer-lock prek hook (.github/scripts/check_devcontainer_lock.py)
    so a stale lockfile fails Checks and blocks Renovate automerge
  - Document the manual regeneration step for Renovate feature bumps
  ```
- Tell the user that `template-fastapi` has the same stale lockfile on
  its `main`, and that the hook reaches it (and `template-react` and
  `template-axum`) only through template sync. Its current mismatch
  will then fail its Checks until that repo's lockfile is regenerated
  too.
