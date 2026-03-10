"""
Unit of Work: Transaction management with shopping cart pattern.

This module implements the Unit of Work pattern, providing a "shopping cart"
for database operations. Changes are staged (registered) and only persisted
when commit() is called, ensuring atomicity.

Design Principles:
    1. Backend-agnostic: Only depends on NodeRepository protocol
    2. Shopping cart semantics: Collect changes, commit all at once
    3. Caller-controlled: The caller decides when to commit/rollback
    4. Exception safety: Rollback on commit failure, clear staging area

The UnitOfWork is the bridge between the domain layer (which manipulates
TreeNode objects) and the storage layer (which persists changes).

Usage:
    async with factory.begin() as uow:
        # Register changes
        uow.register_new(new_node)
        uow.register_dirty(modified_node)
        uow.register_cascade_rename(old_path, new_path)

        # Commit all at once
        await uow.commit()
        # Or let context manager handle rollback on exception
"""
from __future__ import annotations
from typing import List
import logging
from .core.node import TreeNode
from .ports.repo import NodeRepository
from .ports.factory import IUnitOfWork

logger = logging.getLogger(__name__)


class UnitOfWork(IUnitOfWork):
    """
    Shopping cart for database operations.

    UnitOfWork collects all changes (new nodes, modified nodes, renames)
    and commits them atomically. This ensures that either all changes
    succeed or none do, maintaining database consistency.

    The UnitOfWork only depends on the NodeRepository protocol, making
    it completely backend-agnostic. The same UnitOfWork code works with
    SQLite, PostgreSQL, or in-memory storage.

    Attributes:
        repo: The NodeRepository for executing operations.
        nodes: Alias for repo (backward compatibility).

    Internal State:
        _new: List of newly created nodes to INSERT.
        _dirty: List of modified nodes to UPDATE.
        _renames: List of (old_path, new_path) for cascade renames.

    Usage:
        uow = UnitOfWork(repo)
        uow.register_new(new_node)
        uow.register_dirty(modified_node)
        await uow.commit()  # Persists all changes atomically
    """

    def __init__(self, repo: NodeRepository) -> None:
        """
        Initialize a new Unit of Work.

        Args:
            repo: The NodeRepository to use for persistence.
        """
        self.repo = repo
        self.nodes = repo  # Backward compatibility alias
        self._new: List[TreeNode] = []
        self._dirty: List[TreeNode] = []
        self._renames: List[tuple] = []

    def register_new(self, node: TreeNode) -> None:
        """
        Stage a newly created node for INSERT.

        Args:
            node: A brand new TreeNode to be inserted.
        """
        self._new.append(node)

    def register_dirty(self, node: TreeNode) -> None:
        """
        Stage a modified node for UPDATE.

        Args:
            node: An existing TreeNode that has been modified.
        """
        self._dirty.append(node)

    def register_cascade_rename(self, old_path: str, new_path: str) -> None:
        """
        Stage a cascade path rename operation.

        When a category is renamed, all its descendants need their
        parent_path updated. This method stages that operation.

        Args:
            old_path: The old path prefix to replace.
            new_path: The new path prefix.
        """
        self._renames.append((old_path, new_path))

    async def commit(self) -> None:
        """
        Atomically persist all staged changes.

        Executes operations in order:
        1. UPDATE all dirty nodes
        2. INSERT all new nodes
        3. CASCADE RENAME all path changes
        4. COMMIT the transaction

        If any operation fails, rollback is triggered and the exception
        is re-raised. The staging area is always cleared after commit
        (whether successful or not).

        Raises:
            Exception: Any exception from the underlying repository.
        """
        try:
            # Stage dirty nodes (updates)
            for node in self._dirty:
                await self.repo.stage(node)
            # Stage new nodes (inserts)
            for node in self._new:
                await self.repo.stage(node)
            # Stage cascade renames
            for old, new in self._renames:
                await self.repo.cascade_rename(old, new)
            # Commit all changes atomically
            await self.repo.commit()
            logger.debug(
                "[UoW] commit: new=%d dirty=%d renames=%d",
                len(self._new),
                len(self._dirty),
                len(self._renames),
            )
        except Exception:
            await self.rollback()
            raise
        finally:
            self._clear()

    async def rollback(self) -> None:
        """
        Discard all staged changes and rollback the transaction.

        Clears the staging area and calls the repository's rollback
        to revert any pending database changes.
        """
        await self.repo.rollback()
        self._clear()
        logger.debug("[UoW] rollback")

    def _clear(self) -> None:
        """Clear all staging lists."""
        self._new.clear()
        self._dirty.clear()
        self._renames.clear()
