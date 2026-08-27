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

from agent2.app.config import get_last_model, set_last_model
from agent2.app.tui.app import Agent2App, TUIReActAgent, build_tui_agent
from agent2.app.tui.session import SessionManager


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="agent2-tui",
        description="Agent2 Terminal User Interface (TUI)",
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


def main(argv: list[str] | None = None) -> None:
    """CLI entry point for the TUI."""
    args = parse_args(argv)

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
        asyncio.run(_run_single(agent, args.p))
        return

    app = Agent2App(agent, SessionManager(), initial_message=args.i)
    app.run()
