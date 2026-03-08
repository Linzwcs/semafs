from __future__ import annotations
from typing import List
import logging
from .core.node import TreeNode
from .ports.repo import NodeRepository
from .ports.factory import IUnitOfWork

logger = logging.getLogger(__name__)


class UnitOfWork(IUnitOfWork):
    """
    纯购物车逻辑，完全后端无关。

    只依赖 NodeRepository 协议：
    - stage()          → 暂存节点变更（不提交）
    - cascade_rename() → 暂存级联重命名（不提交）
    - commit()         → 提交事务
    - rollback()       → 回滚事务

    """

    def __init__(self, repo: NodeRepository) -> None:
        self.repo = repo
        self.nodes = repo  # 向后兼容别名
        self._new: List[TreeNode] = []
        self._dirty: List[TreeNode] = []
        self._renames: List[tuple] = []

    def register_new(self, node: TreeNode) -> None:
        self._new.append(node)

    def register_dirty(self, node: TreeNode) -> None:
        self._dirty.append(node)

    def register_cascade_rename(self, old_path: str, new_path: str) -> None:
        self._renames.append((old_path, new_path))

    async def commit(self) -> None:
        try:
            for node in self._new:
                await self.repo.stage(node)
            for node in self._dirty:
                await self.repo.stage(node)
            for old, new in self._renames:
                await self.repo.cascade_rename(old, new)
            await self.repo.commit()
            logger.debug(
                "[UoW] commit: new=%d dirty=%d renames=%d",
                len(self._new),
                len(self._dirty),
                len(self._renames),
            )
        except Exception:
            await self.rollback()
            raise
        finally:
            self._clear()

    async def rollback(self) -> None:
        await self.repo.rollback()
        self._clear()
        logger.debug("[UoW] rollback")

    def _clear(self) -> None:
        self._new.clear()
        self._dirty.clear()
        self._renames.clear()
