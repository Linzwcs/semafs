from __future__ import annotations
from typing import Optional, Protocol, runtime_checkable

from ...models.nodes import TreeNode


@runtime_checkable
class NodeStore(Protocol):
    """
    纯存储原语，无业务逻辑。
    新增存储后端只需实现此协议。
    """

    async def get_raw(self, node_id: str) -> Optional[TreeNode]:
        """按 id 获取节点（含 ARCHIVED）。"""
        ...

    async def save_raw(self, node: TreeNode) -> None:
        """直接写入。"""
        ...

    async def path_exists(self, path: str) -> bool:
        """检查路径是否已被非 ARCHIVED 节点占用。"""
        ...

    async def get_node(self, path: str) -> Optional[TreeNode]:
        """按 path 获取节点（排除 ARCHIVED）。"""
        ...

    async def get_category_by_name(
            self,
            name: str,
            prefer_under_parent: Optional[str] = None) -> Optional[TreeNode]:
        """按展示名 name 查找 CATEGORY。prefer_under_parent 优先同目录下的匹配。"""
        ...
