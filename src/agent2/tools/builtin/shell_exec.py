"""Built-in tool: shell command execution."""

from __future__ import annotations

import asyncio

from agent2.tools.base import tool


@tool(name="shell_exec", description="Execute a shell command and return its stdout, stderr, and exit code.")
async def shell_exec(command: str, timeout: float = 30.0) -> str:
    """Execute a shell command asynchronously and return the result.

    Parameters
    ----------
    command : str
        The shell command string to execute.
    timeout : float
        Timeout in seconds (default: 30.0).
    """
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            return f"Error: Command timed out after {timeout} seconds."

        stdout = stdout_b.decode("utf-8", errors="replace")
        stderr = stderr_b.decode("utf-8", errors="replace")
        exit_code = proc.returncode

        output_parts: list[str] = []
        if stdout:
            if len(stdout) > 8000:
                stdout = stdout[:8000] + f"\n... (stdout truncated, total {len(stdout)} chars)"
            output_parts.append(stdout)
        if stderr:
            if len(stderr) > 2000:
                stderr = stderr[:2000] + f"\n... (stderr truncated, total {len(stderr)} chars)"
            output_parts.append(f"[stderr]\n{stderr}")
        if exit_code != 0:
            output_parts.append(f"(exit code: {exit_code})")

        result = "\n".join(output_parts).strip()
        if not result:
            return f"(Command executed with exit code {exit_code}, no output)"
        return result
    except Exception as e:
        return f"Execution error: {e}"
