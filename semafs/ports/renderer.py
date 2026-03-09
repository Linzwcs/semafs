"""
渲染器协议：定义视图对象到不同格式的转换接口。

设计原则：
1. 协议优先：定义接口而非实现
2. 单一职责：每个渲染器只负责一种格式
3. 无状态：所有方法都是纯函数
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..core.views import NodeView, TreeView, RelatedNodes, StatsView


@runtime_checkable
class Renderer(Protocol):
    """
    渲染器协议。

    所有渲染器都应该实现这个协议，提供统一的渲染接口。
    实现可以选择性地实现部分方法（返回 NotImplementedError）。
    """

    @staticmethod
    def render_node(view: NodeView) -> str:
        """渲染单个节点视图。"""
        ...

    @staticmethod
    def render_tree(view: TreeView) -> str:
        """渲染树形视图。"""
        ...

    @staticmethod
    def render_related(related: RelatedNodes) -> str:
        """渲染相关节点。"""
        ...

    @staticmethod
    def render_stats(stats: StatsView) -> str:
        """渲染统计信息。"""
        ...
