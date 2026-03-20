# LLM Integration

Connect SemaFS to OpenAI or Anthropic adapters for semantic rebalancing, placement, and summary generation.

## Supported Adapters

| Provider | Adapter |
|---|---|
| OpenAI | `semafs.infra.llm.openai.OpenAIAdapter` |
| Anthropic | `semafs.infra.llm.anthropic.AnthropicAdapter` |

## OpenAI Setup

```python
from openai import AsyncOpenAI

from semafs import SemaFS
from semafs.algo import (
    DefaultPolicy,
    HybridStrategy,
    LLMSummarizer,
    LLMRecursivePlacer,
    PlacementConfig,
)
from semafs.infra.bus import InMemoryBus
from semafs.infra.llm.openai import OpenAIAdapter
from semafs.infra.storage.sqlite.store import SQLiteStore
from semafs.infra.storage.sqlite.uow import SQLiteUoWFactory

store = SQLiteStore("data/llm.db")
factory = SQLiteUoWFactory(store)
await factory.init()

client = AsyncOpenAI()  # uses OPENAI_API_KEY
adapter = OpenAIAdapter(client, model="gpt-4o-mini")

fs = SemaFS(
    store=store,
    uow_factory=factory,
    bus=InMemoryBus(),
    strategy=HybridStrategy(adapter),
    placer=LLMRecursivePlacer(
        store=store,
        adapter=adapter,
        config=PlacementConfig(max_depth=4, min_confidence=0.55),
    ),
    summarizer=LLMSummarizer(adapter),
    policy=DefaultPolicy(),
)
```

## Anthropic Setup

```python
from anthropic import AsyncAnthropic
from semafs.infra.llm.anthropic import AnthropicAdapter

client = AsyncAnthropic()  # uses ANTHROPIC_API_KEY
adapter = AnthropicAdapter(client, model="claude-haiku-4-5-20251001")
```

Use this `adapter` the same way in `HybridStrategy`, `LLMRecursivePlacer`, and `LLMSummarizer`.

## What the Adapter Is Used For

- `strategy`: draft rebalance plan (`MERGE/GROUP/MOVE/RENAME`)
- `placer`: recursive routing for write placement
- `summarizer`: category summary/keywords refresh

## Operational Advice

- start with low-cost model (`gpt-4o-mini`, fast Claude tier)
- keep `HintPlacer + RuleSummarizer` for offline/local flows
- use `sweep(limit)` in batch jobs after large imports

## Current vs Old Docs

Use now:

- `HybridStrategy(adapter)`
- `LLMRecursivePlacer(...)`
- `LLMSummarizer(adapter)`

Do not rely on old docs claiming:

- built-in `RuleOnlyStrategy`
- `maintain()` entrypoint

## Next Steps

- [Strategies](./strategies) - Implement custom `draft(snapshot)` behavior
- [Maintenance](./maintenance) - Reconcile pipeline and sweep policy
- [Agent Memory](./agent-memory) - Tool-oriented integration patterns
