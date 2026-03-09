from __future__ import annotations
import logging
import re
from typing import List, Optional
from .core.enums import NodeType, NodeStatus
from .core.exceptions import NodeNotFoundError, PlanExecutionError
from .core.node import TreeNode, NodePath
from .core.ops import UpdateContext
from .executor import Executor
from .ports.strategy import LLMStrategy
from .ports.factory import UoWFactory

logger = logging.getLogger(__name__)


class SemaFS:

    def __init__(self,
                 uow_factory: UoWFactory,
                 strategy: LLMStrategy,
                 executor: Optional[Executor] = None,
                 max_children: int = 10,
                 db_name: str = "default") -> None:
        self._uow_factory = uow_factory
        self._strategy = strategy
        self._executor = executor or Executor()
        self._max_children = max_children
        self.db_name = db_name

    async def write(self, path: str, content: str, payload: dict) -> str:
        resolved = await self._resolve_category(path)
        fragment = TreeNode.new_fragment(parent_path=NodePath(resolved),
                                         content=content,
                                         payload=payload)
        async with self._uow_factory.begin() as uow:
            parent = await uow.nodes.get_by_path(resolved)
            if not parent or parent.node_type != NodeType.CATEGORY:
                raise NodeNotFoundError(resolved)
            parent.receive_fragment()
            uow.register_dirty(parent)
            uow.register_new(fragment)
            await uow.commit()
        logger.info("[%s] 写入碎片 -> '%s' (id=%s)", self.db_name, fragment.path,
                    fragment.id[:8])
        return fragment.id

    async def read(self, path: str) -> List[TreeNode]:
        node = await self._uow_factory.repo.get_by_path(path)
        if not node: return []
        if node.node_type == NodeType.LEAF: return [node]
        return await self._uow_factory.repo.list_children(path)

    async def maintain(self) -> int:
        dirty_cats = await self._uow_factory.repo.list_dirty_categories()
        if not dirty_cats: return 0
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

        try:
            plan = await self._strategy.create_plan(context,
                                                    self._max_children)
        except Exception as e:
            logger.warning("[%s] LLM 失败 '%s': %s", self.db_name, path, e)
            await self._rollback_processing(path)
            return False

        if plan is None:
            await self._finish_processing_without_changes(path)
            return True

        async with self._uow_factory.begin() as uow:
            try:
                await self._executor.execute(plan, context, uow)

                covered_ids = set()
                for op in plan.ops:
                    covered_ids.update(getattr(op, "ids", ()))

                for node in context.all_nodes:
                    if node.id not in covered_ids:
                        node.finish_processing()
                        uow.register_dirty(node)

                context.parent.finish_processing()
                uow.register_dirty(context.parent)

            except PlanExecutionError as e:
                logger.error("[%s] 计划执行失败 '%s': %s", self.db_name, path, e)
                await uow.rollback()
                await self._rollback_processing(path)
                return False

            await uow.commit()

        logger.info("[%s] 整理完成 '%s': %s", self.db_name, path, plan.ops_summary)
        return True

    async def _resolve_category(self, path: str) -> str:
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

    async def _finish_processing_without_changes(self, path: str) -> None:
        async with self._uow_factory.begin() as uow:
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
