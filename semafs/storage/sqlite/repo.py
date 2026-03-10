"""
SQLite repository implementation for SemaFS.

This module provides SQLiteRepository, which implements the NodeRepository
protocol using SQLite as the storage backend.

Design Decisions:
    - Uses asyncio.to_thread() to wrap synchronous sqlite3 calls
    - Single table (semafs_nodes) with composite key (parent_path, name)
    - WAL mode for better concurrency
    - Unique constraint prevents duplicate paths for non-ARCHIVED nodes

Schema:
    - id: UUID primary key
    - parent_path: Path to parent (empty for root's children)
    - name: Node name (last segment of path)
    - node_type: CATEGORY or LEAF
    - status: ACTIVE, ARCHIVED, PENDING_REVIEW, PROCESSING
    - content, display_name, payload, tags: Node data
    - is_dirty, version, access_count: State tracking
    - created_at, updated_at, last_accessed_at: Timestamps

Usage:
    conn = sqlite3.connect("semafs.db")
    repo = SQLiteRepository(conn)

    node = await repo.get_by_path("root.work")
    children = await repo.list_children("root.work")
"""
from __future__ import annotations
import asyncio
import json
import logging
import sqlite3
import uuid
from typing import List, Optional
from ...ports.repo import NodeRepository
from ...core.enums import NodeStatus, NodeType
from ...core.node import NodePath, TreeNode

logger = logging.getLogger(__name__)

# Database schema definition
_DDL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS semafs_nodes (
    id              TEXT PRIMARY KEY,
    parent_path     TEXT NOT NULL DEFAULT '',
    name            TEXT NOT NULL,
    node_type       TEXT NOT NULL CHECK(node_type IN ('CATEGORY','LEAF')),
    status          TEXT NOT NULL DEFAULT 'ACTIVE'
                         CHECK(status IN ('ACTIVE','ARCHIVED','PENDING_REVIEW','PROCESSING')),
    content         TEXT NOT NULL DEFAULT '',
    display_name    TEXT,
    name_editable   INTEGER NOT NULL DEFAULT 1,
    payload         TEXT NOT NULL DEFAULT '{}',
    tags            TEXT NOT NULL DEFAULT '[]',
    is_dirty        INTEGER NOT NULL DEFAULT 0,
    version         INTEGER NOT NULL DEFAULT 1,
    access_count    INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    last_accessed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_semafs_parent ON semafs_nodes(parent_path);
CREATE INDEX IF NOT EXISTS idx_semafs_status  ON semafs_nodes(status);
CREATE INDEX IF NOT EXISTS idx_semafs_dirty   ON semafs_nodes(is_dirty, node_type, status);

-- Only one non-ARCHIVED node per (parent_path, name)
-- Using partial unique index to allow archived nodes with the same original path
CREATE UNIQUE INDEX IF NOT EXISTS idx_semafs_unique_path
    ON semafs_nodes(parent_path, name)
    WHERE status != 'ARCHIVED';
"""


def _row_to_node(row: sqlite3.Row) -> TreeNode:
    """
    Deserialize a database row to TreeNode.

    Handles datetime parsing with fallback for timezone variations.

    Args:
        row: SQLite Row object with node columns.

    Returns:
        Reconstructed TreeNode instance.
    """
    from datetime import datetime, timezone

    def _parse_dt(s: str) -> datetime:
        """Parse ISO datetime string, fallback to current UTC on failure."""
        try:
            return datetime.fromisoformat(s)
        except Exception:
            return datetime.now(timezone.utc)

    node = TreeNode(
        parent_path=row["parent_path"],
        name=row["name"],
        node_type=NodeType(row["node_type"]),
        content=row["content"] or "",
        display_name=row["display_name"],
        name_editable=bool(row["name_editable"]),
        payload=json.loads(row["payload"] or "{}"),
        tags=json.loads(row["tags"] or "[]"),
        status=NodeStatus(row["status"]),
        is_dirty=bool(row["is_dirty"]),
        version=row["version"],
        access_count=row["access_count"],
        created_at=_parse_dt(row["created_at"]),
        updated_at=_parse_dt(row["updated_at"]),
        last_accessed_at=_parse_dt(row["last_accessed_at"]),
        id=row["id"],
    )
    return node


class SQLiteRepository(NodeRepository):
    """
    SQLite implementation of NodeRepository.

    Wraps synchronous sqlite3 operations with asyncio.to_thread() to
    provide an async interface compatible with the repository protocol.

    All read and write operations execute SQL but don't commit until
    commit() is called, following the Unit of Work pattern.

    Attributes:
        _conn: SQLite connection (shared with UoWFactory).

    Thread Safety:
        Operations are serialized via asyncio.Lock in SQLiteUoWFactory.
        The connection is created with check_same_thread=False.

    Example:
        repo = SQLiteRepository(conn)

        # Read operations
        node = await repo.get_by_path("root.work")
        children = await repo.list_children("root.work")

        # Write operations (within UoW)
        await repo.stage(modified_node)
        await repo.commit()
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        """
        Initialize the repository with a SQLite connection.

        Args:
            conn: SQLite connection (caller manages lifecycle).
        """
        self._conn = conn

    # ==================== Synchronous Internal Methods ====================

    def _get_by_path_sync(self, path: str) -> Optional[TreeNode]:
        """Get node by path (sync, excludes ARCHIVED)."""
        np = NodePath(path)
        cur = self._conn.execute(
            "SELECT * FROM semafs_nodes "
            "WHERE parent_path=? AND name=? AND status != 'ARCHIVED'",
            (np.parent_path_str, np.name),
        )
        cur.row_factory = sqlite3.Row
        row = cur.fetchone()
        return _row_to_node(row) if row else None

    def _get_by_id_sync(self, node_id: str) -> Optional[TreeNode]:
        """Get node by UUID (sync, includes all statuses)."""
        cur = self._conn.execute("SELECT * FROM semafs_nodes WHERE id=?",
                                 (node_id, ))
        cur.row_factory = sqlite3.Row
        row = cur.fetchone()
        return _row_to_node(row) if row else None

    def _save_sync(self, node: TreeNode) -> None:
        """
        Upsert a node (UPDATE if exists, INSERT otherwise).

        This ensures status changes (like archive) persist correctly.
        The operation is not committed until commit() is called.
        """
        # Try UPDATE first
        cur = self._conn.execute(
            "UPDATE semafs_nodes SET "
            "parent_path=?, name=?, status=?, content=?, display_name=?, "
            "name_editable=?, payload=?, tags=?, is_dirty=?, version=?, "
            "access_count=?, updated_at=?, last_accessed_at=? WHERE id=?",
            (
                node.parent_path,
                node.name,
                node.status.value,
                node.content,
                node.display_name,
                int(node.name_editable),
                json.dumps(node.payload, ensure_ascii=False),
                json.dumps(node.tags, ensure_ascii=False),
                int(node.is_dirty),
                node.version,
                node.access_count,
                node.updated_at.isoformat(),
                node.last_accessed_at.isoformat(),
                node.id,
            ),
        )
        if cur.rowcount > 0:
            return

        # INSERT if UPDATE didn't match
        self._conn.execute(
            """
            INSERT INTO semafs_nodes
                (id, parent_path, name, node_type, status,
                 content, display_name, name_editable,
                 payload, tags, is_dirty, version, access_count,
                 created_at, updated_at, last_accessed_at)
            VALUES (?,?,?,?,?, ?,?,?, ?,?,?,?,?, ?,?,?)
            """,
            (
                node.id,
                node.parent_path,
                node.name,
                node.node_type.value,
                node.status.value,
                node.content,
                node.display_name,
                int(node.name_editable),
                json.dumps(node.payload, ensure_ascii=False),
                json.dumps(node.tags, ensure_ascii=False),
                int(node.is_dirty),
                node.version,
                node.access_count,
                node.created_at.isoformat(),
                node.updated_at.isoformat(),
                node.last_accessed_at.isoformat(),
            ),
        )

    def _list_children_sync(
        self,
        path: str,
        statuses: Optional[List[NodeStatus]] = None,
    ) -> List[TreeNode]:
        """List direct children with optional status filter (sync)."""
        if statuses is None:
            statuses = [
                NodeStatus.ACTIVE,
                NodeStatus.PENDING_REVIEW,
                NodeStatus.PROCESSING,
            ]
        placeholders = ",".join("?" for _ in statuses)
        vals = [path] + [s.value for s in statuses]
        cur = self._conn.execute(
            f"SELECT * FROM semafs_nodes "
            f"WHERE parent_path=? AND status IN ({placeholders})",
            vals,
        )
        cur.row_factory = sqlite3.Row
        return [_row_to_node(r) for r in cur.fetchall()]

    def _list_dirty_categories_sync(self) -> List[TreeNode]:
        """List all categories with is_dirty=True (sync)."""
        cur = self._conn.execute(
            "SELECT * FROM semafs_nodes "
            "WHERE node_type='CATEGORY' AND is_dirty=1 AND status != 'ARCHIVED'"
        )
        cur.row_factory = sqlite3.Row
        return [_row_to_node(r) for r in cur.fetchall()]

    def _list_all_categories_sync(self) -> List[TreeNode]:
        """List all non-archived categories (sync)."""
        cur = self._conn.execute(
            "SELECT * FROM semafs_nodes "
            "WHERE node_type='CATEGORY' AND status != 'ARCHIVED'")
        cur.row_factory = sqlite3.Row
        return [_row_to_node(r) for r in cur.fetchall()]

    def _path_exists_sync(self, path: str) -> bool:
        """Check if a non-archived node exists at path (sync)."""
        np = NodePath(path)
        cur = self._conn.execute(
            "SELECT 1 FROM semafs_nodes "
            "WHERE parent_path=? AND name=? AND status != 'ARCHIVED' LIMIT 1",
            (np.parent_path_str, np.name),
        )
        return cur.fetchone() is not None

    def _ensure_unique_path_sync(self, preferred: NodePath) -> NodePath:
        """Generate unique path by appending suffix if needed (sync)."""
        if not self._path_exists_sync(str(preferred)):
            return preferred
        i = 1
        while True:
            candidate = NodePath(f"{preferred}_{uuid.uuid4().hex[:6]}")
            if not self._path_exists_sync(str(candidate)):
                return candidate
            i += 1
            if i > 100:
                raise RuntimeError(
                    f"Unable to resolve path conflict: {preferred}")

    def _cascade_rename_sync(self, old_path: str, new_path: str) -> None:
        """Update parent_path for all descendants after rename (sync)."""
        self._conn.execute(
            """
            UPDATE semafs_nodes
            SET parent_path = ? || substr(parent_path, ?)
            WHERE parent_path = ? OR parent_path LIKE ? ESCAPE '\\'
            """,
            (new_path, len(old_path) + 1, old_path, old_path + ".%"),
        )

    def _list_sibling_categories_sync(self, path: str) -> List[TreeNode]:
        """Get sibling CATEGORY nodes at the same level (sync)."""
        np = NodePath(path)
        if np.is_root:
            return []  # Root has no siblings
        cur = self._conn.execute(
            "SELECT * FROM semafs_nodes "
            "WHERE parent_path=? AND node_type='CATEGORY' AND status='ACTIVE' AND name!=?",
            (np.parent_path_str, np.name),
        )
        cur.row_factory = sqlite3.Row
        return [_row_to_node(r) for r in cur.fetchall()]

    def _get_ancestor_categories_sync(
            self,
            path: str,
            max_depth: Optional[int] = None) -> List[TreeNode]:
        """Get ancestor chain from node to root (nearest first, sync)."""
        ancestors = []
        current = NodePath(path)
        depth = 0

        while not current.is_root:
            current = current.parent
            if max_depth is not None and depth >= max_depth:
                break

            node = self._get_by_path_sync(str(current))
            if node and node.node_type == NodeType.CATEGORY:
                ancestors.append(node)
            depth += 1

        return ancestors

    def _commit_sync(self) -> None:
        """Commit the current transaction (sync)."""
        self._conn.commit()

    def _rollback_sync(self) -> None:
        """Rollback the current transaction (sync)."""
        self._conn.rollback()

    # ==================== Async Public Interface ====================

    async def get_by_path(self, path: str) -> Optional[TreeNode]:
        """Get node by path (async wrapper)."""
        return await asyncio.to_thread(self._get_by_path_sync, path)

    async def get_by_id(self, node_id: str) -> Optional[TreeNode]:
        """Get node by UUID (async wrapper)."""
        return await asyncio.to_thread(self._get_by_id_sync, node_id)

    async def stage(self, node: TreeNode) -> None:
        """Stage node changes (execute SQL but don't commit)."""
        await asyncio.to_thread(self._save_sync, node)

    async def cascade_rename(self, old_path: str, new_path: str) -> None:
        """Stage cascade rename operation."""
        await asyncio.to_thread(self._cascade_rename_sync, old_path, new_path)

    async def commit(self) -> None:
        """Commit all staged changes."""
        await asyncio.to_thread(self._commit_sync)

    async def rollback(self) -> None:
        """Rollback all staged changes."""
        await asyncio.to_thread(self._rollback_sync)

    async def list_children(
        self,
        path: str,
        statuses: Optional[List[NodeStatus]] = None,
    ) -> List[TreeNode]:
        """List direct children with optional status filter."""
        return await asyncio.to_thread(self._list_children_sync, path,
                                       statuses)

    async def list_dirty_categories(self) -> List[TreeNode]:
        """List all categories needing maintenance."""
        return await asyncio.to_thread(self._list_dirty_categories_sync)

    async def list_all_categories(self) -> List[TreeNode]:
        """List all non-archived categories."""
        return await asyncio.to_thread(self._list_all_categories_sync)

    async def path_exists(self, path: str) -> bool:
        """Check if a non-archived node exists at path."""
        return await asyncio.to_thread(self._path_exists_sync, path)

    async def ensure_unique_path(self, preferred: NodePath) -> NodePath:
        """Generate unique path by appending suffix if needed."""
        return await asyncio.to_thread(self._ensure_unique_path_sync,
                                       preferred)

    async def list_sibling_categories(self, path: str) -> List[TreeNode]:
        """Get sibling CATEGORY nodes at the same level."""
        return await asyncio.to_thread(self._list_sibling_categories_sync,
                                       path)

    async def get_ancestor_categories(
            self,
            path: str,
            max_depth: Optional[int] = None) -> List[TreeNode]:
        """Get ancestor chain from node to root (nearest first)."""
        return await asyncio.to_thread(self._get_ancestor_categories_sync,
                                       path, max_depth)
