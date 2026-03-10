"""
Storage backend implementations for SemaFS.

This package contains storage adapters that implement the NodeRepository
and UoWFactory protocols for different database backends.

Available Backends:
    - sqlite/: SQLite-based storage (production-ready)

Adding New Backends:
    1. Implement NodeRepository protocol from semafs.ports.repo
    2. Implement UoWFactory protocol from semafs.ports.factory
    3. Ensure atomic transactions (commit/rollback)
    4. Handle unique path generation with ensure_unique_path()
    5. Support cascade rename for path updates

Usage:
    from semafs.storage.sqlite import SQLiteUoWFactory

    factory = SQLiteUoWFactory("knowledge.db")
    await factory.init()

    # Read operations
    node = await factory.repo.get_by_path("root.work")

    # Write operations
    async with factory.begin() as uow:
        uow.register_new(new_node)
        await uow.commit()
"""
