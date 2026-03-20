# Architecture Overview

SemaFS uses a layered architecture centered on the `SemaFS` facade.

## 1. Layer Diagram

```mermaid
graph TD
  A[Entry: CLI / Python / MCP / Viewer] --> B[Facade: SemaFS]
  B --> C[Engine: Intake / Pulse / Keeper]
  C --> D[Algorithm: Strategy / Placer / Summarizer / Policy]
  C --> E[Execution: Resolver / Guard / Executor]
  B --> F[Ports: Store / UoW / Bus / LLM]
  F --> G[Infra: SQLite / OpenAI / Anthropic / InMemoryBus]
```

## 2. Runtime Components

### 2.1 `SemaFS`

Application facade exposing high-level APIs:

- write/read/list/tree/related/stats/sweep/apply_skeleton

### 2.2 `Intake`

Write pipeline component:

- placement routing
- pending leaf staging
- placement payload enrichment

### 2.3 `Pulse`

Event entry component:

- subscribe to selected domain events
- seed propagation signal via policy
- dispatch reconcile to keeper

### 2.4 `Keeper`

Maintenance orchestrator:

- per-node lock management
- reconcile phase coordination
- metric collection
- optional parent propagation

### 2.5 `Resolver + PlanGuard + Executor`

Plan execution stack:

- normalize and resolve names/paths
- enforce semantic/naming guards
- stage transactional mutations

## 3. Default Composition

CLI and MCP runtime initialize with:

- `SQLiteStore`
- `SQLiteUoWFactory`
- `InMemoryBus`
- `HybridStrategy`
- `LLMRecursivePlacer`
- `LLMSummarizer`
- `DefaultPolicy`

## 4. Main Runtime Flows

### 4.1 Write Flow

```mermaid
sequenceDiagram
  participant Caller
  participant FS as SemaFS
  participant Intake
  participant UoW
  participant Bus

  Caller->>FS: write(content, hint, payload)
  FS->>UoW: begin transaction
  FS->>Intake: route + stage pending leaf
  Intake->>UoW: register_new
  FS->>UoW: commit
  FS->>Bus: publish(Placed)
```

### 4.2 Reconcile Flow

```mermaid
sequenceDiagram
  participant Bus
  participant Pulse
  participant Keeper
  participant Phase

  Bus->>Pulse: Placed/Persisted/Moved
  Pulse->>Keeper: reconcile(node_id, signal)
  Keeper->>Phase: Rebalance
  Keeper->>Phase: Rollup
  Keeper->>Phase: Lifecycle + Summary
  Keeper->>Keeper: Propagation (if needed)
```

## 5. Extension Points

Primary customization paths:

- custom `Strategy`
- custom `Placer`
- custom `Summarizer`
- custom `Policy`
- custom `NodeStore` and `UoWFactory`
