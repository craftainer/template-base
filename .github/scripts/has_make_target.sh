#!/usr/bin/env bash
# Whether the Makefile in the current directory defines a rule for a target,
# without running any recipe (not even `$(MAKE)` lines).
#
# Usage: has_make_target.sh TARGET
# Exit:  0 = defined, 1 = not defined, 2 = the Makefile failed to parse
#        (make's output is printed).
#
# Reads make's rule database (`make -p`, documented in the GNU make manual
# under "Summary of Options") through a goal that does not exist, with
# `-q` so nothing runs. A Makefile that fails to parse never reaches the
# dump (or ends in an error other than the probe's own). In the dump, `# Not a target:` marks a name that is only a
# prerequisite or file, which is not a rule.
set -u
target=${1:?usage: has_make_target.sh TARGET}
out=$(LC_ALL=C make -pqRr ".${target}-probe" 2>&1 || true)
# The probe goal itself always ends in "No rule to make target"; any other
# `***` error (a failed include, a bad recipe-prefix line) means the Makefile
# is broken, even when make still printed the rule database.
if ! grep -q '^# Make data base' <<< "$out" ||
  grep -F '***' <<< "$out" | grep -qvF ".${target}-probe"; then
  echo "$out"
  exit 2
fi
awk -v t="$target" '
  /^# Not a target:/ { nt = 1; next }
  index($0, t ":") == 1 && !nt { found = 1 }
  { nt = 0 }
  END { exit !found }
' <<< "$out"
