"""OpenAI adapter for SemaFS LLM integration."""

from __future__ import annotations
import functools
import json
import logging
import time
from typing import Any, Awaitable, Callable, Dict, TypeVar, cast
from ...core.exceptions import SemaFSError
from ...core.plan.ops import Plan
from ...core.snapshot import Snapshot
from .prompt import (
    _TREE_OPS_SCHEMA,
    _PLACEMENT_SCHEMA,
    _SUMMARY_SCHEMA,
    _PLAN_REVIEW_SCHEMA,
    build_prompt,
    build_placement_prompt,
    build_plan_review_prompt,
    build_summary_prompt,
)

logger = logging.getLogger(__name__)
TimedCall = TypeVar("TimedCall", bound=Callable[..., Awaitable[Dict]])


def time_it(func: TimedCall) -> TimedCall:
    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Dict:
        start_time = time.perf_counter()
        logger.debug("llm.call.start fn=%s", func.__name__)
        try:
            return await func(*args, **kwargs)
        finally:
            elapsed = time.perf_counter() - start_time
            logger.debug("llm.call.done fn=%s elapsed_sec=%.5f", func.__name__,
                         elapsed)

    return cast(TimedCall, wrapper)


class OpenAIAdapter:
    """OpenAI API adapter using function calling."""

    def __init__(self, client: Any, model: str = "gpt-4o-mini") -> None:
        self._client = client
        self._model = model

    @time_it
    async def call(
            self,
            snapshot: Snapshot,
            *,
            retry_feedback: dict[str, Any] | None = None,
            frozen_ops: tuple[dict[str, Any], ...] = (),
    ) -> Dict:
        """Call LLM with snapshot context, return raw dict."""
        system, user = build_prompt(
            snapshot,
            retry_feedback=retry_feedback,
            frozen_ops=frozen_ops,
        )

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

    @time_it
    async def call_placement(
        self,
        *,
        content: str,
        current_path: str,
        current_summary: str,
        children: tuple[dict[str, Any], ...],
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

    @time_it
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

    @time_it
    async def call_plan_review(self, snapshot: Snapshot, plan: Plan) -> Dict:
        """Call LLM to review candidate plan quality."""
        system, user = build_plan_review_prompt(snapshot, plan)
        tool = {
            "type": "function",
            "function": {
                "name": _PLAN_REVIEW_SCHEMA["name"],
                "description": _PLAN_REVIEW_SCHEMA["description"],
                "parameters": _PLAN_REVIEW_SCHEMA["input_schema"],
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
                        "name": "review_tree_ops"
                    },
                },
            )
        except Exception as e:
            raise SemaFSError(f"OpenAI plan review call failed: {e}") from e

        if not hasattr(resp, "choices") or not resp.choices:
            raise SemaFSError("Unexpected OpenAI plan review response format")
        msg = resp.choices[0].message
        if not msg.tool_calls:
            raise SemaFSError("OpenAI did not call review_tree_ops tool")
        return json.loads(msg.tool_calls[0].function.arguments)
