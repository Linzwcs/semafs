# Quick Start

Get SemaFS running with the **latest API**.

## Installation

```bash
pip install semafs
```

Optional providers:

```bash
pip install semafs[openai]
pip install semafs[anthropic]
```

## Minimal Python Example (No LLM)

```python
import asyncio

from semafs import SemaFS
from semafs.algo import DefaultPolicy, HintPlacer, RuleSummarizer
from semafs.core.capacity import Budget
from semafs.infra.bus import InMemoryBus
from semafs.infra.storage.sqlite.store import SQLiteStore
from semafs.infra.storage.sqlite.uow import SQLiteUoWFactory


class NoopStrategy:
    async def draft(self, snapshot):
        return None


async def main() -> None:
    store = SQLiteStore("data/quickstart.db")
    factory = SQLiteUoWFactory(store)
    await factory.init()

    fs = SemaFS(
        store=store,
        uow_factory=factory,
        bus=InMemoryBus(),
        strategy=NoopStrategy(),
        placer=HintPlacer(),
        summarizer=RuleSummarizer(),
        policy=DefaultPolicy(),
        budget=Budget(soft=4, hard=6),
    )

    await fs.write(content="User likes dark roast coffee", hint="root.preferences")
    await fs.write(content="Prefers async standup updates", hint="root.work")

    # Optional manual maintenance for overloaded categories
    changed = await fs.sweep(limit=10)
    print("sweep changed:", changed)

    tree = await fs.tree("root", max_depth=2)
    if tree:
        print("total nodes:", tree.total_nodes)


asyncio.run(main())
```

## CLI Quick Run

```bash
# 1) Write
semafs write "User likes dark roast coffee" --hint root.preferences --db data/demo.db

# 2) Run one maintenance sweep
semafs sweep --db data/demo.db --limit 20

# 3) Read tree
semafs tree root --db data/demo.db --max-depth 3

# 4) Start web server (browse/search)
semafs serve --db data/demo.db --port 8080
```

## LLM Mode (OpenAI Example)

```bash
export OPENAI_API_KEY="sk-..."
semafs write "Ethiopian beans are favorite" \
  --hint root.preferences \
  --provider openai \
  --model gpt-4o-mini \
  --db data/demo.db \
  --sweep
```

## Next Steps

- [Value & Benchmark](./value-benchmark) - Why SemaFS is valuable and where it stands
- [Core Concepts](./concepts) - Data model and lifecycle
- [Writing Memories](./writing) - `write(content, hint, payload)` details
- [Maintenance](./maintenance) - `sweep(limit)` and event-driven reconcile
