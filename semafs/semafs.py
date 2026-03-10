"""
SemaFS: Main facade for the semantic filesystem.

This module provides the primary API for interacting with the SemaFS
knowledge tree. It coordinates between the storage layer, strategy layer,
and executor to provide a clean, high-level interface.

Core Operations:
    - write(): Add new knowledge fragments to the tree
    - read(): Get a single node with navigation context
    - list(): List direct children of a category
    - view_tree(): Get recursive tree structure
    - get_related(): Get navigation map around a node
    - stats(): Get knowledge base statistics
    - maintain(): Process dirty categories and reorganize

Architecture:
    SemaFS acts as an application service (facade pattern), coordinating:
    - UoWFactory: Transaction management and storage access
    - Strategy: Reorganization decision-making
    - Executor: Plan execution

Usage:
    from semafs import SemaFS
    from semafs.storage.sqlite import SQLiteUoWFactory
    from semafs.strategies.rule import RuleOnlyStrategy

    factory = SQLiteUoWFactory("knowledge.db")
    await factory.init()

    semafs = SemaFS(factory, RuleOnlyStrategy())

    # Write a knowledge fragment
    frag_id = await semafs.write("root.work", "Meeting notes...", {})

    # Process pending fragments
    await semafs.maintain()

    # Read back
    view = await semafs.read("root.work")
"""
from __future__ import annotations
import asyncio
import logging
import re
from typing import List, Optional
from .core.enums import NodeType, NodeStatus
from .core.exceptions import NodeNotFoundError, PlanExecutionError
from .core.node import TreeNode, NodePath
from .core.ops import UpdateContext
from .core.views import (
    NodeView,
    TreeView,
    RelatedNodes,
    StatsView,
)
from .ports.strategy import Strategy
from .ports.factory import UoWFactory
from .executor import Executor

logger = logging.getLogger(__name__)


class SemaFS:
    """
    Main facade for the semantic filesystem.

    SemaFS provides the primary API for knowledge management operations.
    It coordinates storage, strategy, and execution to maintain a
    well-organized knowledge tree.

    The lifecycle is:
        1. write() - Add fragments (creates PENDING_REVIEW nodes)
        2. maintain() - Process dirty categories (reorganizes tree)
        3. read()/list()/view_tree() - Query the organized knowledge

    Attributes:
        db_name: Identifier for logging (useful in multi-db scenarios).

    Configuration:
        max_children: Threshold for triggering LLM reorganization.

    Thread Safety:
        SemaFS uses async/await and is safe for concurrent operations
        within a single event loop. Transaction isolation is handled
        by the UoWFactory.

    Example:
        semafs = SemaFS(factory, strategy, max_children=10)
        await semafs.write("root.work", "New project idea", {"priority": "high"})
        await semafs.maintain()
        tree = await semafs.view_tree("root")
    """

    def __init__(self,
                 uow_factory: UoWFactory,
                 strategy: Strategy,
                 executor: Optional[Executor] = None,
                 max_children: int = 10,
                 db_name: str = "default") -> None:
        """
        Initialize SemaFS.

        Args:
            uow_factory: Factory for creating Unit of Work instances.
            strategy: Strategy for reorganization decisions.
            executor: Executor for plan execution (default: new Executor()).
            max_children: Max children before triggering reorganization.
            db_name: Identifier for logging purposes.
        """
        self._uow_factory = uow_factory
        self._strategy = strategy
        self._executor = executor or Executor()
        self._max_children = max_children
        self.db_name = db_name

    async def write(self, path: str, content: str, payload: dict) -> str:
        """
        Write a knowledge fragment to the tree.

        Creates a PENDING_REVIEW fragment under the specified category.
        The parent category is marked dirty, triggering reorganization
        on the next maintain() call.

        Args:
            path: Target category path (will be resolved/created).
            content: Text content of the fragment.
            payload: Metadata dict (JSON-serializable).

        Returns:
            The UUID of the created fragment.

        Raises:
            NodeNotFoundError: If the resolved path is not a category.
        """
        resolved = await self._resolve_category(path)
        fragment = TreeNode.new_fragment(parent_path=NodePath(resolved),
                                         content=content,
                                         payload=payload)

        async with self._uow_factory.begin() as uow:
            parent = await uow.nodes.get_by_path(resolved)
            if not parent or parent.node_type != NodeType.CATEGORY:
                raise NodeNotFoundError(resolved)
            parent.receive_fragment()
            uow.register_dirty(parent)
            uow.register_new(fragment)
            await uow.commit()

        logger.info("[%s] Wrote fragment -> '%s' (id=%s)", self.db_name,
                    fragment.path, fragment.id[:8])
        return fragment.id

    async def read(self, path: str) -> Optional[NodeView]:
        """
        Get a single node with navigation context.

        Returns a NodeView containing the node plus contextual information
        like breadcrumbs, child count, and sibling count.

        Args:
            path: Full path to the node.

        Returns:
            NodeView if found, None if node doesn't exist.
        """
        node = await self._uow_factory.repo.get_by_path(path)
        if not node:
            return None

        # Parallel fetch of context information
        children, siblings, ancestors = await asyncio.gather(
            self._uow_factory.repo.list_children(path,
                                                 statuses=[NodeStatus.ACTIVE]),
            self._uow_factory.repo.list_sibling_categories(path),
            self._uow_factory.repo.get_ancestor_categories(path),
        )

        breadcrumb = tuple(a.path for a in reversed(ancestors)) + (path, )

        return NodeView(
            node=node,
            breadcrumb=breadcrumb,
            child_count=len(children),
            sibling_count=len(siblings),
        )

    async def list(self,
                   path: str,
                   include_archived: bool = False) -> List[NodeView]:
        """
        List direct children of a category.

        Returns NodeViews for each child, sorted by path. Does not
        recurse into subcategories.

        Args:
            path: Category path to list.
            include_archived: Whether to include ARCHIVED nodes.

        Returns:
            List of NodeViews for direct children, sorted by path.
        """
        statuses = [NodeStatus.ACTIVE, NodeStatus.PENDING_REVIEW]
        if include_archived:
            statuses.append(NodeStatus.ARCHIVED)

        children = await self._uow_factory.repo.list_children(path, statuses)

        views = []
        for child in children:
            child_count = 0
            if child.node_type == NodeType.CATEGORY:
                grandchildren = await self._uow_factory.repo.list_children(
                    child.path, statuses=[NodeStatus.ACTIVE])
                child_count = len(grandchildren)

            siblings = await self._uow_factory.repo.list_sibling_categories(
                child.path)
            ancestors = await self._uow_factory.repo.get_ancestor_categories(
                child.path)
            breadcrumb = tuple(a.path
                               for a in reversed(ancestors)) + (child.path, )

            views.append(
                NodeView(
                    node=child,
                    breadcrumb=breadcrumb,
                    child_count=child_count,
                    sibling_count=len(siblings),
                ))

        return sorted(views, key=lambda v: v.path)

    async def view_tree(self,
                        path: str = "root",
                        max_depth: int = 3) -> Optional[TreeView]:
        """
        Get recursive tree structure.

        Returns a TreeView containing the node and all descendants
        up to the specified depth.

        Args:
            path: Root path for the subtree.
            max_depth: Maximum recursion depth (prevents deep trees).

        Returns:
            TreeView if root exists, None otherwise.
        """
        node = await self._uow_factory.repo.get_by_path(path)
        if not node:
            return None

        return await self._build_tree_view(node, depth=0, max_depth=max_depth)

    async def _build_tree_view(self, node: TreeNode, depth: int,
                               max_depth: int) -> TreeView:
        """Recursively build TreeView structure."""
        children_views = ()

        if node.node_type == NodeType.CATEGORY and depth < max_depth:
            children = await self._uow_factory.repo.list_children(
                node.path, statuses=[NodeStatus.ACTIVE])
            children_views = tuple([
                await self._build_tree_view(child, depth + 1, max_depth)
                for child in children
            ])

        return TreeView(node=node, children=children_views, depth=depth)

    async def get_related(self, path: str) -> Optional[RelatedNodes]:
        """
        Get navigation map around a node.

        Returns RelatedNodes containing parent, siblings, children,
        and ancestors - useful for navigation and LLM context.

        Args:
            path: Path of the focal node.

        Returns:
            RelatedNodes if node exists, None otherwise.
        """
        current_view = await self.read(path)
        if not current_view:
            return None

        node = current_view.node
        np = NodePath(path)

        # Parallel fetch of related nodes
        parent_node, sibling_nodes, children_nodes, ancestor_nodes = (
            await asyncio.gather(
                self._uow_factory.repo.get_by_path(str(np.parent))
                if not np.is_root else None,
                self._uow_factory.repo.list_sibling_categories(path),
                self._uow_factory.repo.list_children(
                    path, statuses=[NodeStatus.ACTIVE])
                if node.node_type == NodeType.CATEGORY else [],
                self._uow_factory.repo.get_ancestor_categories(path),
            ))

        # Build NodeViews for each related node
        parent_view = None
        if parent_node:
            parent_view = await self.read(parent_node.path)

        sibling_views = []
        for sib in sibling_nodes:
            view = await self.read(sib.path)
            if view:
                sibling_views.append(view)

        children_views = []
        for child in children_nodes:
            view = await self.read(child.path)
            if view:
                children_views.append(view)

        ancestor_views = []
        for anc in ancestor_nodes:
            view = await self.read(anc.path)
            if view:
                ancestor_views.append(view)

        return RelatedNodes(
            current=current_view,
            parent=parent_view,
            siblings=tuple(sibling_views),
            children=tuple(children_views),
            ancestors=tuple(ancestor_views),
        )

    async def stats(self) -> StatsView:
        """
        Get knowledge base statistics.

        Returns metrics including total nodes, depth, dirty categories,
        and top categories by child count.

        Returns:
            StatsView with comprehensive statistics.
        """
        repo = self._uow_factory.repo

        all_categories = await repo.list_all_categories()
        dirty_categories = await repo.list_dirty_categories()

        total_leaves = 0
        max_depth = 0
        category_child_counts = []

        for cat in all_categories:
            depth = NodePath(cat.path).depth
            max_depth = max(max_depth, depth)

            children = await repo.list_children(cat.path,
                                                statuses=[NodeStatus.ACTIVE])
            leaves = [c for c in children if c.node_type == NodeType.LEAF]
            total_leaves += len(leaves)

            if len(children) > 0:
                category_child_counts.append((cat.path, len(children)))

        top_categories = tuple(
            sorted(category_child_counts, key=lambda x: -x[1])[:10])

        return StatsView(
            total_categories=len(all_categories),
            total_leaves=total_leaves,
            max_depth=max_depth,
            dirty_categories=len(dirty_categories),
            top_categories=top_categories,
        )

    async def maintain(self) -> int:
        """
        Process all dirty categories.

        Fetches categories marked as dirty (needing reorganization),
        processes them deepest-first (leaf-to-root), and applies
        the Strategy's reorganization plan.

        Returns:
            Number of categories successfully processed.
        """
        dirty_cats = await self._uow_factory.repo.list_dirty_categories()
        if not dirty_cats:
            return 0

        # Process deepest categories first (leaf-to-root)
        dirty_cats.sort(key=lambda n: -n.depth)
        processed = 0

        for category in dirty_cats:
            try:
                if await self._maintain_one(category.path):
                    processed += 1
            except Exception as e:
                logger.error("[%s] Maintenance failed for '%s': %s",
                             self.db_name,
                             category.path,
                             e,
                             exc_info=True)
        return processed

    async def _maintain_one(self, path: str) -> bool:
        """
        Maintain a single category.

        Gathers context, calls Strategy for a plan, and executes it.
        Handles status transitions and error recovery.

        Args:
            path: Path of the category to maintain.

        Returns:
            True if maintenance completed, False if skipped/failed.
        """
        async with self._uow_factory.begin() as uow:

            category = await uow.repo.get_by_path(path)
            if not category or category.node_type != NodeType.CATEGORY:
                return False

            # Parallel fetch of all context information
            all_children, siblings, ancestors = await asyncio.gather(
                uow.repo.list_children(
                    path,
                    statuses=[NodeStatus.ACTIVE, NodeStatus.PENDING_REVIEW]),
                uow.repo.list_sibling_categories(path),
                uow.repo.get_ancestor_categories(path, max_depth=3),
            )

            active = tuple(c for c in all_children
                           if c.status == NodeStatus.ACTIVE)
            pending = tuple(c for c in all_children
                            if c.status == NodeStatus.PENDING_REVIEW)

            context = UpdateContext(
                parent=category,
                active_nodes=active,
                pending_nodes=pending,
                sibling_categories=tuple(siblings),
                ancestor_categories=tuple(ancestors),
            )

            # Quick exit if nothing to do
            total_nodes = len(context.all_nodes)
            if not pending and total_nodes <= self._max_children:
                category.clear_dirty()
                uow.register_dirty(category)
                await uow.commit()
                return True

            # Mark nodes as PROCESSING
            category.start_processing()
            uow.register_dirty(category)
            for child in context.all_nodes:
                child.start_processing()
                uow.register_dirty(child)
            await uow.commit()

        # Call Strategy for reorganization plan (outside transaction)
        try:
            plan = await self._strategy.create_plan(context,
                                                    self._max_children)
        except Exception as e:
            logger.warning("[%s] LLM failed for '%s': %s", self.db_name, path,
                           e)
            await self._safe_rollback_processing(path)
            return False

        # No plan needed
        if plan is None:
            await self._finish_processing_without_changes(path)
            return True

        # Execute the plan
        async with self._uow_factory.begin() as uow:
            try:
                await self._executor.execute(plan, context, uow)

                # Finish processing for nodes not covered by ops
                covered_ids = set()
                for op in plan.ops:
                    covered_ids.update(getattr(op, "ids", ()))

                for node in context.all_nodes:
                    if node.id not in covered_ids:
                        node.finish_processing()
                        uow.register_dirty(node)

                context.parent.finish_processing()
                uow.register_dirty(context.parent)

                await uow.commit()

            except PlanExecutionError as e:
                logger.error("[%s] Plan execution failed for '%s': %s",
                             self.db_name, path, e)
                await uow.rollback()
                await self._safe_rollback_processing(path)
                return False
            except Exception as e:
                # Catch commit failures (e.g., IntegrityError) and rollback processing
                logger.error("[%s] Commit failed for '%s': %s",
                             self.db_name, path, e)
                await uow.rollback()
                await self._safe_rollback_processing(path)
                raise

        logger.info("[%s] Maintenance complete for '%s': %s", self.db_name,
                    path, plan.ops_summary)
        return True

    async def _resolve_category(self, path: str) -> str:
        """
        Resolve a path to an existing category.

        Walks up the path hierarchy to find the deepest existing category.
        Falls back to "root" if no category exists.

        Args:
            path: Path to resolve.

        Returns:
            Path to the existing category (may be ancestor of input).
        """
        clean = re.sub(r"[^a-z0-9._]", "", path.lower()).strip(".")
        parts = clean.split(".") if clean else []
        while parts:
            candidate = ".".join(parts)
            node = await self._uow_factory.repo.get_by_path(candidate)
            if node and node.node_type == NodeType.CATEGORY:
                return candidate
            parts.pop()
        return "root"

    async def _safe_rollback_processing(self, path: str) -> None:
        """
        Safely rollback PROCESSING status, logging errors instead of raising.

        This wrapper ensures that rollback failures don't mask the original error.
        Failed rollbacks will be recovered on next startup via _recover_processing_nodes.

        Args:
            path: Path of the category that failed.
        """
        try:
            await self._rollback_processing(path)
        except Exception as e:
            logger.error(
                "[%s] Failed to rollback PROCESSING for '%s': %s. "
                "Will be recovered on next startup.",
                self.db_name, path, e
            )

    async def _rollback_processing(self, path: str) -> None:
        """
        Rollback PROCESSING status to original status on failure.

        Args:
            path: Path of the category that failed.
        """
        async with self._uow_factory.begin() as uow:
            category = await uow.nodes.get_by_path(path)

            if category:
                category.fail_processing()
                uow.register_dirty(category)

            children = await uow.nodes.list_children(
                path, statuses=[NodeStatus.PROCESSING])

            for child in children:
                child.fail_processing()
                uow.register_dirty(child)

            await uow.commit()

    async def _finish_processing_without_changes(self, path: str) -> None:
        """
        Complete processing when no changes are needed.

        Transitions nodes from PROCESSING to ACTIVE and clears dirty flag.

        Args:
            path: Path of the category.
        """
        async with self._uow_factory.begin() as uow:
            category = await uow.nodes.get_by_path(path)
            if category:
                category.finish_processing()
                category.clear_dirty()
                uow.register_dirty(category)
            children = await uow.nodes.list_children(
                path, statuses=[NodeStatus.PROCESSING])
            for child in children:
                child.finish_processing()
                uow.register_dirty(child)
            await uow.commit()
