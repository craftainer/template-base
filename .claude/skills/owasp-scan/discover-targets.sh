#!/usr/bin/env bash
# Print the owasp-scan target list for the repository in the current
# directory, one "<category><TAB><path>" line per file (read-only).
#
# Categories: python, tsjs, rust, workflow, docker, compose, shell, config.
# Each file lands in exactly one category (first match wins). Only
# git-tracked files are considered, so untracked and gitignored trees never
# appear. Nothing is dropped silently: every tracked file that is not a
# target is counted under a reason (see --summary and --skipped).
#
# Dropped, with a reason each:
#   lockfile      osv-scanner's job
#   vendored      node_modules/, vendor/, third_party/, __generated__/ at any depth
#   build-output  dist/, build/, target/, generated/ at the repo root or
#                 directly inside a package root (a directory holding
#                 package.json, Cargo.toml, pyproject.toml or go.mod);
#                 hand-written dirs such as scripts/build/ are kept
#   generated     *.min.js, *.d.ts, *.map, *_pb2.py, *.generated.*, ...
#   tests         test directories and files (keep with --include-tests)
#   binary        non-text file
#   uncategorised text file matching no category (docs, markdown, ...);
#                 review this count: it is where a missed file type shows up
#
# Usage: discover-targets.sh [--include-tests] [--summary] [--skipped]
#   (default)  targets on stdout as "<category><TAB><path>", sorted
#   --summary  target counts per category, then "not-scanned <reason> <n>"
#   --skipped  "skip:<reason><TAB><path>" for every non-target tracked file
set -euo pipefail

include_tests=0
mode=targets
for arg in "$@"; do
  case "$arg" in
    --include-tests) include_tests=1 ;;
    --summary) mode=summary ;;
    --skipped) mode=skipped ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

# Directories (repo-relative, "" = root) that hold a package manifest.
declare -A pkgroot=([.]=1)
while IFS= read -r -d '' f; do
  case "${f##*/}" in
    package.json|Cargo.toml|pyproject.toml|go.mod) d=${f%/*}; [ "$d" = "$f" ] && d="."; pkgroot[$d]=1 ;;
  esac
done < <(git ls-files -z)

in_build_output() { # $1 = path; true when a build dir sits at a package root
  local rest=$1 prefix="" seg
  while [[ $rest == */* ]]; do
    seg=${rest%%/*}
    rest=${rest#*/}
    case "$seg" in
      dist|build|target|generated)
        [ -n "${pkgroot[${prefix:-.}]:-}" ] && return 0 ;;
    esac
    prefix=${prefix:+$prefix/}$seg
  done
  return 1
}

skip_reason() { # $1 = path; prints a reason when the file is never a target
  case "$1" in
    *package-lock.json|*pnpm-lock.yaml|*yarn.lock|*Cargo.lock|*uv.lock|*poetry.lock|*Pipfile.lock|*requirements*.lock|*.terraform.lock.hcl) echo lockfile; return ;;
    node_modules/*|*/node_modules/*|vendor/*|*/vendor/*|third_party/*|*/third_party/*|__generated__/*|*/__generated__/*) echo vendored; return ;;
    *.min.js|*.min.css|*.d.ts|*.map|*_pb2.py|*_pb2_grpc.py|*.generated.*|*.gen.ts|*.gen.rs) echo generated; return ;;
  esac
  if in_build_output "$1"; then echo build-output; return; fi
  if [ "$include_tests" -eq 0 ]; then
    case "$1" in
      tests/*|*/tests/*|test/*|*/test/*|__tests__/*|*/__tests__/*|e2e/*|*/e2e/*) echo tests; return ;;
      *.test.*|*.spec.*|*_test.py|*/test_*.py|test_*.py|*_test.rs) echo tests; return ;;
    esac
  fi
  return 0
}

shebang_kind() { # $1 = path; category from an interpreter line, or nothing
  local first=""
  IFS= read -r first < "$1" 2>/dev/null || true
  case "$first" in
    '#!'*sh*|'#!'*bash*|'#!'*zsh*) echo shell ;;
    '#!'*python*) echo python ;;
    '#!'*node*|'#!'*deno*|'#!'*bun*) echo tsjs ;;
  esac
}

categorise() { # $1 = path; prints a category, or nothing
  local base=${1##*/}
  case "$1" in
    .github/workflows/*.yml|.github/workflows/*.yaml) echo workflow; return ;;
    */action.yml|*/action.yaml|action.yml|action.yaml) echo workflow; return ;;
  esac
  case "$base" in
    Dockerfile|Dockerfile.*|*.Dockerfile|Containerfile|Containerfile.*) echo docker; return ;;
    compose.yml|compose.yaml|compose.*.yml|compose.*.yaml|docker-compose*.yml|docker-compose*.yaml) echo compose; return ;;
    *.sh|*.bash|*.zsh|Makefile|GNUmakefile|*.mk) echo shell; return ;;
    *.py) echo python; return ;;
    *.ts|*.tsx|*.js|*.jsx|*.mjs|*.cjs|*.mts|*.cts) echo tsjs; return ;;
    *.rs) echo rust; return ;;
    # package manifests and tooling schemas carry no app/BFF/proxy settings
    package.json|tsconfig*.json|jsconfig*.json|Cargo.toml|pyproject.toml|*.schema.json) return ;;
    # app / BFF / proxy / realm / devcontainer / CI-tool configuration, wherever it lives
    *.conf|Caddyfile|.env|.env.*|*.env|*.properties|*.yml|*.yaml|*.json|*.jsonc|*.toml|*.ini|*.cfg) echo config; return ;;
  esac
  # extensionless scripts (e.g. .github/scripts/foo) by interpreter line
  case "$base" in
    *.*) ;;
    *) shebang_kind "$1"; return ;;
  esac
}

emit() { # prints "<category-or-skip:reason>\t<path>" for every tracked file
  local f reason kind
  while IFS= read -r -d '' f; do
    [ -f "$f" ] || { printf 'skip:missing\t%s\n' "$f"; continue; }
    reason=$(skip_reason "$f")
    if [ -n "$reason" ]; then printf 'skip:%s\t%s\n' "$reason" "$f"; continue; fi
    if ! grep -Iq . "$f" 2>/dev/null; then
      # empty files also fail grep -I .; only non-empty ones are binary
      if [ -s "$f" ]; then printf 'skip:binary\t%s\n' "$f"; else printf 'skip:empty\t%s\n' "$f"; fi
      continue
    fi
    kind=$(categorise "$f")
    if [ -n "$kind" ]; then printf '%s\t%s\n' "$kind" "$f"; else printf 'skip:uncategorised\t%s\n' "$f"; fi
  done < <(git ls-files -z)
}

case "$mode" in
  targets) emit | grep -v '^skip:' | sort || true ;;
  skipped) emit | grep '^skip:' | sort || true ;;
  summary)
    all=$(emit)
    printf '%s\n' "$all" | grep -v '^skip:' | cut -f1 | sort | uniq -c | sort -rn || true
    printf '%s\n' "$all" | grep '^skip:' | cut -f1 | sort | uniq -c | sed -E 's/^ *([0-9]+) skip:(.*)$/not-scanned \2 \1/' || true
    ;;
esac
