#!/usr/bin/env python3
"""Claude Code PostToolUse hook: format and lint the file that was just edited.

Runs on the edited file only, so it stays fast enough to sit on every Edit/Write.
Formatters are applied in place; the linter's findings are reported back to the
agent (exit code 2) so it fixes them in the same turn instead of discovering them
at commit time.

Wired from ``.claude/settings.json``:

    "PostToolUse": [{"matcher": "Edit|Write|MultiEdit",
                     "hooks": [{"type": "command",
                                "command": "python3 .claude/hooks/lint_edited_file.py"}]}]

Skips silently when the project does not use the tool in question, so the same
hook works on a Python backend and on a Next.js frontend.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

_MANIFEST = Path(".ialab-standards.json")

# Directories whose content is never ours to lint.
_IGNORED_PARTS = {".venv", "node_modules", "__pycache__", ".git", "migrations", "alembic"}

_PYTHON_SUFFIXES = {".py"}
_FRONTEND_SUFFIXES = {".ts", ".tsx", ".js", ".jsx"}

# A hook must never hang a turn.
_TIMEOUT_SECONDS = 60


def _read_edited_path() -> Path | None:
    """Extract the edited file path from the hook payload on stdin.

    Returns:
        The path, or None when the payload carries no usable file path.
    """
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return None
    raw = (payload.get("tool_input") or {}).get("file_path")
    return Path(raw) if raw else None


def _vendored_paths() -> set[str]:
    """Read the paths of the checksum-managed files of this repo.

    Returns:
        Repo-relative paths listed in ``.ialab-standards.json``, or an empty set.
    """
    if not _MANIFEST.exists():
        return set()
    try:
        return set(json.loads(_MANIFEST.read_text(encoding="utf-8")).get("files", {}).values())
    except (json.JSONDecodeError, OSError):
        return set()


def _is_ours(path: Path) -> bool:
    """Check the file is inside the project and safe to reformat.

    Args:
        path: Edited file path.

    Returns:
        True when the file should be linted.
    """
    if not path.exists() or not path.is_file():
        return False
    if _IGNORED_PARTS & set(path.parts):
        return False
    try:
        relative = path.relative_to(Path.cwd())
    except ValueError:
        return False
    # Vendored files carry a checksum: reformatting one would break its stamp
    # and fail the ialab-standards hook. They are never edited by hand anyway.
    return str(relative) not in _vendored_paths()


def _run(command: list[str], path: Path) -> subprocess.CompletedProcess | None:
    """Run one tool on one file, tolerating a missing executable.

    Args:
        command: Command and arguments, without the file path.
        path: File to process.

    Returns:
        The completed process, or None when the tool is not installed.
    """
    if shutil.which(command[0]) is None:
        return None
    try:
        return subprocess.run(
            [*command, str(path)],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None


def _poetry_prefix() -> list[str]:
    """Return the command prefix running tools inside the project environment.

    Returns:
        ``["poetry", "run"]`` for a Poetry project, an empty list otherwise.
    """
    if Path("pyproject.toml").exists() and shutil.which("poetry"):
        return ["poetry", "run"]
    return []


def _lint_python(path: Path) -> list[str]:
    """Format the file, then lint it.

    Args:
        path: Python file to process.

    Returns:
        Messages to report back to the agent; empty when the file is clean.
    """
    prefix = _poetry_prefix()
    _run([*prefix, "black", "--line-length", "100", "--quiet"], path)
    _run([*prefix, "isort", "--profile", "black", "--line-length", "100"], path)

    rcfile = ["--rcfile=.pylintrc"] if Path(".pylintrc").exists() else []
    result = _run([*prefix, "pylint", *rcfile], path)
    if result is None or result.returncode == 0:
        return []
    findings = [
        line
        for line in result.stdout.splitlines()
        if ": " in line and not line.startswith(("*", "-", "Your code"))
    ]
    return findings


def _lint_frontend(path: Path) -> list[str]:
    """Run ESLint with autofix on the edited file.

    Args:
        path: TypeScript or JavaScript file to process.

    Returns:
        Messages to report back to the agent; empty when the file is clean.
    """
    if not Path("package.json").exists():
        return []
    result = _run(["npx", "--no-install", "eslint", "--fix"], path)
    if result is None or result.returncode == 0:
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


def main() -> int:
    """Lint the edited file and report findings to the agent.

    Returns:
        0 when the file is clean or out of scope, 2 when findings must be fixed.
    """
    path = _read_edited_path()
    if path is None or not _is_ours(path):
        return 0

    if path.suffix in _PYTHON_SUFFIXES:
        findings = _lint_python(path)
    elif path.suffix in _FRONTEND_SUFFIXES:
        findings = _lint_frontend(path)
    else:
        return 0

    if not findings:
        return 0

    relative = os.path.relpath(path, Path.cwd())
    print(f"Lint findings on {relative} — fix them now:", file=sys.stderr)
    for finding in findings[:20]:
        print(f"  {finding}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
