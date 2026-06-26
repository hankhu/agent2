"""Built-in tool: sandboxed Python code execution."""

from __future__ import annotations

import io
import contextlib
import traceback

from agent2.tools.base import tool


@tool(description="Execute Python code and return the output. Use print() to produce output.")
def python_exec(code: str) -> str:
    """Execute Python code in a sandboxed environment.

    The code runs in a restricted namespace with limited builtins.
    Use print() statements to produce output.

    WARNING: This is a basic sandbox. For production use, consider
    using a proper sandboxing solution (Docker, gVisor, etc.).
    """
    # Capture stdout
    stdout = io.StringIO()

    # Restricted global namespace
    restricted_globals: dict = {
        "__builtins__": {
            "print": print,
            "len": len,
            "range": range,
            "enumerate": enumerate,
            "zip": zip,
            "map": map,
            "filter": filter,
            "sorted": sorted,
            "reversed": reversed,
            "sum": sum,
            "min": min,
            "max": max,
            "abs": abs,
            "round": round,
            "int": int,
            "float": float,
            "str": str,
            "bool": bool,
            "list": list,
            "dict": dict,
            "tuple": tuple,
            "set": set,
            "type": type,
            "isinstance": isinstance,
            "hasattr": hasattr,
            "getattr": getattr,
            "ValueError": ValueError,
            "TypeError": TypeError,
            "KeyError": KeyError,
            "IndexError": IndexError,
            "Exception": Exception,
            "True": True,
            "False": False,
            "None": None,
        }
    }

    try:
        with contextlib.redirect_stdout(stdout):
            exec(code, restricted_globals)

        output = stdout.getvalue()
        if not output:
            return "(Code executed successfully with no output)"
        if len(output) > 5000:
            return output[:5000] + "\n\n... (output truncated)"
        return output

    except Exception:
        error = traceback.format_exc()
        return f"Execution error:\n{error}"
