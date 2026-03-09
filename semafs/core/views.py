"""
视图层：为 LLM 提供结构化的记忆查询视图。

设计哲学：
1. 结构化：返回专门的视图对象，而非原始 TreeNode 列表
2. 语义化：每个视图对象都有明确的语义和用途
3. LLM 友好：提供面包屑、统计信息、导航提示
4. 不可变：所有视图对象都是 frozen dataclass
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from .node import TreeNode
from .enums import NodeType


@dataclass(frozen=True)
class NodeView:
    """
    单个节点的完整视图。

    提供节点本身的信息 + 上下文导航信息（面包屑、兄弟数量等）。
    适用于：详情页、单节点查询、LLM 快速理解节点位置。
    """

    node: TreeNode
    breadcrumb: Tuple[str, ...]  # 从 root 到当前节点的路径链
    child_count: int  # 子节点数量（仅 ACTIVE）
    sibling_count: int  # 同级节点数量（仅 ACTIVE CATEGORY）

    @property
    def path(self) -> str:
        """节点完整路径。"""
        return self.node.path

    @property
    def is_category(self) -> bool:
        """是否为目录节点。"""

        return self.node.node_type == NodeType.CATEGORY

    @property
    def summary(self) -> str:
        """节点摘要：路径 + 内容前 100 字符。"""
        content_preview = self.node.content[:100]
        suffix = "..." if len(self.node.content) > 100 else ""
        return f"[{self.path}] {content_preview}{suffix}"


@dataclass(frozen=True)
class TreeView:
    """
    树形视图：递归展示节点及其子树。

    适用于：目录浏览、整体结构查看、导出完整知识树。
    支持深度限制以控制返回数据量。
    """

    node: TreeNode
    children: Tuple["TreeView", ...] = ()
    depth: int = 0  # 当前节点在树中的深度（root 为 0）

    @property
    def path(self) -> str:
        return self.node.path

    @property
    def total_nodes(self) -> int:
        """递归统计子树中的总节点数（包括自己）。"""
        return 1 + sum(child.total_nodes for child in self.children)

    @property
    def leaf_count(self) -> int:
        """递归统计叶子节点数量。"""

        if self.node.node_type == NodeType.LEAF:
            return 1
        return sum(child.leaf_count for child in self.children)


@dataclass(frozen=True)
class RelatedNodes:
    """
    相关节点视图：当前节点的上下文关联节点。

    提供"导航地图"，帮助 LLM 快速理解节点周边环境。
    """

    current: NodeView
    parent: Optional[NodeView] = None
    siblings: Tuple[NodeView, ...] = ()
    children: Tuple[NodeView, ...] = ()
    ancestors: Tuple[NodeView, ...] = ()  # 从近到远的祖先链

    @property
    def navigation_summary(self) -> str:
        """导航摘要：当前位置 + 相关节点数量。"""
        parts = [f"当前: {self.current.path}"]

        if self.parent:
            parts.append(f"父级: {self.parent.path}")

        if self.siblings:
            parts.append(f"{len(self.siblings)} 个同级节点")

        if self.children:
            parts.append(f"{len(self.children)} 个子节点")

        if self.ancestors:
            parts.append(f"祖先链深度: {len(self.ancestors)}")

        return " | ".join(parts)


@dataclass(frozen=True)
class StatsView:
    """
    统计视图：提供知识库的整体统计信息。

    适用于：LLM 了解记忆库规模、生成报告。
    """

    total_categories: int
    total_leaves: int
    max_depth: int
    dirty_categories: int
    top_categories: Tuple[Tuple[str, int], ...]  # (路径, 子节点数) 的排序列表

    @property
    def total_nodes(self) -> int:
        """总节点数。"""
        return self.total_categories + self.total_leaves

    @property
    def summary(self) -> str:
        """统计摘要。"""
        return (f"总计 {self.total_nodes} 个节点 "
                f"({self.total_categories} 个目录, {self.total_leaves} 个叶子), "
                f"最大深度 {self.max_depth}")
