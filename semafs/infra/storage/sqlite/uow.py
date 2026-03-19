import asyncio
import json
import sqlite3
from contextlib import asynccontextmanager
from collections import defaultdict
from ....core.node import Node, NodeType, NodeStage
from ....core.summary import normalize_category_meta, render_category_summary
from ....ports.factory import TxReader, UnitOfWork
from .store import SQLiteStore


def _row_to_node(row: sqlite3.Row) -> Node:
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


class SQLiteTxReader(TxReader):
    """Transactional reader bound to one SQLite connection."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._conn.row_factory = sqlite3.Row

    async def get_by_id(self, node_id: str) -> Node | None:
        return await asyncio.to_thread(self._get_by_id_sync, node_id)

    def _get_by_id_sync(self, node_id: str) -> Node | None:
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT * FROM nodes WHERE id = ? AND is_archived = 0",
            (node_id,),
        )
        row = cursor.fetchone()
        return _row_to_node(row) if row else None

    async def get_by_path(self, path: str) -> Node | None:
        node_id = await self.resolve_path(path)
        if not node_id:
            return None
        return await self.get_by_id(node_id)

    async def resolve_path(self, path: str) -> str | None:
        return await asyncio.to_thread(self._resolve_path_sync, path)

    def _resolve_path_sync(self, path: str) -> str | None:
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT node_id FROM node_paths WHERE canonical_path = ?",
            (path,),
        )
        row = cursor.fetchone()
        return row["node_id"] if row else None

    async def canonical_path(self, node_id: str) -> str | None:
        return await asyncio.to_thread(self._canonical_path_sync, node_id)

    def _canonical_path_sync(self, node_id: str) -> str | None:
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT canonical_path FROM node_paths WHERE node_id = ?",
            (node_id,),
        )
        row = cursor.fetchone()
        return row["canonical_path"] if row else None

    async def list_children(self, node_id: str) -> list[Node]:
        return await asyncio.to_thread(self._list_children_sync, node_id)

    def _list_children_sync(self, node_id: str) -> list[Node]:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT * FROM nodes
            WHERE parent_id = ? AND is_archived = 0
            ORDER BY node_type DESC, name ASC
            """,
            (node_id,),
        )
        return [_row_to_node(row) for row in cursor.fetchall()]

    async def list_siblings(self, node_id: str) -> list[Node]:
        return await asyncio.to_thread(self._list_siblings_sync, node_id)

    def _list_siblings_sync(self, node_id: str) -> list[Node]:
        cursor = self._conn.cursor()
        # Get parent_id first
        cursor.execute(
            "SELECT parent_id FROM nodes WHERE id = ? AND is_archived = 0",
            (node_id,),
        )
        row = cursor.fetchone()
        if not row or not row["parent_id"]:
            return []
        parent_id = row["parent_id"]
        # Get siblings (same parent, exclude self)
        cursor.execute(
            """
            SELECT * FROM nodes
            WHERE parent_id = ? AND id != ? AND is_archived = 0
            ORDER BY node_type DESC, name ASC
            """,
            (parent_id, node_id),
        )
        return [_row_to_node(row) for row in cursor.fetchall()]

    async def get_ancestors(
        self,
        node_id: str,
        max_depth: int = 3,
    ) -> list[Node]:
        return await asyncio.to_thread(
            self._get_ancestors_sync, node_id, max_depth
        )

    def _get_ancestors_sync(self, node_id: str, max_depth: int) -> list[Node]:
        ancestors: list[Node] = []
        current_id = node_id
        cursor = self._conn.cursor()

        for _ in range(max_depth):
            cursor.execute(
                "SELECT parent_id FROM nodes WHERE id = ? AND is_archived = 0",
                (current_id,),
            )
            row = cursor.fetchone()
            if not row or not row["parent_id"]:
                break
            parent_id = row["parent_id"]
            cursor.execute(
                "SELECT * FROM nodes WHERE id = ? AND is_archived = 0",
                (parent_id,),
            )
            parent_row = cursor.fetchone()
            if parent_row:
                ancestors.append(_row_to_node(parent_row))
            current_id = parent_id

        return ancestors

    async def all_paths(self) -> frozenset[str]:
        return await asyncio.to_thread(self._all_paths_sync)

    def _all_paths_sync(self) -> frozenset[str]:
        cursor = self._conn.cursor()
        cursor.execute("SELECT canonical_path FROM node_paths")
        return frozenset(row["canonical_path"] for row in cursor.fetchall())



class SQLiteUnitOfWork(UnitOfWork):
    """SQLite-backed Unit of Work with shopping cart semantics."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._conn.row_factory = sqlite3.Row
        self.reader = SQLiteTxReader(conn)
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

