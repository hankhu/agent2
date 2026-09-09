"""File path completion for @file reference in chat inputs."""

from __future__ import annotations

import os
from pathlib import Path

_IGNORED_DIRS: frozenset[str] = frozenset({
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "node_modules",
    "dist",
    "build",
    ".eggs",
})


def _format_size(size_bytes: int) -> str:
    if size_bytes >= 1_000_000:
        return f"{size_bytes / 1_000_000:.1f} MB"
    if size_bytes >= 1_000:
        return f"{size_bytes / 1_000:.1f} KB"
    return f"{size_bytes} B"


def get_file_completions(
    query: str,
    root_dir: Path | None = None,
    limit: int = 25,
) -> list[tuple[str, str]]:
    """Return matching file and directory completions for a given prefix.

    Parameters
    ----------
    query : str
        The typed path after '@', e.g. '', 'src/', 'src/ag', 'README'.
    root_dir : Path | None
        The base directory for resolution (defaults to cwd).
    limit : int
        Maximum number of completion suggestions to return.

    Returns
    -------
    list[tuple[str, str]]
        List of (completion_string, description) pairs, e.g.:
        [('@src/', '📁 Directory'), ('@src/agent2/agent/react.py', '📄 3.8 KB')]
    """
    root = (root_dir or Path.cwd()).resolve()

    # Clean query (strip leading @ or angle brackets if present)
    clean = query.strip()
    if clean.startswith("@"):
        clean = clean[1:]
    if clean.startswith("<") and clean.endswith(">"):
        clean = clean[1:-1]

    has_slash = "/" in clean or "\\" in clean
    clean_norm = clean.replace("\\", "/")

    results: list[tuple[str, str]] = []

    if has_slash:
        parent_part, _, name_part = clean_norm.rpartition("/")
        target_dir = (root / parent_part).resolve()
        name_lower = name_part.lower()

        if not target_dir.exists() or not target_dir.is_dir():
            return []

        try:
            entries = sorted(target_dir.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        except (PermissionError, OSError):
            return []

        for e in entries:
            if e.name in _IGNORED_DIRS:
                continue
            if e.name.startswith(".") and not name_lower.startswith("."):
                continue

            if not name_lower or name_lower in e.name.lower():
                rel_path = f"{parent_part}/{e.name}".lstrip("/")
                if e.is_dir():
                    results.append((f"@{rel_path}/", "📁 Directory"))
                else:
                    try:
                        sz = _format_size(e.stat().st_size)
                    except OSError:
                        sz = "file"
                    results.append((f"@{rel_path}", f"📄 {sz}"))

                if len(results) >= limit:
                    break

        return results

    # No slash: list matching entries in root directory, plus recursive search if query provided
    name_lower = clean_norm.lower()

    # 1. Immediate root entries
    try:
        root_entries = sorted(root.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
    except (PermissionError, OSError):
        root_entries = []

    for e in root_entries:
        if e.name in _IGNORED_DIRS:
            continue
        if e.name.startswith(".") and not name_lower.startswith("."):
            continue

        if not name_lower or name_lower in e.name.lower():
            if e.is_dir():
                results.append((f"@{e.name}/", "📁 Directory"))
            else:
                try:
                    sz = _format_size(e.stat().st_size)
                except OSError:
                    sz = "file"
                results.append((f"@{e.name}", f"📄 {sz}"))

    # 2. If query is provided, also search deeper (depth up to 3)
    if name_lower and len(results) < limit:
        seen_paths = {r[0] for r in results}
        for dirpath, dirnames, filenames in os.walk(root):
            # Prune ignored directories
            dirnames[:] = [d for d in dirnames if d not in _IGNORED_DIRS and not d.startswith(".")]
            rel_dir = os.path.relpath(dirpath, root)
            if rel_dir == ".":
                depth = 0
            else:
                depth = rel_dir.count(os.sep) + 1

            if depth > 3:
                dirnames.clear()
                continue

            if depth > 0:
                for d in dirnames:
                    if name_lower in d.lower():
                        cand = f"@{os.path.join(rel_dir, d)}/".replace("\\", "/")
                        if cand not in seen_paths:
                            seen_paths.add(cand)
                            results.append((cand, "📁 Directory"))
                            if len(results) >= limit:
                                break

            for f in filenames:
                if f.startswith("."):
                    continue
                if name_lower in f.lower():
                    rel_file = os.path.join(rel_dir, f).replace("\\", "/") if rel_dir != "." else f
                    cand = f"@{rel_file}"
                    if cand not in seen_paths:
                        seen_paths.add(cand)
                        try:
                            full_p = Path(dirpath) / f
                            sz = _format_size(full_p.stat().st_size)
                        except OSError:
                            sz = "file"
                        results.append((cand, f"📄 {sz}"))
                        if len(results) >= limit:
                            break

            if len(results) >= limit:
                break

    return results[:limit]
