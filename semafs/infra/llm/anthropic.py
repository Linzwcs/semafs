"""Anthropic Claude adapter for SemaFS LLM integration."""

from __future__ import annotations
from typing import Any, Dict

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


class AnthropicAdapter:
    """Anthropic Claude adapter using tool use."""

    def __init__(
        self,
        client: Any,
        model: str = "claude-haiku-4-5-20251001",
    ) -> None:
        self._client = client
        self._model = model

    async def call(
        self,
        snapshot: Snapshot,
        *,
        retry_feedback: dict | None = None,
        frozen_ops: tuple[dict, ...] = (),
    ) -> Dict:
        """Call LLM with snapshot context, return raw dict."""
        system, user = build_prompt(
            snapshot,
            retry_feedback=retry_feedback,
            frozen_ops=frozen_ops,
        )

        try:
            resp = await self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                system=system,
                messages=[{
                    "role": "user",
                    "content": user
                }],
                tools=[_TREE_OPS_SCHEMA],
                tool_choice={
                    "type": "tool",
                    "name": "tree_ops"
                },
            )
        except Exception as e:
            raise SemaFSError(f"Anthropic API call failed: {e}") from e

        for block in resp.content:
            if block.type == "tool_use" and block.name == "tree_ops":
                return block.input

        raise SemaFSError("Anthropic did not call tree_ops tool")

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
        try:
            resp = await self._client.messages.create(
                model=self._model,
                max_tokens=512,
                system=system,
                messages=[{
                    "role": "user",
                    "content": user
                }],
                tools=[_PLACEMENT_SCHEMA],
                tool_choice={
                    "type": "tool",
                    "name": "route_placement"
                },
            )
        except Exception as e:
            raise SemaFSError(f"Anthropic placement call failed: {e}") from e

        for block in resp.content:
            if block.type == "tool_use" and block.name == "route_placement":
                return block.input
        raise SemaFSError("Anthropic did not call route_placement tool")

    async def call_summary(self, snapshot: Snapshot) -> Dict:
        """Call LLM for summary-only generation."""
        system, user = build_summary_prompt(snapshot)
        try:
            resp = await self._client.messages.create(
                model=self._model,
                max_tokens=512,
                system=system,
                messages=[{
                    "role": "user",
                    "content": user
                }],
                tools=[_SUMMARY_SCHEMA],
                tool_choice={
                    "type": "tool",
                    "name": "generate_summary"
                },
            )
        except Exception as e:
            raise SemaFSError(f"Anthropic summary call failed: {e}") from e

        for block in resp.content:
            if block.type == "tool_use" and block.name == "generate_summary":
                return block.input
        raise SemaFSError("Anthropic did not call generate_summary tool")

    async def call_plan_review(self, snapshot: Snapshot, plan: Plan) -> Dict:
        """Call LLM to review candidate plan quality."""
        system, user = build_plan_review_prompt(snapshot, plan)
        try:
            resp = await self._client.messages.create(
                model=self._model,
                max_tokens=512,
                system=system,
                messages=[{
                    "role": "user",
                    "content": user
                }],
                tools=[_PLAN_REVIEW_SCHEMA],
                tool_choice={
                    "type": "tool",
                    "name": "review_tree_ops"
                },
            )
        except Exception as e:
            raise SemaFSError(f"Anthropic plan review call failed: {e}") from e

        for block in resp.content:
            if block.type == "tool_use" and block.name == "review_tree_ops":
                return block.input
        raise SemaFSError("Anthropic did not call review_tree_ops tool")
