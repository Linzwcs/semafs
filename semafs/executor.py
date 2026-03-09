from __future__ import annotations
import logging
from typing import Optional
from uuid import uuid4
from .core.enums import NodeStatus, NodeType
from .core.exceptions import PlanExecutionError
from .core.node import TreeNode, NodePath
from .core.ops import RebalancePlan, UpdateContext, MergeOp, GroupOp, MoveOp, PersistOp
from .uow import UnitOfWork

logger = logging.getLogger(__name__)


def _slug(s: str, max_len: int = 32) -> Optional[str]:

    import re
    if not s or not s.strip().isascii():
        return None
    normalized = re.sub(r"[^a-z0-9_]", "",
                        s.strip().lower().replace(" ", "_")).strip("_")

    return normalized[:max_len] if normalized else None


class Executor:
    """
    在 UoW 沙盘上执行 RebalancePlan。

    整个执行过程零 SQL：所有变更通过 register_new / register_dirty
    登记到 UoW 购物车，由调用方在合适时机 commit。

    这意味着：
    - LLM 返回了不存在的 ids → get_by_id 返回 None → 跳过 → 无副作用
    - 执行到一半抛异常 → UoW 尚未 commit → 数据库完全干净
    - 测试时换一个 DictUoW → 不需要任何 Mock，毫秒级测试
    """

    async def execute(
        self,
        plan: RebalancePlan,
        context: UpdateContext,
        uow: UnitOfWork,
    ) -> None:
        """
        执行整理计划的入口。

        Args:
            plan: LLM 或规则策略产出的计划
            context: 执行前快照的上下文（不在执行过程中重新读库）
            uow: 工作单元，用于 register 变更和查询节点
        """
        logger.debug(
            "[PlanExecutor] 开始执行计划: %s | parent=%s",
            plan.ops_summary,
            context.parent.path,
        )

        id_index: dict[str, TreeNode] = {n.id: n for n in context.all_nodes}

        short_id_index: dict[str, TreeNode] = {
            n.id[:8]: n
            for n in context.all_nodes if n.id[:8] not in id_index
        }

        def resolve(node_id: str) -> Optional[TreeNode]:
            return id_index.get(node_id) or short_id_index.get(node_id[:8])

        for i, op in enumerate(plan.ops):
            try:
                match op:
                    case MergeOp():
                        await self._do_merge(op, context, uow, resolve)
                    case GroupOp():
                        await self._do_group(op, context, uow, resolve)
                    case MoveOp():
                        await self._do_move(op, context, uow, resolve)
                    case PersistOp():
                        await self._do_persist(op, context, uow, resolve)
                    case _:
                        logger.warning("[PlanExecutor] 未知 Op 类型: %s，跳过",
                                       type(op))
            except Exception as exc:
                raise PlanExecutionError(str(exc), op_index=i) from exc

        parent = context.parent
        old_path = parent.apply_plan_result(plan.updated_content,
                                            plan.updated_name)
        uow.register_dirty(parent)

        if old_path:
            new_path = parent.path
            uow.register_cascade_rename(old_path, new_path)
            logger.info("[PlanExecutor] 触发级联更名: %s -> %s", old_path, new_path)

        if not parent.node_path.is_root and plan.should_dirty_parent:
            grandparent_path = parent.node_path.parent
            grandparent = await uow.nodes.get_by_path(str(grandparent_path))
            if grandparent:
                grandparent.request_semantic_rethink()
                uow.register_dirty(grandparent)
                logger.info(
                    "[PlanExecutor] 语义上浮：标记父目录 '%s' 为 dirty 且强制 LLM 整理",
                    grandparent.path)

        logger.debug(
            "[PlanExecutor] 计划执行完毕: %s | parent=%s is_dirty=%s",
            plan.ops_summary,
            parent.path,
            parent.is_dirty,
        )

    async def _do_merge(
        self,
        op: MergeOp,
        context: UpdateContext,
        uow: UnitOfWork,
        resolve,
    ) -> None:
        """
        MERGE：归档参与合并的旧节点，创建一个新的合并叶子。

        父路径从第一个有效节点推导——合并结果落在同一目录下。
        content 和 name 完全来自 LLM 决策（op 字段），不做任何语义推断。
        """
        parent_path_str = context.parent.path
        valid_nodes = []

        for nid in op.ids:
            node = resolve(nid)
            if not node:
                logger.warning("[PlanExecutor] MERGE: id=%s 不在上下文快照中，跳过", nid)
                continue
            if node.node_type != NodeType.LEAF:
                logger.warning(
                    "[PlanExecutor] MERGE: id=%s 是 CATEGORY，不能合并，跳过", nid)
                continue
            # 领域行为：节点自己归档自己
            node.archive()
            uow.register_dirty(node)
            valid_nodes.append(node)

        if not valid_nodes:
            logger.warning("[PlanExecutor] MERGE: 没有有效的叶子节点，跳过整个 MergeOp")
            return

        name = _slug(op.name) or f"merged_{uuid4().hex[:6]}"
        preferred = NodePath(parent_path_str).child(name)
        safe_path = await uow.nodes.ensure_unique_path(preferred)

        new_leaf = TreeNode.new_leaf(
            path=safe_path,
            content=op.content,  # LLM 决定的内容，原样使用
            payload={
                "_merged": True,
                "_merged_from": [n.id for n in valid_nodes]
            },
            status=NodeStatus.ACTIVE,
        )
        uow.register_new(new_leaf)

        logger.debug(
            "[PlanExecutor] MERGE: 归档 %d 个节点 → 新节点 %s",
            len(valid_nodes),
            safe_path,
        )

    async def _do_group(
        self,
        op: GroupOp,
        context: UpdateContext,
        uow: UnitOfWork,
        resolve,
    ) -> None:
        """
        GROUP：创建新子 CATEGORY，将 ids 里的叶子归入其下。

        注意：原叶子被归档，在新 CATEGORY 下创建内容相同的新叶子。
        新 CATEGORY 的 content 由 LLM 提供（op.content），是语义浓缩。
        """
        parent_path = context.parent.path
        name = _slug(op.name)
        if not name:
            logger.warning("[PlanExecutor] GROUP: name 无效，跳过")
            return

        cat_path = NodePath(parent_path).child(name)
        existing_cat = await uow.nodes.get_by_path(str(cat_path))

        if existing_cat and existing_cat.node_type == NodeType.CATEGORY:
            logger.info(f"目标目录 {cat_path} 已存在，执行无缝合入...")
            safe_cat_path = NodePath(existing_cat.path)
            existing_cat.request_semantic_rethink()
            uow.register_dirty(existing_cat)
        else:
            safe_cat_path = await uow.nodes.ensure_unique_path(cat_path)
            new_cat = TreeNode.new_category(
                path=safe_cat_path,
                content=op.content,
                display_name=name,
                status=NodeStatus.ACTIVE,
                name_editable=True,
            )
            uow.register_new(new_cat)

        moved_count = 0

        for i, nid in enumerate(op.ids):
            node = resolve(nid)

            if not node or node.node_type != NodeType.LEAF:
                logger.warning("[PlanExecutor] GROUP: id=%s 无效或非叶子，跳过", nid)
                continue
            node.archive()
            uow.register_dirty(node)

            child_path = safe_cat_path.child(f"leaf_{uuid4().hex[:6]}")
            safe_child = await uow.nodes.ensure_unique_path(child_path)

            new_leaf = TreeNode.new_leaf(
                path=safe_child,
                content=node.content,
                payload={
                    **node.payload, "_grouped": True
                },
                tags=node.tags,
                status=NodeStatus.ACTIVE,
            )
            uow.register_new(new_leaf)
            moved_count += 1

        logger.debug(
            "[PlanExecutor] GROUP: 新建 CATEGORY %s，移入 %d 个叶子",
            safe_cat_path,
            moved_count,
        )

    async def _do_move(
        self,
        op: MoveOp,
        context: UpdateContext,
        uow: UnitOfWork,
        resolve,
    ) -> None:
        """
        MOVE：将单个叶子移入已存在的目标 CATEGORY。

        path_to_move 必须是已存在的 CATEGORY 路径（LLM 从提示词里的列表精确复制）。
        目标不存在时，记录警告并跳过，不自动创建目录（防止 LLM 编造路径导致结构污染）。
        """
        node = resolve(op.ids[0])
        if not node or node.node_type != NodeType.LEAF:
            logger.warning("[PlanExecutor] MOVE: 源节点 id=%s 无效或非叶子，跳过",
                           op.ids[0])
            return

        target = await uow.nodes.get_by_path(op.path_to_move)
        if not target or target.node_type != NodeType.CATEGORY:
            logger.warning(
                "[PlanExecutor] MOVE: 目标路径 '%s' 不存在或非 CATEGORY，跳过",
                op.path_to_move,
            )
            return

        node.archive()
        uow.register_dirty(node)

        name = _slug(op.name) or f"moved_{uuid4().hex[:6]}"
        preferred = NodePath(op.path_to_move).child(name)
        safe_path = await uow.nodes.ensure_unique_path(preferred)

        new_leaf = TreeNode.new_leaf(
            path=safe_path,
            content=node.content,
            payload={
                **node.payload, "_moved": True
            },
            tags=node.tags,
            status=NodeStatus.ACTIVE,
        )
        uow.register_new(new_leaf)

        logger.debug(
            "[PlanExecutor] MOVE: %s → %s",
            node.path,
            safe_path,
        )

    async def _do_persist(
        self,
        op: PersistOp,
        context: UpdateContext,
        uow: UnitOfWork,
        resolve,
    ) -> None:

        node = resolve(op.ids[0])
        if not node:
            logger.warning("[PlanExecutor] PERSIST: id=%s 不存在，跳过", op.ids[0])
            return

        node.archive()
        uow.register_dirty(node)

        parent_path = NodePath(context.parent.path)
        name = _slug(op.name)
        preferred = parent_path.child(name)
        safe_path = await uow.nodes.ensure_unique_path(preferred)
        payload = dict(op.payload)

        new_leaf = TreeNode.new_leaf(
            path=safe_path,
            content=op.content,
            payload=payload,
            status=NodeStatus.ACTIVE,
        )
        uow.register_new(new_leaf)

        logger.debug("[PlanExecutor] PERSIST: %s → %s", node.path, safe_path)
