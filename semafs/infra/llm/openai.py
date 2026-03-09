from __future__ import annotations
import json
from typing import Any, Dict
from ...core.exceptions import LLMAdapterError
from ...ports.llm import BaseLLMAdapter, _TREE_OPS_SCHEMA


class OpenAIAdapter(BaseLLMAdapter):

    def __init__(self, client: Any, model: str = "gpt-4o-mini") -> None:
        self._client = client
        self._model = model

    async def _call_api(self, system: str, user: str) -> Dict:
        tool = {
            "type": "function",
            "function": {
                "name": _TREE_OPS_SCHEMA["name"],
                "description": _TREE_OPS_SCHEMA["description"],
                "parameters": _TREE_OPS_SCHEMA["input_schema"],
            },
        }

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

        if not hasattr(resp, "choices") or not resp.choices:
            hint = "若使用自建 API，请确保 base_url 以 /v1 结尾（如 https://xxx/v1）"
            raise LLMAdapterError(
                f"API 返回格式异常（收到 {type(resp).__name__}）: {hint}")
        msg = resp.choices[0].message
        if not msg.tool_calls:
            raise LLMAdapterError("OpenAI 未调用 tree_ops tool")
        return json.loads(msg.tool_calls[0].function.arguments)
