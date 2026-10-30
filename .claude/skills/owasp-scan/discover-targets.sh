#!/usr/bin/env bash
# Print the owasp-scan target list for the repository in the current
# directory, one "<category><TAB><path>" line per file (read-only).
#
# Categories: python, tsjs, rust, workflow, docker, compose, shell, config.
# Each file lands in exactly one category (first match wins). Only
# git-tracked files are considered, so untracked and gitignored trees
# (node_modules, .venv, target, build output) never appear. Vendored and
# generated code, lockfiles (osv-scanner's job) and test files are dropped;
# pass --include-tests to keep the tests.
#
# Usage: discover-targets.sh [--include-tests] [--summary]
set -euo pipefail

include_tests=0
summary=0
for arg in "$@"; do
  case "$arg" in
    --include-tests) include_tests=1 ;;
    --summary) summary=1 ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

excluded() { # $1 = path; true when the file is never a target
  case "$1" in
    # lockfiles
    *package-lock.json|*pnpm-lock.yaml|*yarn.lock|*Cargo.lock|*uv.lock|*poetry.lock|*Pipfile.lock|*requirements*.lock|*.terraform.lock.hcl) return 0 ;;
    # vendored / generated / build output
    node_modules/*|*/node_modules/*|vendor/*|*/vendor/*|third_party/*|*/third_party/*) return 0 ;;
    dist/*|*/dist/*|build/*|*/build/*|target/*|*/target/*|generated/*|*/generated/*|__generated__/*|*/__generated__/*) return 0 ;;
    *.dockerignore|*.min.js|*.min.css|*.d.ts|*.map|*_pb2.py|*_pb2_grpc.py|*.generated.*|*.gen.ts|*.gen.rs) return 0 ;;
  esac
  if [ "$include_tests" -eq 0 ]; then
    case "$1" in
      tests/*|*/tests/*|test/*|*/test/*|__tests__/*|*/__tests__/*|e2e/*|*/e2e/*) return 0 ;;
      *.test.*|*.spec.*|*_test.py|*/test_*.py|test_*.py|*_test.rs) return 0 ;;
    esac
  fi
  return 1
}

categorise() { # $1 = path; prints a category, or nothing
  local base=${1##*/}
  case "$1" in
    .github/workflows/*.yml|.github/workflows/*.yaml) echo workflow; return ;;
    .github/actions/*/action.yml|.github/actions/*/action.yaml) echo workflow; return ;;
  esac
  case "$base" in
    Dockerfile|Dockerfile.*|*.Dockerfile|Containerfile|Containerfile.*) echo docker; return ;;
    compose.yml|compose.yaml|compose.*.yml|compose.*.yaml|docker-compose*.yml|docker-compose*.yaml) echo compose; return ;;
    *.sh|*.bash) echo shell; return ;;
    *.py) echo python; return ;;
    *.ts|*.tsx|*.js|*.jsx|*.mjs|*.cjs|*.mts|*.cts) echo tsjs; return ;;
    *.rs) echo rust; return ;;
    # app / BFF / proxy / realm configuration (not package manifests)
    *.conf|Caddyfile|.env|.env.*|*.env|*realm*.json|*.properties) echo config; return ;;
  esac
  case "$1" in
    bff/*|*/bff/*|config/*|*/config/*|conf/*|*/conf/*)
      case "$base" in *.json|*.yml|*.yaml|*.toml|*.ini) echo config; return ;; esac ;;
  esac
}

emit() {
  local f kind
  while IFS= read -r f; do
    [ -f "$f" ] || continue
    if excluded "$f"; then continue; fi
    kind=$(categorise "$f")
    if [ -n "$kind" ]; then printf '%s\t%s\n' "$kind" "$f"; fi
  done < <(git ls-files)
}

if [ "$summary" -eq 1 ]; then
  emit | cut -f1 | sort | uniq -c | sort -rn
else
  emit | sort
fi
