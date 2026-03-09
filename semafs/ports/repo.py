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
