from __future__ import annotations
import logging
import re
from typing import List, Union
from .models.nodes import TreeNode, VirtualTreeNode
from .models.enums import NodeType, OpType
from .interface import TreeRepository, NodeUpdateStrategy

logger = logging.getLogger(__name__)


class SemaFS:
    """
    SemaFS 核心协调者 (Application Service Layer).

    设计理念：
    1. 极简的 API: 外部视角只有 write 和 read，全部基于统一的 TreeNode 模型。
    2. 无锁化阅读: 读写分离，依靠底层 PROCESSING 状态防阻塞。
    3. 纯粹编排: 不再包含具体的 DB 拼装逻辑 (无 _build_txn)，Op 的执行交给底层。
    """

    def __init__(
        self,
        repo: TreeRepository,
        strategy: NodeUpdateStrategy,
        *,
        db_name: str = "default",
        max_leaf_nodes: int | None = None,
        max_category_nodes: int | None = None,
    ) -> None:
        self._repo = repo
        self._strategy = strategy
        self.db_name = db_name
        self._max_leaf_nodes = max_leaf_nodes or getattr(
            strategy, "_max_leaf_nodes", getattr(strategy, "max_leaf_nodes",
                                                 5))
        self._max_category_nodes = max_category_nodes or getattr(
            strategy, "_max_category_nodes",
            getattr(strategy, "max_category_nodes", self._max_leaf_nodes))

    async def write(self, path: str, content: str, payload: dict) -> str:

        safe_path = await self.resolve_path(path)
        frag_node = VirtualTreeNode.create(
            parent_path=safe_path,
            content=content,
            payload=payload,
        )
        logger.debug(
            "[插入] 路径解析: 请求=%s -> 解析后=%s -> 插入路径=%s",
            path,
            safe_path,
            frag_node.path,
        )
        await self._repo.add_node(frag_node)
        logger.info(f"📥 [{self.db_name}] 写入记忆碎片 -> '{frag_node.path}'")
        return frag_node.id

    async def read(self, path: str) -> Union[TreeNode, List[TreeNode]]:
        """
        读取节点内容（合路视图）。
        返回稳定节点(ACTIVE) + 碎片记忆(PENDING_REVIEW) + 正在整理中的节点(PROCESSING)。
        前端/终端用户能看到所有的状态，所写即所见。
        """
        node = await self._repo.get_node(path)

        if not node:
            return []

        if node.node_type == NodeType.LEAF:
            return [node]

        children = await self._repo.list_children(path)
        return children

    async def maintain(self) -> int:
        """
        后台整理任务 (由 Cron 定时触发)
        """
        dirty_nodes = await self._repo.list_dirty_categories()
        if not dirty_nodes:
            return 0

        dirty_nodes.sort(key=lambda n: -n.depth)  # 从最深层开始整理
        processed = 0

        for node in dirty_nodes:
            async with self._repo.lock_and_get_context(node.path) as ctx:

                if not ctx:
                    continue

                all_children = list(ctx.children or []) + list(ctx.inbox or [])
                leaf_count = sum(1 for c in all_children
                                 if c.node_type == NodeType.LEAF)
                category_count = sum(1 for c in all_children
                                     if c.node_type == NodeType.CATEGORY)

                if not ctx.inbox:
                    if (leaf_count <= self._max_leaf_nodes
                            and category_count <= self._max_category_nodes):
                        node.is_dirty = False
                        await self._repo.add_node(node)
                        continue
                    # 叶子数或子分类数超限，无 inbox 也需触发策略整理

                try:
                    node_update_op = await self._strategy.create_update_op(ctx)
                except Exception as e:
                    node_update_op = self._strategy.create_fallback_op(ctx)
                    logger.warning(
                        f"⚠️ 大脑思考失败 {node.path}: {e}, 使用 fallback 策略")

                if node_update_op:
                    await self._repo.execute(node_update_op, ctx)
                    summary = node_update_op.ops_summary
                    logger.info(
                        f"✅ [{self.db_name}] 记忆已重组 {node.path}: {summary}")
                else:
                    node.is_dirty = False
                    await self._repo.add_node(node)

                processed += 1

        # post-check: 若某 category 的叶子数或子分类数 > 阈值，标记 dirty 促下一轮整理
        for cat in await self._repo.list_all_categories():
            children = await self._repo.list_children(cat.path)
            leaf_count = sum(1 for c in children
                             if c.node_type == NodeType.LEAF)
            category_count = sum(1 for c in children
                                 if c.node_type == NodeType.CATEGORY)
            over_leaf = leaf_count > self._max_leaf_nodes
            over_cat = category_count > self._max_category_nodes
            if (over_leaf or over_cat) and not cat.is_dirty:
                cat.is_dirty = True
                cat.bump_version()
                await self._repo.add_node(cat)
                parts = []
                if over_leaf:
                    parts.append(f"叶子数 {leaf_count} > {self._max_leaf_nodes}")
                if over_cat:
                    parts.append(
                        f"子分类数 {category_count} > {self._max_category_nodes}")
                logger.info(
                    f"📌 [{self.db_name}] {cat.path} {'，'.join(parts)}，标记 dirty"
                )

        return processed

    async def resolve_path(self, path: str) -> str:

        clean = re.sub(r"[^a-z0-9._]", "", path.lower()).strip(".")
        if not clean:
            return "root"

        parts = clean.split(".")
        while parts:
            candidate = ".".join(parts)
            node = await self._repo.get_node(candidate)
            if node and node.node_type == NodeType.CATEGORY:
                return candidate
            parts.pop()

        return "root"
