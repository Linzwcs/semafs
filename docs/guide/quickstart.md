# Quick Start

## 1. Install

```bash
pip install semafs
pip install "semafs[openai]"      # or anthropic
pip install "semafs[mcp]"         # MCP runtime
pip install "semafs[server]"      # web viewer runtime
```

## 2. Configure Credentials

```bash
export OPENAI_API_KEY="sk-..."
# or
export ANTHROPIC_API_KEY="..."
```

## 3. Minimal CLI Lifecycle

### 3.1 Write a Fragment

```bash
semafs write "User prefers async updates" \
  --hint root.work \
  --provider openai \
  --db data/demo.db
```

### 3.2 Inspect Memory

```bash
semafs read root.work --provider openai --db data/demo.db
semafs tree root --provider openai --db data/demo.db --max-depth 3
semafs stats --provider openai --db data/demo.db --output json
```

### 3.3 Optional Backlog Sweep

```bash
semafs sweep --provider openai --db data/demo.db --limit 20
```

## 4. Start MCP Server

```bash
semafs serve --provider openai --db data/demo.db
```

MCP tools exposed by default:

- `write`
- `read`
- `list`
- `tree`
- `stats`
- `sweep`

## 5. Start Viewer

```bash
semafs view --db data/demo.db --host 127.0.0.1 --port 8080
```

Open: `http://127.0.0.1:8080`

## 6. Minimal Python Example

```python
import asyncio

from openai import AsyncOpenAI

from semafs import SemaFS
from semafs.algo import (
    DefaultPolicy,
    HybridStrategy,
    LLMSummarizer,
    LLMRecursivePlacer,
)
from semafs.infra.bus import InMemoryBus
from semafs.infra.llm.openai import OpenAIAdapter
from semafs.infra.storage.sqlite.store import SQLiteStore
from semafs.infra.storage.sqlite.uow import SQLiteUoWFactory


async def main() -> None:
    store = SQLiteStore("data/demo_py.db")
    uow_factory = SQLiteUoWFactory(store)
    await uow_factory.init()

    adapter = OpenAIAdapter(AsyncOpenAI(), model="gpt-4o-mini")

    fs = SemaFS(
        store=store,
        uow_factory=uow_factory,
        bus=InMemoryBus(),
        strategy=HybridStrategy(adapter),
        placer=LLMRecursivePlacer(store, adapter),
        summarizer=LLMSummarizer(adapter),
        policy=DefaultPolicy(),
    )

    leaf_id = await fs.write("Coffee: dark roast", hint="root.preferences")
    print(leaf_id)


asyncio.run(main())
```

## 7. Common Early Errors

- `OPENAI_API_KEY is required`: set env var or pass `--api-key`.
- `Target category not found`: your hint path does not exist.
- `Database not found`: invalid DB path for `serve` or `view`.
- missing provider package: install `semafs[openai]` or `semafs[anthropic]`.
