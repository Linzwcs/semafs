"""SQLite implementation of NodeStore."""

import asyncio
import json
import sqlite3
import threading
from typing import Optional

from ....core.node import Node, NodeType, NodeStage
from ....core.summary import normalize_category_meta, render_category_summary
from ....ports.store import NodeStore


class SQLiteStore(NodeStore):
    """SQLite-backed node storage (ID-first, path projection aware)."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.RLock()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._ensure_schema(self._conn)
        return self._conn

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS nodes (
                id TEXT PRIMARY KEY,
                parent_id TEXT NULL,
                name TEXT NOT NULL,
                canonical_path TEXT NOT NULL UNIQUE,
                node_type TEXT NOT NULL,
                stage TEXT NOT NULL DEFAULT 'active',
                content TEXT,
                summary TEXT,
                category_meta TEXT NOT NULL DEFAULT '{}',
                payload TEXT NOT NULL DEFAULT '{}',
                tags TEXT NOT NULL DEFAULT '[]',
                skeleton INTEGER NOT NULL DEFAULT 0,
                name_editable INTEGER NOT NULL DEFAULT 1,
                is_archived INTEGER NOT NULL DEFAULT 0,
                version INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY(parent_id) REFERENCES nodes(id)
            )
            """)
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_nodes_sibling_name
            ON nodes(parent_id, name)
            WHERE is_archived = 0
            """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS node_paths (
                node_id TEXT PRIMARY KEY,
                canonical_path TEXT NOT NULL UNIQUE,
                depth INTEGER NOT NULL,
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY(node_id) REFERENCES nodes(id)
            )
            """)
        cursor.execute("SELECT id FROM nodes "
                       "WHERE parent_id IS NULL AND is_archived = 0 LIMIT 1")
        if cursor.fetchone() is None:
            from uuid import uuid4
            root_id = str(uuid4())
            cursor.execute(
                """
                INSERT INTO nodes(
                    id, parent_id, name, canonical_path, node_type, stage,
                    content, summary, category_meta, payload, tags,
                    skeleton, name_editable,
                    is_archived, created_at, updated_at
                ) VALUES (?, NULL, 'root', 'root', 'category', 'active',
                          NULL, 'Root of knowledge tree', '{}', '{}', '[]',
                          1, 0, 0,
                          datetime('now'), datetime('now'))
                """,
                (root_id, ),
            )
            cursor.execute(
                """
                INSERT OR REPLACE INTO node_paths(
                    node_id, canonical_path, depth, updated_at
                )
                VALUES (?, 'root', 0, datetime('now'))
                """,
                (root_id, ),
            )
        cursor.execute("PRAGMA table_info(nodes)")
        columns = {row[1] for row in cursor.fetchall()}
        if "category_meta" not in columns:
            cursor.execute("ALTER TABLE nodes ADD COLUMN category_meta "
                           "TEXT NOT NULL DEFAULT '{}'")
        # Backward compatibility migration:
        # archived rows should carry archived lifecycle stage explicitly.
        cursor.execute("""
            UPDATE nodes
            SET stage = 'archived'
            WHERE is_archived = 1 AND stage != 'archived'
            """)
        conn.commit()

    async def get_by_id(self, node_id: str) -> Node | None:
        return await asyncio.to_thread(self._get_by_id_sync, node_id)

    def _get_by_id_sync(self, node_id: str) -> Node | None:
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM nodes WHERE id = ? AND is_archived = 0",
                (node_id, ),
            )
            row = cursor.fetchone()
            return self._row_to_node(row) if row else None

    async def get_by_path(self, path: str) -> Node | None:
        return await asyncio.to_thread(self._get_by_path_sync, path)

    def _get_by_path_sync(self, path: str) -> Node | None:
        node_id = self._resolve_path_sync(path)
        if not node_id:
            return None
        return self._get_by_id_sync(node_id)

    async def resolve_path(self, path: str) -> str | None:
        return await asyncio.to_thread(self._resolve_path_sync, path)

    def _resolve_path_sync(self, path: str) -> str | None:
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT node_id FROM node_paths WHERE canonical_path = ?",
                (path, ),
            )
            row = cursor.fetchone()
            return row["node_id"] if row else None

    async def canonical_path(self, node_id: str) -> str | None:
        return await asyncio.to_thread(self._canonical_path_sync, node_id)

    def _canonical_path_sync(self, node_id: str) -> str | None:
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT canonical_path FROM node_paths WHERE node_id = ?",
                (node_id, ),
            )
            row = cursor.fetchone()
            return row["canonical_path"] if row else None

    async def save(self, node: Node) -> None:
        await asyncio.to_thread(self._save_sync, node)

    def _save_sync(self, node: Node) -> None:
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM nodes WHERE id = ?", (node.id, ))
            exists = cursor.fetchone() is not None
            summary, category_meta = self._normalize_for_storage(node)

            if exists:
                cursor.execute(
                    """
                    UPDATE nodes
                    SET parent_id = ?, name = ?, canonical_path = ?, node_type = ?,
                        content = ?, summary = ?, category_meta = ?,
                        stage = ?, payload = ?, tags = ?,
                        skeleton = ?, name_editable = ?,
                        updated_at = datetime('now'), version = version + 1
                    WHERE id = ?
                    """,
                    (
                        node.parent_id,
                        node.name,
                        node.canonical_path,
                        node.node_type.value,
                        node.content,
                        summary,
                        json.dumps(category_meta),
                        node.stage.value,
                        json.dumps(node.payload),
                        json.dumps(node.tags),
                        1 if node.skeleton else 0,
                        1 if node.name_editable else 0,
                        node.id,
                    ),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO nodes (
                        id, parent_id, name, canonical_path, node_type, stage,
                        content, summary, category_meta, payload, tags,
                        skeleton, name_editable,
                        is_archived,
                        created_at, updated_at
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0,
                        datetime('now'), datetime('now')
                    )
                    """,
                    (
                        node.id,
                        node.parent_id,
                        node.name,
                        node.canonical_path,
                        node.node_type.value,
                        node.stage.value,
                        node.content,
                        summary,
                        json.dumps(category_meta),
                        json.dumps(node.payload),
                        json.dumps(node.tags),
                        1 if node.skeleton else 0,
                        1 if node.name_editable else 0,
                    ),
                )

            self._refresh_path_projection_sync(cursor)
            conn.commit()

    @staticmethod
    def _normalize_for_storage(node: Node) -> tuple[str | None, dict]:
        if node.node_type != NodeType.CATEGORY:
            return node.summary, {}
        meta = normalize_category_meta(node.category_meta)
        return render_category_summary(meta), meta

    async def list_children(self, node_id: str) -> list[Node]:
        return await asyncio.to_thread(self._list_children_sync, node_id)

    def _list_children_sync(self, node_id: str) -> list[Node]:
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM nodes
                WHERE parent_id = ? AND is_archived = 0
                ORDER BY node_type DESC, name ASC
                """,
                (node_id, ),
            )
            return [self._row_to_node(row) for row in cursor.fetchall()]

    async def list_siblings(self, node_id: str) -> list[Node]:
        return await asyncio.to_thread(self._list_siblings_sync, node_id)

    def _list_siblings_sync(self, node_id: str) -> list[Node]:
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT parent_id FROM nodes WHERE id = ? AND is_archived = 0",
                (node_id, ),
            )
            row = cursor.fetchone()
            if not row:
                return []
            parent_id = row["parent_id"]
            if parent_id is None:
                return []
            cursor.execute(
                """
                SELECT * FROM nodes
                WHERE parent_id = ? AND id != ? AND is_archived = 0
                ORDER BY node_type DESC, name ASC
                """,
                (parent_id, node_id),
            )
            return [self._row_to_node(r) for r in cursor.fetchall()]

    async def get_ancestors(self,
                            node_id: str,
                            max_depth: int = 3) -> list[Node]:
        return await asyncio.to_thread(
            self._get_ancestors_sync,
            node_id,
            max_depth,
        )

    def _get_ancestors_sync(self, node_id: str, max_depth: int) -> list[Node]:
        with self._lock:
            ancestors: list[Node] = []
            current_id = node_id
            for _ in range(max_depth):
                current = self._get_by_id_sync(current_id)
                if not current or not current.parent_id:
                    break
                parent = self._get_by_id_sync(current.parent_id)
                if not parent:
                    break
                ancestors.append(parent)
                current_id = parent.id
            return ancestors

    async def all_node_ids(self) -> frozenset[str]:
        return await asyncio.to_thread(self._all_node_ids_sync)

    def _all_node_ids_sync(self) -> frozenset[str]:
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM nodes WHERE is_archived = 0")
            return frozenset(row["id"] for row in cursor.fetchall())

    async def all_paths(self) -> frozenset[str]:
        return await asyncio.to_thread(self._all_paths_sync)

    def _all_paths_sync(self) -> frozenset[str]:
        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            # canonical_path is globally unique on `nodes`, including archived.
            # We return full history to avoid planning a path that will fail
            # on INSERT due to collision with archived rows.
            cursor.execute("SELECT canonical_path FROM nodes")
            return frozenset(row["canonical_path"]
                             for row in cursor.fetchall())

    def _refresh_path_projection_sync(self, cursor: sqlite3.Cursor) -> None:
        cursor.execute(
            "SELECT id, canonical_path FROM nodes WHERE is_archived = 0")
        rows = cursor.fetchall()
        cursor.execute("DELETE FROM node_paths")
        for row in rows:
            path = row["canonical_path"]
            depth = 0 if path == "root" else path.count(".") + 1
            cursor.execute(
                """
                INSERT OR REPLACE INTO node_paths(
                    node_id, canonical_path, depth, updated_at
                )
                VALUES (?, ?, ?, datetime('now'))
                """,
                (row["id"], path, depth),
            )

    def _row_to_node(self, row: sqlite3.Row) -> Node:
        return Node(
            id=row["id"],
            parent_id=row["parent_id"],
            name=row["name"],
            canonical_path=row["canonical_path"],
            node_type=NodeType(row["node_type"]),
            content=row["content"],
            summary=row["summary"],
            category_meta=json.loads(row["category_meta"] or "{}"),
            payload=json.loads(row["payload"]),
            tags=tuple(json.loads(row["tags"])),
            stage=NodeStage(row["stage"]),
            skeleton=bool(row["skeleton"]),
            name_editable=bool(row["name_editable"]),
        )

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
