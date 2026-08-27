"""Session persistence for TUI conversations."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any


SESSION_DIR = Path.home() / ".local" / "share" / "agent2" / "sessions"


class SessionManager:
    """Manage saving, loading, and listing of agent sessions."""

    def __init__(self, session_dir: Path = SESSION_DIR) -> None:
        self.session_dir = session_dir
        try:
            self.session_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

    def save(
        self,
        session_id: str,
        agent_data: dict[str, Any],
        title: str = "",
    ) -> Path:
        """Persist agent state to a JSON session file."""
        path = self.session_dir / f"{session_id}.json"
        existing_title = ""
        if not title and path.exists():
            try:
                old = json.loads(path.read_text(encoding="utf-8"))
                existing_title = old.get("title", "")
            except Exception:
                pass
        final_title = title.strip() or existing_title or _extract_title(agent_data)
        payload = {
            "id": session_id,
            "title": final_title,
            "saved_at": time.time(),
            "agent": agent_data,
        }
        try:
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            # Auto-save is best-effort; never block the TUI because the
            # session directory is not writable.
            pass
        return path

    def rename(self, session_id: str, new_title: str) -> None:
        """Rename a session title."""
        path = self.session_dir / f"{session_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Session '{session_id}' not found")
        data = json.loads(path.read_text(encoding="utf-8"))
        data["title"] = new_title.strip()
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load(self, session_id: str) -> dict[str, Any]:

        """Load a session by its ID.  Raises ``FileNotFoundError``."""
        path = self.session_dir / f"{session_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Session '{session_id}' not found")
        return json.loads(path.read_text(encoding="utf-8"))

    def list_sessions(self) -> list[dict[str, Any]]:
        """Return metadata of all saved sessions, newest first."""
        sessions: list[dict[str, Any]] = []
        for f in self.session_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                sessions.append({
                    "id": data.get("id", f.stem),
                    "title": data.get("title", ""),
                    "saved_at": data.get("saved_at", 0),
                })
            except (json.JSONDecodeError, KeyError):
                continue
        sessions.sort(key=lambda s: s["saved_at"], reverse=True)
        return sessions

    def delete(self, session_id: str) -> None:
        """Delete a session file."""
        path = self.session_dir / f"{session_id}.json"
        path.unlink(missing_ok=True)


def _extract_title(agent_data: dict[str, Any]) -> str:
    """Try to derive a short, readable title from the first user message."""
    for msg in agent_data.get("messages", []):
        if msg.get("role") != "user" or not msg.get("content"):
            continue
        text = msg["content"]
        # Remove injected file/directory context so titles stay readable.
        text = re.sub(r"<file\b[^>]*>.*?</file>", " ", text, flags=re.S)
        text = re.sub(r"<directory\b[^>]*>.*?</directory>", " ", text, flags=re.S)
        text = re.sub(r"#(?:file|dir)\s+\S+", " ", text)
        # Collapse whitespace/newlines into a single line.
        cleaned = " ".join(text.split()).strip()
        if not cleaned:
            cleaned = " ".join(text.split()).strip() or "(untitled)"
        if len(cleaned) > 60:
            cleaned = cleaned[:60].rstrip() + "…"
        return cleaned
    return ""
