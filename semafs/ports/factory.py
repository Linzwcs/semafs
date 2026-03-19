"""UoWFactory - Unit of Work factory protocol."""

from typing import Protocol, runtime_checkable, AsyncIterator
from contextlib import asynccontextmanager

from ..core.node import Node
from .store import NodeStore


@runtime_checkable
class TxReader(Protocol):
    """Transactional read interface bound to one database transaction."""

    async def get_by_id(self, node_id: str) -> Node | None:
        """Transactional read: get node by ID."""
        ...

    async def get_by_path(self, path: str) -> Node | None:
        """Transactional read: get node by canonical path."""
        ...

    async def resolve_path(self, path: str) -> str | None:
        """Transactional read: resolve path to node ID."""
        ...

    async def canonical_path(self, node_id: str) -> str | None:
        """Transactional read: resolve node ID to canonical path."""
        ...

    async def list_children(self, node_id: str) -> list[Node]:
        """Transactional read: list active children of node."""
        ...


@runtime_checkable
class UnitOfWork(Protocol):
    """Unit of Work interface for transaction management."""

    reader: TxReader

    def register_new(self, node: Node) -> None:
        """Stage new node for creation."""
        ...

    def register_dirty(self, node: Node) -> None:
        """Stage modified node for update."""
        ...

    def register_removed(self, node_id: str) -> None:
        """Stage node for removal (archive)."""
        ...

    def register_rename(self, node_id: str, new_name: str) -> None:
        """Stage node rename."""
        ...

    def register_move(self, node_id: str, new_parent_id: str) -> None:
        """Stage parent move."""
        ...

    async def commit(self) -> None:
        """Persist all staged changes atomically."""
        ...

    async def rollback(self) -> None:
        """Discard all staged changes."""
        ...


@runtime_checkable
class UoWFactory(Protocol):
    """Unit of Work factory interface."""

    store: NodeStore

    async def init(self) -> None:
        """Initialize storage (create tables, etc)."""
        ...

    @asynccontextmanager
    async def begin(self) -> AsyncIterator[UnitOfWork]:
        """Create and manage UnitOfWork transaction."""
        ...
