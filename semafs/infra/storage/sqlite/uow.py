import asyncio
import json
import sqlite3
from contextlib import asynccontextmanager
from collections import defaultdict
from ....core.node import Node, NodeType
from ....core.summary import normalize_category_meta, render_category_summary
from ....ports.factory import UnitOfWork
from .store import SQLiteStore


class SQLiteUoWFactory:
    """Factory that opens an isolated write connection per transaction."""

    def __init__(self, store: SQLiteStore):
        self.store = store

    async def init(self) -> None:
        await self.store.resolve_path("root")

    @asynccontextmanager
    async def begin(self):
        """
        Open a fresh write connection via store.write_conn() and hand it to
        the UoW.  The connection is closed automatically when the block exits.
        """
        with self.store.write_conn() as conn:
            uow = SQLiteUnitOfWork(conn)
            try:
                yield uow
            except Exception:
                await uow.rollback()
                raise


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
                summary, category_meta = self._normalize_for_storage(node)
                cursor.execute(
                    "INSERT INTO nodes "
                    "(id, parent_id, name, canonical_path, node_type, "
                    "content, summary, category_meta, stage, payload, tags, "
                    "skeleton, name_editable, "
                    "is_archived, created_at, updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?, ?,datetime('now'),"
                    "datetime('now'))",
                    (
                        node.id,
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
                        0,
                    ),
                )

            for node in self._dirty:
                summary, category_meta = self._normalize_for_storage(node)
                cursor.execute(
                    "UPDATE nodes SET parent_id=?, name=?, canonical_path=?, "
                    "content=?, summary=?, category_meta=?, stage=?, "
                    "payload=?, tags=?, skeleton=?, name_editable=?, "
                    "version=version+1, updated_at=datetime('now') WHERE id=?",
                    (
                        node.parent_id,
                        node.name,
                        node.canonical_path,
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
                    "UPDATE nodes SET is_archived=1, stage='archived', "
                    "updated_at=datetime('now') WHERE id=?",
                    (node_id, ),
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

    @staticmethod
    def _normalize_for_storage(node: Node) -> tuple[str | None, dict]:
        """
        Enforce category_meta contract at write boundary.

        Categories:
        - normalize meta to minimal contract
        - render summary from meta (single source of truth)
        Leaves:
        - keep summary as is (normally None)
        - force category_meta to {}
        """
        if node.node_type != NodeType.CATEGORY:
            return node.summary, {}
        meta = normalize_category_meta(node.category_meta)
        summary = render_category_summary(meta)
        return summary, meta

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
        """
        Recompute canonical paths from (parent_id, name) graph.

        This guarantees cascade path updates for descendants when a parent node
        is renamed or moved inside the same transaction.
        """
        cursor.execute("SELECT id, parent_id, name, canonical_path "
                       "FROM nodes WHERE is_archived = 0")
        rows = cursor.fetchall()
        by_id = {row["id"]: row for row in rows}
        children: dict[str, set[str]] = defaultdict(set)
        for row in rows:
            parent_id = row["parent_id"]
            if parent_id is not None:
                children[parent_id].add(row["id"])

        impacted = self._collect_impacted_ids(by_id, children)
        if not impacted:
            return

        memo: dict[str, str] = {}
        visiting: set[str] = set()

        def build_path(node_id: str) -> str:
            cached = memo.get(node_id)
            if cached is not None:
                return cached
            if node_id in visiting:
                raise ValueError("Cycle detected while recomputing paths, "
                                 f"node_id={node_id}")
            visiting.add(node_id)
            node = by_id[node_id]
            parent_id = node["parent_id"]
            name = node["name"]
            if parent_id is None:
                path = "root"
            else:
                if parent_id not in by_id:
                    raise ValueError(
                        "Orphan active node detected while recomputing paths: "
                        f"node_id={node_id}, missing_parent_id={parent_id}")
                parent_path = build_path(parent_id)
                path = f"{parent_path}.{name}"
            visiting.remove(node_id)
            memo[node_id] = path
            return path

        for node_id in impacted:
            path = build_path(node_id)
            if path == by_id[node_id]["canonical_path"]:
                continue
            cursor.execute(
                "UPDATE nodes SET canonical_path=?, "
                "updated_at=datetime('now') WHERE id=?",
                (path, node_id),
            )

    def _collect_impacted_ids(
        self,
        by_id: dict[str, sqlite3.Row],
        children: dict[str, set[str]],
    ) -> set[str]:
        """
        Collect path-impacted subtree roots and descendants.

        We only need cascade recompute when structure changes:
        - rename, move, create
        - dirty update (conservative: include, to tolerate direct edits)
        """
        roots: set[str] = set()
        roots.update(node_id for node_id, _ in self._renamed)
        roots.update(node_id for node_id, _ in self._moved)
        roots.update(node.id for node in self._new)
        roots.update(node.id for node in self._dirty)

        queue = [node_id for node_id in roots if node_id in by_id]
        impacted: set[str] = set(queue)
        while queue:
            current = queue.pop()
            for child_id in children.get(current, ()):
                if child_id in impacted:
                    continue
                impacted.add(child_id)
                queue.append(child_id)
        return impacted

    def _refresh_projection(self, cursor: sqlite3.Cursor) -> None:
        cursor.execute("DELETE FROM node_paths")
        cursor.execute(
            "SELECT id, canonical_path FROM nodes WHERE is_archived = 0")
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
