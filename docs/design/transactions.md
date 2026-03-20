# Transaction Model

SemaFS relies on SQLite transactions plus Unit of Work staging.

## 1. Write Connection Lifecycle

`SQLiteUoWFactory.begin()` opens a dedicated write connection and starts `BEGIN IMMEDIATE`.

Effects:

- deterministic write lock acquisition
- serialized write transactions
- isolated transactional reader view

## 2. Unit of Work Staging

`SQLiteUnitOfWork` keeps pending mutations in memory:

- `_new`
- `_dirty`
- `_removed`
- `_renamed`
- `_moved`

Mutations become visible only after `commit()`.

## 3. Commit Responsibilities

Commit includes more than row updates:

1. apply staged inserts/updates/moves/renames/removals
2. recompute impacted canonical paths
3. refresh `node_paths` projection table
4. commit and clear staging

## 4. Path Cascade Consistency

When parent names or parents change, descendants must update paths.

`_recompute_paths(...)` performs a subtree-aware recomputation within the same transaction.

## 5. Archival Semantics

Removal is logical archive:

- `is_archived = 1`
- `stage = 'archived'`

Rows remain in history for inspection.

## 6. Failure Behavior

On error:

- SQL rollback
- staging queues are cleared
- exception propagates to caller
