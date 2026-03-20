# Introduction

SemaFS is a semantic filesystem for LLM memory workloads.

Instead of storing memory only as flat records, SemaFS keeps a canonical tree (`root.*`) and continuously reconciles structure as new fragments arrive.

## What Makes SemaFS Different

- It treats path hierarchy as first-class data, not just a display artifact.
- It separates write durability from heavy maintenance logic.
- It models maintenance as explicit plans and operations.
- It uses transactional storage semantics for structural changes.

## Runtime Surfaces

The current repository exposes four entry surfaces:

- Python API (`SemaFS` class)
- CLI (`semafs ...`)
- MCP server (`semafs serve`)
- Web viewer (`semafs view`)

Boundary notes:

- `serve` is MCP over stdio, not HTTP.
- `view` is HTTP-only browsing/search UI, not MCP.

## End-to-End Runtime Flow

```mermaid
graph LR
  W[write(content, hint, payload)] --> I[Intake place + stage pending leaf]
  I --> C[UoW commit]
  C --> E[publish Placed]
  E --> P[Pulse seed signal]
  P --> K[Keeper reconcile]
  K --> R[Rebalance -> Rollup -> Summary -> Propagation]
  R --> Q[read/list/tree/stats]
```

## Typical Usage Scenarios

- Agent long-term memory and preference tracking
- Session-to-session knowledge accumulation
- Self-organizing internal notes and research logs
- Memory systems requiring inspectable structure and auditability

## Current Practical Constraints

- Runtime commands (except `view`) require a configured LLM provider.
- Default persistence is single-node SQLite.
- Structural quality depends on prompt quality and model behavior.
