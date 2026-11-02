"""Tests for ``moderate_apply_triage.sh`` (the privileged apply step of the triage workflows)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from test_moderate_apply_result import BASE, FAKE_GH, FAKE_GIT, REMOTE

SCRIPTS = Path(__file__).resolve().parent
NEEDS_HUMAN = "gh issue edit 7 --add-label needs-human"
COMMENT = "gh issue comment 7 --body looks reproducible"


def setup_calls(branch: str, result: Path) -> list[str]:
    """Return the git calls that build, then check, the branch from the patch."""
    return [
        "git config user.name claude-moderator[bot]",
        "git config user.email claude-moderator[bot]@users.noreply.github.com",
        f"git fetch --depth=1 -- origin {BASE}",
        f"git checkout -B {branch} FETCH_HEAD --",
        f"git am -- {result}/patch.diff",
        f"git diff --raw -z --no-renames {BASE} HEAD --",
    ]


@unittest.skipUnless(shutil.which("jq"), "jq not installed (the script parses meta.json with it)")
class ApplyTriageTest(unittest.TestCase):
    """What a triage result may do: comment, one fixed label, and a checked branch push."""

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
        self,
        action: str,
        kind: str = "bug",
        comment: str = "looks reproducible",
        fail: str = "",
        remote_sha: str = "",
        run_env: dict[str, str] | None = None,
        meta_extra: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run the script against a canned ``meta.json``."""
        meta = {
            "issue_number": "7",
            "base_sha": BASE,
            "action": action,
            "comment": comment,
            **(meta_extra or {}),
        }
        (self.result / "meta.json").write_text(json.dumps(meta))
        env = {
            **os.environ,
            "PATH": f"{self.tmp / 'bin'}{os.pathsep}{os.environ['PATH']}",
            "FAKE_LOG": str(self.tmp / "log.txt"),
            "FAKE_FAIL": fail,
            "FAKE_REMOTE_SHA": remote_sha,
            "GITHUB_SERVER_URL": "https://github.com",
            "GITHUB_REPOSITORY": "o/r",
            "GITHUB_RUN_ID": "99",
            "DEFAULT_BRANCH": "main",
            "ISSUE_NUMBER": "7",
            **(run_env or {}),
        }
        return subprocess.run(  # noqa: S603 -- fixed argv, trusted script
            [str(SCRIPTS / "moderate_apply_triage.sh"), kind, str(self.result)],
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

    def test_needs_info_only_comments_and_labels(self) -> None:
        """No branch work at all: the comment, then the table's label."""
        proc = self.run_script("needs-info")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.log(), [COMMENT, "gh issue edit 7 --add-label bug:needs-info"])

    def test_cannot_reproduce_flags_needs_human(self) -> None:
        """The give-up outcome maps to needs-human, still with its comment."""
        proc = self.run_script("cannot-reproduce")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.log(), [COMMENT, NEEDS_HUMAN])

    def test_repro_ready_pushes_the_checked_branch_first(self) -> None:
        """Branch built from the patch, checked and pushed (leased on absence) before the comment."""
        proc = self.run_script("repro-ready")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        branch = "bug/7-repro"
        self.assertEqual(
            self.log(),
            [
                f"git ls-remote -- origin refs/heads/{branch}",
                f"gh api repos/o/r/compare/{BASE}...main --jq .status",
                *setup_calls(branch, self.result),
                f"git push --force-with-lease={branch}: -- origin {branch}",
                "gh issue comment 7 --body looks reproducible",
                "",
                f"Branch diff: https://github.com/o/r/compare/main...{branch}",
                "gh issue edit 7 --add-label bug:repro-ready",
            ],
        )

    def test_feature_plan_ready(self) -> None:
        """The feature kind uses its own branch and label."""
        proc = self.run_script("plan-ready", kind="feature")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        log = self.log()
        self.assertIn("git push --force-with-lease=feature/7-plan: -- origin feature/7-plan", log)
        self.assertEqual(log[-1], "gh issue edit 7 --add-label enhancement:plan-ready")

    def test_unknown_action_acts_on_nothing_from_the_result(self) -> None:
        """An action outside the kind's table, or a bad shape, only flags needs-human."""
        for action in ("not-a-fit", "repro-ready; rm -rf /", "failed", "", "REPRO-READY", "x]"):
            with self.subTest(action=action):
                (self.tmp / "log.txt").unlink(missing_ok=True)
                proc = self.run_script(action)
                log = self.log()
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(log[0], NEEDS_HUMAN)
                self.assertEqual(len(log), 2, log)
                self.assertTrue(log[1].startswith("gh issue comment 7 --body Automated triage ended"))

    def test_result_labels_are_ignored(self) -> None:
        """Only the fixed table decides the label; a label field in the result is never read."""
        self.run_script("needs-info", meta_extra={"label": "claude:ok", "labels": "x"})
        edits = [c for c in self.log() if c.startswith("gh issue edit")]
        self.assertEqual(edits, ["gh issue edit 7 --add-label bug:needs-info"])

    def test_denied_path_blocks_the_push(self) -> None:
        """A repro touching the workflows is applied locally only; the issue gets needs-human."""
        diff = ":100644 100644 a b M\\0.github/workflows/release.yml\\0"
        proc = self.run_script("repro-ready", run_env={"FAKE_DIFF": diff})
        log = self.log()
        self.assertEqual(proc.returncode, 1)
        self.assertFalse([c for c in log if c.startswith("git push")])
        self.assertIn(NEEDS_HUMAN, log)
        self.assertNotIn("gh issue edit 7 --add-label bug:repro-ready", log)

    def test_bad_base_sha_never_reaches_git(self) -> None:
        """A non-hex base (including an option) fails before any fetch or api call."""
        for bad in ("--upload-pack=x", "abc", ""):
            with self.subTest(base_sha=bad):
                (self.tmp / "log.txt").unlink(missing_ok=True)
                proc = self.run_script("repro-ready", meta_extra={"base_sha": bad})
                log = self.log()
                self.assertEqual(proc.returncode, 1)
                self.assertFalse([c for c in log if c.startswith(("git", "gh api"))])
                self.assertIn(NEEDS_HUMAN, log)

    def test_base_not_on_default_branch(self) -> None:
        """A base that is not an ancestor of the default branch is refused."""
        proc = self.run_script("repro-ready", run_env={"FAKE_DIVERGED": "...main"})
        self.assertEqual(proc.returncode, 1)
        self.assertFalse([c for c in self.log() if c.startswith(("git push", "git fetch"))])

    def test_foreign_branch_is_not_overwritten(self) -> None:
        """An existing branch that does not descend from the base is left alone."""
        proc = self.run_script(
            "repro-ready", remote_sha=REMOTE, run_env={"FAKE_DIVERGED": f"...{REMOTE}"}
        )
        self.assertEqual(proc.returncode, 1)
        self.assertFalse([c for c in self.log() if c.startswith(("git push", "git fetch"))])

    def test_push_failure_flags_needs_human(self) -> None:
        """A failed push neither comments the result nor sets the stage label."""
        proc = self.run_script("repro-ready", fail="git push")
        log = self.log()
        self.assertEqual(proc.returncode, 1)
        self.assertNotIn("gh issue edit 7 --add-label bug:repro-ready", log)
        self.assertLess(
            log.index(NEEDS_HUMAN),
            next(i for i, c in enumerate(log) if c.startswith("gh issue comment 7")),
        )

    def test_comment_cannot_ping_users(self) -> None:
        """An @ in the model's comment is broken so it notifies nobody."""
        self.run_script("needs-info", comment="cc @octocat")
        comment = next(c for c in self.log() if c.startswith("gh issue comment 7"))
        self.assertNotIn("@octocat", comment)

    def test_result_for_another_issue_is_refused(self) -> None:
        """An artifact for a different issue changes nothing."""
        proc = self.run_script("needs-info", run_env={"ISSUE_NUMBER": "8"})
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(self.log(), [])


if __name__ == "__main__":
    unittest.main()
