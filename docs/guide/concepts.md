# Core Concepts

## 1. Node and Path

The fundamental entity is `Node`, with two kinds:

- `NodeType.CATEGORY`
- `NodeType.LEAF`

Paths are validated by `NodePath`:

- root path is always `root`
- child paths are `root.<segment>(.<segment>...)`
- path segments are constrained to `[a-z0-9_]`

## 2. Lifecycle Stage

`NodeStage` values:

- `PENDING`: newly ingested fragment before promotion
- `ACTIVE`: standard visible node
- `COLD`: rolled-up historical node retained for retrieval
- `ARCHIVED`: logically archived node

## 3. Capacity Zones

`Budget(soft, hard)` classifies category pressure:

- `HEALTHY`
- `PRESSURED`
- `OVERFLOW`

These zones drive whether structural rebalancing should run.

## 4. Snapshot

Maintenance is driven by immutable `Snapshot`, including:

- target category
- leaf/subcategory/pending partitions
- sibling and ancestor context
- budget and globally used paths

This isolates decision logic from live mutable storage state.

## 5. Raw Plan vs Executable Plan

LLM output enters the raw layer:

- `RawPlan`, `RawMerge`, `RawGroup`, `RawMove`, `RawRename`

Then resolver compiles to executable layer:

- `Plan`, `MergeOp`, `GroupOp`, `MoveOp`, `RenameOp`

The split enables strict validation between language output and execution.

## 6. Events and Propagation Signals

Relevant events include:

- `Placed`
- `Persisted`
- `Moved`
- execution output events like `Merged` and `Grouped`

`Pulse` converts events to `Signal` and `Policy.step(...)` decides upward propagation.

## 7. Skeleton Categories

`apply_skeleton(...)` marks categories as structural skeleton nodes:

- `skeleton=True`
- `name_editable=False`

Skeleton names are locked against rename operations while summaries/meta can still update.
