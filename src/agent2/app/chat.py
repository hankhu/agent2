"""Interactive chat application built on agent2.

Usage examples::

    # Interactive chat (default)
    uv run -m agent2.app.chat

    # Override model
    uv run -m agent2.app.chat --model deepseek-v4-flash

    # Set system message
    uv run -m agent2.app.chat --sys-msg "You are a Python expert."

    # Single-turn mode — print answer and exit
    uv run -m agent2.app.chat -p "Explain Python GIL in 3 sentences."

    # Interactive mode with first message pre-filled
    uv run -m agent2.app.chat -i "Hi, let's discuss async programming."
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from agent2.app.config import load_config
from agent2.llm import Message, create_llm
from agent2.llm.base import BaseLLM

# ── Console ─────────────────────────────────────────────────────────

console = Console()

DEFAULT_SYSTEM_MSG = "You are a helpful assistant."


# ── Helpers ─────────────────────────────────────────────────────────


def _build_llm(args: argparse.Namespace) -> BaseLLM:
    """Create an LLM instance from merged config + CLI args."""
    cfg = load_config()
    llm_cfg = cfg.llm

    # CLI --model overrides config
    model = args.model or llm_cfg.model
    provider = llm_cfg.provider

    kwargs: dict[str, object] = {
        "model": model,
        "temperature": llm_cfg.temperature,
        "max_tokens": llm_cfg.max_tokens,
    }
    if llm_cfg.api_key:
        kwargs["api_key"] = llm_cfg.api_key
    if llm_cfg.base_url:
        kwargs["base_url"] = llm_cfg.base_url

    return create_llm(provider, **kwargs)


async def _single_chat(
    llm: BaseLLM,
    messages: list[Message],
) -> str:
    """Send messages and return the assistant's reply."""
    response = await llm.chat(messages)
    return response.content or ""


def _print_assistant(content: str) -> None:
    """Render the assistant's response as a Rich Markdown panel."""
    console.print()
    console.print(
        Panel(
            Markdown(content),
            title="[bold bright_green]Assistant[/bold bright_green]",
            border_style="bright_green",
            padding=(1, 2),
        )
    )


def _print_welcome(model: str, system_msg: str) -> None:
    """Print a welcome banner for interactive mode."""
    console.print()
    console.rule("[bold magenta]agent2 chat[/bold magenta]", style="magenta")
    console.print(
        f"  [dim]Model:[/dim]  [bold]{model}[/bold]\n"
        f"  [dim]System:[/dim] [italic]{system_msg}[/italic]\n"
        f"  [dim]Type[/dim]  [bold yellow]exit[/bold yellow] [dim]or[/dim] "
        f"[bold yellow]quit[/bold yellow] [dim]to leave.  Ctrl+C also works.[/dim]"
    )
    console.rule(style="dim")


def _read_user_input() -> str | None:
    """Read user input, returning None on EOF / exit commands."""
    try:
        console.print()
        text = console.input("[bold cyan]You:[/bold cyan] ").strip()
    except (EOFError, KeyboardInterrupt):
        return None
    if text.lower() in ("exit", "quit"):
        return None
    return text


# ── Main routines ──────────────────────────────────────────────────


async def _run_single(llm: BaseLLM, system_msg: str, prompt: str) -> None:
    """Single-turn mode: answer the prompt and exit."""
    messages = [Message.system(system_msg), Message.user(prompt)]
    reply = await _single_chat(llm, messages)
    _print_assistant(reply)


async def _run_interactive(
    llm: BaseLLM,
    system_msg: str,
    first_message: str | None = None,
) -> None:
    """Multi-turn interactive chat loop."""
    model_display = llm.model
    _print_welcome(model_display, system_msg)

    messages: list[Message] = [Message.system(system_msg)]

    # If a first message was provided via -i, process it immediately
    if first_message:
        console.print(f"\n[bold cyan]You:[/bold cyan] {first_message}")
        messages.append(Message.user(first_message))
        reply = await _single_chat(llm, messages)
        messages.append(Message.assistant(content=reply))
        _print_assistant(reply)

    while True:
        user_input = _read_user_input()
        if user_input is None:
            console.print("\n[dim]Bye! 👋[/dim]\n")
            break
        if not user_input:
            continue

        messages.append(Message.user(user_input))

        reply = await _single_chat(llm, messages)
        messages.append(Message.assistant(content=reply))
        _print_assistant(reply)


# ── CLI entry point ────────────────────────────────────────────────


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="agent2-chat",
        description="Chat with an LLM via the agent2 framework.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Override the model name (e.g. gpt-4o, deepseek-v4-flash).",
    )
    parser.add_argument(
        "--sys-msg",
        default=None,
        help="Set a custom system message.",
    )
    parser.add_argument(
        "-p",
        metavar="MSG",
        default=None,
        help="Single-turn mode: send MSG, print the reply, and exit.",
    )
    parser.add_argument(
        "-i",
        metavar="MSG",
        default=None,
        help="Interactive mode with MSG as the first user message.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    args = parse_args(argv)
    llm = _build_llm(args)
    system_msg = args.sys_msg or DEFAULT_SYSTEM_MSG

    if args.p:
        asyncio.run(_run_single(llm, system_msg, args.p))
    else:
        asyncio.run(_run_interactive(llm, system_msg, first_message=args.i))


# Allow ``python -m agent2.app.chat``
if __name__ == "__main__":
    main()
