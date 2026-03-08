from __future__ import annotations
import asyncio
from contextlib import asynccontextmanager
from typing import Dict, List, Optional
from ...interface import TreeRepository
from ...models.ops import NodeUpdateOp
from ...models.nodes import TreeNode
from ...models.ops import NodeUpdateContext
from ...models.enums import NodeStatus, NodeType
from ...utils import ensure_root, is_direct_child
from .executor import OpExecutor, apply_add_node
from .protocol import NodeStore


class MemoryNodeStore(NodeStore):

    def __init__(self) -> None:
        self._nodes: Dict[str, TreeNode] = {}
        self._path_to_id: Dict[str, str] = {}

    def _ensure_root(self) -> None:
        ensure_root(self._nodes)

    async def get_raw(self, node_id: str) -> Optional[TreeNode]:
        return self._nodes.get(node_id)

    async def save_raw(self, node: TreeNode) -> None:
        old = self._nodes.get(node.id)
        if old and old.path != node.path and self._path_to_id.get(old.path) == node.id:
            del self._path_to_id[old.path]
        self._nodes[node.id] = node
        if node.status == NodeStatus.ARCHIVED:
            if self._path_to_id.get(node.path) == node.id:
                del self._path_to_id[node.path]
        else:
            self._path_to_id[node.path] = node.id

    async def path_exists(self, path: str) -> bool:
        return path in self._path_to_id

    def list_nodes(self) -> List[TreeNode]:

        return list(self._nodes.values())

    async def get_node(self, path: str) -> Optional[TreeNode]:
        self._ensure_root()
        nid = self._path_to_id.get(path)
        if nid:
            node = self._nodes.get(nid)
            if node and node.status != NodeStatus.ARCHIVED:
                return node
        for n in self._nodes.values():
            if n.path == path and n.status != NodeStatus.ARCHIVED:
                return n
        return None

    async def get_category_by_name(
            self,
            name: str,
            prefer_under_parent: Optional[str] = None) -> Optional[TreeNode]:
        """按展示名查找 CATEGORY；优先同目录下的匹配。"""
        candidates = [
            n for n in self._nodes.values()
            if n.node_type == NodeType.CATEGORY and n.status !=
            NodeStatus.ARCHIVED and (n.name == name or n.display_name == name)
        ]
        if not candidates:
            return None
        if prefer_under_parent is not None:
            for n in candidates:
                if n.parent_path == prefer_under_parent:
                    return n
        return candidates[0]

    async def cascade_rename_path(
            self,
            old_path: str,
            new_path: str,
    ) -> int:
        """级联更新子孙 parent_path，并同步 path_to_id。"""
        updated = 0
        prefix = old_path + "."
        for node in list(self._nodes.values()):
            if node.status == NodeStatus.ARCHIVED:
                continue
            pp = node.parent_path
            if pp != old_path and not pp.startswith(prefix):
                continue
            old_node_path = node.path
            new_pp = new_path + pp[len(old_path):]
            node.parent_path = new_pp
            new_node_path = node.path
            if old_node_path in self._path_to_id and self._path_to_id[old_node_path] == node.id:
                del self._path_to_id[old_node_path]
            self._path_to_id[new_node_path] = node.id
            updated += 1
        return updated


class MemoryTreeRepository(TreeRepository):

    def __init__(self) -> None:
        self._store = MemoryNodeStore()
        self._executor = OpExecutor()
        self._locks: Dict[str, asyncio.Lock] = {}

    async def init(self) -> None:
        pass

    async def close(self) -> None:
        pass

    def _get_lock(self, path: str) -> asyncio.Lock:
        if path not in self._locks:
            self._locks[path] = asyncio.Lock()
        return self._locks[path]

    async def get_node(self, path: str) -> Optional[TreeNode]:
        return await self._store.get_node(path)

    async def add_node(self, node: TreeNode) -> str:
        self._store._ensure_root()
        return await apply_add_node(self._store, node)

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
        prefix = path + "." if path != "root" else "root."
        result = []
        seen_paths: set = set()
        for n in self._store.list_nodes():
            if n.status not in statuses:
                continue
            if not n.path.startswith(prefix):
                continue
            parent = path if path != "root" else "root"
            if not is_direct_child(n.path, parent):
                continue
            if n.path in seen_paths:
                continue
            seen_paths.add(n.path)
            result.append(n)
        return sorted(result, key=lambda x: x.path)

    async def list_dirty_categories(self) -> List[TreeNode]:
        result = [
            n for n in self._store.list_nodes()
            if n.node_type == NodeType.CATEGORY and n.is_dirty
            and n.status != NodeStatus.ARCHIVED
        ]
        return result

    async def list_all_categories(self) -> List[TreeNode]:
        return [
            n for n in self._store.list_nodes()
            if n.node_type == NodeType.CATEGORY
            and n.status != NodeStatus.ARCHIVED
        ]

    @asynccontextmanager
    async def lock_and_get_context(self, path: str):
        lock = self._get_lock(path)
        async with lock:
            parent = await self.get_node(path)
            if not parent or parent.node_type != NodeType.CATEGORY:
                yield None
                return

            all_children = await self.list_children(path)
            active = [c for c in all_children if c.status == NodeStatus.ACTIVE]
            pending = [
                c for c in all_children
                if c.status == NodeStatus.PENDING_REVIEW
            ]
            ctx = NodeUpdateContext(
                parent=parent,
                active_nodes=active,
                pending_nodes=pending,
            )
            yield ctx

    async def execute(self, op: NodeUpdateOp, context: NodeUpdateContext) -> None:
        await self._executor.execute(op, self._store, context.parent.path)
