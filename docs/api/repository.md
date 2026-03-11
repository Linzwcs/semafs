# Repository API

Storage abstraction for node persistence.

## NodeRepository Protocol

```python
from typing import Protocol, Optional, List
from semafs.core.node import TreeNode
from semafs.core.enums import NodeStatus

class NodeRepository(Protocol):
    # Read Operations (no transaction)

    async def get_by_path(
        self,
        path: str
    ) -> Optional[TreeNode]:
        """
        Get node by full path.

        Excludes ARCHIVED nodes.
        """
        ...

    async def get_by_id(
        self,
        node_id: str
    ) -> Optional[TreeNode]:
        """
        Get node by UUID.

        Includes all statuses.
        """
        ...

    async def list_children(
        self,
        parent_path: str,
        statuses: Optional[List[NodeStatus]] = None
    ) -> List[TreeNode]:
        """
        List direct children of a category.

        Args:
            parent_path: Parent's full path
            statuses: Filter by status (None = all non-archived)
        """
        ...

    async def list_dirty_categories(self) -> List[TreeNode]:
        """
        List categories with is_dirty=True.

        Ordered by depth descending (deepest first).
        """
        ...

    async def path_exists(self, path: str) -> bool:
        """
        Check if non-ARCHIVED node exists at path.
        """
        ...

    async def list_sibling_categories(
        self,
        path: str
    ) -> List[TreeNode]:
        """
        List sibling CATEGORY nodes.

        Used for naming conflict detection.
        """
        ...

    async def get_ancestor_categories(
        self,
        path: str,
        max_depth: int = 3
    ) -> List[TreeNode]:
        """
        Get ancestor chain up to root.

        Args:
            path: Starting path
            max_depth: Maximum ancestors to return

        Returns:
            Nearest to farthest order
        """
        ...

    # Write Operations (within transaction)

    def stage(self, node: TreeNode) -> None:
        """
        Stage node for INSERT or UPDATE.

        Upsert semantics based on ID.
        """
        ...

    async def cascade_rename(
        self,
        old_path: str,
        new_path: str
    ) -> None:
        """
        Rename node and update all descendants.

        Updates parent_path of all children recursively.
        """
        ...

    async def commit(self) -> None:
        """
        Persist all staged changes atomically.
        """
        ...

    async def rollback(self) -> None:
        """
        Discard all staged changes.
        """
        ...
```

## UoWFactory Protocol

```python
from typing import Protocol
from contextlib import asynccontextmanager

class UoWFactory(Protocol):
    @property
    def repo(self) -> NodeRepository:
        """
        Non-transactional repository for reads.
        """
        ...

    @asynccontextmanager
    async def begin(self):
        """
        Create transactional context.

        Yields:
            UnitOfWork instance

        Example:
            async with factory.begin() as uow:
                uow.register_new(node)
                await uow.commit()
        """
        ...

    async def init(self) -> None:
        """
        Initialize storage (create tables, etc).
        """
        ...

    async def close(self) -> None:
        """
        Close connections and cleanup.
        """
        ...
```

## UnitOfWork Protocol

```python
class UnitOfWork(Protocol):
    def register_new(self, node: TreeNode) -> None:
        """
        Stage node for INSERT.
        """
        ...

    def register_dirty(self, node: TreeNode) -> None:
        """
        Stage node for UPDATE.
        """
        ...

    def register_cascade_rename(
        self,
        old_path: str,
        new_path: str
    ) -> None:
        """
        Stage path rename with cascade.
        """
        ...

    async def commit(self) -> None:
        """
        Persist all changes atomically.

        Order: UPDATE → INSERT → CASCADE → COMMIT
        """
        ...

    async def rollback(self) -> None:
        """
        Discard all staged changes.
        """
        ...
```

## Built-in Implementation

### SQLiteUoWFactory

```python
from semafs.storage.sqlite import SQLiteUoWFactory

# Create factory
factory = SQLiteUoWFactory("knowledge.db")

# Initialize (creates tables)
await factory.init()

# Read without transaction
node = await factory.repo.get_by_path("root.work")
children = await factory.repo.list_children("root")

# Write with transaction
async with factory.begin() as uow:
    new_node = TreeNode.new_leaf("root", "test", "content")
    uow.register_new(new_node)
    await uow.commit()

# Cleanup
await factory.close()
```

### Database Schema

```sql
CREATE TABLE semafs_nodes (
    id TEXT PRIMARY KEY,
    parent_path TEXT NOT NULL,
    name TEXT NOT NULL,
    node_type TEXT CHECK(node_type IN ('CATEGORY', 'LEAF')),
    status TEXT CHECK(status IN ('ACTIVE', 'ARCHIVED',
                                  'PENDING_REVIEW', 'PROCESSING')),
    content TEXT,
    display_name TEXT,
    name_editable INTEGER DEFAULT 1,
    payload TEXT DEFAULT '{}',
    tags TEXT DEFAULT '[]',
    is_dirty INTEGER DEFAULT 0,
    version INTEGER DEFAULT 1,
    access_count INTEGER DEFAULT 0,
    created_at TEXT,
    updated_at TEXT,
    last_accessed_at TEXT
);

-- Unique paths for non-archived nodes
CREATE UNIQUE INDEX idx_unique_path
    ON semafs_nodes(parent_path, name)
    WHERE status != 'ARCHIVED';

-- Efficient queries
CREATE INDEX idx_parent_path ON semafs_nodes(parent_path);
CREATE INDEX idx_status ON semafs_nodes(status);
CREATE INDEX idx_dirty_categories
    ON semafs_nodes(is_dirty, node_type, status);
```

## Custom Repository

```python
from semafs.ports.repo import NodeRepository
from semafs.core.node import TreeNode

class MyRepository(NodeRepository):
    def __init__(self, connection):
        self.conn = connection
        self._staged_new = []
        self._staged_dirty = []
        self._staged_renames = []

    async def get_by_path(self, path: str) -> Optional[TreeNode]:
        # Your implementation
        row = await self.conn.fetchone(
            "SELECT * FROM nodes WHERE path = ? AND status != 'ARCHIVED'",
            (path,)
        )
        return self._row_to_node(row) if row else None

    async def list_children(
        self,
        parent_path: str,
        statuses: Optional[List[NodeStatus]] = None
    ) -> List[TreeNode]:
        # Your implementation
        ...

    def stage(self, node: TreeNode) -> None:
        # Check if new or existing
        if self._is_new(node):
            self._staged_new.append(node)
        else:
            self._staged_dirty.append(node)

    async def commit(self) -> None:
        async with self.conn.transaction():
            # Update dirty
            for node in self._staged_dirty:
                await self._update(node)

            # Insert new
            for node in self._staged_new:
                await self._insert(node)

            # Cascade renames
            for old, new in self._staged_renames:
                await self._cascade(old, new)

        self._clear_staged()

    async def rollback(self) -> None:
        self._clear_staged()
```

## Testing with In-Memory Repository

```python
from tests.memory_repo import InMemoryRepository

# Fast tests without database
repo = InMemoryRepository()

# Add test data
node = TreeNode.new_category("root", "test", "content")
repo.stage(node)
await repo.commit()

# Query
result = await repo.get_by_path("root.test")
assert result is not None
```

## See Also

- [Transactions Guide](/guide/transactions) - Transaction patterns
- [Architecture](/design/architecture) - System design
- [SemaFS](/api/semafs) - Main facade
