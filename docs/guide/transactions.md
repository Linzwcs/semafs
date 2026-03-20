# Transactions and Consistency

All structural mutations in SemaFS are committed through Unit of Work.

## 1. Staging Queues

`SQLiteUnitOfWork` stages mutations in five queues:

- new nodes
- dirty nodes
- removals (archive semantics)
- renames
- moves

No SQL commit occurs until `commit()`.

## 2. Commit Sequence

Current implementation applies in this order:

1. insert new nodes
2. update dirty nodes
3. apply renames
4. apply moves
5. apply archival removals
6. recompute canonical paths
7. refresh `node_paths` projection
8. commit transaction

## 3. Path Cascade Guarantee

rename/move can affect entire subtrees.

`_recompute_paths(...)` ensures descendants receive correct updated `canonical_path` values in the same transaction.

## 4. Write Locking

`SQLiteStore.write_conn()` uses `BEGIN IMMEDIATE`:

- obtains write lock early
- serializes concurrent write transactions
- preserves deterministic commit visibility

## 5. Deletion Semantics

SemaFS uses logical archival, not physical row deletion:

- `is_archived = 1`
- `stage = 'archived'`

This retains historical data for diagnostics and offline analysis.
