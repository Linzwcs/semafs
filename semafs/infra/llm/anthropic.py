from __future__ import annotations
from typing import Any, Dict
from ...core.exceptions import LLMAdapterError
from ...ports.llm import BaseLLMAdapter, _TREE_OPS_SCHEMA


class AnthropicAdapter(BaseLLMAdapter):
    """Anthropic Claude 适配器（tool use 格式）。"""

    def __init__(self,
                 client: Any,
                 model: str = "claude-haiku-4-5-20251001") -> None:
        self._client = client
        self._model = model

    async def _call_api(self, system: str, user: str) -> Dict:
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
        for block in resp.content:
            if block.type == "tool_use" and block.name == "tree_ops":
                return block.input
        raise LLMAdapterError("Anthropic 未调用 tree_ops tool")
