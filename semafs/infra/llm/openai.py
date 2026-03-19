"""OpenAI adapter for SemaFS LLM integration."""

from __future__ import annotations
import json
from typing import Any, Dict

from ...core.exceptions import SemaFSError
from ...core.snapshot import Snapshot
from .prompt import (
    _TREE_OPS_SCHEMA,
    _PLACEMENT_SCHEMA,
    _SUMMARY_SCHEMA,
    build_prompt,
    build_placement_prompt,
    build_summary_prompt,
)


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
                    {
                        "role": "system",
                        "content": system
                    },
                    {
                        "role": "user",
                        "content": user
                    },
                ],
                tools=[tool],
                tool_choice={
                    "type": "function",
                    "function": {
                        "name": "tree_ops"
                    },
                },
            )
        except Exception as e:
            raise SemaFSError(f"OpenAI API call failed: {e}") from e

        if not hasattr(resp, "choices") or not resp.choices:
            raise SemaFSError("Unexpected OpenAI response format")

        msg = resp.choices[0].message
        if not msg.tool_calls:
            raise SemaFSError("OpenAI did not call tree_ops tool")

        return json.loads(msg.tool_calls[0].function.arguments)

    async def call_placement(
        self,
        *,
        content: str,
        current_path: str,
        current_summary: str,
        children: tuple[dict[str, str], ...],
    ) -> Dict:
        """Call LLM for one placement routing step."""
        system, user = build_placement_prompt(
            content=content,
            current_path=current_path,
            current_summary=current_summary,
            children=children,
        )
        tool = {
            "type": "function",
            "function": {
                "name": _PLACEMENT_SCHEMA["name"],
                "description": _PLACEMENT_SCHEMA["description"],
                "parameters": _PLACEMENT_SCHEMA["input_schema"],
            },
        }
        try:
            resp = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {
                        "role": "system",
                        "content": system
                    },
                    {
                        "role": "user",
                        "content": user
                    },
                ],
                tools=[tool],
                tool_choice={
                    "type": "function",
                    "function": {
                        "name": "route_placement"
                    },
                },
            )
        except Exception as e:
            raise SemaFSError(f"OpenAI placement call failed: {e}") from e

        if not hasattr(resp, "choices") or not resp.choices:
            raise SemaFSError("Unexpected OpenAI placement response format")
        msg = resp.choices[0].message
        if not msg.tool_calls:
            raise SemaFSError("OpenAI did not call route_placement tool")
        return json.loads(msg.tool_calls[0].function.arguments)

    async def call_summary(self, snapshot: Snapshot) -> Dict:
        """Call LLM for summary-only generation."""
        system, user = build_summary_prompt(snapshot)
        tool = {
            "type": "function",
            "function": {
                "name": _SUMMARY_SCHEMA["name"],
                "description": _SUMMARY_SCHEMA["description"],
                "parameters": _SUMMARY_SCHEMA["input_schema"],
            },
        }
        try:
            resp = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {
                        "role": "system",
                        "content": system
                    },
                    {
                        "role": "user",
                        "content": user
                    },
                ],
                tools=[tool],
                tool_choice={
                    "type": "function",
                    "function": {
                        "name": "generate_summary"
                    },
                },
            )
        except Exception as e:
            raise SemaFSError(f"OpenAI summary call failed: {e}") from e

        if not hasattr(resp, "choices") or not resp.choices:
            raise SemaFSError("Unexpected OpenAI summary response format")
        msg = resp.choices[0].message
        if not msg.tool_calls:
            raise SemaFSError("OpenAI did not call generate_summary tool")
        return json.loads(msg.tool_calls[0].function.arguments)
