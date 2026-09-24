# Let an instance classify its own files for the manifest check

## Status

In progress

## Goal

An instance that isn't itself a template (e.g. `craftainer/.github` with
`profile/` and `brand/`) can't list its own files in
`.github/template-sync-manifest.yml`: that file is `replace`-tier, so a
local edit is overwritten on the next sync, and the
`template-sync-manifest` hook fails on any unlisted path. Give instances
an instance-owned place to classify their own files.

## Approach

1. `template_sync_manifest.py`'s `check()` also reads
   `.github/template-sync-manifest.local.yml` (next to the manifest)
   when it exists, and appends its `ignore` patterns to the manifest's.
   Only `ignore` is allowed there; `replace`/`merge` entries are an
   error. `template_sync.py` keeps using `parse_manifest` on the
   template's manifest alone, so the local file never affects sync
   decisions.
2. Add `.github/template-sync-manifest.local.yml` to the manifest's
   `ignore` tier so the local file itself is classified and never synced.
3. Document it in `docs/TEMPLATE.md`'s "Template sync" section,
   `.github/scripts/README.md`, and the manifest's header.
4. Cut `v1.1.0` (release workflow, by hand — not done by this plan).

## Open questions

None. Adding `profile/` and `brand/` to base's own `ignore` tier was
rejected: it puts repo-specific paths in the shared base.
