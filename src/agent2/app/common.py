"""Shared utilities and constants across CLI and TUI apps."""

from __future__ import annotations

from pathlib import Path
import re

YOLO_INSTRUCTION = (
    "\n\n[YOLO / Autopilot Mode Active]\n"
    "All operations and tool executions are automatically approved. "
    "You must make decisions, choose options, and solve problems autonomously "
    "without asking the user for confirmation or choices. "
    "Make your best judgment and proceed proactively to complete the goal."
)


def process_context(text: str) -> str:
    """Expand ``#file <path>``, ``#dir <path>``, and ``@<path>`` into inline context."""

    def _read_file(m: re.Match[str]) -> str:
        p = Path(m.group(1)).expanduser()
        try:
            content = p.read_text(encoding="utf-8")
            return f'\n<file path="{p}">\n{content}\n</file>\n'
        except Exception as exc:
            return f"\n[Error reading {p}: {exc}]\n"

    def _read_dir(m: re.Match[str]) -> str:
        p = Path(m.group(1)).expanduser()
        try:
            entries = sorted(p.iterdir())
            listing = "\n".join(
                f"{'[dir]' if e.is_dir() else '[file]'} {e.name}"
                for e in entries
            )
            return f'\n<directory path="{p}">\n{listing}\n</directory>\n'
        except Exception as exc:
            return f"\n[Error reading dir {p}: {exc}]\n"

    def _read_at_ref(m: re.Match[str]) -> str:
        raw_path = m.group(1).strip()
        if raw_path.startswith("<") and raw_path.endswith(">"):
            raw_path = raw_path[1:-1].strip()
        p = Path(raw_path).expanduser()
        if not p.exists():
            return m.group(0)
        if p.is_dir():
            try:
                entries = sorted(p.iterdir())
                listing = "\n".join(
                    f"{'[dir]' if e.is_dir() else '[file]'} {e.name}"
                    for e in entries
                    if not e.name.startswith(".")
                )
                return f'\n<directory path="{p}">\n{listing}\n</directory>\n'
            except Exception as exc:
                return f"\n[Error reading dir {p}: {exc}]\n"
        else:
            try:
                content = p.read_text(encoding="utf-8")
                return f'\n<file path="{p}">\n{content}\n</file>\n'
            except Exception as exc:
                return f"\n[Error reading {p}: {exc}]\n"

    text = re.sub(r"#file\s+(\S+)", _read_file, text)
    text = re.sub(r"#dir\s+(\S+)", _read_dir, text)
    text = re.sub(r"(?:^|(?<=\s))@(\S+)", _read_at_ref, text)
    return text


_process_context = process_context

__all__ = ["YOLO_INSTRUCTION", "process_context", "_process_context"]
