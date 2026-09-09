"""Tool execution approval manager supporting conversation, project, and global scopes."""

from __future__ import annotations

import json
from pathlib import Path

from agent2.app.config import CONFIG_DIR

GLOBAL_APPROVALS_FILE = CONFIG_DIR / "approvals.json"


def get_global_approvals_path() -> Path:
    """Return the global approvals file path (~/.config/agent2/approvals.json)."""
    return GLOBAL_APPROVALS_FILE


def find_project_root(start: Path | None = None) -> Path:
    """Find closest project root directory containing .git or .agent2, falling back to cwd."""
    cur = (start or Path.cwd()).resolve()
    for parent in [cur, *cur.parents]:
        if (parent / ".agent2").exists() or (parent / ".git").exists() or (parent / "pyproject.toml").exists():
            return parent
    return cur


def get_project_approvals_path(start: Path | None = None) -> Path:
    """Return the project approvals file path (<project_root>/.agent2/approvals.json)."""
    root = find_project_root(start)
    return root / ".agent2" / "approvals.json"


def load_approved_tools(path: Path) -> set[str]:
    """Read set of approved tool names from a JSON file."""
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return set(data.get("approved_tools", []))
        if isinstance(data, list):
            return set(data)
    except Exception:
        pass
    return set()


def save_approved_tool(path: Path, tool_name: str) -> None:
    """Add tool_name to the approved_tools list in the specified JSON file."""
    current = load_approved_tools(path)
    if tool_name in current:
        return
    current.add(tool_name)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"approved_tools": sorted(current)}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def is_tool_approved(
    tool_name: str,
    conversation_approved: set[str] | None = None,
    cwd: Path | None = None,
) -> bool:
    """Check if tool is approved in conversation, project, or global scope."""
    if conversation_approved and tool_name in conversation_approved:
        return True

    proj_path = get_project_approvals_path(cwd)
    if tool_name in load_approved_tools(proj_path):
        return True

    glob_path = get_global_approvals_path()
    if tool_name in load_approved_tools(glob_path):
        return True

    return False


def record_approval(
    tool_name: str,
    scope: str,
    conversation_approved: set[str],
    cwd: Path | None = None,
) -> None:
    """Persist tool approval according to scope.

    Scopes:
    - 'once' / 'approve_once' / 'approve': single execution approval, not persisted.
    - 'conversation' / 'approve_conversation': approved for this conversation session.
    - 'project' / 'approve_project': approved for the project in .agent2/approvals.json.
    - 'always' / 'approve_always': approved globally in ~/.config/agent2/approvals.json.
    """
    scope_clean = scope.lower().strip()
    if scope_clean in ("conversation", "approve_conversation"):
        conversation_approved.add(tool_name)
    elif scope_clean in ("project", "approve_project"):
        conversation_approved.add(tool_name)
        save_approved_tool(get_project_approvals_path(cwd), tool_name)
    elif scope_clean in ("always", "approve_always"):
        conversation_approved.add(tool_name)
        save_approved_tool(get_global_approvals_path(), tool_name)
