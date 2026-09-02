"""Helpers for extracting JSON from LLM output."""

from __future__ import annotations

import json
import re
from typing import Any


def extract_json(text: str) -> Any:
    """Extract and parse JSON from *text*, tolerating Markdown fences.

    Tries, in order:
    1. Fenced code block (```json ... ``` or ``` ... ```)
    2. First top-level JSON array or object found via regex
    3. Plain ``json.loads`` on the stripped text

    Raises ``json.JSONDecodeError`` if nothing can be parsed.
    """
    # 1. Markdown fenced block
    m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 2. First JSON array or object
    m = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # 3. Plain parse
    return json.loads(text.strip())
