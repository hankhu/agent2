"""Agent2 TUI — terminal user interface built on Textual.

Launch with::

    uv run -m agent2.app.tui
    uv run -m agent2.app.tui --model deepseek
    uv run -m agent2.app.tui --no-tools
    uv run -m agent2.app.tui -p "List files in the current directory"
    uv run -m agent2.app.tui -i "Hi, please check what files are in this project."
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
import uuid
from pathlib import Path

from agent2 import __version__
from agent2.app.config import get_last_model, set_last_model
from agent2.app.tui.app import Agent2App, TUIReActAgent, build_tui_agent, restore_agent
from agent2.app.tui.session import SessionManager
from agent2.llm.message import Role


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="agent2-tui",
        description="Agent2 Terminal User Interface (TUI)",
    )
    parser.add_argument(
        "--version",
        "-v",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    resume_group = parser.add_mutually_exclusive_group()
    resume_group.add_argument(
        "--resume",
        metavar="SESSION",
        default=None,
        help="Resume a previous session by ID or name.",
    )
    resume_group.add_argument(
        "--continue",
        "-c",
        dest="continue_session",
        action="store_true",
        default=False,
        help="Continue the latest session.",
    )
    parser.add_argument(
        "--model", default=None, help="Override the model name.",
    )
    parser.add_argument(
        "--sys-msg", default=None, help="Custom system message.",
    )
    parser.add_argument(
        "--no-tools",
        action="store_true",
        default=False,
        help="Disable built-in tools (pure chat mode).",
    )
    parser.add_argument(
        "--export",
        metavar="PATH",
        nargs="?",
        const="",
        default=None,
        help="Export session conversation history to Markdown/JSON/text file.",
    )
    parser.add_argument(
        "-p",
        metavar="MSG",
        default=None,
        help="Single-turn mode: send MSG, execute/answer, and exit.",
    )
    parser.add_argument(
        "-i",
        metavar="MSG",
        default=None,
        help="Interactive mode with MSG as the first user message.",
    )
    return parser.parse_args(argv)


async def _run_single(agent: TUIReActAgent, prompt: str) -> None:
    """Single-turn mode: answer the prompt and exit."""
    await agent.chat(prompt)


def _print_exit_info(session_id: str, log_path: Path | str | None = None) -> None:
    """Display the resume command and log file path upon exit."""
    print(f"\nResume with: agent2 --resume {session_id}")
    if log_path:
        p = Path(log_path)
        if not p.exists():
            try:
                p.parent.mkdir(parents=True, exist_ok=True)
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                p.write_text(
                    f"[{timestamp}] [SESSION_INIT] Session ID: {session_id}\n",
                    encoding="utf-8",
                )
            except OSError:
                pass
        print(f"Log file:    {log_path}")


def main(argv: list[str] | None = None) -> None:
    """CLI entry point for the TUI."""
    args = parse_args(argv)

    session_manager = SessionManager()
    resume_session_id: str | None = None

    if args.continue_session:
        latest = session_manager.get_latest_session()
        if not latest:
            print("Error: No saved sessions found to continue.", file=sys.stderr)
            sys.exit(1)
        resume_session_id = latest["id"]
    elif args.resume:
        found = session_manager.find_session(args.resume)
        if not found:
            print(f"Error: Session '{args.resume}' not found.", file=sys.stderr)
            sys.exit(1)
        resume_session_id = found["id"]

    # Handle --export command line option directly
    if args.export is not None:
        target_id = resume_session_id
        if not target_id:
            latest = session_manager.get_latest_session()
            target_id = latest["id"] if latest else None
        if not target_id:
            print("Error: No saved session found to export.", file=sys.stderr)
            sys.exit(1)
        out_path = session_manager.export(target_id, dest_path=args.export or None)
        print(f"Conversation exported to: {out_path}")
        return

    # Prefer an explicit --model; otherwise restore the last selected model.
    model = args.model or get_last_model()
    agent = build_tui_agent(
        model=model,
        system_msg=args.sys_msg,
        no_tools=args.no_tools,
    )

    if args.model:
        set_last_model(agent.llm.model)

    if args.p:
        session_id = resume_session_id or uuid.uuid4().hex[:8]
        session_title: str | None = None
        if resume_session_id:
            session_title = restore_agent(agent, session_manager, resume_session_id)

        log_path = session_manager.get_log_path(session_id)
        agent.log.log_file = log_path
        session_manager.log_event(session_id, "USER", args.p)
        try:
            asyncio.run(_run_single(agent, args.p))
        except Exception as exc:
            session_manager.log_event(session_id, "ERROR", str(exc))
            session_manager.save(session_id, agent.to_dict(), title=session_title or "")
            _print_exit_info(session_id, log_path)
            raise

        if any(m.role == Role.USER for m in agent.messages):
            if agent.messages and agent.messages[-1].role == Role.ASSISTANT:
                session_manager.log_event(
                    session_id, "ASSISTANT", agent.messages[-1].content or ""
                )
            session_manager.save(session_id, agent.to_dict(), title=session_title or "")
            _print_exit_info(session_id, log_path)
        return

    app = Agent2App(
        agent,
        session_manager,
        initial_message=args.i,
        resume_session_id=resume_session_id,
    )
    log_path = session_manager.get_log_path(app.session_id)
    agent.log.log_file = log_path

    app.run()

    if any(m.role == Role.USER for m in app.agent.messages):
        log_path = session_manager.get_log_path(app.session_id)
        _print_exit_info(app.session_id, log_path)
