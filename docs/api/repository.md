# Storage and Unit of Work API

Primary files:

- `semafs/ports/store.py`
- `semafs/ports/factory.py`
- `semafs/infra/storage/sqlite/store.py`
- `semafs/infra/storage/sqlite/uow.py`

## 1. `NodeStore` Protocol

Core methods include:

- lookup: `get_by_id`, `get_by_path`, `resolve_path`, `canonical_path`
- mutation: `save`
- traversal: `list_children`, `list_siblings`, `get_ancestors`
- scans: `all_node_ids`, `all_paths`

## 2. `TxReader` Protocol

Transaction-bound read interface used inside UoW.

## 3. `UnitOfWork` Protocol

Staging operations:

- `register_new`
- `register_dirty`
- `register_removed`
- `register_rename`
- `register_move`

Transaction operations:

- `commit`
- `rollback`

## 4. `UoWFactory` Protocol

- `init()`
- `begin()` async context manager

## 5. SQLite Implementations

- `SQLiteStore`
- `SQLiteUoWFactory`
- `SQLiteUnitOfWork`

Implementation characteristics:

- transactional write connection per UoW
- `BEGIN IMMEDIATE` write lock
- commit-time canonical path recomputation
- projection table refresh (`node_paths`)
- archival instead of physical delete
