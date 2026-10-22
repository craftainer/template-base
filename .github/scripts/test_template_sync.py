"""Tests for ``template_sync.py`` and the executable bits CI relies on.

Stdlib ``unittest`` only (see this directory's README); run with
``python3 -m unittest discover -s .github/scripts -p 'test_*.py'`` -- the
``scripts-tests`` prek hook does exactly that.
"""

from __future__ import annotations

import re
import stat
import tempfile
import unittest
from pathlib import Path

import template_sync

REPO_ROOT = Path(__file__).resolve().parents[2]


def is_exec(path: Path) -> bool:
    # The mode bits, not os.access(): some bind-mounted filesystems report
    # every file as executable to os.access().
    return bool(path.stat().st_mode & stat.S_IXUSR)


def write(path: Path, content: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    path.chmod(mode)


class ApplyReplaceExecutableBitTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.old, self.new, self.instance = root / "old", root / "new", root / "instance"

    def apply(self, path: str) -> dict[str, list[str]]:
        return template_sync.apply_replace(self.old, self.new, self.instance, {path})

    def test_same_content_gains_executable_bit(self) -> None:
        # The v1.8.0 bug: the template fixed 644 -> 755 with no content change.
        write(self.old / "s.sh", b"#!/bin/sh\n", 0o644)
        write(self.new / "s.sh", b"#!/bin/sh\n", 0o755)
        write(self.instance / "s.sh", b"#!/bin/sh\n", 0o644)
        result = self.apply("s.sh")
        self.assertEqual(result["updated"], ["s.sh"])
        self.assertEqual(stat.S_IMODE((self.instance / "s.sh").stat().st_mode), 0o755)

    def test_same_content_loses_executable_bit(self) -> None:
        write(self.old / "s.sh", b"x\n", 0o755)
        write(self.new / "s.sh", b"x\n", 0o644)
        write(self.instance / "s.sh", b"x\n", 0o755)
        self.assertEqual(self.apply("s.sh")["updated"], ["s.sh"])
        self.assertFalse(is_exec(self.instance / "s.sh"))

    def test_identical_content_and_mode_is_not_reported(self) -> None:
        for root in (self.old, self.new, self.instance):
            write(root / "s.sh", b"x\n", 0o755)
        self.assertEqual(self.apply("s.sh"), {"updated": [], "removed": []})

    def test_changed_content_copies_the_executable_bit(self) -> None:
        write(self.old / "s.sh", b"a\n", 0o644)
        write(self.new / "s.sh", b"b\n", 0o755)
        write(self.instance / "s.sh", b"a\n", 0o644)
        self.assertEqual(self.apply("s.sh")["updated"], ["s.sh"])
        self.assertEqual((self.instance / "s.sh").read_bytes(), b"b\n")
        self.assertTrue(is_exec(self.instance / "s.sh"))

    def test_new_file_keeps_the_executable_bit(self) -> None:
        write(self.new / "s.sh", b"x\n", 0o755)
        self.instance.mkdir()
        self.assertEqual(self.apply("s.sh")["updated"], ["s.sh"])
        self.assertTrue(is_exec(self.instance / "s.sh"))


class DirectlyInvokedScriptsAreExecutableTest(unittest.TestCase):
    """A workflow step that names a script as the command needs mode 755 (exit 126 otherwise)."""

    # A script path at the start of a shell command: line start, or after a
    # `run:`/`runCmd:` key, `>-`/`|` aside. `bash x`, `python3 x` and
    # `$(...)` contexts don't match because the path isn't first.
    COMMAND_RE = re.compile(r"^\s*(?:(?:run|runCmd):\s*(?:[>|][-+]?\s*)?)?(\.github/scripts/[\w.-]+\.sh)\b")

    def test_every_directly_invoked_script_is_executable(self) -> None:
        invoked: set[str] = set()
        for workflow in (REPO_ROOT / ".github" / "workflows").glob("*.yml"):
            for line in workflow.read_text().splitlines():
                match = self.COMMAND_RE.match(line)
                if match:
                    invoked.add(match.group(1))
        self.assertTrue(invoked, "expected the moderate-* workflows to invoke scripts directly")
        for rel in sorted(invoked):
            self.assertTrue(is_exec(REPO_ROOT / rel), f"{rel} is not executable")

    def test_claude_hook_is_executable(self) -> None:
        # .claude/settings.json runs it directly as a hook command.
        self.assertTrue(is_exec(REPO_ROOT / ".claude" / "hooks" / "self-check.sh"))


if __name__ == "__main__":
    unittest.main()
