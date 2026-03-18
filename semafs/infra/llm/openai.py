"""OpenAI adapter for SemaFS LLM integration."""

from __future__ import annotations
import json
from typing import Any, Dict

from ...core.exceptions import SemaFSError
from ...core.snapshot import Snapshot
from .prompt import _TREE_OPS_SCHEMA, build_prompt


class OpenAIAdapter:
    """OpenAI API adapter using function calling."""

    def __init__(self, client: Any, model: str = "gpt-4o-mini") -> None:
        self._client = client
        self._model = model

    async def call(self, snapshot: Snapshot) -> Dict:
        """Call LLM with snapshot context, return raw dict."""
        system, user = build_prompt(snapshot)

        tool = {
            "type": "function",
            "function": {
                "name": _TREE_OPS_SCHEMA["name"],
                "description": _TREE_OPS_SCHEMA["description"],
                "parameters": _TREE_OPS_SCHEMA["input_schema"],
            },
        }

        try:
            resp = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                tools=[tool],
                tool_choice={"type": "function", "function": {"name": "tree_ops"}},
            )
        except Exception as e:
            raise SemaFSError(f"OpenAI API call failed: {e}") from e

        if not hasattr(resp, "choices") or not resp.choices:
            raise SemaFSError("Unexpected OpenAI response format")

        msg = resp.choices[0].message
        if not msg.tool_calls:
            raise SemaFSError("OpenAI did not call tree_ops tool")

        return json.loads(msg.tool_calls[0].function.arguments)
