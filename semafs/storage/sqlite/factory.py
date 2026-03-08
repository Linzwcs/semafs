from __future__ import annotations

import asyncio
import logging
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Optional
from core.node import NodePath, TreeNode
from ...ports.factory import UoWFactory
from ...uow import UnitOfWork
from .sqlite import SQLiteRepository, _DDL

logger = logging.getLogger(__name__)


class SQLiteUoWFactory(UoWFactory):
    """
    工厂只负责：组装 SQLiteRepository（含 _conn）+ 提供 begin() 上下文。

    _conn 在这里创建，注入给 SQLiteRepository，之后上层永远看不到它。
    """

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._db_path = str(db_path)
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = asyncio.Lock()
        self.repo: Optional[SQLiteRepository] = None

    async def init(self) -> None:
        self._conn = await asyncio.to_thread(
            lambda: sqlite3.connect(self._db_path, check_same_thread=False))
        self._conn.row_factory = sqlite3.Row
        await asyncio.to_thread(self._conn.executescript, _DDL)

        def _migrate(conn: sqlite3.Connection) -> None:
            cur = conn.execute(
                "SELECT name FROM pragma_table_info('semafs_nodes') WHERE name='name_editable'"
            )
            if not cur.fetchone():
                conn.execute(
                    "ALTER TABLE semafs_nodes ADD COLUMN name_editable INTEGER NOT NULL DEFAULT 1"
                )
            conn.commit()

        await asyncio.to_thread(_migrate, self._conn)
        self.repo = SQLiteRepository(self._conn)
        await self._ensure_root()

    async def close(self) -> None:
        if self._conn:
            await asyncio.to_thread(self._conn.close)
            self._conn = None

    @asynccontextmanager
    async def begin(self) -> AsyncIterator[UnitOfWork]:
        assert self._conn is not None, "请先调用 factory.init()"
        async with self._lock:
            uow = UnitOfWork(self.repo)
            try:
                yield uow
            except Exception:
                await uow.rollback()
                raise

    async def _ensure_root(self) -> None:

        def _check_and_insert(conn: sqlite3.Connection) -> None:
            cur = conn.execute(
                "SELECT id FROM semafs_nodes "
                "WHERE parent_path='' AND name='root' AND node_type='CATEGORY'"
            )
            if cur.fetchone():
                return
            root = TreeNode.new_category(
                path=NodePath.root(),
                content="根目录",
                name_editable=False,
            )
            SQLiteRepository(conn)._save_sync(root)
            conn.commit()

        await asyncio.to_thread(_check_and_insert, self._conn)
