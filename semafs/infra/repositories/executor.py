from __future__ import annotations
import logging
import os
from typing import List, Optional
from uuid import uuid4
from ...models.enums import NodeStatus, NodeType, OpType
from ...models.nodes import TreeNode
from ...models.ops import MergeOp, MoveOp, NodeUpdateOp, SplitOp
from ...utils import (
    derive_category_content_from_children,
    path_to_parent_and_segment,
    sanitize_llm_name,
    sanitize_path,
    slug_from_uuid,
)
from .protocol import NodeStore

logger = logging.getLogger(__name__)

_DEBUG_OPS = os.environ.get("SEMAFS_DEBUG_OPS", "1") in ("1", "true", "yes")

# 通用占位符；LLM 在 op 生成时会配套提供语义化 name/path，此处 fallback 仅用于 Rule 策略
_GENERIC_NAMES = frozenset({"split", "item", ""})


def _split_payload(payload: dict) -> dict:
    p = dict(payload) if payload else {}
    p["_split"] = True
    return p


async def apply_add_node(
    store: NodeStore,
    node: TreeNode,
) -> str:
    """
    添加节点：save_raw + PENDING_REVIEW 触发的父目录 is_dirty 等副作用。
    TreeRepository.add_node 与 OpExecutor 共用此逻辑。
    """
    logger.debug(
        "[DB] 插入节点: path=%s id=%s type=%s status=%s parent=%s",
        node.path,
        node.id,
        node.node_type.value,
        node.status.value,
        node.parent_path,
    )
    await store.save_raw(node)
    if node.status == NodeStatus.PENDING_REVIEW and node.parent_path:
        parent = await store.get_node(node.parent_path)
        if parent and parent.node_type == NodeType.CATEGORY:
            parent.is_dirty = True
            parent.bump_version()
            logger.debug(
                "[DB] 更新父目录: path=%s is_dirty=True version=%s",
                parent.path,
                parent.version,
            )
            await store.save_raw(parent)
    return node.id


class OpExecutor:

    async def execute(self, op: NodeUpdateOp, store: NodeStore) -> None:

        parent_path: Optional[str] = None
        ids_to_archive: List[str] = []

        for sub_op in op.ops:
            ids_to_archive.extend(sub_op.ids)

        logger.debug("[Op] NodeUpdateOp 开始执行: %s", op.ops_summary)
        if _DEBUG_OPS:
            print(
                f"\n[Op Exec] NodeUpdateOp 开始: {op.ops_summary} | reasoning={op.overall_reasoning[:50]}..."
            )

        # ids 仅应包含叶子节点，跳过非叶子
        archived = []
        for nid in ids_to_archive:
            node = await store.get_raw(nid)
            if node and node.node_type == NodeType.LEAF:
                if parent_path is None:
                    parent_path = node.parent_path
                node.status = NodeStatus.ARCHIVED
                archived.append(f"{nid[:8]}:{node.path}")
                logger.debug(
                    "[DB] ARCHIVE: id=%s path=%s -> status=ARCHIVED",
                    nid,
                    node.path,
                )
                await store.save_raw(node)
            elif node and node.node_type != NodeType.LEAF:
                logger.debug("[Op] 跳过非叶子节点 id=%s type=%s", nid,
                             node.node_type.value)
            elif not node:
                if _DEBUG_OPS:
                    print(f"  [Op Exec] 警告: id={nid} 节点不存在，跳过")
        if _DEBUG_OPS and archived:
            print(
                f"  [Op Exec] ARCHIVED {len(archived)} 个叶子: {archived[:5]}{'...' if len(archived) > 5 else ''}"
            )

        for i, sub_op in enumerate(op.ops):
            logger.debug("[Op] 执行 #%d: %s ids=%s", i + 1, sub_op.op_type.value,
                         sub_op.ids)
            if sub_op.op_type == OpType.MERGE:
                new_path = await self._execute_merge(sub_op,
                                                     op.updated_content, store)
                if _DEBUG_OPS:
                    print(
                        f"  [Op Exec] MERGE ids={sub_op.ids} -> new_path={new_path or '(失败)'}"
                    )
            elif sub_op.op_type == OpType.SPLIT:
                ok = await self._execute_split(sub_op, op.updated_content,
                                               store, parent_path)
                if _DEBUG_OPS:
                    print(
                        f"  [Op Exec] SPLIT ids={sub_op.ids} name={getattr(sub_op, 'name', '')} -> ok={ok}"
                    )
            elif sub_op.op_type == OpType.MOVE:
                new_path = await self._execute_move(sub_op, store)
                if _DEBUG_OPS:
                    print(
                        f"  [Op Exec] MOVE ids={sub_op.ids} path_to_move={getattr(sub_op, 'path_to_move', '')} -> new_path={new_path or '(失败)'}"
                    )

        if parent_path:
            parent = await store.get_node(parent_path)
            if parent:
                parent.content = op.updated_content
                if op.updated_name is not None:
                    parent.display_name = op.updated_name
                parent.is_dirty = False
                parent.bump_version()
                logger.debug(
                    "[DB] 更新父目录: path=%s content_len=%d is_dirty=False",
                    parent.path,
                    len(op.updated_content),
                )
                await store.save_raw(parent)
                if _DEBUG_OPS:
                    print(
                        f"  [Op Exec] 更新父目录 {parent_path}: content_len={len(op.updated_content)} is_dirty=False"
                    )
            elif _DEBUG_OPS:
                print(f"  [Op Exec] 警告: parent_path={parent_path} 不存在，无法更新父目录")

    async def _execute_merge(self, merge_op: MergeOp, fallback_content: str,
                             store: NodeStore) -> Optional[str]:

        content = merge_op.content or fallback_content

        first = await store.get_raw(merge_op.ids[0]) if merge_op.ids else None
        pdir = first.parent_path if first else "root"
        raw_name = (merge_op.name or "").strip()
        name = sanitize_llm_name(raw_name) if raw_name else None
        if not name:
            name = slug_from_uuid(str(uuid4()))
        new_path = await self._unique_path(store, f"{pdir}.{name}")
        pp, seg = path_to_parent_and_segment(new_path)
        new_node = TreeNode(
            parent_path=pp,
            name=seg,
            node_type=NodeType.LEAF,
            content=content,
            payload={"_merged": True},
        )

        logger.debug("[DB] MERGE 新建: path=%s (合并 ids=%s)", new_path,
                     merge_op.ids)
        await apply_add_node(store, new_node)
        return new_path

    async def _execute_split(
        self,
        split_op: SplitOp,
        fallback_content: str,
        store: NodeStore,
        parent_path: Optional[str] = None,
    ) -> bool:
        """创建子树：父路径由执行上下文 parent_path 决定，完整路径=parent_path.name。
        SPLIT 至少需要 2 个叶子。"""
        if not split_op.ids or len(split_op.ids) < 2:
            return False

        raw_name = (split_op.name or "").strip()
        name = sanitize_llm_name(raw_name) if raw_name else None
        if not name:
            return False

        if not parent_path:
            first = await store.get_raw(split_op.ids[0])
            parent_path = first.parent_path if first else "root"

        target_path = f"{parent_path}.{name}"

        # 确保父 category 链存在
        await self._ensure_category_path(store, target_path, name)

        target = await store.get_node(target_path)
        if not target or target.node_type != NodeType.CATEGORY:
            return False

        moved_children: List[TreeNode] = []
        for nid in split_op.ids:
            node = await store.get_raw(nid)
            if not node or node.node_type != NodeType.LEAF:
                continue
            base = f"{target_path}.item"
            new_path = await self._unique_path(store, base)
            pp, seg = path_to_parent_and_segment(new_path)
            new_node = TreeNode(
                parent_path=pp,
                name=seg,
                node_type=NodeType.LEAF,
                content=node.content,
                payload={**_split_payload(node.payload)},
            )
            await apply_add_node(store, new_node)
            moved_children.append(new_node)
            logger.debug(
                "[DB] SPLIT 移入: %s -> %s (ids=%s)",
                node.path,
                new_path,
                split_op.ids,
            )

        # category content 与展示名：优先用 LLM 提供的语义浓缩，否则从子节点机械推导
        if moved_children:
            target.content = (
                split_op.content.strip()
                if split_op.content and split_op.content.strip() else
                derive_category_content_from_children(moved_children))
            target.display_name = raw_name  # 展示名供 MOVE 按 display_name 解析
            target.bump_version()
            await store.save_raw(target)
        return len(moved_children) > 0

    async def _ensure_category_path(self, store: NodeStore, full_path: str,
                                    leaf_name: str) -> None:
        """确保 category 路径存在，缺失的父节点按路径段创建。"""
        parts = full_path.split(".")
        if not parts or parts[0] != "root":
            return
        # 逐段确保父链存在
        for i in range(1, len(parts)):
            seg_path = ".".join(parts[:i + 1])
            existing = await store.get_node(seg_path)
            if existing:
                continue
            parent_path = ".".join(parts[:i]) if i > 0 else "root"
            parent = await store.get_node(parent_path)
            if not parent or parent.node_type != NodeType.CATEGORY:
                return
            pp = "" if parts[i] == "root" else ".".join(parts[:i])
            seg = parts[i]  # name=路径段
            cat = TreeNode(
                parent_path=pp,
                name=seg,
                node_type=NodeType.CATEGORY,
                content="",
            )
            await store.save_raw(cat)
            logger.debug("[DB] SPLIT 新建 category: %s", seg_path)

    async def _execute_move(self, move_op: MoveOp,
                            store: NodeStore) -> Optional[str]:
        """path_to_move 为目标 category 路径，必须已存在才移入。一次仅移动一个节点。"""
        if not move_op.ids:
            return None
        if len(move_op.ids) > 1:
            logger.debug("[Op] MOVE 一次仅移动一个节点，忽略多余 ids: %s", move_op.ids[1:])

        first = await store.get_raw(move_op.ids[0])
        if not first:
            return None

        raw_target = (move_op.path_to_move or "").strip()
        if not raw_target:
            return None
        target_path = sanitize_path(raw_target)

        target = await store.get_node(target_path)
        if not target or target.node_type != NodeType.CATEGORY:
            # LLM 可能返回展示名而非 path，尝试按 name 解析
            target = await store.get_category_by_name(
                target_path, prefer_under_parent=first.parent_path)
        if not target or target.node_type != NodeType.CATEGORY:
            if _DEBUG_OPS:
                print(
                    f"  [Op Exec] MOVE 失败: target_path={target_path} 不存在或非 category"
                )
            return None
        target_path = target.path

        raw_name = (move_op.name or "").strip()
        name = sanitize_llm_name(raw_name) if raw_name else None
        if not name:
            name = slug_from_uuid(str(uuid4()))
        new_path = await self._unique_path(store, f"{target_path}.{name}")
        pp, seg = path_to_parent_and_segment(new_path)
        payload = dict(first.payload) if first.payload else {}
        if not payload:
            payload["_moved"] = True
        new_node = TreeNode(
            parent_path=pp,
            name=seg,
            node_type=NodeType.LEAF,
            content=first.content,
            payload=payload,
        )

        logger.debug(
            "[DB] MOVE 新建: path=%s (从 %s 移入 target=%s)",
            new_path,
            first.path,
            target_path,
        )
        await apply_add_node(store, new_node)
        return new_path

    async def _unique_path(self, store: NodeStore, base: str) -> str:
        path, idx = base, 0
        while await store.path_exists(path):
            idx += 1
            path = f"{base}_{idx}"
        return path
