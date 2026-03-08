from __future__ import annotations
import logging
import re
from typing import List, Optional
from core.enums import NodeType, NodeStatus
from core.exceptions import NodeNotFoundError, PlanExecutionError
from core.node import TreeNode, NodePath
from core.ops import UpdateContext
from .executor import Executor
from .ports.strategy import LLMStrategy
from .ports.factory import UoWFactory

logger = logging.getLogger(__name__)


class SemaFS:
    """
    SemaFS 应用服务门面。

    依赖注入：所有外部依赖通过构造函数传入，不持有任何具体实现。
    测试时只需要注入 DictUoW + MockStrategy，无需任何 Mock 框架。
    """

    def __init__(
        self,
        uow_factory: UoWFactory,
        strategy: LLMStrategy,
        executor: Optional[Executor] = None,
        max_children: int = 10,
        db_name: str = "default",
    ) -> None:
        self._uow_factory = uow_factory
        self._strategy = strategy
        self._executor = executor or Executor()
        self._max_children = max_children
        self.db_name = db_name

    # ── 写入 ────────────────────────────────────────────────

    async def write(self, path: str, content: str, payload: dict) -> str:
        """
        写入一条记忆碎片。

        path 会被尽力匹配到已存在的 CATEGORY：
        - "root.work.coding" → 找不到时向上找 "root.work" → 再找 "root"
        这样调用方不需要保证路径精确存在。

        若解析后仍找不到父 CATEGORY 节点，抛出 NodeNotFoundError，写入失败。

        返回新建碎片的 node ID。
        """
        resolved = await self._resolve_category(path)

        fragment = TreeNode.new_fragment(
            parent_path=NodePath(resolved),
            content=content,
            payload=payload,
        )
        async with self._uow_factory.begin() as uow:

            parent = await uow.nodes.get_by_path(resolved)
            if not parent or parent.node_type != NodeType.CATEGORY:
                raise NodeNotFoundError(resolved)
            parent.receive_fragment()
            uow.register_dirty(parent)
            uow.register_new(fragment)
            await uow.commit()

        logger.info(
            "[%s] 写入碎片 -> '%s' (id=%s)",
            self.db_name,
            fragment.path,
            fragment.id[:8],
        )
        return fragment.id

    async def read(self, path: str) -> List[TreeNode]:
        """
        读取节点。直接使用 factory.repo，不开启事务，无任何锁开销。
        """

        node = await self._uow_factory.repo.get_by_path(path)
        if not node:
            return []
        if node.node_type == NodeType.LEAF:
            return [node]
        return await self._uow_factory.repo.list_children(path)

    async def maintain(self) -> int:

        dirty_cats = await self._uow_factory.repo.list_dirty_categories()
        if not dirty_cats:
            return 0

        dirty_cats.sort(key=lambda n: -n.depth)
        processed = 0

        for category in dirty_cats:
            try:
                if await self._maintain_one(category.path):
                    processed += 1
            except Exception as e:
                logger.error("[%s] 整理崩溃 '%s': %s",
                             self.db_name,
                             category.path,
                             e,
                             exc_info=True)
        return processed

    async def _maintain_one(self, path: str) -> bool:
        """
        Saga 编排：
        1. 极速微事务：挂牌 (PROCESSING)
        2. 无锁慢操作：调大模型深思熟虑
        3. 极速微事务：执行沙盘推演、摘牌 (ACTIVE/ARCHIVED)
        """
        # ==========================================
        # Phase 1: 挂牌 (微事务)
        # ==========================================
        async with self._uow_factory.begin() as uow:
            category = await uow.repo.get_by_path(path)
            if not category or category.node_type != NodeType.CATEGORY:
                return False

            all_children = await uow.repo.list_children(
                path, statuses=[NodeStatus.ACTIVE, NodeStatus.PENDING_REVIEW])

            active = tuple(c for c in all_children
                           if c.status == NodeStatus.ACTIVE)
            pending = tuple(c for c in all_children
                            if c.status == NodeStatus.PENDING_REVIEW)

            context = UpdateContext(parent=category,
                                    active_nodes=active,
                                    pending_nodes=pending)

            total_nodes = len(context.all_nodes)
            if not pending and total_nodes <= self._max_children:
                category.clear_dirty()
                uow.register_dirty(category)
                await uow.commit()
                return True

            category.start_processing()
            uow.register_dirty(category)
            for child in context.all_nodes:
                child.start_processing()
                uow.register_dirty(child)

            await uow.commit()

        # ==========================================
        # Phase 2: 离线思考 (无锁网络 I/O)
        # ==========================================
        try:
            plan = await self._strategy.create_plan(context)
        except Exception as e:
            logger.warning("[%s] LLM 失败 '%s': %s", self.db_name, path, e)
            await self._rollback_processing(path)
            return False

        if plan is None:
            await self._finish_processing_without_changes(path)
            return True

        # ==========================================
        # Phase 3: 沙盘落地与摘牌 (微事务)
        # ==========================================
        async with self._uow_factory.begin() as uow:

            category = await uow.repo.get_by_path(path)
            try:

                await self._executor.execute(plan, context, uow)
                category.finish_processing()
                uow.register_dirty(category)

                current_children = await uow.repo.list_children(
                    path, statuses=[NodeStatus.PROCESSING])

                for child in current_children:
                    child.finish_processing()
                    uow.register_dirty(child)

            except PlanExecutionError as e:
                logger.error("[%s] 计划执行失败 '%s': %s", self.db_name, path, e)
                await uow.rollback()  # 取消内存的 Ops
                await self._rollback_processing(path)  # 退回挂牌前状态
                return False

            await uow.commit()

        logger.info("[%s] 整理完成 '%s': %s", self.db_name, path, plan.ops_summary)
        return True

    async def _resolve_category(self, path: str) -> str:
        """
        路径向上解析：找到最近的已存在 CATEGORY。

        "root.work.coding.python" 不存在
        → 尝试 "root.work.coding"  不存在
        → 尝试 "root.work"         存在 → 返回
        """
        clean = re.sub(r"[^a-z0-9._]", "", path.lower()).strip(".")
        parts = clean.split(".") if clean else []

        while parts:
            candidate = ".".join(parts)
            node = await self._uow_factory.repo.get_by_path(candidate)
            if node and node.node_type == NodeType.CATEGORY:
                return candidate
            parts.pop()

        return "root"

    async def _rollback_processing(self, path: str) -> None:

        async with self._uow_factory.begin() as uow:
            from core.enums import NodeStatus
            category = await uow.nodes.get_by_path(path)
            if category:
                category.fail_processing()
                uow.register_dirty(category)

            children = await uow.nodes.list_children(
                path, statuses=[NodeStatus.PROCESSING])
            for child in children:
                child.fail_processing()
                uow.register_dirty(child)

            await uow.commit()
            logger.info("[%s] 已回滚 '%s' 的 PROCESSING 状态", self.db_name, path)

    async def _finish_processing_without_changes(self, path: str) -> None:

        async with self._uow_factory() as uow:
            from core.enums import NodeStatus
            category = await uow.nodes.get_by_path(path)
            if category:
                category.finish_processing()
                category.clear_dirty()
                uow.register_dirty(category)

            children = await uow.nodes.list_children(
                path, statuses=[NodeStatus.PROCESSING])
            for child in children:
                child.finish_processing()
                uow.register_dirty(child)

            await uow.commit()
