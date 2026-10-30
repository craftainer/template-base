"""Tests for ``moderate_apply_result.sh`` (the privileged apply step of the moderation pipeline)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
# Both fakes append their argv (one line per call) to $FAKE_LOG. The fake gh
# answers `issue view` with $FAKE_LABELS; the fake git fails when its
# subcommand is $FAKE_GIT_FAIL.
FAKE_GH = """#!/usr/bin/env bash
echo "gh $*" >> "$FAKE_LOG"
if [ "$1 $2" = "issue view" ]; then printf '%s\\n' $FAKE_LABELS; fi
"""
FAKE_GIT = """#!/usr/bin/env bash
echo "git $*" >> "$FAKE_LOG"
[ "$1" != "${FAKE_GIT_FAIL:-}" ] || { echo "fake git: $1 failed" >&2; exit 1; }
"""

ARGS = ["bug", "repro", "bug:repro-ready", "bug:confirmed", "bug:fixed", "bug:confirm", "Fixes"]


@unittest.skipUnless(shutil.which("jq"), "jq not installed (the script parses meta.json with it)")
class ApplyResultTest(unittest.TestCase):
    """Argument order, success ordering and the failure path."""

    def setUp(self) -> None:
        """Put fake ``gh`` and ``git`` first on PATH inside a temp dir."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        for name, body in (("gh", FAKE_GH), ("git", FAKE_GIT)):
            exe = self.tmp / "bin" / name
            exe.parent.mkdir(exist_ok=True)
            exe.write_text(body)
            exe.chmod(0o755)
        self.result = self.tmp / "result"
        self.result.mkdir()

    def run_script(
        self, outcome: str = "built", labels: str = "bug bug:repro-ready", git_fail: str = ""
    ) -> subprocess.CompletedProcess[str]:
        """Run the script against a canned ``meta.json``."""
        meta = {
            "issue_number": "7",
            "base_sha": "abc123",
            "outcome": outcome,
            "subject": "fix: the thing",
            "body": "details",
        }
        (self.result / "meta.json").write_text(json.dumps(meta))
        env = {
            **os.environ,
            "PATH": f"{self.tmp / 'bin'}{os.pathsep}{os.environ['PATH']}",
            "FAKE_LOG": str(self.tmp / "log.txt"),
            "FAKE_LABELS": labels,
            "FAKE_GIT_FAIL": git_fail,
        }
        return subprocess.run(  # noqa: S603 -- fixed argv, trusted script
            [str(SCRIPTS / "moderate_apply_result.sh"), str(self.result), *ARGS],
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )

    def log(self) -> list[str]:
        """Return the recorded fake-command calls, in order."""
        path = self.tmp / "log.txt"
        return path.read_text().splitlines() if path.exists() else []

    def index(self, prefix: str) -> int:
        """Return the position of the first call starting with ``prefix``."""
        for i, line in enumerate(self.log()):
            if line.startswith(prefix):
                return i
        self.fail(f"no call starting with {prefix!r} in {self.log()}")

    def test_success_creates_pr_then_moves_stage(self) -> None:
        """The stage label moves only after the PR exists; args 7 and 8 are used correctly."""
        proc = self.run_script()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        log = self.log()
        self.assertIn("gh issue edit 7 --remove-label bug:confirm", log)  # arg 7
        pr = self.index("gh pr create")
        # arg 8: the PR body is multi-line, so its last line is logged on its own.
        self.assertIn("Fixes #7 --base main --head bug/7-repro", log[pr:])
        self.assertLess(self.index("git push"), pr)
        self.assertLess(pr, self.index("gh issue edit 7 --remove-label bug:repro-ready --add-label bug:confirmed"))
        self.assertLess(
            self.index("gh issue edit 7 --remove-label bug:repro-ready"),
            self.index("gh issue edit 7 --remove-label bug:confirmed --add-label bug:fixed"),
        )
        self.assertNotIn("gh issue edit 7 --add-label needs-human", log)

    def test_failure_keeps_ready_stage_and_flags_needs_human(self) -> None:
        """A failing push leaves the ready label alone, comments and adds needs-human."""
        proc = self.run_script(git_fail="push")
        self.assertEqual(proc.returncode, 1)
        log = self.log()
        self.assertFalse([c for c in log if c.startswith("gh pr create")])
        self.assertFalse([c for c in log if "--add-label bug:confirmed" in c or "--add-label bug:fixed" in c])
        self.assertFalse([c for c in log if "--remove-label bug:repro-ready" in c])
        self.assertTrue([c for c in log if c.startswith("gh issue comment 7")])
        self.assertIn("gh issue edit 7 --add-label needs-human", log)

    def test_not_built_outcome_comments_and_flags_needs_human(self) -> None:
        """A needs-human outcome posts Claude's explanation and does no git work."""
        proc = self.run_script(outcome="needs-human")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        log = self.log()
        self.assertFalse([c for c in log if c.startswith("git ")])
        self.assertTrue([c for c in log if c.startswith("gh issue comment 7")])
        self.assertIn("gh issue edit 7 --add-label needs-human", log)

    def test_already_processed_is_a_noop(self) -> None:
        """Without the ready label the script does nothing beyond consuming the confirm label."""
        proc = self.run_script(labels="bug")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse([c for c in self.log() if c.startswith(("git ", "gh pr", "gh issue comment"))])


if __name__ == "__main__":
    unittest.main()
