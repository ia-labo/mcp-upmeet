#!/usr/bin/env python3
"""Claude Code PreToolUse hook: block the two git mistakes that leak secrets.

Two rules, both from the IALab standards:

* ``git add .`` / ``git add -A`` / ``git commit -a`` — bulk staging is how an
  untracked ``.env`` or a stray dump ends up in a commit. Stage by name.
* ``git add`` on a ``.env`` file — never, whatever the intent.

Wired from ``.claude/settings.json``:

    "PreToolUse": [{"matcher": "Bash",
                    "hooks": [{"type": "command",
                               "command": "python3 .claude/hooks/guard_bash.py"}]}]

Exit code 2 denies the call and hands the reason back to the agent.
"""

import json
import re
import shlex
import sys

# ``git add`` / ``git stage`` with a bulk target, in any position of the command.
_BULK_ADD = re.compile(r"\bgit\s+(?:add|stage)\b[^|;&]*?(?:\s-A\b|\s--all\b|\s\.(?:\s|$))")

# ``git commit -a`` stages every tracked change without naming anything.
_COMMIT_ALL = re.compile(r"\bgit\s+commit\b[^|;&]*?\s-(?:a|[a-zA-Z]*a[a-zA-Z]*)\b")

# Any .env variant: .env, .env.local, .env.production, app/core/.env
_ENV_FILE = re.compile(r"(?:^|/)\.env(?:\.[\w.-]+)?$")


def _staged_paths(command: str) -> list[str]:
    """List the paths passed to a ``git add`` / ``git stage`` in the command.

    Args:
        command: Full shell command requested by the agent.

    Returns:
        The positional arguments of the staging command, flags excluded.
    """
    try:
        tokens = shlex.split(command)
    except ValueError:
        return []
    paths: list[str] = []
    index = 0
    while index < len(tokens):
        is_staging = tokens[index] == "git" and tokens[index + 1 : index + 2] in (
            ["add"],
            ["stage"],
        )
        if not is_staging:
            index += 1
            continue
        index += 2
        while index < len(tokens) and tokens[index] not in {"&&", "||", ";", "|"}:
            if not tokens[index].startswith("-"):
                paths.append(tokens[index])
            index += 1
    return paths


def _violation(command: str) -> str:
    """Return the reason this command must be denied, or an empty string.

    Args:
        command: Full shell command requested by the agent.

    Returns:
        A message explaining what to do instead, or "" when the command is fine.
    """
    if _BULK_ADD.search(command):
        return (
            "Bulk staging is forbidden on IALab repos (`git add .` / `git add -A`): it is how "
            "a .env or a dump ends up committed. Stage each file explicitly by name."
        )
    if _COMMIT_ALL.search(command):
        return (
            "`git commit -a` stages every tracked change without naming it. Stage the files "
            "explicitly, then commit without -a."
        )
    for path in _staged_paths(command):
        if _ENV_FILE.search(path):
            return (
                f"'{path}' is an environment file and must never be committed. "
                "Put the variable in .env.example with a placeholder value instead."
            )
    return ""


def main() -> int:
    """Inspect the requested Bash command and deny it when it breaks a rule.

    Returns:
        0 to let the command run, 2 to deny it.
    """
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    command = (payload.get("tool_input") or {}).get("command", "")
    if not command:
        return 0

    reason = _violation(command)
    if not reason:
        return 0

    print(reason, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
