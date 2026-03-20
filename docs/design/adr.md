# ADR Records

This page captures architecture decisions reflected by current code.

## ADR-001: Commit-Then-Event Write Semantics

Status: Accepted

Decision:

- write transaction commits first
- `Placed` event is published after commit

Why:

- preserve write durability boundary
- decouple heavy maintenance from immediate write latency

## ADR-002: Raw Plan to Executable Plan Pipeline

Status: Accepted

Decision:

- LLM output is parsed into raw structures
- resolver + guard + executor mediate execution

Why:

- improve safety and traceability
- reduce direct prompt-output mutation risk

## ADR-003: SQLite + Unit of Work as Default Runtime

Status: Accepted

Decision:

- use SQLite as default persistence
- route all structural writes through UoW

Why:

- simple deployment model
- explicit and testable consistency boundaries

## ADR-004: MCP and Viewer Responsibility Split

Status: Accepted

Decision:

- MCP transport and viewer HTTP are separate entrypoints

Why:

- cleaner protocol boundaries
- simpler operational ownership

## ADR-005: Path Projection Table

Status: Accepted

Decision:

- maintain `node_paths` as path projection
- refresh projection inside transaction commit

Why:

- fast path-to-id lookup
- decouple identity graph storage from lookup optimization
