"""Session persistence for TUI conversations."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, cast

from rich.markup import escape


SESSION_DIR = Path.home() / ".local" / "share" / "agent2" / "sessions"
LOG_DIR = Path.home() / ".local" / "share" / "agent2" / "logs"


class SessionManager:
    """Manage saving, loading, listing, logging, and exporting of agent sessions."""

    def __init__(
        self,
        session_dir: Path = SESSION_DIR,
        log_dir: Path = LOG_DIR,
    ) -> None:
        self.session_dir = session_dir
        self.log_dir = log_dir
        try:
            self.session_dir.mkdir(parents=True, exist_ok=True)
            self.log_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

    def save(
        self,
        session_id: str,
        agent_data: dict[str, Any],
        title: str = "",
        usage: dict[str, Any] | None = None,
    ) -> Path:
        """Persist agent state to a JSON session file."""
        path = self.session_dir / f"{session_id}.json"
        existing_title = ""
        existing_usage = None
        if path.exists():
            try:
                old = json.loads(path.read_text(encoding="utf-8"))
                if not title:
                    existing_title = old.get("title", "")
                existing_usage = old.get("usage")
            except Exception:
                pass
        final_title = title.strip() or existing_title or _extract_title(agent_data)
        usage_data = usage
        if usage_data is None and isinstance(agent_data, dict):
            usage_data = agent_data.get("extra", {}).get("usage")
        if usage_data is None:
            usage_data = existing_usage
        payload = {
            "id": session_id,
            "title": final_title,
            "saved_at": time.time(),
            "agent": agent_data,
            "usage": usage_data,
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

        # Ensure session log file exists
        log_path = self.get_log_path(session_id)
        if not log_path.exists():
            self._init_log_from_messages(session_id, agent_data.get("messages", []))

        return path

    def _init_log_from_messages(
        self,
        session_id: str,
        messages: list[dict[str, Any]],
    ) -> None:
        """Create a log file from conversation messages if missing."""
        log_path = self.get_log_path(session_id)
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            lines = [f"[{timestamp}] [SESSION_INIT] Session ID: {session_id}\n"]
            for m in messages:
                role = (m.get("role") or "").upper()
                content = m.get("content") or ""
                if role and content:
                    lines.append(f"[{timestamp}] [{role}] {content}\n")
            log_path.write_text("".join(lines), encoding="utf-8")
        except OSError:
            pass

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
        return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))

    def list_sessions(self) -> list[dict[str, Any]]:
        """Return metadata of all saved sessions, newest first."""
        sessions: list[dict[str, Any]] = []
        for f in self.session_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                agent_data = data.get("agent", {})
                messages = agent_data.get("messages", [])
                preview = _extract_preview(agent_data)
                sessions.append({
                    "id": data.get("id", f.stem),
                    "title": data.get("title", ""),
                    "saved_at": data.get("saved_at", 0),
                    "message_count": len(messages),
                    "preview": preview,
                })
            except (json.JSONDecodeError, KeyError):
                continue
        sessions.sort(key=lambda s: s["saved_at"], reverse=True)
        return sessions

    def get_latest_session(self) -> dict[str, Any] | None:
        """Return the most recently saved session metadata, or None."""
        sessions = self.list_sessions()
        return sessions[0] if sessions else None

    def find_session(self, query: str) -> dict[str, Any] | None:
        """Find a session matching query by ID or title.

        Match priority:
        1. Exact session ID match
        2. Exact title match (case-insensitive)
        3. Prefix session ID match
        4. Substring title match (case-insensitive)
        """
        q = query.strip()
        if not q:
            return None
        sessions = self.list_sessions()
        if not sessions:
            return None

        q_lower = q.lower()

        # 1. Exact ID
        for s in sessions:
            if s["id"] == q:
                return s

        # 2. Exact Title
        for s in sessions:
            if s.get("title", "").strip().lower() == q_lower:
                return s

        # 3. Prefix ID
        for s in sessions:
            if s["id"].startswith(q):
                return s

        # 4. Substring in Title
        for s in sessions:
            if q_lower in s.get("title", "").lower():
                return s

        return None

    def get_log_path(self, session_id: str) -> Path:
        """Return the path to the session's log file."""
        return self.log_dir / f"{session_id}.log"

    def log_event(self, session_id: str, tag: str, message: str) -> None:
        """Append a timestamped log entry to the session log file."""
        log_path = self.get_log_path(session_id)
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] [{tag.upper()}] {message.strip()}\n"
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(entry)
        except OSError:
            pass

    def export(
        self,
        session_id: str,
        dest_path: Path | str | None = None,
    ) -> Path:
        """Export session conversation history to Markdown, JSON, or text.

        If dest_path is omitted or a directory, defaults to ./session_<session_id>.md.
        Format is inferred from file extension (.md, .json, .txt), defaulting to Markdown.
        """
        data = self.load(session_id)
        title = data.get("title") or "Untitled Session"
        agent_data = data.get("agent", {})
        messages = agent_data.get("messages", [])
        saved_at_ts = data.get("saved_at", 0)
        saved_at_str = (
            time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(saved_at_ts))
            if saved_at_ts
            else time.strftime("%Y-%m-%d %H:%M:%S")
        )

        if dest_path:
            p = Path(dest_path).expanduser()
            if p.is_dir():
                p = p / f"session_{session_id}.md"
        else:
            p = Path.cwd() / f"session_{session_id}.md"

        p.parent.mkdir(parents=True, exist_ok=True)
        ext = p.suffix.lower()

        if ext == ".json":
            p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        elif ext == ".txt":
            lines = [
                f"Session: {title}",
                f"Session ID: {session_id}",
                f"Date: {saved_at_str}",
                "=" * 40,
                "",
            ]
            for m in messages:
                role = m.get("role", "")
                content = m.get("content", "")
                if role == "user":
                    lines.append(f"User:\n{content}\n")
                elif role == "assistant":
                    lines.append(f"Assistant:\n{content}\n")
                elif role == "tool":
                    tr = m.get("tool_result", {})
                    lines.append(f"Tool Output:\n{tr.get('content', '')}\n")
            p.write_text("\n".join(lines), encoding="utf-8")
        else:
            # Default to Markdown (.md)
            lines = [
                f"# Conversation: {title}",
                f"- **Session ID**: `{session_id}`",
                f"- **Date**: `{saved_at_str}`",
                "",
                "---",
                "",
            ]
            for m in messages:
                role = m.get("role", "")
                content = m.get("content") or ""
                if role == "user":
                    lines.append(f"### 👤 User\n\n{content}\n")
                elif role == "assistant":
                    lines.append("### 🤖 Assistant\n")
                    if content:
                        lines.append(f"{content}\n")
                    tool_calls = m.get("tool_calls", [])
                    if tool_calls:
                        for tc in tool_calls:
                            tc_name = tc.get("name", "tool")
                            tc_args = json.dumps(tc.get("arguments", {}), ensure_ascii=False, indent=2)
                            lines.append(f"> **Tool Call**: `{tc_name}`\n> ```json\n> {tc_args}\n> ```\n")
                elif role == "tool":
                    tr = m.get("tool_result", {})
                    tc_id = tr.get("tool_call_id", "")
                    tr_content = tr.get("content", "")
                    is_err = tr.get("is_error", False)
                    header = "❌ **Tool Error**" if is_err else "👁️ **Tool Output**"
                    lines.append(f"> {header} (`{tc_id}`):\n> ```\n> {tr_content}\n> ```\n")
            p.write_text("\n".join(lines), encoding="utf-8")

        return p

    def delete(self, session_id: str) -> None:
        """Delete a session file and its associated log file."""
        path = self.session_dir / f"{session_id}.json"
        path.unlink(missing_ok=True)
        log_path = self.log_dir / f"{session_id}.log"
        log_path.unlink(missing_ok=True)

    def get_session_preview(self, session_id: str, max_messages: int = 15) -> str:
        """Return formatted conversation transcript/preview for a session."""
        try:
            data = self.load(session_id)
        except Exception:
            return "[dim](Session data not found)[/dim]"

        title = data.get("title") or "Untitled Session"
        agent_data = data.get("agent", {})
        messages = agent_data.get("messages", [])
        saved_at = float(data.get("saved_at", 0) or 0)
        time_str = (
            time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(saved_at))
            if saved_at
            else "unknown"
        )

        lines = [
            f"[bold cyan]{escape(str(title))}[/bold cyan]",
            f"[dim]ID: {escape(str(session_id))}  ·  Saved: {time_str}  ·  {len(messages)} messages[/dim]",
            "[dim]" + "─" * 40 + "[/dim]",
            "",
        ]

        if not messages:
            lines.append("[dim](No messages in this session)[/dim]")
            return "\n".join(lines)

        shown_messages = messages[:max_messages]
        for m in shown_messages:
            role = (m.get("role") or "").lower()
            content = (m.get("content") or "").strip()
            if role == "user":
                snippet = escape(_clean_msg_text(content, 200))
                lines.append(f"[bold dodger_blue1]👤 User:[/bold dodger_blue1]\n{snippet}\n")
            elif role == "assistant":
                if content:
                    snippet = escape(_clean_msg_text(content, 200))
                    lines.append(f"[bold green]🤖 Assistant:[/bold green]\n{snippet}\n")
                tool_calls = m.get("tool_calls", [])
                for tc in tool_calls:
                    tc_name = escape(str(tc.get("name", "tool")))
                    args = tc.get("arguments", {})
                    args_str = " ".join(f"{k}={repr(v)}" for k, v in args.items())
                    if len(args_str) > 60:
                        args_str = args_str[:57] + "…"
                    lines.append(f"[dim yellow]⚙ {tc_name} {escape(args_str)}[/dim yellow]\n")
            elif role == "tool":
                tr = m.get("tool_result", {})
                tr_content = (tr.get("content") or "").strip()
                if tr_content:
                    snippet = escape(_clean_msg_text(tr_content, 100))
                    lines.append(f"[dim]  ↳ output: {snippet}[/dim]\n")

        if len(messages) > max_messages:
            lines.append(f"[dim]… and {len(messages) - max_messages} more messages[/dim]")

        return "\n".join(lines)


def _clean_msg_text(text: str, limit: int = 240) -> str:
    """Strip XML/directory tags and clean up message snippet for preview."""
    text = re.sub(r"<file\b[^>]*>.*?</file>", " ", text, flags=re.S)
    text = re.sub(r"<directory\b[^>]*>.*?</directory>", " ", text, flags=re.S)
    text = re.sub(r"#(?:file|dir)\s+\S+", " ", text)
    cleaned = " ".join(text.split()).strip()
    return cleaned[:limit] + "…" if len(cleaned) > limit else cleaned


def _extract_preview(agent_data: dict[str, Any]) -> str:
    """Derive a short preview from conversation messages."""
    for msg in agent_data.get("messages", []):
        if msg.get("role") == "user" and msg.get("content"):
            return _clean_msg_text(msg["content"], 80)
    return ""


def _extract_title(agent_data: dict[str, Any]) -> str:
    """Try to derive a short, readable title from the first user message."""
    for msg in agent_data.get("messages", []):
        if msg.get("role") != "user" or not msg.get("content"):
            continue
        text = msg["content"]
        cleaned = _clean_msg_text(text, 60)
        return cleaned or "(untitled)"
    return ""
