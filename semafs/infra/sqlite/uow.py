"""SQLite implementation of UnitOfWork."""

import asyncio
import json
import sqlite3

from ...core.node import Node
from ...ports.factory import UnitOfWork


class SQLiteUnitOfWork(UnitOfWork):
    """SQLite-backed Unit of Work with shopping cart semantics."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._conn.row_factory = sqlite3.Row
        self._new: list[Node] = []
        self._dirty: list[Node] = []
        self._removed: list[str] = []
        self._renamed: list[tuple[str, str]] = []
        self._moved: list[tuple[str, str]] = []

    def register_new(self, node: Node) -> None:
        self._new.append(node)

    def register_dirty(self, node: Node) -> None:
        self._dirty.append(node)

    def register_removed(self, node_id: str) -> None:
        self._removed.append(node_id)

    def register_rename(self, node_id: str, new_name: str) -> None:
        self._renamed.append((node_id, new_name))

    def register_move(self, node_id: str, new_parent_id: str) -> None:
        self._moved.append((node_id, new_parent_id))

    async def commit(self) -> None:
        await asyncio.to_thread(self._commit_sync)

    def _commit_sync(self) -> None:
        cursor = self._conn.cursor()
        try:
            for node in self._new:
                cursor.execute(
                    "INSERT INTO nodes "
                    "(id, parent_id, name, canonical_path, node_type, "
                    "content, summary, stage, payload, tags, "
                    "is_archived, created_at, updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,datetime('now'),"
                    "datetime('now'))",
                    (
                        node.id,
                        node.parent_id,
                        node.name,
                        node.canonical_path,
                        node.node_type.value,
                        node.content,
                        node.summary,
                        node.stage.value,
                        json.dumps(node.payload),
                        json.dumps(node.tags),
                        0,
                    ),
                )

            for node in self._dirty:
                cursor.execute(
                    "UPDATE nodes SET parent_id=?, name=?, canonical_path=?, "
                    "content=?, summary=?, stage=?, payload=?, tags=?, "
                    "version=version+1, updated_at=datetime('now') WHERE id=?",
                    (
                        node.parent_id,
                        node.name,
                        node.canonical_path,
                        node.content,
                        node.summary,
                        node.stage.value,
                        json.dumps(node.payload),
                        json.dumps(node.tags),
                        node.id,
                    ),
                )

            for node_id, new_name in self._renamed:
                cursor.execute(
                    "UPDATE nodes SET name=?, "
                    "updated_at=datetime('now') WHERE id=?",
                    (new_name, node_id),
                )

            for node_id, new_parent_id in self._moved:
                cursor.execute(
                    "UPDATE nodes SET parent_id=?, "
                    "updated_at=datetime('now') WHERE id=?",
                    (new_parent_id, node_id),
                )

            for node_id in self._removed:
                cursor.execute(
                    "UPDATE nodes SET is_archived=1, "
                    "updated_at=datetime('now') WHERE id=?",
                    (node_id,),
                )

            self._recompute_paths(cursor)
            self._refresh_projection(cursor)
            self._conn.commit()
            self._new.clear()
            self._dirty.clear()
            self._removed.clear()
            self._renamed.clear()
            self._moved.clear()

        except Exception:
            self._conn.rollback()
            raise

    async def rollback(self) -> None:
        await asyncio.to_thread(self._rollback_sync)

    def _rollback_sync(self) -> None:
        self._new.clear()
        self._dirty.clear()
        self._removed.clear()
        self._renamed.clear()
        self._moved.clear()
        self._conn.rollback()

    def _recompute_paths(self, cursor: sqlite3.Cursor) -> None:
        cursor.execute(
            "SELECT id, parent_id, name FROM nodes WHERE is_archived = 0"
        )
        rows = cursor.fetchall()
        by_id = {row["id"]: row for row in rows}

        def build_path(node_id: str) -> str:
            node = by_id[node_id]
            parent_id = node["parent_id"]
            name = node["name"]
            if parent_id is None:
                return "root"
            parent_path = build_path(parent_id)
            return name if parent_path == "root" else f"{parent_path}.{name}"

        for node_id in by_id:
            path = build_path(node_id)
            cursor.execute(
                "UPDATE nodes SET canonical_path=?, "
                "updated_at=datetime('now') WHERE id=?",
                (path, node_id),
            )

    def _refresh_projection(self, cursor: sqlite3.Cursor) -> None:
        cursor.execute("DELETE FROM node_paths")
        cursor.execute(
            "SELECT id, canonical_path FROM nodes WHERE is_archived = 0"
        )
        for row in cursor.fetchall():
            path = row["canonical_path"]
            depth = 0 if path == "root" else path.count(".") + 1
            cursor.execute(
                """
                INSERT INTO node_paths(
                    node_id, canonical_path, depth, updated_at
                )
                VALUES (?, ?, ?, datetime('now'))
                """,
                (row["id"], path, depth),
            )
