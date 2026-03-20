# Value & Benchmark

How much value does the latest SemaFS provide, and how should we evolve it based on the best open-source memory systems?

> Scope date: **2026-03-20** (latest local commit and docs refresh date)

## Latest SemaFS Snapshot

Current strengths observed in the latest codebase:

- **Stable write path**: `write(content, hint, payload)` with Unit-of-Work transaction boundaries
- **Controlled maintenance**: `sweep(limit)` with phase-based keeper flow and plan guards
- **Structured reads**: `read`, `list`, `tree`, `related`, `stats` for hierarchical and navigable context
- **Deployment surface**: unified CLI (`semafs ...`) + web server/viewer entrypoints

Local evidence used for this snapshot:

- latest commit: `feat(cli): add unified CLI, web serve, and viewer entrypoints` (2026-03-20)
- smoke script: `run_latest_semafs_smoke.py` passed
- regression checks: `scripts/regression_checks.py` passed (with `PYTHONPATH=.`)

## Value Assessment

### 1) Product Value

- **High** for agent memory that needs persistent, explainable hierarchy instead of flat retrieval.
- **High** for teams that require local-first storage and predictable operational control.
- **Medium** for scenarios that need only nearest-neighbor retrieval (vector-only stacks can be simpler).

### 2) Engineering Value

- **Reliability**: High (transaction semantics and guarded plan execution)
- **Maintainability**: Medium-to-High (recent phase split reduced keeper complexity)
- **Extensibility**: High (ports/adapters for strategy, summarizer, placer, storage)
- **Cost control**: High (rules for cheap path, LLM only when needed)

### 3) Strategic Value

SemaFS is differentiated by:

- filesystem-like semantic hierarchy
- explicit maintenance phases
- controllable, inspectable memory evolution

This is a strong position for enterprise/agent workflows that cannot accept opaque memory mutation.

## Benchmark Against Leading Open-Source Libraries

| Library | Core Strength | Where It Beats SemaFS Today | Where SemaFS Is Stronger |
|---|---|---|---|
| [LangGraph](https://github.com/langchain-ai/langgraph) | Durable agent workflows + checkpoints | Rich graph orchestration and ecosystem depth | More explicit semantic tree maintenance model |
| [LangMem](https://github.com/langchain-ai/langmem) | Memory patterns for LangGraph agents | Faster integration for LangGraph-native stacks | Clearer storage/mutation boundaries with UoW |
| [Mem0](https://github.com/mem0ai/mem0) | Turn-key memory layer for assistants | Out-of-box developer ergonomics and hosted options | Better local deterministic hierarchy and path semantics |
| [Zep](https://github.com/getzep/zep) | Temporal/long-term memory infra | Mature memory platform features and APIs | Tighter category-tree abstraction with explicit rebalance |
| [Graphiti](https://github.com/getzep/graphiti) | Temporal knowledge graph memory | Rich graph/temporal relation modeling | Lower conceptual overhead for filesystem-like memory |
| [LlamaIndex](https://github.com/run-llama/llama_index) | Retrieval/index ecosystem breadth | Many retrieval/index strategies out of the box | Native hierarchical memory maintenance flow |

## What to Borrow From the Best OSS

Priority improvements inspired by top projects:

1. **Workflow composability (LangGraph)**  
   Add first-class workflow hooks/events around `write -> sweep -> read` for orchestration frameworks.
2. **Memory quality lifecycle (Mem0 / LangMem)**  
   Introduce explicit memory scoring, decay, and retention policies.
3. **Temporal semantics (Zep / Graphiti)**  
   Add optional time-aware edges/events to represent evolving user facts.
4. **Retriever interoperability (LlamaIndex)**  
   Expose adapters to use SemaFS tree nodes directly in popular retriever pipelines.
5. **Benchmark suite as contract**  
   Publish stable benchmark tasks: latency, mutation quality, token-efficiency, and consistency under concurrency.

## Recommended Positioning

Use SemaFS as:

- the **semantic memory core** (hierarchical truth + controlled mutation)
- integrated with external orchestrators/retrievers when needed

Do not position it as a full replacement for every vector/search stack. Position it as the **memory governance layer** for long-lived agent systems.

## Next Actions for Docs

1. Keep all examples on latest API names (`write`, `sweep`, `tree`, `related`, `stats`).
2. Add one production blueprint page: `SemaFS + LangGraph` and `SemaFS + LlamaIndex`.
3. Publish benchmark methodology and reproducible scripts in `docs/design/`.
