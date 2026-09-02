"""Interactive chat application built on agent2.

Usage examples::

    # Interactive chat with built-in tools (file_read, file_write, shell_exec)
    uv run -m agent2.app.chat

    # Interactively select model from menu at startup
    uv run -m agent2.app.chat -s

    # Override model directly
    uv run -m agent2.app.chat --model deepseek

    # Set system message
    uv run -m agent2.app.chat --sys-msg "You are a Python expert."

    # Single-turn mode with tools — run and exit
    uv run -m agent2.app.chat -p "List files in the current directory and check git status."

    # Interactive mode with first message pre-filled
    uv run -m agent2.app.chat -i "Hi, please check what files are in this project."

    # Disable tools (pure LLM chat mode)
    uv run -m agent2.app.chat --no-tools
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any

from rich import box
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from agent2.agent.react import ReActAgent
from agent2.app.config import get_last_model, load_config, set_last_model
from agent2.llm import create_llm
from agent2.tools.builtin import file_read, file_write, shell_exec
from agent2.utils.config import settings

# ── Console ─────────────────────────────────────────────────────────

console = Console()

DEFAULT_SYSTEM_MSG = (
    "You are a helpful assistant with access to local tools (reading/writing files, "
    "executing shell commands). Use tools proactively when needed to inspect files, "
    "run commands, or create/modify code."
)


# ── Model Selection Dialog ──────────────────────────────────────────


def _is_local_or_lan(url: str | None) -> bool:
    """Return True if ``url`` points to localhost or a private LAN address."""
    import ipaddress

    if not url:
        return False
    host = url.lower().strip()
    if "://" in host:
        host = host.split("://", 1)[1]
    # Strip path and port.
    host = host.split("/", 1)[0]
    if host.startswith("["):
        end = host.find("]")
        host = host[1:end] if end != -1 else host.strip("[]")
    else:
        host = host.split(":", 1)[0].strip()

    if host in {"localhost", "0.0.0.0"} or host.endswith(".local"):
        return True
    try:
        return ipaddress.ip_address(host).is_private
    except ValueError:
        return False


def _provider_from_url(url: str | None) -> str:
    """Extract a short provider name from a base URL.

    Examples::

        https://api.deepseek.com/v1       -> deepseek
        https://integrate.api.nvidia.com  -> nvidia
        https://api.siliconflow.cn        -> siliconflow
        http://localhost:11434/v1         -> localhost
    """
    if not url:
        return "default"
    host = url.lower().strip()
    if "://" in host:
        host = host.split("://", 1)[1]
    host = host.split("/", 1)[0]
    if host.startswith("["):
        end = host.find("]")
        host = host[1:end] if end != -1 else host.strip("[]")
    else:
        host = host.split(":", 1)[0].strip()

    if not host:
        return "default"
    if "default" in host or host.startswith("openai api"):
        return "default"
    if host in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}:
        return host
    # IP addresses: show the address itself.
    parts = host.split(".")
    if len(parts) == 4 and all(p.isdigit() for p in parts):
        return host
    if len(parts) >= 2:
        return parts[-2] or "default"
    return host


def _visible_model(item: dict[str, Any]) -> bool:
    """Hide remote models that have no API key; keep local/LAN models."""
    if item.get("api_key") or settings.api_key:
        return True
    return _is_local_or_lan(item.get("base_url"))


def get_available_models() -> list[dict[str, Any]]:
    """Return visible models from config and built-in presets.

    Remote models without an API key are hidden.  Local/LAN models are always
    shown because they normally do not require a key.
    """
    cfg = load_config()
    items: list[dict[str, Any]] = []

    # 1. Models from config.models
    for name, entry in cfg.models.items():
        if isinstance(entry, dict):
            provider_name = entry.get("provider")
            prov = cfg.providers.get(provider_name) if provider_name else None
            base_url = (
                entry.get("base_url")
                or (prov.base_url if prov else None)
                or cfg.llm.base_url
                or settings.base_url
                or "Default endpoint"
            )
            api_key = entry.get("api_key") or (prov.api_key if prov else None) or cfg.llm.api_key
            items.append({
                "name": name,
                "model": entry.get("model_id") or entry.get("model", name),
                "base_url": base_url,
                "provider": provider_name or _provider_from_url(base_url),
                "api_key": api_key,
                "source": "config.models",
            })
        elif isinstance(entry, str):
            prov = cfg.providers.get(entry)
            if prov:
                base_url = prov.base_url or settings.base_url or "Default endpoint"
                api_key = prov.api_key or cfg.llm.api_key
                items.append({
                    "name": name,
                    "model": name,
                    "base_url": base_url,
                    "provider": entry,
                    "api_key": api_key,
                    "source": "config.models",
                })
            else:
                base_url = cfg.llm.base_url or settings.base_url or "Default endpoint"
                items.append({
                    "name": name,
                    "model": entry,
                    "base_url": base_url,
                    "provider": _provider_from_url(base_url),
                    "api_key": cfg.llm.api_key,
                    "source": "config.models",
                })

    # 2. Add any providers not already referenced by a model
    for p_name, p_cfg in cfg.providers.items():
        if not any(m.get("provider") == p_name or m.get("name") == p_name for m in items):
            base_url = p_cfg.base_url or "Default endpoint"
            items.append({
                "name": p_name,
                "model": p_name,
                "base_url": base_url,
                "provider": p_name,
                "api_key": p_cfg.api_key,
                "source": "config.providers",
            })

    # 3. Config default model if specified and not already in list
    default_model = cfg.default or cfg.llm.model
    if default_model and not any(m["name"] == "default" or m["model"] == default_model or m["name"] == default_model for m in items):
        base_url = cfg.llm.base_url or settings.base_url or "Default endpoint"
        items.append({
            "name": "default",
            "model": default_model,
            "base_url": base_url,
            "provider": _provider_from_url(base_url),
            "api_key": cfg.llm.api_key,
            "source": "config.default",
        })

    # 4. Built-in Presets
    if not any(m["name"].lower() == "deepseek" for m in items):
        items.append({
            "name": "deepseek",
            "model": "deepseek-chat",
            "base_url": "https://api.deepseek.com/v1",
            "provider": "deepseek",
            "api_key": cfg.llm.api_key,
            "source": "preset",
        })
    if not any(m["name"].lower() == "ollama" for m in items):
        items.append({
            "name": "ollama",
            "model": "llama3.1",
            "base_url": "http://localhost:11434/v1",
            "provider": "localhost",
            "api_key": "ollama",
            "source": "preset",
        })
    if not any(m["name"].lower() == "openai" for m in items):
        items.append({
            "name": "openai",
            "model": "gpt-4o-mini",
            "base_url": "api.openai.com",
            "provider": "openai",
            "api_key": cfg.llm.api_key,
            "source": "preset",
        })

    return [item for item in items if _visible_model(item)]



def select_model_menu(current_name: str | None = None) -> str:
    """Display an interactive table menu to select a model."""
    models = get_available_models()
    if not models:
        return current_name or "gpt-4o-mini"

    table = Table(
        title="🤖 [bold magenta]Model Selection Menu[/bold magenta]",
        box=box.ROUNDED,
        header_style="bold cyan",
        show_header=True,
        border_style="magenta",
        padding=(0, 1),
    )
    table.add_column("#", justify="center", style="bold yellow", width=4)
    table.add_column("Provider", style="bold green", min_width=10, max_width=16, overflow="ellipsis")
    table.add_column("Model", style="bright_white", min_width=18, max_width=50, overflow="ellipsis")
    table.add_column("Status", justify="center", width=10)

    default_idx = 1
    for idx, m in enumerate(models, 1):
        is_active = current_name and (
            m["name"].lower() == current_name.lower()
            or m["model"].lower() == current_name.lower()
        )
        if is_active:
            default_idx = idx
            status = "[bold green]● Active[/bold green]"
        else:
            status = ""
        table.add_row(
            str(idx),
            m.get("provider") or m["name"],
            m["model"],
            status,
        )

    console.print()
    console.print(table)
    console.print(
        f"  [dim]• Enter a number [1-{len(models)}], a model alias, or a custom model name.[/dim]\n"
        f"  [dim]• Press [bold]Enter[/bold] for default: [bold green]{models[default_idx - 1]['name']}[/bold green][/dim]\n"
    )

    try:
        choice = console.input(
            f"[bold cyan]Select model [1-{len(models)}] (default: {models[default_idx - 1]['name']}): [/bold cyan]"
        ).strip()
    except (EOFError, KeyboardInterrupt):
        return current_name or models[0]["name"]

    if not choice:
        return models[default_idx - 1]["name"]

    if choice.isdigit():
        num = int(choice)
        if 1 <= num <= len(models):
            return models[num - 1]["name"]

    # Exact match
    for m in models:
        if choice.lower() == m["name"].lower() or choice.lower() == m["model"].lower():
            return m["name"]

    # Substring / partial match (both directions so friendly labels like
    # "小米Mimo-v2.5" can resolve to the configured "mimo-v2.5").
    choice_l = choice.lower()
    matched = [
        m for m in models
        if (
            choice_l in m["name"].lower()
            or choice_l in m["model"].lower()
            or m["name"].lower() in choice_l
            or m["model"].lower() in choice_l
        )
    ]
    if matched:
        return matched[0]["name"]

    return choice


def _switch_agent_model(agent: ReActAgent, model_name: str) -> None:
    """Recreate and assign a new LLM instance to the agent."""
    new_llm = create_llm(model_name)
    agent.llm = new_llm
    set_last_model(new_llm.model)
    console.print()
    console.print(
        Panel(
            f"Active model switched to: [bold green]{new_llm.model}[/bold green] (key: [bold cyan]{model_name}[/bold cyan])",
            title="🔄 Model Switched",
            border_style="green",
            padding=(0, 1),
        )
    )


# ── Helpers ─────────────────────────────────────────────────────────


def _build_agent(args: argparse.Namespace) -> ReActAgent:
    """Create an agent instance with default tools and merged config + CLI args."""
    cfg = load_config()

    # Model selection resolution
    if args.select:
        name_or_model = select_model_menu(current_name=args.model or cfg.default or cfg.llm.model)
    else:
        name_or_model = args.model or get_last_model() or cfg.default or cfg.llm.model

    llm = create_llm(name_or_model)
    if args.model or args.select:
        set_last_model(llm.model)
    system_msg = args.sys_msg or DEFAULT_SYSTEM_MSG


    tools = []
    if not args.no_tools:
        tools = [file_read, file_write, shell_exec]

    return ReActAgent(
        name="assistant",
        llm=llm,
        system_prompt=system_msg,
        tools=tools,
        verbose=True,
    )


def _print_welcome(model: str, system_msg: str, tool_names: list[str]) -> None:
    """Print a welcome banner for interactive mode."""
    console.print()
    console.rule("[bold magenta]agent2 chat[/bold magenta]", style="magenta")
    tools_str = (
        ", ".join(f"[bold green]{t}[/bold green]" for t in tool_names)
        if tool_names
        else "[dim]None (pure chat mode)[/dim]"
    )
    console.print(
        f"  [dim]Model:[/dim]    [bold]{model}[/bold]\n"
        f"  [dim]Tools:[/dim]    {tools_str}\n"
        f"  [dim]Commands:[/dim] [bold cyan]/model[/bold cyan] (switch model), "
        f"[bold cyan]/tools[/bold cyan] (view tools), "
        f"[bold cyan]/clear[/bold cyan] (reset history), "
        f"[bold cyan]/help[/bold cyan], "
        f"[bold yellow]exit[/bold yellow]"
    )
    console.rule(style="dim")


def _print_help() -> None:
    """Print available interactive commands."""
    table = Table(
        title="💡 [bold cyan]Available Commands[/bold cyan]",
        box=box.SIMPLE,
        header_style="bold yellow",
        show_header=True,
    )
    table.add_column("Command", style="bold green", width=18)
    table.add_column("Description", style="white")

    table.add_row("/model [name]", "Open model selection menu or switch directly (e.g. `/model deepseek`)")
    table.add_row("/tools", "List currently enabled tools and their descriptions")
    table.add_row("/clear", "Clear conversation history")
    table.add_row("/help", "Show this help table")
    table.add_row("exit / quit", "Exit the chat session (or Ctrl+C / Ctrl+D)")

    console.print()
    console.print(table)


def _print_tools(agent: ReActAgent) -> None:
    """Print registered tools info."""
    tools = agent.tool_registry.list_tools()
    if not tools:
        console.print("\n[dim]No tools currently registered (pure chat mode).[/dim]\n")
        return

    table = Table(
        title="🔧 [bold green]Active Tools[/bold green]",
        box=box.ROUNDED,
        header_style="bold cyan",
        show_header=True,
        border_style="green",
    )
    table.add_column("Tool Name", style="bold green", width=16)
    table.add_column("Description", style="white")

    for t in tools:
        table.add_row(t.name, t.description or "(no description)")

    console.print()
    console.print(table)


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


async def _run_single(agent: ReActAgent, prompt: str) -> None:
    """Single-turn mode: answer the prompt and exit."""
    await agent.chat(prompt)


async def _run_interactive(
    agent: ReActAgent,
    first_message: str | None = None,
) -> None:
    """Multi-turn interactive chat loop."""
    model_display = agent.llm.model
    tool_names = [t.name for t in agent.tool_registry.list_tools()]
    _print_welcome(model_display, agent.system_prompt, tool_names)

    # If a first message was provided via -i, process it immediately
    if first_message:
        console.print(f"\n[bold cyan]You:[/bold cyan] {first_message}")
        await agent.chat(first_message)

    while True:
        user_input = _read_user_input()
        if user_input is None:
            console.print("\n[dim]Bye! 👋[/dim]\n")
            break
        if not user_input:
            continue

        # Handle slash commands
        if user_input.startswith("/"):
            parts = user_input.strip().split(maxsplit=1)
            cmd = parts[0].lower()
            arg = parts[1].strip() if len(parts) > 1 else None

            if cmd in ("/model", "/models"):
                if arg:
                    _switch_agent_model(agent, arg)
                else:
                    selected = select_model_menu(current_name=agent.llm.model)
                    _switch_agent_model(agent, selected)
                continue

            elif cmd == "/tools":
                _print_tools(agent)
                continue

            elif cmd == "/clear":
                agent.reset()
                console.print("\n[bold yellow]🧹 Conversation history cleared.[/bold yellow]\n")
                continue

            elif cmd == "/help":
                _print_help()
                continue

            elif cmd in ("/exit", "/quit"):
                console.print("\n[dim]Bye! 👋[/dim]\n")
                break

            else:
                console.print(
                    f"[dim yellow]Unknown command: {cmd}. Type [bold]/help[/bold] for available commands.[/dim yellow]"
                )
                continue

        await agent.chat(user_input)


# ── CLI entry point ────────────────────────────────────────────────


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    from agent2 import __version__

    parser = argparse.ArgumentParser(
        prog="agent2-chat",
        description="Chat with an LLM / ReAct Agent via the agent2 framework.",
    )
    parser.add_argument(
        "--version",
        "-v",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "-s",
        "--select",
        action="store_true",
        default=False,
        help="Interactively select a model from the menu at startup.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Override the model name (e.g. gpt-4o, deepseek).",
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
        help="Single-turn mode: send MSG, execute/answer, and exit.",
    )
    parser.add_argument(
        "-i",
        metavar="MSG",
        default=None,
        help="Interactive mode with MSG as the first user message.",
    )
    parser.add_argument(
        "--no-tools",
        action="store_true",
        default=False,
        help="Disable built-in tools (pure LLM chat mode).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    args = parse_args(argv)
    agent = _build_agent(args)

    if args.p:
        asyncio.run(_run_single(agent, args.p))
    else:
        asyncio.run(_run_interactive(agent, first_message=args.i))


# Allow ``python -m agent2.app.chat``
if __name__ == "__main__":
    main()
