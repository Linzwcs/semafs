# Operations and Plans API

Core files:

- `semafs/core/raw.py`
- `semafs/core/ops.py`
- `semafs/engine/resolver.py`
- `semafs/engine/executor.py`

## 1. Raw Structures

- `RawPlan`
- `RawMerge`
- `RawGroup`
- `RawMove`
- `RawRename`
- `RawRollup`

Raw layer represents untrusted/partial LLM intent.

## 2. Executable Structures

- `Plan`
- `MergeOp`
- `GroupOp`
- `MoveOp`
- `RenameOp`
- `RollupOp`
- `ArchiveOp`

`Plan` also carries optional parent updates:

- `updated_summary`
- `updated_keywords`
- `updated_name`
- `reasoning`

## 3. Compilation API

`Resolver.compile(raw, snapshot) -> Plan`

Key responsibilities:

- normalize/resolve names and paths
- allocate unique category segments
- transform raw IDs and path references into executable operations

## 4. Execution API

`Executor.execute(plan, snapshot, uow) -> list[events]`

Stages changes in UoW and returns emitted operation result events.

## 5. Guard APIs

`PlanGuard` provides validation/sanitization passes:

- `validate_raw_plan(...)`
- `validate_plan(...)`
- (context-aware filtering utility also exists)
