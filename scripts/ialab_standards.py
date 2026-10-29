"""Vendor and verify the shared IALab standard files (CODE.md, logger.py, ...).

Some files are owned centrally and copied verbatim into every repository. To keep
the copies from drifting, each vendored file carries a two-line stamp header
holding the source name, the version, and a sha256 of everything below it.

Two commands:
    sync: copy the canonical files listed in ``.ialab-standards.json`` from the
        source directory and stamp them. Developer machines only.
    check: recompute the digest of every vendored file and fail when it no
        longer matches its own stamp. Runs offline, so it works in pre-commit
        hooks and in CI without access to the source directory.

The repository manifest ``.ialab-standards.json`` maps a canonical template name
to its destination path::

    {"files": {"logger.py": "app/utils/logger.py", "CODE.md": "CODE.md"}}

Usage:
    python scripts/ialab_standards.py check
    python scripts/ialab_standards.py sync [--source DIR]
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

MANIFEST_NAME = ".ialab-standards.json"
DEFAULT_SOURCE = Path.home() / ".claude" / "contexts" / "ialab" / "templates"
VERSION = "1.0"

# Comment syntax used to carry the stamp, keyed by file suffix.
_COMMENT_STYLES = {
    ".py": ("# ", ""),
    ".md": ("<!-- ", " -->"),
    ".yaml": ("# ", ""),
    ".yml": ("# ", ""),
    ".toml": ("# ", ""),
}

# The stamp spans two comment lines so it stays under the 100-character limit.
_NAME_RE = re.compile(r"ialab-standards:\s*(?P<name>\S+)\s+v(?P<version>\S+)")
_SHA_RE = re.compile(r"ialab-standards-sha256:\s*(?P<digest>[0-9a-f]{64})")


def _digest(body: str) -> str:
    """Compute the sha256 of a file body.

    Args:
        body: File content below the stamp header.

    Returns:
        Lowercase hex digest.
    """
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _stamp(path: Path, name: str, digest: str) -> str:
    """Build the two-line stamp header for a destination file.

    Args:
        path: Destination path, used to pick the comment syntax.
        name: Canonical template name.
        digest: sha256 of the body.

    Returns:
        The full stamp header, trailing newline included.

    Raises:
        ValueError: If the file extension has no known comment syntax.
    """
    style = _COMMENT_STYLES.get(path.suffix)
    if style is None:
        raise ValueError(f"No comment syntax known for {path.suffix} files")
    prefix, suffix = style
    header = f"ialab-standards: {name} v{VERSION} - generated, do not edit"
    return f"{prefix}{header}{suffix}\n{prefix}ialab-standards-sha256: {digest}{suffix}\n"


def _split_stamp(text: str) -> tuple[str, str]:
    """Split a vendored file into its stamp header and its body.

    Args:
        text: Full file content.

    Returns:
        Tuple of (stamp, body). The stamp is empty when absent or incomplete.
    """
    lines = text.split("\n")
    if len(lines) >= 2 and _NAME_RE.search(lines[0]) and _SHA_RE.search(lines[1]):
        return "\n".join(lines[:2]) + "\n", "\n".join(lines[2:])
    return "", text


def _load_manifest(repo_root: Path) -> dict[str, str]:
    """Read the repository manifest of vendored files.

    Args:
        repo_root: Repository root holding ``.ialab-standards.json``.

    Returns:
        Mapping of canonical template name to destination path.

    Raises:
        SystemExit: If the manifest is missing or malformed.
    """
    manifest_path = repo_root / MANIFEST_NAME
    if not manifest_path.exists():
        sys.exit(f"No {MANIFEST_NAME} found in {repo_root}")
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        sys.exit(f"Malformed {MANIFEST_NAME}: {exc}")
    files = data.get("files")
    if not isinstance(files, dict) or not files:
        sys.exit(f"{MANIFEST_NAME} must define a non-empty 'files' mapping")
    return files


def cmd_sync(repo_root: Path, source: Path) -> int:
    """Copy every managed file from the source directory and stamp it.

    Args:
        repo_root: Repository root.
        source: Directory holding the canonical templates.

    Returns:
        Process exit code.
    """
    if not source.is_dir():
        print(f"Source directory not found: {source}", file=sys.stderr)
        return 1

    for name, relative in _load_manifest(repo_root).items():
        origin = source / name
        if not origin.exists():
            print(f"  missing in source: {name}", file=sys.stderr)
            return 1
        body = origin.read_text(encoding="utf-8")
        destination = repo_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(_stamp(destination, name, _digest(body)) + body, "utf-8")
        print(f"  synced {relative} <- {name}")
    return 0


def _check_one(path: Path, name: str) -> str:
    """Verify one vendored file against its own stamp.

    Args:
        path: Destination path to verify.
        name: Canonical template name expected in the stamp.

    Returns:
        An error message, or an empty string when the file is valid.
    """
    if not path.exists():
        return f"{path}: missing (run: python scripts/ialab_standards.py sync)"
    stamp, body = _split_stamp(path.read_text(encoding="utf-8"))
    if not stamp:
        return f"{path}: no ialab-standards stamp"
    stamped_name = _NAME_RE.search(stamp).group("name")
    if stamped_name != name:
        return f"{path}: stamped as {stamped_name}, expected {name}"
    if _SHA_RE.search(stamp).group("digest") != _digest(body):
        return f"{path}: edited by hand (run: python scripts/ialab_standards.py sync)"
    return ""


def cmd_check(repo_root: Path) -> int:
    """Verify every managed file against its stamp.

    Args:
        repo_root: Repository root.

    Returns:
        Process exit code: 0 when every file matches, 1 otherwise.
    """
    errors = [
        error
        for name, relative in _load_manifest(repo_root).items()
        if (error := _check_one(repo_root / relative, name))
    ]
    for error in errors:
        print(f"  {error}", file=sys.stderr)
    return 1 if errors else 0


def main() -> int:
    """Parse arguments and dispatch to the requested command.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(description="Vendor and verify IALab standard files.")
    parser.add_argument("command", choices=["sync", "check"])
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Repository root")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="Template directory")
    parser.add_argument("_files", nargs="*", help="Ignored; lets pre-commit pass file names")
    args = parser.parse_args()

    if args.command == "sync":
        return cmd_sync(args.root, args.source)
    return cmd_check(args.root)


if __name__ == "__main__":
    sys.exit(main())
