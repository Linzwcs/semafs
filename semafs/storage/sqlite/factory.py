"""
SQLite UoW factory for SemaFS.

This module provides SQLiteUoWFactory, which implements the UoWFactory
protocol for SQLite-based storage.

Responsibilities:
    - Initialize SQLite connection and schema
    - Run database migrations
    - Create root category if missing
    - Provide transaction management via begin()

The factory owns the database connection and ensures proper lifecycle
management. It's the only place where SQLite-specific code exists,
keeping the rest of the application database-agnostic.

Usage:
    factory = SQLiteUoWFactory("knowledge.db")
    await factory.init()

    # Read operations (no transaction)
    node = await factory.repo.get_by_path("root.work")

    # Write operations (with transaction)
    async with factory.begin() as uow:
        uow.register_new(new_node)
        await uow.commit()

    await factory.close()
"""
from __future__ import annotations

import asyncio
import logging
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Optional
from ...core.node import NodePath, TreeNode
from ...ports.factory import UoWFactory
from ...uow import UnitOfWork
from .repo import SQLiteRepository, _DDL

logger = logging.getLogger(__name__)


class SQLiteUoWFactory(UoWFactory):
    """
    Factory for SQLite-based Unit of Work instances.

    SQLiteUoWFactory manages the database connection lifecycle and
    provides transactional access via the begin() context manager.

    Key Responsibilities:
        - Create and manage SQLite connection
        - Execute DDL for schema creation
        - Run migrations for schema evolution
        - Create root category on initialization
        - Serialize write access via asyncio.Lock

    The factory exposes two interfaces:
        - repo: For read-only queries outside transactions
        - begin(): For atomic write operations

    Attributes:
        repo: SQLiteRepository for read operations (set after init()).

    Example:
        factory = SQLiteUoWFactory("knowledge.db")
        await factory.init()

        # Read-only (no transaction overhead)
        node = await factory.repo.get_by_path("root.work")

        # Atomic writes
        async with factory.begin() as uow:
            uow.register_new(new_node)
            uow.register_dirty(modified_node)
            await uow.commit()

        await factory.close()
    """

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        """
        Initialize the factory.

        Args:
            db_path: Path to SQLite database file, or ":memory:" for in-memory.
        """
        self._db_path = str(db_path)
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = asyncio.Lock()
        self.repo: Optional[SQLiteRepository] = None

    async def init(self) -> None:
        """
        Initialize database connection and schema.

        Must be called once before any operations. Creates the database
        file if it doesn't exist, runs DDL, executes migrations, and
        ensures the root category exists.
        """
        # Create connection with threading support
        self._conn = await asyncio.to_thread(
            lambda: sqlite3.connect(self._db_path, check_same_thread=False))
        self._conn.row_factory = sqlite3.Row

        # Execute DDL for schema creation
        await asyncio.to_thread(self._conn.executescript, _DDL)

        # Run migrations
        def _migrate(conn: sqlite3.Connection) -> None:
            """Add name_editable column if missing (migration)."""
            cur = conn.execute(
                "SELECT name FROM pragma_table_info('semafs_nodes') WHERE name='name_editable'"
            )
            if not cur.fetchone():
                conn.execute(
                    "ALTER TABLE semafs_nodes ADD COLUMN name_editable INTEGER NOT NULL DEFAULT 1"
                )
            conn.commit()

        await asyncio.to_thread(_migrate, self._conn)

        # Initialize repository
        self.repo = SQLiteRepository(self._conn)

        # Ensure root category exists
        await self._ensure_root()

        # Recover any PROCESSING nodes left by previous crash/termination
        await self._recover_processing_nodes()

    async def close(self) -> None:
        """
        Close database connection.

        Should be called on application shutdown for clean resource release.
        """
        if self._conn:
            await asyncio.to_thread(self._conn.close)
            self._conn = None

    @asynccontextmanager
    async def begin(self) -> AsyncIterator[UnitOfWork]:
        """
        Create a new transactional Unit of Work.

        The context manager:
        - Acquires the write lock (serializes transactions)
        - Creates a UnitOfWork instance
        - Auto-rollbacks on exception
        - Requires explicit commit() for persistence

        Yields:
            UnitOfWork instance for registering changes.

        Raises:
            AssertionError: If factory.init() was not called.

        Example:
            async with factory.begin() as uow:
                uow.register_new(new_node)
                await uow.commit()  # Or exception triggers rollback
        """
        assert self._conn is not None, "Call factory.init() first"
        async with self._lock:
            uow = UnitOfWork(self.repo)
            try:
                yield uow
            except Exception:
                await uow.rollback()
                raise

    async def _ensure_root(self) -> None:
        """
        Ensure the root category exists.

        Creates a root category if one doesn't exist. The root category
        is the entry point for all paths in the knowledge tree.
        """

        def _check_and_insert(conn: sqlite3.Connection) -> None:
            """Check for root and create if missing (sync)."""
            cur = conn.execute(
                "SELECT id FROM semafs_nodes "
                "WHERE parent_path='' AND name='root' AND node_type='CATEGORY'"
            )
            if cur.fetchone():
                return

            root = TreeNode.new_category(
                path=NodePath.root(),
                content="Root directory",
                name_editable=False,
            )
            SQLiteRepository(conn)._save_sync(root)
            conn.commit()

        await asyncio.to_thread(_check_and_insert, self._conn)

    async def _recover_processing_nodes(self) -> None:
        """
        Recover PROCESSING nodes left by crashed/terminated processes.

        When a maintain operation is interrupted (crash, kill, timeout),
        nodes may be left in PROCESSING state. This method restores them
        to their original status on system startup.

        This is called during init() to ensure database consistency.
        """

        def _recover(conn: sqlite3.Connection) -> int:
            """Recover PROCESSING nodes (sync)."""
            # Find all PROCESSING nodes
            cur = conn.execute(
                "SELECT id FROM semafs_nodes WHERE status='PROCESSING'"
            )
            processing_ids = [row[0] for row in cur.fetchall()]

            if not processing_ids:
                return 0

            # Restore to PENDING_REVIEW (safest option - will be reprocessed)
            # We use PENDING_REVIEW instead of ACTIVE because we don't know
            # if the maintenance was completed or not
            conn.execute(
                "UPDATE semafs_nodes SET status='PENDING_REVIEW' WHERE status='PROCESSING'"
            )
            conn.commit()

            return len(processing_ids)

        recovered = await asyncio.to_thread(_recover, self._conn)
        if recovered > 0:
            logger.warning(
                "Recovered %d PROCESSING nodes from previous crash/termination",
                recovered
            )
