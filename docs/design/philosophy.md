# Design Philosophy

SemaFS is designed as an architecture-first memory core for systems that need both automation and explainability.

## 1. Core Principles

### 1.1 Structure-First Memory

Tree structure is a primary asset. Paths are not presentation-only metadata.

- humans can inspect and reason over `root.*`
- machine workflows can perform deterministic tree navigation

### 1.2 Durable Writes, Deferred Reconcile

Write durability takes priority over immediate heavy reorganization.

- write path commits quickly
- structural optimization runs through event-driven reconcile

### 1.3 Typed Execution over Raw LLM Output

LLM output is treated as intent, not executable truth.

- parse into `RawPlan`
- compile with `Resolver`
- constrain with `PlanGuard`
- apply with `Executor` inside UoW

### 1.4 Dependency Inversion for Replaceability

Business logic depends on protocol boundaries (`ports`), not concrete infrastructure.

- storage can be replaced
- strategy stacks can be swapped
- propagation behavior can be decorated

### 1.5 Explicit Consistency Boundaries

All structural changes flow through Unit of Work.

- mutation staging is explicit
- commit boundaries are atomic
- path projection refresh is part of mutation completion

## 2. Intentional Surface Separation

- `semafs serve`: MCP stdio server
- `semafs view`: HTTP viewer

The split avoids protocol and lifecycle coupling.

## 3. Current Non-Goals

- distributed multi-writer consistency across nodes
- built-in multi-tenant namespace policy
- no-LLM mode with equivalent automatic organization quality
