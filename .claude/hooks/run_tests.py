#!/usr/bin/env python3
"""Claude Code Stop hook: run the test suite when Python files changed.

Catches the regression before the agent hands the turn back, rather than at
commit time. Does nothing when the working tree has no Python change, so a
documentation or config turn stays instant.

Wired from ``.claude/settings.json``:

    "Stop": [{"hooks": [{"type": "command",
                         "command": "python3 .claude/hooks/run_tests.py"}]}]

Set ``IALAB_SKIP_TEST_HOOK=1`` to disable it for a session (long refactors where
a red suite is expected for a while).
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# A suite that runs longer than this is not a Stop-hook candidate.
_TIMEOUT_SECONDS = 300

# Directories holding a test suite, in the order they are usually found.
_TEST_DIRS = ("tests", "app/tests")


def _changed_python_files() -> list[str]:
    """List the Python files modified in the working tree.

    Returns:
        Paths reported by git, or an empty list outside a git repository.
    """
    if shutil.which("git") is None:
        return []
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return []
    if result.returncode != 0:
        return []
    files = []
    for line in result.stdout.splitlines():
        path = line[3:].strip()
        if path.endswith(".py") and "/tests/" not in path:
            files.append(path)
    return files


def _test_target() -> str | None:
    """Find the directory holding the test suite.

    Returns:
        A path to pass to pytest, or None when the repo has no test suite.
    """
    return next((d for d in _TEST_DIRS if Path(d).is_dir()), None)


def _already_ran() -> bool:
    """Check whether this hook already fired for the current turn.

    The Stop hook can be re-entered when the agent continues after a failure;
    re-running a full suite each time would stall the session.

    Returns:
        True when a stop-hook run is already in progress.
    """
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return False
    return bool(payload.get("stop_hook_active"))


def _should_run() -> bool:
    """Decide whether running the suite is worth it for this turn.

    Returns:
        True when the turn touched Python code in a repo that has tests.
    """
    if os.getenv("IALAB_SKIP_TEST_HOOK") == "1" or _already_ran():
        return False
    if not _changed_python_files():
        return False
    return _test_target() is not None


def main() -> int:
    """Run the suite when relevant and report failures to the agent.

    Returns:
        0 when the suite passes or is skipped, 2 when tests fail.
    """
    if not _should_run():
        return 0

    target = _test_target()
    prefix = ["poetry", "run"] if Path("pyproject.toml").exists() and shutil.which("poetry") else []
    if not prefix and shutil.which("pytest") is None:
        return 0

    try:
        result = subprocess.run(
            [*prefix, "pytest", target, "-q", "--no-header"],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
            check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return 0

    if result.returncode == 0:
        return 0

    print(f"Tests fail after this change ({target}):", file=sys.stderr)
    for line in result.stdout.splitlines()[-30:]:
        print(f"  {line}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
