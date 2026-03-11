---
layout: home

hero:
  name: SemaFS
  text: Semantic Filesystem for LLM Memory
  tagline: Give your LLM a persistent, self-organizing memory that grows smarter over time.
  image:
    src: /logo.svg
    alt: SemaFS
  actions:
    - theme: brand
      text: Get Started
      link: /guide/introduction
    - theme: alt
      text: View on GitHub
      link: https://github.com/linzwcs/semafs

features:
  - icon: 🌲
    title: Hierarchical Organization
    details: Organize memories like a filesystem. Deeper = more specific. Parents automatically summarize children.
  - icon: 🤖
    title: LLM-Powered Maintenance
    details: Automatic reorganization with Merge, Group, and Move operations. Your knowledge base grows smarter over time.
  - icon: ⚡
    title: Write-Maintain-Read
    details: O(1) writes, batch maintenance, structured reads. Designed for high performance and low latency.
  - icon: 🛡️
    title: ACID Transactions
    details: Unit of Work pattern ensures atomic operations. All changes succeed together or roll back completely.
  - icon: 💰
    title: Cost-Optimized
    details: Hybrid strategy uses rules when possible, LLM when needed. Guaranteed fallback ensures reliability.
  - icon: 🔌
    title: Pluggable Architecture
    details: Hexagonal design with clean ports & adapters. Swap storage, LLM providers, or strategies easily.
---

<style>
:root {
  --vp-home-hero-name-color: transparent;
  --vp-home-hero-name-background: -webkit-linear-gradient(120deg, #3eaf7c 30%, #42b983);
  --vp-home-hero-image-background-image: linear-gradient(-45deg, #3eaf7c50 50%, #42b98350 50%);
  --vp-home-hero-image-filter: blur(40px);
}
</style>

## Quick Example

```python
from semafs import SemaFS
from semafs.storage.sqlite import SQLiteUoWFactory
from semafs.strategies.hybrid import HybridStrategy

# Initialize
factory = SQLiteUoWFactory("memory.db")
await factory.init()
semafs = SemaFS(factory, HybridStrategy(llm_adapter))

# Write memories
await semafs.write("root.preferences", "I love dark roast coffee")
await semafs.write("root.preferences", "Ethiopian beans are my favorite")

# Auto-organize (LLM merges similar memories)
await semafs.maintain()

# Read with context
tree = await semafs.view_tree("root", max_depth=2)
```

## The Problem

LLMs are **stateless**. Every conversation starts fresh.

| Existing Approach | Limitation |
|-------------------|------------|
| Vector DB | No structure, just similarity |
| Key-Value Store | Flat, no relationships |
| RAG | Retrieval-only, no organization |
| Context Stuffing | Token limits, expensive |

## The Solution

**SemaFS organizes memories hierarchically** with automatic semantic maintenance.

```
root/
├── preferences/
│   ├── food/
│   │   ├── coffee → "Dark roast, Ethiopian, no sugar"
│   │   └── cuisine → "Japanese, especially sushi"
│   └── work/
│       └── meetings → "Morning standups, async preferred"
└── projects/
    └── semafs → "Building a semantic filesystem..."
```

::: tip Key Insight
Human knowledge is hierarchical. LLM memory should be too.
:::
