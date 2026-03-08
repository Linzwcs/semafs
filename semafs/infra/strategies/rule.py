from __future__ import annotations
from typing import List, Optional
from ...models.enums import NodeType
from ...models.ops import NodeUpdateContext, NodeUpdateOp, MergeOp
from ...utils import derive_category_content_from_children
from ...interface import NodeUpdateStrategy


class RuleBasedStrategy(NodeUpdateStrategy):
    """
    纯规则策略：根据 inbox/children 数量决定是否重组。
    - 数量少：生成轻量级 MergeOp，仅更新摘要。
    - 数量多：将所有 inbox 合并为一个节点。
    - 无 inbox：返回 None（由调用方处理）。
    """

    def __init__(
        self,
        max_leaf_nodes: int = 3,
    ) -> None:
        self.max_leaf_nodes = max_leaf_nodes

    async def create_update_op(
        self,
        context: NodeUpdateContext,
    ) -> Optional[NodeUpdateOp]:
        """
        根据 inbox + children 数量决定动作。
        若 inbox 为空，返回 None（调用方会提前跳过）。
        """
        inbox = context.inbox
        children = context.children
        total = len(inbox) + len(children)
        leaf_count = sum(1 for n in (list(inbox) + list(children))
                         if getattr(n, "node_type", None) == NodeType.LEAF)
        if not inbox and leaf_count <= self.max_leaf_nodes:
            return None
        if not inbox and leaf_count > self.max_leaf_nodes:
            return self._over_limit_merge_op(context)

        if total < self.max_leaf_nodes:
            return self._lightweight_op(context)
        return self._full_merge_op(context)

    def create_fallback_op(self, context: NodeUpdateContext) -> NodeUpdateOp:
        """LLM 失败时的保底。"""
        leaf_count = sum(1 for n in (list(context.inbox) +
                                     list(context.children))
                         if getattr(n, "node_type", None) == NodeType.LEAF)
        if not context.inbox and leaf_count > self.max_leaf_nodes:
            return self._over_limit_merge_op(context)
        return self._full_merge_op(context)

    def _over_limit_merge_op(self, context: NodeUpdateContext) -> NodeUpdateOp:
        """叶子数超限且无 inbox：合并所有叶子为 1 个，满足「最多 N 叶子」约束。"""
        all_leaves = [
            n for n in (list(context.children) + list(context.inbox))
            if getattr(n, "node_type", None) == NodeType.LEAF
        ]
        if not all_leaves:
            return self._full_merge_op(context)
        parts = [n.content for n in all_leaves if n.content]
        merged_content = "\n\n".join(parts) or "(空)"
        ids = tuple(n.id for n in all_leaves)
        op = MergeOp(
            ids=ids,
            reasoning="叶子数超限，合并以满足每 category 最多 N 叶子约束",
            content=merged_content,
            name="merged_over_limit",
        )

        class _N:

            def __init__(self, c):
                self.content = c

        return NodeUpdateOp(
            ops=[op],
            updated_content=derive_category_content_from_children(
                [_N(merged_content)]) or merged_content[:200],
            is_macro_change=True,
            overall_reasoning="规则：超限合并",
        )

    def _lightweight_op(self, context: NodeUpdateContext) -> NodeUpdateOp:
        """轻量级：仅用规则生成摘要，不改变结构。摘要仅来自子节点内容。"""
        all_nodes = list(context.children) + list(context.inbox)
        summary = derive_category_content_from_children(all_nodes) or "(无内容)"
        ids = tuple(n.id for n in context.inbox)  # 仅叶子节点
        if not ids:
            return None
        op = MergeOp(
            ids=ids,
            reasoning="轻量级摘要，未达重组阈值",
            content=summary,
        )
        return NodeUpdateOp(
            ops=[op],
            updated_content=summary,
            is_macro_change=False,
            overall_reasoning="规则摘要",
        )

    def _full_merge_op(self, context: NodeUpdateContext) -> NodeUpdateOp:
        """完整合并：将 inbox 全部合并为一个新节点。"""
        parts: List[str] = []
        for n in context.inbox:
            if n.content:
                parts.append(n.content)
        merged_content = "\n\n".join(parts) or "(空)"

        # 父目录摘要仅来自子节点（合并后 + 原有 children）
        class _Node:

            def __init__(self, c):
                self.content = c

        all_after = list(context.children) + [_Node(merged_content)]
        parent_summary = derive_category_content_from_children(
            all_after) or merged_content[:200]
        ids = tuple(n.id for n in context.inbox)  # 仅叶子节点
        if not ids:
            return None
        op = MergeOp(
            ids=ids,
            reasoning="合并所有待整理碎片",
            content=merged_content,
        )
        return NodeUpdateOp(
            ops=[op],
            updated_content=parent_summary,
            is_macro_change=True,
            overall_reasoning="规则合并",
        )
