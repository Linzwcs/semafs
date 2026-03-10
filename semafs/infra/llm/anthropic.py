"""
Anthropic Claude adapter for SemaFS LLM integration.

This module provides AnthropicAdapter, which implements the BaseLLMAdapter
interface using Anthropic's messages API with tool use.

Requirements:
    - anthropic package (async client)
    - ANTHROPIC_API_KEY environment variable

Usage:
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic()
    adapter = AnthropicAdapter(client, model="claude-haiku-4-5-20251001")

    result = await adapter.call(context, max_children=10)
    # result contains ops, overall_reasoning, updated_content, etc.
"""
from __future__ import annotations
from typing import Any, Dict
from ...core.exceptions import LLMAdapterError
from ...ports.llm import BaseLLMAdapter, _TREE_OPS_SCHEMA


class AnthropicAdapter(BaseLLMAdapter):
    """
    Anthropic Claude adapter using tool use.

    This adapter uses Anthropic's native tool use format, which matches
    the _TREE_OPS_SCHEMA structure directly.

    The adapter uses `tool_choice` to force the model to call the
    tree_ops tool, ensuring consistent output format.

    Attributes:
        _client: Anthropic AsyncClient instance.
        _model: Model identifier (e.g., "claude-haiku-4-5-20251001").

    Example:
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic()
        adapter = AnthropicAdapter(client)

        # Used by HybridStrategy internally
        result = await adapter._call_api(system_prompt, user_prompt)
    """

    def __init__(self,
                 client: Any,
                 model: str = "claude-haiku-4-5-20251001") -> None:
        """
        Initialize the Anthropic adapter.

        Args:
            client: AsyncAnthropic client instance.
            model: Model identifier (default: "claude-haiku-4-5-20251001").
        """
        self._client = client
        self._model = model

    async def _call_api(self, system: str, user: str) -> Dict:
        """
        Call Anthropic's messages API with tool use.

        Uses the native tool use format and parses the tool_use block
        from the response.

        Args:
            system: System prompt string.
            user: User prompt string.

        Returns:
            Tool input dict containing:
            - ops: List of operation dicts
            - overall_reasoning: Explanation string
            - updated_content: New category summary
            - updated_name: Optional new display name
            - should_dirty_parent: Boolean flag

        Raises:
            LLMAdapterError: If tree_ops tool was not called.
        """
        # Make API call with forced tool use
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

        # Find and return the tool_use block
        for block in resp.content:
            if block.type == "tool_use" and block.name == "tree_ops":
                return block.input

        raise LLMAdapterError("Anthropic did not call tree_ops tool")
