from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
from typing import AsyncIterator, Dict, List, Optional

from semafs.core.enums import NodeStatus, NodeType
from semafs.core.node import NodePath, TreeNode
from semafs.ports.factory import UoWFactory
from semafs.ports.repo import NodeRepository
from semafs.uow import UnitOfWork


def _path_key(path: str) -> tuple:
    """将路径解析为 (parent_path, name) 用于索引"""
    np = NodePath(path)
    return (np.parent_path_str, np.name)


class InMemoryRepository(NodeRepository):
    """
    内存实现 NodeRepository，支持事务语义。

    stage() 暂存变更，commit() 提交，rollback() 回滚。
    """

    def __init__(self) -> None:
        self._nodes: Dict[str, TreeNode] = {}
        self._path_to_id: Dict[str, str] = {}
        self._tx_staged: Dict[str, TreeNode] = {}
        self._tx_renames: List[tuple] = []
        self._tx_undos: List[tuple] = []

    def _index_node(self, node: TreeNode) -> None:
        if node.status != NodeStatus.ARCHIVED:
            self._path_to_id[node.path] = node.id
        else:
            self._path_to_id.pop(node.path, None)

    def _unindex_node(self, path: str) -> None:
        self._path_to_id.pop(path, None)

    async def get_by_path(self, path: str) -> Optional[TreeNode]:
        nid = self._path_to_id.get(path)
        if nid:
            node = self._tx_staged.get(nid) or self._nodes.get(nid)
            if node and node.status != NodeStatus.ARCHIVED:
                return node
        return None

    async def get_by_id(self, node_id: str) -> Optional[TreeNode]:
        node = self._tx_staged.get(node_id) or self._nodes.get(node_id)
        return node if node and node.status != NodeStatus.ARCHIVED else None

    async def list_children(
        self,
        path: str,
        statuses: Optional[List[NodeStatus]] = None,
    ) -> List[TreeNode]:
        if statuses is None:
            statuses = [
                NodeStatus.ACTIVE,
                NodeStatus.PENDING_REVIEW,
                NodeStatus.PROCESSING,
            ]
        by_id = {**self._nodes, **self._tx_staged}
        result = [
            n for n in by_id.values()
            if n.status in statuses and n.parent_path == path
        ]
        return sorted(result, key=lambda n: n.path)

    async def list_dirty_categories(self) -> List[TreeNode]:
        by_id = {**self._nodes, **self._tx_staged}
        return [
            n for n in by_id.values() if n.node_type == NodeType.CATEGORY
            and n.is_dirty and n.status != NodeStatus.ARCHIVED
        ]

    async def list_all_categories(self) -> List[TreeNode]:
        """获取所有 ACTIVE 状态的 CATEGORY 节点。"""
        by_id = {**self._nodes, **self._tx_staged}
        return [
            n
            for n in by_id.values()
            if n.node_type == NodeType.CATEGORY and n.status == NodeStatus.ACTIVE
        ]

    async def path_exists(self, path: str) -> bool:
        return path in self._path_to_id

    async def ensure_unique_path(self, preferred: NodePath) -> NodePath:
        p = str(preferred)
        if p not in self._path_to_id:
            return preferred
        i = 1
        while True:
            candidate = NodePath(f"{p}_{i}")
            if str(candidate) not in self._path_to_id:
                return candidate
            i += 1
            if i > 100:
                raise RuntimeError(f"路径冲突无法解决: {preferred}")

    async def list_sibling_categories(self, path: str) -> List[TreeNode]:
        """获取与指定节点同级的所有 CATEGORY 节点（不包括指定节点自身）。"""
        np = NodePath(path)
        if np.is_root:
            return []

        by_id = {**self._nodes, **self._tx_staged}
        siblings = [
            n for n in by_id.values()
            if n.parent_path == np.parent_path_str
            and n.node_type == NodeType.CATEGORY
            and n.status == NodeStatus.ACTIVE
            and n.name != np.name
        ]
        return sorted(siblings, key=lambda n: n.path)

    async def get_ancestor_categories(
        self, path: str, max_depth: Optional[int] = None
    ) -> List[TreeNode]:
        """获取从指定节点到 root 的祖先 CATEGORY 链（从近到远）。"""
        ancestors = []
        current = NodePath(path)
        depth = 0

        while not current.is_root:
            current = current.parent
            if max_depth is not None and depth >= max_depth:
                break

            node = await self.get_by_path(str(current))
            if node and node.node_type == NodeType.CATEGORY:
                ancestors.append(node)
            depth += 1

        return ancestors

    async def stage(self, node: TreeNode) -> None:
        old = self._nodes.get(node.id) or self._tx_staged.get(node.id)
        self._tx_undos.append((node.id, deepcopy(old) if old else None))
        if old:
            self._unindex_node(old.path)
        self._tx_staged[node.id] = node
        self._index_node(node)

    async def cascade_rename(self, old: str, new: str) -> None:
        self._tx_renames.append((old, new))
        prefix = old + "."
        for node in list(self._nodes.values()) + list(
                self._tx_staged.values()):
            if node.status == NodeStatus.ARCHIVED:
                continue
            pp = node.parent_path
            if pp == old:
                new_pp = new
            elif pp.startswith(prefix):
                new_pp = new + pp[len(old):]
            else:
                continue
            self._unindex_node(node.path)
            node.parent_path = new_pp
            self._index_node(node)

    async def commit(self) -> None:
        for nid, node in self._tx_staged.items():
            self._nodes[nid] = node
        self._tx_staged.clear()
        self._tx_undos.clear()
        self._tx_renames.clear()

    async def rollback(self) -> None:
        for node in self._tx_staged.values():
            self._unindex_node(node.path)
        for nid, old in reversed(self._tx_undos):
            if old:
                self._nodes[nid] = old
                self._index_node(old)
            else:
                self._nodes.pop(nid, None)
        self._tx_staged.clear()
        self._tx_undos.clear()
        self._tx_renames.clear()


class InMemoryUoWFactory(UoWFactory):
    """内存版 UoW 工厂，用于测试。"""

    def __init__(self) -> None:
        self.repo = InMemoryRepository()
        self._lock = asyncio.Lock()

    async def init(self) -> None:
        root = TreeNode.new_category(
            path=NodePath.root(),
            content="根目录",
            name_editable=False,
        )
        self.repo._nodes[root.id] = root
        self.repo._path_to_id["root"] = root.id

    async def close(self) -> None:
        pass

    @asynccontextmanager
    async def begin(self) -> AsyncIterator[UnitOfWork]:
        async with self._lock:
            uow = UnitOfWork(self.repo)
            try:
                yield uow
            except Exception:
                await uow.rollback()
                raise
