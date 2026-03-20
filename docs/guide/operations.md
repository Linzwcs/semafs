# Operation Pipeline

SemaFS does not execute raw LLM text directly. It uses a staged pipeline from weakly-typed intent to strongly-typed transactional operations.

## 1. Raw Layer

LLM outputs are parsed into raw objects:

- `RawPlan`
- `RawMerge`
- `RawGroup`
- `RawMove`
- `RawRename`

Raw objects may contain short IDs, relative names, and partially ambiguous values.

## 2. Compile Layer (`Resolver`)

`Resolver.compile(raw, snapshot)` performs:

- path/name normalization
- relative-to-absolute path resolution
- uniqueness allocation for names/segments
- conversion to executable `Plan`

Output operation types:

- `MergeOp`
- `GroupOp`
- `MoveOp`
- `RenameOp`

## 3. Guard Layer (`PlanGuard`)

Plan guard validates and sanitizes before execution:

- rejects invalid/generic naming patterns
- sanitizes suspicious summaries/keywords
- applies constraints such as locked-category rename blocking

## 4. Execution Layer (`Executor`)

`Executor.execute(plan, snapshot, uow)`:

- mutates UoW staging queues
- creates/updates/moves/archives nodes as required
- emits operation result events (`Merged`, `Grouped`, `Moved`)

## 5. Why This Pipeline Exists

- deterministic mutation boundary
- clearer auditability of LLM influence
- easier testing per layer
- safer evolution of strategy logic without rewriting storage mutation code
