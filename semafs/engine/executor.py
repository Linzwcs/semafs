"""Executor - executes resolved Plans."""

from ..core.node import Node, NodeStage
from ..core.ops import Plan, MergeOp, GroupOp, MoveOp, PersistOp
from ..core.events import Merged, Grouped, Moved, Persisted
from ..core.snapshot import Snapshot
from ..ports.factory import UnitOfWork


class Executor:
    """Executes resolved Plans by applying operations to nodes."""

    def execute(self, plan: Plan, snapshot: Snapshot,
                uow: UnitOfWork) -> list[Merged | Grouped | Moved | Persisted]:
        """
        Execute plan operations and register changes to UoW.

        Args:
            plan: Resolved plan with absolute paths
            snapshot: Context snapshot for node lookup
            uow: Unit of Work for registering changes

        Returns:
            List of emitted event objects
        """
        events: list[Merged | Grouped | Moved | Persisted] = []

        # Build ID index (supports both full UUIDs and 8-char short IDs)
        id_index = self._build_id_index(snapshot)
        path_index = self._build_path_index(snapshot)

        # Execute each operation
        for op in plan.ops:
            if isinstance(op, MergeOp):
                event = self._do_merge(op, snapshot, id_index, uow)
                if event:
                    events.append(event)

            elif isinstance(op, GroupOp):
                event = self._do_group(op, snapshot, id_index, uow)
                if event:
                    events.append(event)

            elif isinstance(op, MoveOp):
                event = self._do_move(op, snapshot, id_index, path_index, uow)
                if event:
                    events.append(event)

            elif isinstance(op, PersistOp):
                event = self._do_persist(op, snapshot, id_index, uow)
                if event:
                    events.append(event)

        return events

    def _build_id_index(self, snapshot: Snapshot) -> dict[str, Node]:
        """Build index mapping both full IDs and short IDs to nodes."""
        index: dict[str, Node] = {}

        for node in snapshot.leaves + snapshot.pending:
            # Full ID
            index[node.id] = node
            # Short ID (first 8 chars)
            index[node.id[:8]] = node

        for node in snapshot.subcategories:
            index[node.id] = node
            index[node.id[:8]] = node

        return index

    def _build_path_index(self, snapshot: Snapshot) -> dict[str, Node]:
        """Build path -> node lookup for categories in local context."""
        nodes = (
            (snapshot.target,)
            + snapshot.subcategories
            + snapshot.siblings
            + snapshot.ancestors
        )
        return {node.path.value: node for node in nodes}

    def _do_merge(self, op: MergeOp, snapshot: Snapshot,
                  index: dict[str, Node], uow: UnitOfWork) -> Merged | None:
        """Execute merge operation."""
        # Resolve source nodes
        sources = [index.get(sid) for sid in op.source_ids]
        sources = [n for n in sources if n is not None]

        if not sources:
            return None

        # Create merged leaf
        merged = Node.create_leaf(
            parent_id=snapshot.target.id,
            parent_path=snapshot.target.path.value,
            name=op.new_name,
            content=op.new_content,
        )

        # Register changes
        uow.register_new(merged)
        for source in sources:
            uow.register_removed(source.id)

        return Merged(
            source_ids=tuple(s.id for s in sources),
            result_id=merged.id,
            parent_id=snapshot.target.id,
            result_path=merged.path.value,
            parent_path=snapshot.target.path.value,
        )

    def _do_group(self, op: GroupOp, snapshot: Snapshot,
                  index: dict[str, Node], uow: UnitOfWork) -> Grouped | None:
        """Execute group operation."""
        # Resolve source nodes
        sources = [index.get(sid) for sid in op.source_ids]
        sources = [n for n in sources if n is not None]

        if not sources:
            return None

        # Create new category
        category = Node.create_category(
            parent_id=snapshot.target.id,
            parent_path=snapshot.target.path.value,
            name=op.category_name,
            summary=op.category_summary,
        )

        # Move sources into category
        moved_sources = [
            s.with_parent(category.id, category.path.value) for s in sources
        ]

        # Register changes
        uow.register_new(category)
        for source in sources:
            uow.register_removed(source.id)
        for moved in moved_sources:
            uow.register_new(moved)

        return Grouped(
            source_ids=tuple(s.id for s in sources),
            category_id=category.id,
            parent_id=snapshot.target.id,
            category_path=category.path.value,
            parent_path=snapshot.target.path.value,
        )

    def _do_move(self, op: MoveOp, snapshot: Snapshot, index: dict[str, Node],
                 path_index: dict[str, Node],
                 uow: UnitOfWork) -> Moved | None:
        """Execute move operation."""
        # Resolve source node
        source = index.get(op.leaf_id)
        if not source:
            return None

        target = path_index.get(op.target_path)
        if not target:
            return None

        # Create moved node
        moved = source.with_parent(target.id, target.path.value)

        # Register changes
        uow.register_removed(source.id)
        uow.register_new(moved)

        return Moved(
            leaf_id=moved.id,
            target_category_id=target.id,
            old_path=source.path.value,
            new_path=moved.path.value,
            target_category=op.target_path,
        )

    def _do_persist(self, op: PersistOp, snapshot: Snapshot, index: dict[str,
                                                                         Node],
                    uow: UnitOfWork) -> Persisted | None:
        """Execute persist operation (convert pending to active)."""
        # Resolve pending node
        pending = index.get(op.leaf_id)
        if not pending or pending.stage != NodeStage.PENDING:
            return None

        # Promote in place to avoid path-level uniqueness conflicts.
        active = pending.with_stage(NodeStage.ACTIVE)

        # Register changes
        uow.register_dirty(active)

        return Persisted(
            leaf_id=active.id,
            parent_id=snapshot.target.id,
            leaf_path=active.path.value,
            parent_path=snapshot.target.path.value,
        )
