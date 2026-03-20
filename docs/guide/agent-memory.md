# Agent Memory Integration

使用 SemaFS 作为 Agent 的持久化语义记忆层（基于最新 API）。

## Why SemaFS for Agents

相比纯 KV 或纯向量检索，SemaFS 更适合需要“可解释记忆治理”的 Agent：

- 树状记忆结构（可导航）
- 事件驱动 + 批处理治理（可控）
- 事务一致性（可回滚）
- LLM 增强而非强绑定（可降级）

## Recommended Tool Surface

建议对 Agent 暴露以下工具：

- `memory_write(content, hint, payload?)`
- `memory_sweep(limit?)`
- `memory_read(path)`
- `memory_list(path)`
- `memory_tree(path, max_depth)`
- `memory_related(path)`
- `memory_stats()`

## Tool Schema Example

```python
SEMAFS_TOOLS = [
    {
        "name": "memory_write",
        "description": "Write one memory fragment",
        "parameters": {
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "hint": {"type": "string", "default": "root"},
                "payload": {"type": "object"},
            },
            "required": ["content"],
        },
    },
    {
        "name": "memory_tree",
        "description": "Read tree view",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "default": "root"},
                "max_depth": {"type": "integer", "default": 2},
            },
        },
    },
    {
        "name": "memory_sweep",
        "description": "Run one maintenance sweep",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 20},
            },
        },
    },
]
```

## Handler Implementation

```python
from semafs.renderer import LLMRenderer, JSONRenderer


class AgentMemory:
    def __init__(self, semafs):
        self.semafs = semafs

    async def call(self, name: str, args: dict) -> str:
        handlers = {
            "memory_write": self.memory_write,
            "memory_sweep": self.memory_sweep,
            "memory_read": self.memory_read,
            "memory_list": self.memory_list,
            "memory_tree": self.memory_tree,
            "memory_related": self.memory_related,
            "memory_stats": self.memory_stats,
        }
        fn = handlers.get(name)
        if not fn:
            return f"Unknown tool: {name}"
        return await fn(**args)

    async def memory_write(
        self,
        content: str,
        hint: str = "root",
        payload: dict | None = None,
    ) -> str:
        leaf_id = await self.semafs.write(content=content, hint=hint, payload=payload)
        return f"ok: {leaf_id}"

    async def memory_sweep(self, limit: int = 20) -> str:
        changed = await self.semafs.sweep(limit=limit)
        return f"sweep.changed={changed}"

    async def memory_read(self, path: str) -> str:
        view = await self.semafs.read(path)
        if not view:
            return "not_found"
        return LLMRenderer.render_node(view)

    async def memory_list(self, path: str) -> str:
        views = await self.semafs.list(path)
        return "\n".join(v.path for v in views) if views else "empty"

    async def memory_tree(self, path: str = "root", max_depth: int = 2) -> str:
        tree = await self.semafs.tree(path=path, max_depth=max_depth)
        if not tree:
            return "not_found"
        return LLMRenderer.render_tree(tree)

    async def memory_related(self, path: str) -> str:
        rel = await self.semafs.related(path)
        if not rel:
            return "not_found"
        return LLMRenderer.render_related(rel)

    async def memory_stats(self) -> str:
        stats = await self.semafs.stats()
        return JSONRenderer.render_stats(stats)
```

## Production Pattern

### 1) Write frequently, sweep periodically

- 在线对话阶段：只 `memory_write`
- 空闲窗口或批任务：`memory_sweep(limit=...)`

### 2) Read by depth, not by full dump

- 先 `memory_tree(root, depth=1~2)` 找入口
- 再 `memory_read` / `memory_related` 精读

### 3) Keep payload minimal and useful

推荐放入：

- `source`（chat/user/tool）
- `session_id` / `conversation_id`
- `timestamp`
- 业务标签（如 `topic`, `confidence`）

## Guardrails for Agents

- 不要让 Agent 直接执行 SQL 或直接改底层表
- 所有变更走 `write/sweep` API
- 将 `sweep` 调用频率限制在可控范围（如每 N 条写入或每 M 分钟）

## Minimal Runtime Setup

```python
from semafs import SemaFS
from semafs.algo import DefaultPolicy, HintPlacer, RuleSummarizer
from semafs.infra.bus import InMemoryBus
from semafs.infra.storage.sqlite.store import SQLiteStore
from semafs.infra.storage.sqlite.uow import SQLiteUoWFactory


class NoopStrategy:
    async def draft(self, snapshot):
        return None


store = SQLiteStore("data/agent.db")
factory = SQLiteUoWFactory(store)
await factory.init()

semafs = SemaFS(
    store=store,
    uow_factory=factory,
    bus=InMemoryBus(),
    strategy=NoopStrategy(),
    placer=HintPlacer(),
    summarizer=RuleSummarizer(),
    policy=DefaultPolicy(),
)
```

需要 LLM 增强时，将 `NoopStrategy/HintPlacer/RuleSummarizer` 替换为 `HybridStrategy/LLMRecursivePlacer/LLMSummarizer`。
