---
layout: home

hero:
  name: SemaFS
  text: Semantic Filesystem for LLM Memory
  tagline: Structured memory trees with event-driven maintenance and transactional consistency.
  image:
    src: /logo.svg
    alt: SemaFS
  actions:
    - theme: brand
      text: Quick Start
      link: /guide/quickstart
    - theme: alt
      text: Architecture
      link: /design/architecture
    - theme: alt
      text: API Reference
      link: /api/semafs

features:
  - icon: 🌲
    title: Canonical Tree Memory
    details: "All memory is organized under explicit canonical paths such as root.work.notes."
  - icon: 🔄
    title: Event-Driven Reconcile
    details: "Writes commit first, then trigger maintenance through domain events and propagation policy."
  - icon: 🧱
    title: SQLite + Unit of Work
    details: "Structural mutations are atomic, with path recomputation and projection refresh at commit time."
  - icon: 🤖
    title: LLM in Three Roles
    details: "Placement routing, structural rebalancing, and category summarization are independently pluggable."
  - icon: 🔌
    title: MCP Native
    details: "semafs serve exposes write/read/list/tree/stats/sweep as MCP tools over stdio."
  - icon: 👀
    title: Standalone Viewer
    details: "semafs view runs an HTTP explorer for browsing and searching nodes without MCP coupling."
---

## What This Documentation Covers

This documentation is written against the current repository implementation under `semafs/`.

It focuses on:

- Runtime architecture and lifecycle flow
- Operational usage through CLI, Python, MCP, and Viewer
- Extension points through ports, strategies, and adapters
- Consistency guarantees through SQLite and Unit of Work

## Runtime Facts

- Write path: `SemaFS.write -> Intake.write -> UoW commit -> publish(Placed)`
- Maintenance path: `Pulse._on_event -> Keeper.reconcile`
- Reconcile phases: `RebalancePhase -> RollupPhase -> PostRebalancePhases`
- Default storage: `SQLiteStore + SQLiteUoWFactory`
- Default strategy stack: `HybridStrategy + LLMRecursivePlacer + LLMSummarizer + DefaultPolicy`

## Minimal Working Commands

```bash
export OPENAI_API_KEY="sk-..."

semafs write "User prefers async updates" \
  --hint root.work \
  --provider openai \
  --db data/demo.db

semafs tree root --provider openai --db data/demo.db --max-depth 2
semafs stats --provider openai --db data/demo.db --output json
```
