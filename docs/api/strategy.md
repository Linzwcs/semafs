# Strategy API

维护策略的核心输入是 `Snapshot`，核心输出是 `RawPlan | None`。

## Strategy Protocol

```python
class Strategy(Protocol):
    async def draft(self, snapshot: Snapshot) -> RawPlan | None: ...
```

- 返回 `None`：本轮不做结构重排。
- 返回 `RawPlan`：进入 guard + resolve + execute 流程。

## Built-in Strategy

### `HybridStrategy`

```python
from semafs.algo import HybridStrategy

strategy = HybridStrategy(adapter, force_threshold=None)
```

高层行为：

- 健康且无 pending：跳过
- 压力/溢出：调用 LLM 生成 raw ops
- LLM 失败：跳过本轮重排（安全 no-op）

## Raw Plan Types

`RawPlan.ops` 可以包含：

- `RawMerge`
- `RawGroup`
- `RawMove`
- `RawRename`
- `RawRollup`

解析后会转为可执行 `Plan`（见 [Operations](/api/operations)）。

## LLM Adapter Protocol

```python
class LLMAdapter(Protocol):
    async def call(self, snapshot: Snapshot) -> dict: ...
    async def call_summary(self, snapshot: Snapshot) -> dict: ...
    async def call_placement(
        self,
        *,
        content: str,
        current_path: str,
        current_summary: str,
        children: tuple[dict[str, str], ...],
    ) -> dict: ...
```

内置适配器：

- `OpenAIAdapter`
- `AnthropicAdapter`

## Minimal Custom Strategy

```python
from semafs.core.raw import RawPlan


class NoopStrategy:
    async def draft(self, snapshot):
        return None
```

## See Also

- [Strategies Guide](/guide/strategies)
- [LLM Integration](/guide/llm-integration)
- [Operations](/api/operations)
