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
        - Category-aware: When a leaf name conflicts with an existing category,
          the leaf is placed inside that category instead of getting a suffix

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

    async def _resolve_leaf_path(
        self,
        parent_path: str,
        name: str,
        uow: UnitOfWork,
        fallback_prefix: str = "leaf",
    ) -> NodePath:
        """
        Resolve the best path for a new leaf node.

        If the preferred path points to an existing CATEGORY, the leaf will be
        placed inside that category. Otherwise, uses ensure_unique_path to
        avoid conflicts with existing leaves.

        Also checks against paths used within the current batch to prevent
        UNIQUE constraint violations on commit.

        Args:
            parent_path: Path of the parent category.
            name: Preferred name for the leaf.
            uow: UnitOfWork for database queries.
            fallback_prefix: Prefix to use if name is invalid.

        Returns:
            The resolved path for the new leaf.
        """
        slug_name = _slug(name) or f"{fallback_prefix}_{uuid4().hex[:6]}"
        preferred = NodePath(parent_path).child(slug_name)

        # Check if preferred path is an existing CATEGORY
        existing = await uow.nodes.get_by_path(str(preferred))
        if existing and existing.node_type == NodeType.CATEGORY:
            # Place leaf inside the category instead of alongside it
            logger.info(
                "[Executor] Path %s is a CATEGORY, placing leaf inside it",
                preferred)
            existing.request_semantic_rethink()
            uow.register_dirty(existing)
            child_path = preferred.child(
                f"{fallback_prefix}_{uuid4().hex[:6]}")
            final_path = await uow.nodes.ensure_unique_path(child_path)
        else:
            # Normal case: ensure unique path at the same level
            final_path = await uow.nodes.ensure_unique_path(preferred)

        # Check against batch-local used paths and add suffix if needed
        final_path_str = str(final_path)
        if final_path_str in self._used_paths:
            # Path already used in this batch, add unique suffix
            suffix = 1
            while True:
                new_path = NodePath(parent_path).child(f"{slug_name}{suffix}")
                new_path_str = str(new_path)
                if new_path_str not in self._used_paths:
                    # Also check DB for this new path
                    final_path = await uow.nodes.ensure_unique_path(new_path)
                    final_path_str = str(final_path)
                    if final_path_str not in self._used_paths:
                        break
                suffix += 1

        # Register this path as used in current batch
        self._used_paths.add(final_path_str)
        return final_path

    async def execute(
        self,
        plan: RebalancePlan,
        context: UpdateContext,
        uow: UnitOfWork,
        max_children: int = 10,
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
            max_children: Maximum allowed children per category. Used to
                mark new categories as dirty if they exceed this limit.

        Raises:
            PlanExecutionError: If an operation fails irrecoverably.
        """
        self._max_children = max_children
        # Track paths used within this batch to prevent UNIQUE constraint violations
        self._used_paths: set[str] = set()

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
                        logger.warning(
                            "[Executor] Unknown Op type: %s, skipping",
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
        If the target name conflicts with an existing CATEGORY, the merged
        leaf is placed inside that category.

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
                logger.warning(
                    "[Executor] MERGE: id=%s not in context, skipping", nid)
                continue
            if node.node_type != NodeType.LEAF:
                logger.warning(
                    "[Executor] MERGE: id=%s is CATEGORY, cannot merge, skipping",
                    nid)
                continue
            # Archive the original node
            node.archive()
            uow.register_dirty(node)
            valid_nodes.append(node)

        if not valid_nodes:
            logger.warning(
                "[Executor] MERGE: No valid leaf nodes, skipping entire MergeOp"
            )
            return

        # Create new merged leaf (category-aware path resolution)
        safe_path = await self._resolve_leaf_path(parent_path_str,
                                                  op.name,
                                                  uow,
                                                  fallback_prefix="merged")

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

    async def _ensure_category_chain(
        self,
        parent_path: str,
        name_parts: list[str],
        content: str,
        uow: UnitOfWork,
    ) -> tuple[NodePath, Optional[TreeNode]]:
        """
        Ensure a chain of categories exists, creating them if needed.

        When name contains underscores (e.g., "tech_advice_group"), this creates
        a hierarchy: parent_path.tech.advice.group

        Args:
            parent_path: Starting parent path.
            name_parts: List of path segments (split by underscore).
            content: Content for the leaf category.
            uow: UnitOfWork for registering changes.

        Returns:
            Tuple of (final_path, leaf_category_node or None if existing).
        """
        current_path = parent_path
        leaf_cat: Optional[TreeNode] = None

        for i, part in enumerate(name_parts):
            is_leaf = (i == len(name_parts) - 1)
            cat_path = NodePath(current_path).child(part)
            cat_path_str = str(cat_path)

            existing = await uow.nodes.get_by_path(cat_path_str)

            if existing and existing.node_type == NodeType.CATEGORY:
                # Category exists, use it
                if is_leaf:
                    existing.request_semantic_rethink()
                    uow.register_dirty(existing)
                    leaf_cat = existing
                current_path = cat_path_str
            elif cat_path_str in self._used_paths:
                # Created in this batch
                current_path = cat_path_str
                # leaf_cat stays None for batch-created categories
            else:
                # Create new category
                self._used_paths.add(cat_path_str)
                new_cat = TreeNode.new_category(
                    path=cat_path,
                    content=content if is_leaf else f"Category: {part}",
                    display_name=part,
                    status=NodeStatus.ACTIVE,
                    name_editable=True,
                )
                uow.register_new(new_cat)
                if is_leaf:
                    leaf_cat = new_cat
                current_path = cat_path_str
                logger.debug("[Executor] Created category: %s", cat_path_str)

        return NodePath(current_path), leaf_cat

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

        When name contains dots (e.g., "tech.advice"), it creates
        a hierarchy: parent.tech.advice

        Args:
            op: The GroupOp to execute.
            context: Current context snapshot.
            uow: UnitOfWork for registering changes.
            resolve: Function to resolve node IDs.
        """
        parent_path = context.parent.path

        # Parse name: split by dot to create hierarchy
        # e.g., "tech.advice.group" -> ["tech", "advice", "group"]
        raw_name = op.name.strip().lower()
        # Split by dot (primary) or underscore (fallback for compatibility)
        import re
        # Replace underscores with dots for backward compatibility
        raw_name = raw_name.replace("_", ".")
        name_parts = [
            re.sub(r"[^a-z0-9]", "", part) for part in raw_name.split(".")
            if part
        ]
        name_parts = [p for p in name_parts if p]

        if not name_parts:
            logger.warning("[Executor] GROUP: Invalid name '%s', skipping",
                           op.name)
            return

        # Strip leading parts that duplicate parent path segments
        # e.g., if parent is "root.work.guidelines" and name is "guidelines.api",
        # we should use just "api" to avoid "root.work.guidelines.guidelines.api"
        parent_parts = parent_path.split(".")
        while name_parts and name_parts[0] in parent_parts:
            removed = name_parts.pop(0)
            logger.debug(
                "[Executor] GROUP: Stripped duplicate segment '%s' from name",
                removed)

        if not name_parts:
            logger.warning(
                "[Executor] GROUP: Name '%s' only contains parent path segments, skipping",
                op.name)
            return

        # Create category chain and get the leaf category
        safe_cat_path, target_cat = await self._ensure_category_chain(
            parent_path, name_parts, op.content, uow)

        moved_count = 0

        # Move each leaf into the new/existing category
        for i, nid in enumerate(op.ids):
            node = resolve(nid)

            if not node or node.node_type != NodeType.LEAF:
                logger.warning(
                    "[Executor] GROUP: id=%s invalid or not leaf, skipping",
                    nid)
                continue
            # Archive original
            node.archive()
            uow.register_dirty(node)

            # Create copy under new category with unique path
            child_name = f"leaf_{uuid4().hex[:6]}"
            child_path = safe_cat_path.child(child_name)
            child_path_str = str(child_path)

            # Check batch-local used paths
            if child_path_str in self._used_paths:
                suffix = 1
                while True:
                    new_child_path = safe_cat_path.child(
                        f"{child_name}{suffix}")
                    new_child_path_str = str(new_child_path)
                    if new_child_path_str not in self._used_paths:
                        child_path = new_child_path
                        child_path_str = new_child_path_str
                        break
                    suffix += 1

            safe_child = await uow.nodes.ensure_unique_path(child_path)
            safe_child_str = str(safe_child)
            self._used_paths.add(safe_child_str)

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

        # Check if new category exceeds max_children limit
        # If so, mark it as dirty for further reorganization
        if moved_count > self._max_children and target_cat is not None:
            target_cat.request_semantic_rethink()
            uow.register_dirty(target_cat)
            logger.info(
                "[Executor] GROUP: Category %s has %d nodes (> %d), marked dirty for further reorg",
                target_cat.path, moved_count, self._max_children)

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
            logger.warning(
                "[Executor] MOVE: Source id=%s invalid or not leaf, skipping",
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

        # Create new leaf at target (category-aware path resolution)
        safe_path = await self._resolve_leaf_path(op.path_to_move,
                                                  op.name,
                                                  uow,
                                                  fallback_prefix="moved")

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
            logger.warning("[Executor] PERSIST: id=%s not found, skipping",
                           op.ids[0])
            return

        # Archive original fragment
        node.archive()
        uow.register_dirty(node)

        # Create active leaf (category-aware path resolution)
        safe_path = await self._resolve_leaf_path(context.parent.path,
                                                  op.name,
                                                  uow,
                                                  fallback_prefix="leaf")
        payload = dict(op.payload)

        new_leaf = TreeNode.new_leaf(
            path=safe_path,
            content=op.content,
            payload=payload,
            status=NodeStatus.ACTIVE,
        )
        uow.register_new(new_leaf)

        logger.debug("[Executor] PERSIST: %s -> %s", node.path, safe_path)
