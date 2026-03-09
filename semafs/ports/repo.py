from __future__ import annotations
from typing import List, Optional, Protocol, runtime_checkable
from ..core.enums import NodeStatus
from ..core.node import TreeNode, NodePath


@runtime_checkable
class NodeRepository(Protocol):

    async def get_by_path(self, path: str) -> Optional[TreeNode]:
        ...

    async def get_by_id(self, node_id: str) -> Optional[TreeNode]:
        ...

    async def list_children(
            self,
            path: str,
            statuses: Optional[List[NodeStatus]] = None) -> List[TreeNode]:
        ...

    async def list_dirty_categories(self) -> List[TreeNode]:
        ...

    async def path_exists(self, path: str) -> bool:
        ...

    async def ensure_unique_path(self, preferred: NodePath) -> NodePath:
        ...

    async def list_sibling_categories(self, path: str) -> List[TreeNode]:
        """
        获取与指定节点同级的所有 CATEGORY 节点（不包括指定节点自身）。

        用于构建 UpdateContext.sibling_categories，帮助 LLM 避免重命名冲突。
        仅返回 ACTIVE 状态的 CATEGORY 节点。
        """
        ...

    async def get_ancestor_categories(
        self, path: str, max_depth: Optional[int] = None
    ) -> List[TreeNode]:
        """
        获取从指定节点到 root 的祖先 CATEGORY 链（不包括节点自身）。

        返回顺序：从近到远（parent, grandparent, ..., root）。
        用于构建 UpdateContext.ancestor_categories，提供层级语义上下文。

        Args:
            path: 节点路径
            max_depth: 最多向上追溯层数，None 表示追溯到 root
        """
        ...

    # 写（无事务）
    async def stage(self, node: TreeNode) -> None:
        ...

    async def cascade_rename(self, old: str, new: str) -> None:
        ...

    # 事务
    async def commit(self) -> None:
        ...

    async def rollback(self) -> None:
        ...
