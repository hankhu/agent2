"""Structured logging with rich output for Agent thinking/action/observation loops."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.text import Text
from rich.table import Table
from rich.theme import Theme

# ── Custom Theme ────────────────────────────────────────────────────
_theme = Theme(
    {
        "thought": "bold cyan",
        "action": "bold yellow",
        "observation": "bold green",
        "error": "bold red",
        "agent": "bold magenta",
        "tool": "bold blue",
        "plan": "bold white",
        "memory": "bold #A78BFA",
    }
)

console = Console(theme=_theme)

_file_lock = threading.Lock()


class AgentLogger:
    """Structured logger that visualises the Agent reasoning loop.

    Usage::

        log = AgentLogger("ResearchAgent")
        log.thought("I need to search for recent papers on RAG.")
        log.action("web_search", {"query": "RAG papers 2025"})
        log.observation("Found 3 relevant papers ...")
        log.final_answer("Here is a summary ...")
    """

    def __init__(
        self,
        agent_name: str,
        *,
        verbose: bool = True,
        log_file: Path | str | None = None,
    ) -> None:
        self.agent_name = agent_name
        self.verbose = verbose
        self.log_file = Path(log_file) if log_file else None
        self._step = 0
        self._start_time: float | None = None

    def _write_log(self, tag: str, message: str) -> None:
        """Write timestamped entry to log file if configured."""
        if not self.log_file:
            return
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] [{tag.upper()}] {message.strip()}\n"
        try:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            with _file_lock, open(self.log_file, "a", encoding="utf-8") as f:
                f.write(entry)
        except OSError:
            pass

    # ── Lifecycle ───────────────────────────────────────────────────

    def start(self, task: str) -> None:
        """Log the beginning of an agent run."""
        self._start_time = time.monotonic()
        self._step = 0
        self._write_log("START", f"Task: {task}")
        if not self.verbose:
            return
        console.print()
        console.rule(f"[agent]🤖 {self.agent_name}[/agent]", style="magenta")
        console.print(
            Panel(
                Markdown(task),
                title="📋 Task",
                border_style="cyan",
                padding=(1, 2),
            )
        )

    def finish(self, summary: str | None = None) -> None:
        """Log the end of an agent run."""
        self._write_log("FINISH", summary or "Task completed")
        if not self.verbose:
            return
        elapsed = (
            f" ({time.monotonic() - self._start_time:.1f}s)"
            if self._start_time
            else ""
        )
        msg = f"[agent]✅ {self.agent_name}[/agent] completed in {self._step} steps{elapsed}"
        if summary:
            console.print(
                Panel(Markdown(summary), title=msg, border_style="green", padding=(1, 2))
            )
        else:
            console.rule(msg, style="green")
        console.print()

    # ── Step-level logging ──────────────────────────────────────────

    def thought(self, content: str) -> None:
        """Log a reasoning / thinking step."""
        self._step += 1
        self._write_log(f"THOUGHT_STEP_{self._step}", content)
        if not self.verbose:
            return
        console.print()
        header = Text(f"💭 Step {self._step} — Thought", style="thought")
        console.print(Panel(Markdown(content), title=header, border_style="cyan"))

    def action(self, tool_name: str, arguments: dict[str, Any] | None = None) -> None:
        """Log a tool invocation."""
        self._write_log("ACTION", f"{tool_name}({arguments or {}})")
        if not self.verbose:
            return
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("key", style="bold")
        table.add_column("value")
        table.add_row("Tool", f"[tool]{tool_name}[/tool]")
        if arguments:
            for k, v in arguments.items():
                display = str(v)
                if len(display) > 200:
                    display = display[:200] + "…"
                table.add_row(k, display)
        console.print(Panel(table, title="⚡ Action", border_style="yellow"))

    def observation(self, content: str, *, is_error: bool = False) -> None:
        """Log the result of a tool execution."""
        tag = "ERROR" if is_error else "OBSERVATION"
        self._write_log(tag, content)
        if not self.verbose:
            return
        style = "error" if is_error else "observation"
        icon = "❌" if is_error else "👁️"
        display = content
        if len(display) > 1000:
            display = display[:1000] + "\n\n… (truncated)"
        console.print(
            Panel(
                Markdown(display),
                title=f"{icon} Observation",
                border_style="red" if is_error else "green",
            )
        )

    def final_answer(self, content: str) -> None:
        """Log the final answer returned by the agent."""
        self._write_log("FINAL_ANSWER", content)
        if not self.verbose:
            return
        console.print(
            Panel(
                Markdown(content),
                title="🎯 Final Answer",
                border_style="bright_green",
                padding=(1, 2),
            )
        )

    # ── Planning ────────────────────────────────────────────────────

    def plan(self, steps: list[str]) -> None:
        """Log a generated execution plan."""
        self._write_log("PLAN", "\n".join(steps))
        if not self.verbose:
            return
        table = Table(title="📝 Execution Plan", show_lines=True, border_style="white")
        table.add_column("#", style="bold", width=4)
        table.add_column("Step", style="plan")
        for i, step in enumerate(steps, 1):
            table.add_row(str(i), step)
        console.print(table)

    def plan_step_start(self, index: int, description: str) -> None:
        self._write_log(f"PLAN_STEP_{index}_START", description)
        if not self.verbose:
            return
        console.print(f"  [plan]▶ Step {index}:[/plan] {description}")

    def plan_step_done(self, index: int) -> None:
        self._write_log(f"PLAN_STEP_{index}_DONE", "Complete")
        if not self.verbose:
            return
        console.print(f"  [observation]✓ Step {index} complete[/observation]")

    # ── Memory ──────────────────────────────────────────────────────

    def memory_recall(self, query: str, results_count: int) -> None:
        self._write_log("MEMORY_RECALL", f"'{query}' -> {results_count} results")
        if not self.verbose:
            return
        console.print(
            f"  [memory]🧠 Memory recall:[/memory] '{query}' → {results_count} results"
        )

    def memory_store(self, summary: str) -> None:
        self._write_log("MEMORY_STORE", summary)
        if not self.verbose:
            return
        console.print(f"  [memory]💾 Memory stored:[/memory] {summary}")

    # ── Multi-Agent ─────────────────────────────────────────────────

    def delegate(self, from_agent: str, to_agent: str, task: str) -> None:
        self._write_log("DELEGATE", f"{from_agent} -> {to_agent}: {task}")
        if not self.verbose:
            return
        console.print(
            f"  [agent]📨 {from_agent}[/agent] → [agent]{to_agent}[/agent]: {task}"
        )

    def agent_message(self, from_agent: str, content: str) -> None:
        self._write_log("AGENT_MESSAGE", f"{from_agent}: {content}")
        if not self.verbose:
            return
        display = content if len(content) <= 300 else content[:300] + "…"
        console.print(f"  [agent]💬 {from_agent}:[/agent] {display}")
