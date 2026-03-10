"""
OpenAI adapter for SemaFS LLM integration.

This module provides OpenAIAdapter, which implements the BaseLLMAdapter
interface using OpenAI's chat completions API with function calling.

Requirements:
    - openai package (async client)
    - OPENAI_API_KEY environment variable

Usage:
    from openai import AsyncOpenAI

    client = AsyncOpenAI()
    adapter = OpenAIAdapter(client, model="gpt-4o")

    result = await adapter.call(context, max_children=10)
    # result contains ops, overall_reasoning, updated_content, etc.
"""
from __future__ import annotations
import json
from typing import Any, Dict
from ...core.exceptions import LLMAdapterError
from ...ports.llm import BaseLLMAdapter, _TREE_OPS_SCHEMA


class OpenAIAdapter(BaseLLMAdapter):
    """
    OpenAI API adapter using function calling.

    This adapter converts the SemaFS tool schema to OpenAI's function
    calling format and handles response parsing.

    The adapter uses the `tool_choice` parameter to force the model
    to call the tree_ops function, ensuring consistent output format.

    Attributes:
        _client: OpenAI AsyncClient instance.
        _model: Model identifier (e.g., "gpt-4o", "gpt-4o-mini").

    Example:
        from openai import AsyncOpenAI

        client = AsyncOpenAI()
        adapter = OpenAIAdapter(client, model="gpt-4o")

        # Used by HybridStrategy internally
        result = await adapter._call_api(system_prompt, user_prompt)
    """

    def __init__(self, client: Any, model: str = "gpt-4o-mini") -> None:
        """
        Initialize the OpenAI adapter.

        Args:
            client: AsyncOpenAI client instance.
            model: Model identifier (default: "gpt-4o-mini").
        """
        self._client = client
        self._model = model

    async def _call_api(self, system: str, user: str) -> Dict:
        """
        Call OpenAI's chat completions API with function calling.

        Converts the Anthropic-style tool schema to OpenAI's function
        format and parses the response.

        Args:
            system: System prompt string.
            user: User prompt string.

        Returns:
            Parsed function arguments as a dict containing:
            - ops: List of operation dicts
            - overall_reasoning: Explanation string
            - updated_content: New category summary
            - updated_name: Optional new display name
            - should_dirty_parent: Boolean flag

        Raises:
            LLMAdapterError: If response format is invalid or tool not called.
        """
        # Convert to OpenAI function format
        tool = {
            "type": "function",
            "function": {
                "name": _TREE_OPS_SCHEMA["name"],
                "description": _TREE_OPS_SCHEMA["description"],
                "parameters": _TREE_OPS_SCHEMA["input_schema"],
            },
        }

        # Make API call with forced function calling
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
                }
            },
        )

        # Validate response format
        if not hasattr(resp, "choices") or not resp.choices:
            hint = "If using a custom API, ensure base_url ends with /v1 (e.g., https://xxx/v1)"
            raise LLMAdapterError(
                f"Unexpected API response format (received {type(resp).__name__}): {hint}")

        msg = resp.choices[0].message
        if not msg.tool_calls:
            raise LLMAdapterError("OpenAI did not call tree_ops tool")

        # Parse and return function arguments
        return json.loads(msg.tool_calls[0].function.arguments)
