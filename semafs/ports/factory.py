"""
UnitOfWork and Factory protocols: Transaction management abstraction.

This module defines the interfaces for the Unit of Work pattern, which
provides atomic transaction management across the application.

The architecture separates two concerns:
- UoWFactory: Backend initialization and transaction creation
- IUnitOfWork: Shopping cart for staging changes within a transaction

This separation enables:
- Swapping backends without application code changes
- Clean testing with in-memory implementations
- Proper transaction boundaries (caller controls commit/rollback)

Usage:
    # Initialize factory once at application startup
    factory = SQLiteUoWFactory("semafs.db")
    await factory.init()

    # Read operations (no transaction)
    node = await factory.repo.get_by_path("root.work")

    # Write operations (within transaction)
    async with factory.begin() as uow:
        uow.register_new(new_node)
        uow.register_dirty(modified_node)
        await uow.commit()
"""
from __future__ import annotations
from typing import AsyncIterator, Protocol, runtime_checkable
from ..core.node import TreeNode
from .repo import NodeRepository


@runtime_checkable
class IUnitOfWork(Protocol):
    """
    Unit of Work protocol: Shopping cart for staged database changes.

    IUnitOfWork implements the "shopping cart" pattern for database
    operations. Changes are registered (staged) and only persisted
    when commit() is called. This ensures atomicity - either all
    changes succeed, or none do.

    The Unit of Work is typically used as an async context manager
    via UoWFactory.begin().

    Attributes:
        repo: The NodeRepository for querying during the transaction.

    Lifecycle:
        1. Create via factory.begin()
        2. Register changes: register_new(), register_dirty(), register_cascade_rename()
        3. Either commit() to persist or rollback() to discard
        4. Context manager auto-rollbacks on exception
    """
    repo: NodeRepository

    def register_new(self, node: TreeNode):
        """
        Stage a newly created node for INSERT.

        Args:
            node: A brand new TreeNode to be inserted.
        """
        ...

    def register_dirty(self, node: TreeNode):
        """
        Stage a modified node for UPDATE.

        Args:
            node: An existing TreeNode that has been modified.
        """
        ...

    def register_cascade_rename(self, old_path: str, new_path: str):
        """
        Stage a cascade path rename operation.

        When a category is renamed, all its descendants need their
        parent_path updated. This method stages that operation.

        Args:
            old_path: The old path prefix to replace.
            new_path: The new path prefix.
        """
        ...

    async def commit(self) -> None:
        """
        Atomically persist all staged changes.

        Converts the shopping cart contents into database operations:
        - INSERT for registered new nodes
        - UPDATE for registered dirty nodes
        - CASCADE UPDATE for registered renames

        After successful commit, the staging area is cleared.

        Raises:
            Exception: If any database operation fails (triggers rollback).
        """
        ...

    async def rollback(self) -> None:
        """
        Discard all staged changes and rollback the transaction.

        Clears the staging area and reverts the database to its
        state before the transaction began.
        """
        ...


@runtime_checkable
class UoWFactory(Protocol):
    """
    Factory protocol for creating Unit of Work instances.

    UoWFactory is the single entry point for backend-specific operations.
    It manages database connections and provides both read-only access
    (via repo) and transactional access (via begin()).

    Implementation Requirements:
        - init() must be called before any operations
        - close() should be called on application shutdown
        - repo provides non-transactional read access
        - begin() creates a transactional context

    Two Responsibilities (Strictly Separated):
        1. repo: NodeRepository for read-only queries (no transaction)
        2. begin(): Async context manager for atomic write transactions

    Usage:
        factory = SQLiteUoWFactory("semafs.db")
        await factory.init()

        # Read-only query (no transaction overhead)
        node = await factory.repo.get_by_path("root.work")

        # Atomic write operation
        async with factory.begin() as uow:
            uow.register_new(new_node)
            uow.register_dirty(dirty_node)
            await uow.commit()  # Or exception triggers rollback

    Swapping backends requires only changing the factory implementation;
    SemaFS and Executor code remains unchanged.

    Attributes:
        repo: NodeRepository for read-only queries outside transactions.
    """
    repo: NodeRepository

    async def init(self) -> None:
        """
        Initialize the backend (create tables, connection pools, etc.).

        Must be called once at application startup before any operations.
        """
        ...

    async def close(self) -> None:
        """
        Close backend connections.

        Should be called on application shutdown for clean resource release.
        """
        ...

    def begin(self) -> AsyncIterator[IUnitOfWork]:
        """
        Create a new Unit of Work transactional context.

        Returns an async context manager that:
        - Yields an IUnitOfWork for staging changes
        - Auto-rollbacks on exception
        - Requires explicit commit() for persistence

        Usage:
            async with factory.begin() as uow:
                uow.register_new(node)
                await uow.commit()

        Yields:
            IUnitOfWork instance for the transaction.
        """
        ...
