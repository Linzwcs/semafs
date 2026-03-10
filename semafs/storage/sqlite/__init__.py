"""
SQLite storage backend for SemaFS.

This package provides a SQLite-based implementation of the storage
protocols, suitable for single-user and embedded deployments.

Components:
    - SQLiteRepository: Implements NodeRepository for data access
    - SQLiteUoWFactory: Implements UoWFactory for transaction management

Features:
    - WAL mode for better concurrent read performance
    - Automatic schema creation and migrations
    - Unique path constraints for non-archived nodes
    - Async wrapper using asyncio.to_thread()

Usage:
    from semafs.storage.sqlite import SQLiteUoWFactory

    # In-memory database (for testing)
    factory = SQLiteUoWFactory(":memory:")

    # File-based database (for production)
    factory = SQLiteUoWFactory("knowledge.db")

    await factory.init()

    # The factory manages the connection lifecycle
    # Always call close() on application shutdown
    await factory.close()
"""
from .factory import SQLiteUoWFactory
from .repo import SQLiteRepository

__all__ = [
    "SQLiteUoWFactory",
    "SQLiteRepository",
]
