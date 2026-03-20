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
      text: Value & Benchmark
      link: /guide/value-benchmark
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

## Quick Example (Latest API)

```bash
# Write two fragments into root.preferences and run one maintenance sweep
semafs write "I love dark roast coffee" --hint root.preferences --sweep
semafs write "Ethiopian beans are my favorite" --hint root.preferences --sweep

# Read structured tree
semafs tree root --max-depth 2
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

## Why SemaFS Now

`SemaFS` is strongest when you need **deterministic + explainable memory maintenance**:

- Reliable write path with transaction boundaries (SQLite UoW)
- Hybrid maintenance (`rules + LLM`) with guardrails and graceful fallback
- Hierarchical summaries for token-efficient retrieval

For a full evaluation and open-source benchmark, see:
[Value & Benchmark](/guide/value-benchmark)
