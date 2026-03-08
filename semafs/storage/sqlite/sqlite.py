from __future__ import annotations
import asyncio
import json
import logging
import sqlite3
from typing import List, Optional
from ...ports.repo import NodeRepository
from ...core.enums import NodeStatus, NodeType
from ...core.node import NodePath, TreeNode

logger = logging.getLogger(__name__)

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
    last_accessed_at TEXT NOT NULL,

    -- 同一 (parent_path, name) 只能有一个非 ARCHIVED 节点
    UNIQUE(parent_path, name)
);

CREATE INDEX IF NOT EXISTS idx_semafs_parent ON semafs_nodes(parent_path);
CREATE INDEX IF NOT EXISTS idx_semafs_status  ON semafs_nodes(status);
CREATE INDEX IF NOT EXISTS idx_semafs_dirty   ON semafs_nodes(is_dirty, node_type, status);
"""


def _row_to_node(row: sqlite3.Row) -> TreeNode:
    """将数据库行反序列化为 TreeNode。"""
    from datetime import datetime, timezone

    def _parse_dt(s: str) -> datetime:
        # 兼容带/不带时区的 ISO 格式
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
    同步 sqlite3 包装为异步接口，实现 NodeRepository 协议。

    所有 IO 操作通过 asyncio.to_thread 在线程池中执行。
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def _get_by_path_sync(self, path: str) -> Optional[TreeNode]:
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
        cur = self._conn.execute("SELECT * FROM semafs_nodes WHERE id=?",
                                 (node_id, ))
        cur.row_factory = sqlite3.Row
        row = cur.fetchone()
        return _row_to_node(row) if row else None

    def _save_sync(self, node: TreeNode) -> None:
        """INSERT OR REPLACE（通过 UNIQUE 约束触发 conflict）。"""
        self._conn.execute(
            """
            INSERT INTO semafs_nodes
                (id, parent_path, name, node_type, status,
                 content, display_name, name_editable,
                 payload, tags, is_dirty, version, access_count,
                 created_at, updated_at, last_accessed_at)
            VALUES (?,?,?,?,?, ?,?,?, ?,?,?,?,?, ?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                parent_path      = excluded.parent_path,
                name             = excluded.name,
                status           = excluded.status,
                content          = excluded.content,
                display_name     = excluded.display_name,
                name_editable    = excluded.name_editable,
                payload          = excluded.payload,
                tags             = excluded.tags,
                is_dirty         = excluded.is_dirty,
                version          = excluded.version,
                access_count     = excluded.access_count,
                updated_at       = excluded.updated_at,
                last_accessed_at = excluded.last_accessed_at
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
        cur = self._conn.execute(
            "SELECT * FROM semafs_nodes "
            "WHERE node_type='CATEGORY' AND is_dirty=1 AND status != 'ARCHIVED'"
        )
        cur.row_factory = sqlite3.Row
        return [_row_to_node(r) for r in cur.fetchall()]

    def _list_all_categories_sync(self) -> List[TreeNode]:
        cur = self._conn.execute(
            "SELECT * FROM semafs_nodes "
            "WHERE node_type='CATEGORY' AND status != 'ARCHIVED'")
        cur.row_factory = sqlite3.Row
        return [_row_to_node(r) for r in cur.fetchall()]

    def _path_exists_sync(self, path: str) -> bool:
        np = NodePath(path)
        cur = self._conn.execute(
            "SELECT 1 FROM semafs_nodes "
            "WHERE parent_path=? AND name=? AND status != 'ARCHIVED' LIMIT 1",
            (np.parent_path_str, np.name),
        )
        return cur.fetchone() is not None

    def _ensure_unique_path_sync(self, preferred: NodePath) -> NodePath:
        if not self._path_exists_sync(str(preferred)):
            return preferred
        i = 1
        while True:
            candidate = NodePath(f"{preferred}_{i}")
            if not self._path_exists_sync(str(candidate)):
                return candidate
            i += 1
            if i > 100:
                raise RuntimeError(f"路径冲突无法解决: {preferred}")

    def _cascade_rename_sync(self, old_path: str, new_path: str) -> None:
        self._conn.execute(
            """
            UPDATE semafs_nodes
            SET parent_path = ? || substr(parent_path, ?)
            WHERE parent_path = ? OR parent_path LIKE ? ESCAPE '\\'
            """,
            (new_path, len(old_path) + 1, old_path, old_path + ".%"),
        )

    def _commit_sync(self) -> None:
        self._conn.commit()

    def _rollback_sync(self) -> None:
        self._conn.rollback()

    async def get_by_path(self, path: str) -> Optional[TreeNode]:
        return await asyncio.to_thread(self._get_by_path_sync, path)

    async def get_by_id(self, node_id: str) -> Optional[TreeNode]:
        return await asyncio.to_thread(self._get_by_id_sync, node_id)

    async def stage(self, node: TreeNode) -> None:
        """暂存节点变更（执行 SQL，不提交事务）。"""
        await asyncio.to_thread(self._save_sync, node)

    async def cascade_rename(self, old_path: str, new_path: str) -> None:
        await asyncio.to_thread(self._cascade_rename_sync, old_path, new_path)

    async def commit(self) -> None:
        await asyncio.to_thread(self._commit_sync)

    async def rollback(self) -> None:
        await asyncio.to_thread(self._rollback_sync)

    async def list_children(
        self,
        path: str,
        statuses: Optional[List[NodeStatus]] = None,
    ) -> List[TreeNode]:
        return await asyncio.to_thread(self._list_children_sync, path,
                                       statuses)

    async def list_dirty_categories(self) -> List[TreeNode]:
        return await asyncio.to_thread(self._list_dirty_categories_sync)

    async def list_all_categories(self) -> List[TreeNode]:
        return await asyncio.to_thread(self._list_all_categories_sync)

    async def path_exists(self, path: str) -> bool:
        return await asyncio.to_thread(self._path_exists_sync, path)

    async def ensure_unique_path(self, preferred: NodePath) -> NodePath:
        return await asyncio.to_thread(self._ensure_unique_path_sync,
                                       preferred)
