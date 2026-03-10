"""
NodeRepository protocol: Storage abstraction for the knowledge tree.

This module defines the interface that all storage backends must implement.
It follows the Repository pattern from Domain-Driven Design, providing
a collection-like abstraction over the persistence mechanism.

The protocol separates:
- Read operations: get_by_path, list_children, etc. (can be called anytime)
- Write operations: stage, cascade_rename (prepare changes)
- Transaction operations: commit, rollback (finalize or discard changes)

Implementations:
- SQLiteRepository: Production SQLite-based storage
- MemoryRepository: In-memory storage for testing

Usage:
    # Read operations (no transaction needed)
    node = await repo.get_by_path("root.work")
    children = await repo.list_children("root.work")

    # Write operations (use within UnitOfWork)
    async with factory.begin() as uow:
        await uow.repo.stage(modified_node)
        await uow.commit()
"""
from __future__ import annotations
from typing import List, Optional, Protocol, runtime_checkable
from ..core.enums import NodeStatus
from ..core.node import TreeNode, NodePath


@runtime_checkable
class NodeRepository(Protocol):
    """
    Protocol defining the storage interface for TreeNode entities.

    This protocol abstracts all data access operations, enabling the
    application to work with different storage backends (SQLite, PostgreSQL,
    in-memory) without code changes.

    Implementation Requirements:
        - All methods are async for compatibility with async/await patterns
        - Read methods should not require an active transaction
        - Write methods (stage, cascade_rename) prepare changes but don't commit
        - commit() atomically persists all staged changes
        - rollback() discards all staged changes

    Thread Safety:
        Implementations should be safe for concurrent reads but may
        require external synchronization for writes (handled by UnitOfWork).
    """

    async def get_by_path(self, path: str) -> Optional[TreeNode]:
        """
        Retrieve a node by its full path.

        Args:
            path: Full dot-separated path (e.g., "root.work.projects").

        Returns:
            The TreeNode if found and not ARCHIVED, None otherwise.
        """
        ...

    async def get_by_id(self, node_id: str) -> Optional[TreeNode]:
        """
        Retrieve a node by its UUID.

        Args:
            node_id: The UUID string of the node.

        Returns:
            The TreeNode if found, None otherwise.
        """
        ...

    async def list_children(
            self,
            path: str,
            statuses: Optional[List[NodeStatus]] = None) -> List[TreeNode]:
        """
        List direct children of a node.

        Args:
            path: Parent path to list children of.
            statuses: Filter by status (default: ACTIVE, PENDING_REVIEW, PROCESSING).

        Returns:
            List of child TreeNodes matching the status filter.
        """
        ...

    async def list_dirty_categories(self) -> List[TreeNode]:
        """
        List all categories that need maintenance (is_dirty=True).

        Returns:
            List of CATEGORY nodes with is_dirty=True.
        """
        ...

    async def path_exists(self, path: str) -> bool:
        """
        Check if a non-ARCHIVED node exists at the given path.

        Args:
            path: Path to check.

        Returns:
            True if a non-ARCHIVED node exists, False otherwise.
        """
        ...

    async def ensure_unique_path(self, preferred: NodePath) -> NodePath:
        """
        Generate a unique path by appending a suffix if needed.

        If the preferred path is taken, appends _1, _2, etc. until
        a unique path is found.

        Args:
            preferred: The desired path.

        Returns:
            The preferred path if available, or a suffixed variant.

        Raises:
            RuntimeError: If unable to find unique path after 100 attempts.
        """
        ...

    async def list_sibling_categories(self, path: str) -> List[TreeNode]:
        """
        List sibling CATEGORY nodes at the same level.

        Used by LLM to avoid naming conflicts when renaming a category.
        Returns only ACTIVE CATEGORYs, excluding the node at the given path.

        Args:
            path: Path of the node whose siblings to find.

        Returns:
            List of sibling CATEGORY nodes (excludes the node itself).
        """
        ...

    async def get_ancestor_categories(
        self, path: str, max_depth: Optional[int] = None
    ) -> List[TreeNode]:
        """
        Get the ancestor chain from the node to root.

        Returns ancestors in order from nearest to farthest
        (parent, grandparent, ..., root).

        Args:
            path: Path of the node to find ancestors for.
            max_depth: Maximum number of ancestors to return (None = all).

        Returns:
            List of ancestor CATEGORY nodes, nearest first.
        """
        ...

    # Write operations (no transaction commit)

    async def stage(self, node: TreeNode) -> None:
        """
        Stage a node for persistence (INSERT or UPDATE).

        The change is not committed until commit() is called.
        If the node exists, UPDATE is performed; otherwise, INSERT.

        Args:
            node: The TreeNode to stage for persistence.
        """
        ...

    async def cascade_rename(self, old: str, new: str) -> None:
        """
        Stage a cascade path rename operation.

        Updates parent_path for all descendants when a category is renamed.
        The change is not committed until commit() is called.

        Args:
            old: The old path prefix to replace.
            new: The new path prefix.
        """
        ...

    # Transaction control

    async def commit(self) -> None:
        """
        Atomically commit all staged changes.

        After commit, the staging area is cleared.
        """
        ...

    async def rollback(self) -> None:
        """
        Discard all staged changes.

        After rollback, the staging area is cleared and the database
        is unchanged from before the transaction started.
        """
        ...
