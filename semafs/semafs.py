from __future__ import annotations
import asyncio
import logging
import re
from typing import List, Optional
from .core.enums import NodeType, NodeStatus
from .core.exceptions import NodeNotFoundError, PlanExecutionError
from .core.node import TreeNode, NodePath
from .core.ops import UpdateContext
from .core.views import (
    NodeView,
    TreeView,
    RelatedNodes,
    StatsView,
)
from .executor import Executor
from .ports.strategy import Strategy
from .ports.factory import UoWFactory

logger = logging.getLogger(__name__)


class SemaFS:

    def __init__(self,
                 uow_factory: UoWFactory,
                 strategy: Strategy,
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

    async def read(self, path: str) -> Optional[NodeView]:
        """
        获取单个节点的完整视图。

        Args:
            path: 节点路径

        Returns:
            NodeView 包含节点信息 + 导航上下文，节点不存在时返回 None
        """
        node = await self._uow_factory.repo.get_by_path(path)
        if not node:
            return None

        # 并行获取上下文信息
        children, siblings, ancestors = await asyncio.gather(
            self._uow_factory.repo.list_children(path,
                                                 statuses=[NodeStatus.ACTIVE]),
            self._uow_factory.repo.list_sibling_categories(path),
            self._uow_factory.repo.get_ancestor_categories(path),
        )

        breadcrumb = tuple(a.path for a in reversed(ancestors)) + (path, )

        return NodeView(
            node=node,
            breadcrumb=breadcrumb,
            child_count=len(children),
            sibling_count=len(siblings),
        )

    async def list(self,
                   path: str,
                   include_archived: bool = False) -> List[NodeView]:
        """
        列出目录下的所有子节点（仅直接子节点，不递归）。

        Args:
            path: 目录路径
            include_archived: 是否包含已归档节点

        Returns:
            NodeView 列表（按路径排序）
        """
        statuses = [NodeStatus.ACTIVE, NodeStatus.PENDING_REVIEW]
        if include_archived:
            statuses.append(NodeStatus.ARCHIVED)

        children = await self._uow_factory.repo.list_children(path, statuses)

        views = []
        for child in children:
            child_count = 0
            if child.node_type == NodeType.CATEGORY:
                grandchildren = await self._uow_factory.repo.list_children(
                    child.path, statuses=[NodeStatus.ACTIVE])
                child_count = len(grandchildren)

            siblings = await self._uow_factory.repo.list_sibling_categories(
                child.path)
            ancestors = await self._uow_factory.repo.get_ancestor_categories(
                child.path)
            breadcrumb = tuple(a.path
                               for a in reversed(ancestors)) + (child.path, )

            views.append(
                NodeView(
                    node=child,
                    breadcrumb=breadcrumb,
                    child_count=child_count,
                    sibling_count=len(siblings),
                ))

        return sorted(views, key=lambda v: v.path)

    async def view_tree(self,
                        path: str = "root",
                        max_depth: int = 3) -> Optional[TreeView]:
        """
        获取树形视图（递归展示子树）。

        Args:
            path: 根节点路径
            max_depth: 最大递归深度（防止深层嵌套导致性能问题）

        Returns:
            TreeView 包含完整子树结构，节点不存在时返回 None
        """
        node = await self._uow_factory.repo.get_by_path(path)
        if not node:
            return None

        return await self._build_tree_view(node, depth=0, max_depth=max_depth)

    async def _build_tree_view(self, node: TreeNode, depth: int,
                               max_depth: int) -> TreeView:
        """递归构建树形视图。"""
        children_views = ()

        if node.node_type == NodeType.CATEGORY and depth < max_depth:
            children = await self._uow_factory.repo.list_children(
                node.path, statuses=[NodeStatus.ACTIVE])
            children_views = tuple([
                await self._build_tree_view(child, depth + 1, max_depth)
                for child in children
            ])

        return TreeView(node=node, children=children_views, depth=depth)

    async def get_related(self, path: str) -> Optional[RelatedNodes]:
        """
        获取节点的相关节点（导航地图）。

        Args:
            path: 节点路径

        Returns:
            RelatedNodes 包含父节点、兄弟节点、子节点、祖先链
        """
        current_view = await self.read(path)
        if not current_view:
            return None

        node = current_view.node
        np = NodePath(path)

        parent_node, sibling_nodes, children_nodes, ancestor_nodes = (
            await asyncio.gather(
                self._uow_factory.repo.get_by_path(str(np.parent))
                if not np.is_root else None,
                self._uow_factory.repo.list_sibling_categories(path),
                self._uow_factory.repo.list_children(
                    path, statuses=[NodeStatus.ACTIVE])
                if node.node_type == NodeType.CATEGORY else [],
                self._uow_factory.repo.get_ancestor_categories(path),
            ))

        # 构建 NodeView
        parent_view = None
        if parent_node:
            parent_view = await self.read(parent_node.path)

        sibling_views = []
        for sib in sibling_nodes:
            view = await self.read(sib.path)
            if view:
                sibling_views.append(view)

        children_views = []
        for child in children_nodes:
            view = await self.read(child.path)
            if view:
                children_views.append(view)

        ancestor_views = []
        for anc in ancestor_nodes:
            view = await self.read(anc.path)
            if view:
                ancestor_views.append(view)

        return RelatedNodes(
            current=current_view,
            parent=parent_view,
            siblings=tuple(sibling_views),
            children=tuple(children_views),
            ancestors=tuple(ancestor_views),
        )

    async def stats(self) -> StatsView:
        """
        获取知识库的统计信息。

        Returns:
            StatsView 包含节点数量、深度、热门目录等统计数据
        """
        repo = self._uow_factory.repo

        all_categories = await repo.list_all_categories()
        dirty_categories = await repo.list_dirty_categories()

        total_leaves = 0
        max_depth = 0
        category_child_counts = []

        for cat in all_categories:
            depth = NodePath(cat.path).depth
            max_depth = max(max_depth, depth)

            children = await repo.list_children(cat.path,
                                                statuses=[NodeStatus.ACTIVE])
            leaves = [c for c in children if c.node_type == NodeType.LEAF]
            total_leaves += len(leaves)

            if len(children) > 0:
                category_child_counts.append((cat.path, len(children)))

        top_categories = tuple(
            sorted(category_child_counts, key=lambda x: -x[1])[:10])

        return StatsView(
            total_categories=len(all_categories),
            total_leaves=total_leaves,
            max_depth=max_depth,
            dirty_categories=len(dirty_categories),
            top_categories=top_categories,
        )

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

            # 并行获取所有上下文信息
            all_children, siblings, ancestors = await asyncio.gather(
                uow.repo.list_children(
                    path,
                    statuses=[NodeStatus.ACTIVE, NodeStatus.PENDING_REVIEW]),
                uow.repo.list_sibling_categories(path),
                uow.repo.get_ancestor_categories(path, max_depth=3),
            )

            active = tuple(c for c in all_children
                           if c.status == NodeStatus.ACTIVE)
            pending = tuple(c for c in all_children
                            if c.status == NodeStatus.PENDING_REVIEW)

            context = UpdateContext(
                parent=category,
                active_nodes=active,
                pending_nodes=pending,
                sibling_categories=tuple(siblings),
                ancestor_categories=tuple(ancestors),
            )

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
