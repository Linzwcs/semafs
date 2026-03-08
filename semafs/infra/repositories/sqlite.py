from __future__ import annotations
import asyncio
import json
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import List, Optional
import aiosqlite
from ...interface import TreeRepository
from ...models.enums import NodeStatus, NodeType
from ...models.nodes import TreeNode
from ...models.ops import NodeUpdateContext, NodeUpdateOp
from ...utils import is_direct_child, path_to_parent_and_segment
from .executor import OpExecutor, apply_add_node
from .protocol import NodeStore

# 定位键：(parent_path, name)；path=parent_path.name。不兼容旧数据，需删除旧 db 文件。
_DDL = """
CREATE TABLE IF NOT EXISTS semafs_nodes (
    id             TEXT PRIMARY KEY,
    parent_path    TEXT NOT NULL DEFAULT '',
    name           TEXT NOT NULL DEFAULT '',
    display_name   TEXT,
    node_type      TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'ACTIVE',
    content        TEXT NOT NULL DEFAULT '',
    payload        TEXT NOT NULL DEFAULT '{}',
    tags           TEXT NOT NULL DEFAULT '[]',
    is_dirty       INTEGER NOT NULL DEFAULT 0,
    version        INTEGER NOT NULL DEFAULT 1,
    access_count   INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    last_accessed_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_loc_active
    ON semafs_nodes(parent_path, name) WHERE status != 'ARCHIVED';
"""


def _row_to_node(row: aiosqlite.Row) -> TreeNode:
    d = dict(row)
    raw_payload = d.get("payload") or "{}"
    payload = json.loads(raw_payload) if isinstance(raw_payload, str) else (raw_payload or {})
    if not payload and NodeType(d["node_type"]) == NodeType.LEAF:
        payload = {"_legacy": True}  # 兼容旧数据或异常写入的空 payload
    return TreeNode(
        id=d["id"],
        parent_path=d["parent_path"],
        name=d["name"],
        display_name=d.get("display_name"),
        node_type=NodeType(d["node_type"]),
        status=NodeStatus(d["status"]),
        content=d["content"],
        payload=payload,
        tags=json.loads(d["tags"]),
        is_dirty=bool(d["is_dirty"]),
        version=d["version"],
        access_count=d["access_count"],
        created_at=datetime.fromisoformat(d["created_at"]),
        updated_at=datetime.fromisoformat(d["updated_at"]),
        last_accessed_at=datetime.fromisoformat(d["last_accessed_at"]),
    )


class SQLiteNodeStore(NodeStore):

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    async def get_raw(self, node_id: str) -> Optional[TreeNode]:
        row = await (await self._conn.execute(
            "SELECT * FROM semafs_nodes WHERE id=?", (node_id, ))).fetchone()
        return _row_to_node(row) if row else None

    async def save_raw(self, node: TreeNode) -> None:
        # 定位键：(parent_path, name)；path=parent_path.name
        parent_path, name = node.parent_path, node.name
        if node.status != NodeStatus.ARCHIVED:
            if node.node_type == NodeType.LEAF:
                await self._conn.execute(
                    """
                    UPDATE semafs_nodes SET status=?, updated_at=?
                    WHERE parent_path=? AND name=? AND node_type='LEAF'
                    AND status!=? AND id!=?
                    """,
                    (
                        NodeStatus.ARCHIVED.value,
                        node.updated_at.isoformat(),
                        parent_path,
                        name,
                        NodeStatus.ARCHIVED.value,
                        node.id,
                    ),
                )
            else:
                await self._conn.execute(
                    """
                    UPDATE semafs_nodes SET status=?, updated_at=?
                    WHERE parent_path=? AND name=? AND status!=? AND id!=?
                    AND NOT (parent_path='' AND name='root' AND node_type='CATEGORY')
                    """,
                    (
                        NodeStatus.ARCHIVED.value,
                        node.updated_at.isoformat(),
                        parent_path,
                        name,
                        NodeStatus.ARCHIVED.value,
                        node.id,
                    ),
                )
        try:
            await self._conn.execute(
                """
                INSERT INTO semafs_nodes
                    (id, parent_path, name, display_name, node_type, status, content,
                     payload, tags, is_dirty, version, access_count, created_at, updated_at, last_accessed_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    parent_path=excluded.parent_path, name=excluded.name, display_name=excluded.display_name,
                    status=excluded.status, content=excluded.content, payload=excluded.payload,
                    tags=excluded.tags, is_dirty=excluded.is_dirty, version=excluded.version,
                    access_count=excluded.access_count, updated_at=excluded.updated_at,
                    last_accessed_at=excluded.last_accessed_at
                """,
                (
                    node.id,
                    parent_path,
                    name,
                    node.display_name,
                    node.node_type.value,
                    node.status.value,
                    node.content,
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
        except sqlite3.IntegrityError as e:
            if "parent_path" in str(e) and "name" in str(e):
                await self._conn.execute(
                    """
                    UPDATE semafs_nodes SET status=?, updated_at=?
                    WHERE parent_path=? AND name=? AND status!=? AND id!=?
                    AND NOT (parent_path='' AND name='root' AND node_type='CATEGORY')
                    """,
                    (
                        NodeStatus.ARCHIVED.value,
                        node.updated_at.isoformat(),
                        parent_path,
                        name,
                        NodeStatus.ARCHIVED.value,
                        node.id,
                    ),
                )
                await self._conn.execute(
                    """
                    INSERT INTO semafs_nodes
                        (id, parent_path, name, display_name, node_type, status, content,
                         payload, tags, is_dirty, version, access_count, created_at, updated_at, last_accessed_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(id) DO UPDATE SET
                        parent_path=excluded.parent_path, name=excluded.name, display_name=excluded.display_name,
                        status=excluded.status, content=excluded.content, payload=excluded.payload,
                        tags=excluded.tags, is_dirty=excluded.is_dirty, version=excluded.version,
                        access_count=excluded.access_count, updated_at=excluded.updated_at,
                        last_accessed_at=excluded.last_accessed_at
                    """,
                    (
                        node.id,
                        parent_path,
                        name,
                        node.display_name,
                        node.node_type.value,
                        node.status.value,
                        node.content,
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
            else:
                raise
        await self._conn.commit()

    async def path_exists(self, path: str) -> bool:
        parent_path, name = path_to_parent_and_segment(path)
        row = await (await self._conn.execute(
            "SELECT 1 FROM semafs_nodes WHERE parent_path=? AND name=? AND status!='ARCHIVED' LIMIT 1",
            (parent_path, name),
        )).fetchone()
        return row is not None

    async def get_node(self, path: str) -> Optional[TreeNode]:
        parent_path, name = path_to_parent_and_segment(path)
        row = await (await self._conn.execute(
            "SELECT * FROM semafs_nodes WHERE parent_path=? AND name=? AND status!='ARCHIVED' LIMIT 1",
            (parent_path, name),
        )).fetchone()
        return _row_to_node(row) if row else None

    async def get_category_by_name(
            self,
            name: str,
            prefer_under_parent: Optional[str] = None) -> Optional[TreeNode]:
        """按展示名或 name 查找 CATEGORY；优先同目录下的匹配。"""
        if prefer_under_parent is not None:
            row = await (await self._conn.execute(
                """SELECT * FROM semafs_nodes
                   WHERE node_type='CATEGORY' AND status!='ARCHIVED'
                   AND (name=? OR display_name=?) AND parent_path=? LIMIT 1""",
                (name, name, prefer_under_parent),
            )).fetchone()
            if row:
                return _row_to_node(row)
        row = await (await self._conn.execute(
            """SELECT * FROM semafs_nodes
               WHERE node_type='CATEGORY' AND status!='ARCHIVED'
               AND (name=? OR display_name=?) LIMIT 1""",
            (name, name),
        )).fetchone()
        return _row_to_node(row) if row else None

    async def list_nodes_with_status(
            self, statuses: List[NodeStatus]) -> List[TreeNode]:
        placeholders = ",".join("?" * len(statuses))
        rows = await (await self._conn.execute(
            f"SELECT * FROM semafs_nodes WHERE status IN ({placeholders})",
            [s.value for s in statuses],
        )).fetchall()
        return [_row_to_node(r) for r in rows]

    async def list_dirty_categories(self) -> List[TreeNode]:
        rows = await (await self._conn.execute(
            "SELECT * FROM semafs_nodes WHERE node_type='CATEGORY' AND is_dirty=1 AND status!='ARCHIVED'"
        )).fetchall()
        return [_row_to_node(r) for r in rows]


class SQLiteTreeRepository(TreeRepository):
    """基于 SQLiteNodeStore 的 TreeRepository 实现。"""

    def __init__(self, db_path: str | Path = "semafs.db") -> None:
        self._db_path = str(db_path)
        self._locks: dict[str, asyncio.Lock] = {}
        self._conn: Optional[aiosqlite.Connection] = None
        self._store: Optional[SQLiteNodeStore] = None
        self._executor = OpExecutor()

    async def init(self) -> None:
        self._conn = await aiosqlite.connect(self._db_path)
        self._conn.row_factory = aiosqlite.Row
        # 检测旧 schema（含 segment_name），若有则重建
        cursor = await self._conn.execute(
            "SELECT name FROM pragma_table_info('semafs_nodes') WHERE name='segment_name'"
        )
        if await cursor.fetchone():
            await self._conn.execute("DROP TABLE IF EXISTS semafs_nodes")
            await self._conn.execute("DROP INDEX IF EXISTS idx_loc_active")
        await self._conn.executescript(_DDL)
        await self._conn.commit()
        self._store = SQLiteNodeStore(self._conn)
        await self._ensure_root()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None
            self._store = None

    async def _ensure_root(self) -> None:
        row = await (await self._conn.execute(
            "SELECT id FROM semafs_nodes WHERE parent_path='' AND name='root' AND node_type='CATEGORY'"
        )).fetchone()

        if not row:
            root = TreeNode(
                parent_path="",
                name="root",
                node_type=NodeType.CATEGORY,
                content="",
            )
            await self._store.save_raw(root)
            await self._conn.commit()

    async def ensure_root_available(self) -> None:
        """导出前恢复：确保 root 为 CATEGORY 且可读。"""
        # 1) root 必须是 CATEGORY：若存在 root|LEAF|ACTIVE，先归档
        await self._conn.execute("""UPDATE semafs_nodes SET status='ARCHIVED'
               WHERE parent_path='' AND name='root' AND node_type='LEAF' AND status!='ARCHIVED'"""
                                 )
        # 2) 恢复 root 及其子树：每个 (parent_path, name) 只恢复最新一条
        await self._conn.execute(
            """UPDATE semafs_nodes SET status=?
               WHERE status='ARCHIVED'
               AND ((parent_path='' AND name='root') OR parent_path='root' OR parent_path LIKE 'root.%')
               AND NOT EXISTS (
                 SELECT 1 FROM semafs_nodes n2
                 WHERE n2.parent_path=semafs_nodes.parent_path AND n2.name=semafs_nodes.name
                 AND n2.status != 'ARCHIVED'
               )
               AND id = (
                 SELECT id FROM semafs_nodes n2
                 WHERE n2.parent_path=semafs_nodes.parent_path AND n2.name=semafs_nodes.name
                 AND n2.status='ARCHIVED' ORDER BY n2.updated_at DESC LIMIT 1
               )""",
            (NodeStatus.ACTIVE.value, ),
        )
        await self._conn.commit()

    async def get_node(self, path: str) -> Optional[TreeNode]:
        return await self._store.get_node(path)

    async def list_children(
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
        rows = await self._store.list_nodes_with_status(statuses)
        result = []
        seen: set[str] = set()
        for node in rows:
            if is_direct_child(node.path, path) and node.path not in seen:
                seen.add(node.path)
                result.append(node)

        return sorted(result, key=lambda x: x.path)

    async def list_dirty_categories(self) -> List[TreeNode]:
        return await self._store.list_dirty_categories()

    async def list_all_categories(self) -> List[TreeNode]:
        rows = await (await self._conn.execute(
            "SELECT * FROM semafs_nodes WHERE node_type='CATEGORY' AND status!='ARCHIVED'"
        )).fetchall()
        return [_row_to_node(r) for r in rows]

    @asynccontextmanager
    async def lock_and_get_context(self, path: str):
        lock = self._locks.setdefault(path, asyncio.Lock())
        async with lock:
            parent = await self.get_node(path)
            if not parent or parent.node_type != NodeType.CATEGORY:
                yield None
                return
            all_children = await self.list_children(path)
            ctx = NodeUpdateContext(
                parent=parent,
                active_nodes=[
                    c for c in all_children if c.status == NodeStatus.ACTIVE
                ],
                pending_nodes=[
                    c for c in all_children
                    if c.status == NodeStatus.PENDING_REVIEW
                ],
            )
            yield ctx

    async def add_node(self, node: TreeNode) -> str:
        return await apply_add_node(self._store, node)

    async def execute(self, op: NodeUpdateOp) -> None:
        await self._executor.execute(op, self._store)
