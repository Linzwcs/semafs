"""
Plan Executor: Applies RebalancePlan operations to the knowledge tree.

This module contains the Executor class which executes reorganization
operations (MERGE, GROUP, MOVE, PERSIST) on the knowledge tree.

Design Principles:
    1. Zero SQL: All changes go through UnitOfWork registration
    2. Context-based lookup: Uses snapshot, not real-time DB reads
    3. Graceful failure: Invalid IDs are skipped, not fatal errors
    4. Caller-controlled transactions: Executor never commits

The Executor is deliberately "dumb" - it executes what the Strategy decides.
It doesn't make semantic decisions, only applies the plan faithfully.

Usage:
    executor = Executor()
    await executor.execute(plan, context, uow)
    await uow.commit()  # Caller controls commit
"""
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
    """
    Convert a string to a valid path segment slug.

    Normalizes the input to lowercase, replaces spaces with underscores,
    and removes any characters that aren't alphanumeric or underscores.

    Args:
        s: Input string to convert.
        max_len: Maximum length of the resulting slug.

    Returns:
        Normalized slug string, or None if input is empty or non-ASCII.
    """
    import re
    if not s or not s.strip().isascii():
        return None
    normalized = re.sub(r"[^a-z0-9_]", "",
                        s.strip().lower().replace(" ", "_")).strip("_")

    return normalized[:max_len] if normalized else None


class Executor:
    """
    Executes RebalancePlan operations on the knowledge tree.

    The Executor applies a sequence of operations (MERGE, GROUP, MOVE, PERSIST)
    to reorganize a category's contents. All changes are registered with the
    UnitOfWork but never committed - the caller controls transaction boundaries.

    Key Design Decisions:
        - Zero SQL: All mutations via register_new/register_dirty
        - Snapshot-based: Uses context snapshot, not live DB queries
        - LLM-tolerant: Invalid IDs from LLM hallucinations are skipped
        - Supports short IDs: Matches both full UUIDs and 8-char prefixes

    Error Handling:
        - Invalid node IDs: Logged as warning, operation skipped
        - Wrong node type: Logged as warning, operation skipped
        - Other errors: Wrapped in PlanExecutionError with op index

    Usage:
        executor = Executor()
        try:
            await executor.execute(plan, context, uow)
            await uow.commit()
        except PlanExecutionError as e:
            await uow.rollback()
            logger.error(f"Failed at op #{e.op_index}")
    """

    async def execute(
        self,
        plan: RebalancePlan,
        context: UpdateContext,
        uow: UnitOfWork,
    ) -> None:
        """
        Execute a reorganization plan.

        Processes operations sequentially, updates the parent category
        with new content/name, and optionally marks grandparent dirty
        for "semantic floating" (propagating changes upward).

        Args:
            plan: The RebalancePlan containing operations to execute.
            context: Snapshot of category state (used for node lookup).
            uow: UnitOfWork for registering changes (caller commits).

        Raises:
            PlanExecutionError: If an operation fails irrecoverably.
        """
        logger.debug(
            "[Executor] Starting plan execution: %s | parent=%s",
            plan.ops_summary,
            context.parent.path,
        )

        # Build ID lookup indexes for both full and short IDs
        id_index: dict[str, TreeNode] = {n.id: n for n in context.all_nodes}
        short_id_index: dict[str, TreeNode] = {
            n.id[:8]: n
            for n in context.all_nodes if n.id[:8] not in id_index
        }

        def resolve(node_id: str) -> Optional[TreeNode]:
            """Resolve a node ID (full or 8-char short) to TreeNode."""
            return id_index.get(node_id) or short_id_index.get(node_id[:8])

        # Execute each operation sequentially
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
                        logger.warning("[Executor] Unknown Op type: %s, skipping",
                                       type(op))
            except Exception as exc:
                raise PlanExecutionError(str(exc), op_index=i) from exc

        # Apply plan results to parent category
        parent = context.parent
        old_path = parent.apply_plan_result(plan.updated_content,
                                            plan.updated_name)
        uow.register_dirty(parent)

        # Handle cascade rename if parent was renamed
        if old_path:
            new_path = parent.path
            uow.register_cascade_rename(old_path, new_path)
            logger.info("[Executor] Triggering cascade rename: %s -> %s",
                        old_path, new_path)

        # "Semantic floating": Mark grandparent dirty if needed
        if not parent.node_path.is_root and plan.should_dirty_parent:
            grandparent_path = parent.node_path.parent
            grandparent = await uow.nodes.get_by_path(str(grandparent_path))
            if grandparent:
                grandparent.request_semantic_rethink()
                uow.register_dirty(grandparent)
                logger.info(
                    "[Executor] Semantic float: marking parent '%s' dirty with force_llm",
                    grandparent.path)

        logger.debug(
            "[Executor] Plan execution complete: %s | parent=%s is_dirty=%s",
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
        Execute MERGE operation: Archive old leaves, create merged leaf.

        The parent path is derived from the context (all merges stay in
        the same directory). Content and name come entirely from the LLM.

        Args:
            op: The MergeOp to execute.
            context: Current context snapshot.
            uow: UnitOfWork for registering changes.
            resolve: Function to resolve node IDs.
        """
        parent_path_str = context.parent.path
        valid_nodes = []

        for nid in op.ids:
            node = resolve(nid)
            if not node:
                logger.warning("[Executor] MERGE: id=%s not in context, skipping", nid)
                continue
            if node.node_type != NodeType.LEAF:
                logger.warning(
                    "[Executor] MERGE: id=%s is CATEGORY, cannot merge, skipping", nid)
                continue
            # Archive the original node
            node.archive()
            uow.register_dirty(node)
            valid_nodes.append(node)

        if not valid_nodes:
            logger.warning("[Executor] MERGE: No valid leaf nodes, skipping entire MergeOp")
            return

        # Create new merged leaf
        name = _slug(op.name) or f"merged_{uuid4().hex[:6]}"
        preferred = NodePath(parent_path_str).child(name)
        safe_path = await uow.nodes.ensure_unique_path(preferred)

        new_leaf = TreeNode.new_leaf(
            path=safe_path,
            content=op.content,  # LLM-decided content, use as-is
            payload={
                "_merged": True,
                "_merged_from": [n.id for n in valid_nodes]
            },
            status=NodeStatus.ACTIVE,
        )
        uow.register_new(new_leaf)

        logger.debug(
            "[Executor] MERGE: Archived %d nodes -> new node %s",
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
        Execute GROUP operation: Create new category, move leaves into it.

        Original leaves are archived and recreated under the new category.
        If the target category already exists, leaves are merged into it.

        Args:
            op: The GroupOp to execute.
            context: Current context snapshot.
            uow: UnitOfWork for registering changes.
            resolve: Function to resolve node IDs.
        """
        parent_path = context.parent.path
        name = _slug(op.name)
        if not name:
            logger.warning("[Executor] GROUP: Invalid name, skipping")
            return

        cat_path = NodePath(parent_path).child(name)
        existing_cat = await uow.nodes.get_by_path(str(cat_path))

        # Handle existing category (seamless merge)
        if existing_cat and existing_cat.node_type == NodeType.CATEGORY:
            logger.info(f"Target directory {cat_path} exists, merging into it...")
            safe_cat_path = NodePath(existing_cat.path)
            existing_cat.request_semantic_rethink()
            uow.register_dirty(existing_cat)
        else:
            # Create new category
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

        # Move each leaf into the new/existing category
        for i, nid in enumerate(op.ids):
            node = resolve(nid)

            if not node or node.node_type != NodeType.LEAF:
                logger.warning("[Executor] GROUP: id=%s invalid or not leaf, skipping", nid)
                continue
            # Archive original
            node.archive()
            uow.register_dirty(node)

            # Create copy under new category
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
            "[Executor] GROUP: Created CATEGORY %s, moved %d leaves",
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
        Execute MOVE operation: Relocate leaf to existing category.

        The target path must exist and be a CATEGORY. If it doesn't exist,
        the operation is skipped (prevents LLM path fabrication).

        Args:
            op: The MoveOp to execute.
            context: Current context snapshot.
            uow: UnitOfWork for registering changes.
            resolve: Function to resolve node IDs.
        """
        node = resolve(op.ids[0])
        if not node or node.node_type != NodeType.LEAF:
            logger.warning("[Executor] MOVE: Source id=%s invalid or not leaf, skipping",
                           op.ids[0])
            return

        # Verify target exists and is a category
        target = await uow.nodes.get_by_path(op.path_to_move)
        if not target or target.node_type != NodeType.CATEGORY:
            logger.warning(
                "[Executor] MOVE: Target path '%s' doesn't exist or not CATEGORY, skipping",
                op.path_to_move,
            )
            return

        # Archive original
        node.archive()
        uow.register_dirty(node)

        # Create new leaf at target
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
            "[Executor] MOVE: %s -> %s",
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
        """
        Execute PERSIST operation: Convert pending fragment to active leaf.

        This is used by rule-based strategies to promote PENDING_REVIEW
        fragments without semantic reorganization.

        Args:
            op: The PersistOp to execute.
            context: Current context snapshot.
            uow: UnitOfWork for registering changes.
            resolve: Function to resolve node IDs.
        """
        node = resolve(op.ids[0])
        if not node:
            logger.warning("[Executor] PERSIST: id=%s not found, skipping", op.ids[0])
            return

        # Archive original fragment
        node.archive()
        uow.register_dirty(node)

        # Create active leaf
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

        logger.debug("[Executor] PERSIST: %s -> %s", node.path, safe_path)
