"""Built-in tools: file operations."""

from __future__ import annotations

import os
from pathlib import Path

from agent2.tools.base import tool


@tool(description="Read the contents of a file at the given path.")
def read_file(path: str) -> str:
    """Read a text file and return its contents."""
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"Error: File not found: {p}"
    if not p.is_file():
        return f"Error: Not a file: {p}"
    try:
        content = p.read_text(encoding="utf-8")
        if len(content) > 10000:
            return content[:10000] + f"\n\n... (truncated, total {len(content)} chars)"
        return content
    except Exception as e:
        return f"Error reading file: {e}"


@tool(description="Write content to a file at the given path. Creates parent directories if needed.")
def write_file(path: str, content: str) -> str:
    """Write text content to a file."""
    p = Path(path).expanduser().resolve()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Successfully wrote {len(content)} chars to {p}"
    except Exception as e:
        return f"Error writing file: {e}"


@tool(description="List files and directories at the given path.")
def list_directory(path: str = ".") -> str:
    """List directory contents with type indicators."""
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"Error: Path not found: {p}"
    if not p.is_dir():
        return f"Error: Not a directory: {p}"

    entries: list[str] = []
    try:
        for item in sorted(p.iterdir()):
            if item.name.startswith("."):
                continue
            icon = "📁" if item.is_dir() else "📄"
            size = ""
            if item.is_file():
                size_bytes = item.stat().st_size
                if size_bytes < 1024:
                    size = f" ({size_bytes}B)"
                elif size_bytes < 1024 * 1024:
                    size = f" ({size_bytes / 1024:.1f}KB)"
                else:
                    size = f" ({size_bytes / 1024 / 1024:.1f}MB)"
            entries.append(f"{icon} {item.name}{size}")
    except PermissionError:
        return f"Error: Permission denied: {p}"

    if not entries:
        return f"Directory is empty: {p}"
    return f"Contents of {p}:\n" + "\n".join(entries)
