"""Executor - executes resolved Plans."""

from ..core.node import Node
from ..core.plan.ops import Plan, MergeOp, GroupOp, MoveOp, RenameOp
from ..core.summary import build_category_meta, render_category_summary
from ..core.events import Merged, Grouped, Moved
from ..core.snapshot import Snapshot
from ..ports.factory import UnitOfWork


class Executor:
    """Executes resolved Plans by applying operations to nodes."""

    def execute(self, plan: Plan, snapshot: Snapshot,
                uow: UnitOfWork) -> list[Merged | Grouped | Moved]:
        """
        Execute plan operations and register changes to UoW.

        Args:
            plan: Resolved plan with absolute paths
            snapshot: Context snapshot for node lookup
            uow: Unit of Work for registering changes

        Returns:
            List of emitted event objects
        """
        events: list[Merged | Grouped | Moved] = []

        # Build ID index (supports both full UUIDs and 8-char short IDs)
        leaf_index = self._build_leaf_index(snapshot)
        category_index = self._build_category_index(snapshot)
        path_index = self._build_path_index(snapshot)

        # Execute each operation
        for op in plan.ops:
            if isinstance(op, MergeOp):
                event = self._do_merge(op, snapshot, leaf_index, uow)
                if event:
                    events.append(event)

            elif isinstance(op, GroupOp):
                event = self._do_group(op, snapshot, leaf_index, uow)
                if event:
                    events.append(event)

            elif isinstance(op, MoveOp):
                event = self._do_move(op, snapshot, leaf_index, path_index, uow)
                if event:
                    events.append(event)

            elif isinstance(op, RenameOp):
                self._do_rename(op, category_index, uow)

        return events

    def _build_leaf_index(self, snapshot: Snapshot) -> dict[str, Node]:
        """Build index mapping both full IDs and short IDs to leaf nodes."""
        index: dict[str, Node] = {}

        for node in snapshot.leaves + snapshot.pending:
            # Full ID
            index[node.id] = node
            # Short ID (first 8 chars)
            index[node.id[:8]] = node

        return index

    def _build_category_index(self, snapshot: Snapshot) -> dict[str, Node]:
        """Build index mapping both full IDs and short IDs to categories."""
        index: dict[str, Node] = {}
        for node in (snapshot.target,) + snapshot.subcategories:
            index[node.id] = node
            index[node.id[:8]] = node

        return index

    def _build_path_index(self, snapshot: Snapshot) -> dict[str, Node]:
        """Build path -> node lookup for categories in local context."""
        nodes = ((snapshot.target, ) + snapshot.subcategories +
                 snapshot.siblings + snapshot.ancestors)
        return {node.path.value: node for node in nodes}

    def _do_merge(self, op: MergeOp, snapshot: Snapshot,
                  index: dict[str, Node], uow: UnitOfWork) -> Merged | None:
        """Execute merge operation."""
        # Resolve source nodes
        sources = [index.get(sid) for sid in op.source_ids]
        sources = [n for n in sources if n is not None]

        if not sources:
            return None

        merged_content = self._merge_content(op.new_content, sources)

        # Create merged leaf
        merged = Node.create_leaf(
            parent_id=snapshot.target.id,
            parent_path=snapshot.target.path.value,
            name=op.new_name,
            content=merged_content,
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

    @staticmethod
    def _merge_content(raw_content: str, sources: list[Node]) -> str:
        """Guarantee non-empty merged leaf content."""
        direct = (raw_content or "").strip()
        if direct:
            return direct
        snippets = []
        for source in sources:
            text = (source.content or "").strip()
            if text:
                snippets.append(text[:160])
        if snippets:
            return "\n".join(f"- {item}" for item in snippets[:8])
        return "Merged content (auto-generated)"

    def _do_group(self, op: GroupOp, snapshot: Snapshot,
                  index: dict[str, Node], uow: UnitOfWork) -> Grouped | None:
        """Execute group operation."""
        # Resolve source nodes
        sources = [index.get(sid) for sid in op.source_ids]
        sources = [n for n in sources if n is not None]

        if not sources:
            return None

        category = self._ensure_category_chain(
            op.category_path,
            op.category_summary,
            op.category_keywords,
            tuple(n.content for n in sources if n.content),
            tuple(n.name for n in sources),
            snapshot,
            uow,
        )
        if not category:
            return None

        # Move sources into category
        # Register changes
        for source in sources:
            uow.register_move(source.id, category.id)

        return Grouped(
            source_ids=tuple(s.id for s in sources),
            category_id=category.id,
            parent_id=snapshot.target.id,
            category_path=category.path.value,
            parent_path=snapshot.target.path.value,
        )

    def _ensure_category_chain(
        self,
        category_path: str,
        final_summary: str,
        final_keywords: tuple[str, ...],
        source_texts: tuple[str, ...],
        source_names: tuple[str, ...],
        snapshot: Snapshot,
        uow: UnitOfWork,
    ) -> Node | None:
        """Ensure absolute category path exists, create missing segments."""
        target_path = snapshot.target.path.value
        if not category_path.startswith(f"{target_path}."):
            return None

        existing_by_path: dict[str, Node] = {target_path: snapshot.target}
        for cat in snapshot.subcategories:
            existing_by_path[cat.path.value] = cat

        current = snapshot.target
        current_path = target_path
        segments = category_path[len(target_path) + 1:].split(".")
        for index, segment in enumerate(segments):
            next_path = f"{current_path}.{segment}"
            found = existing_by_path.get(next_path)
            if found:
                if index == len(segments) - 1:
                    meta = build_category_meta(
                        raw_summary=final_summary,
                        leaf_texts=source_texts,
                        child_names=source_names,
                        keywords=final_keywords if final_keywords else None,
                    )
                    normalized = render_category_summary(meta)
                    if (
                        found.summary != normalized
                        or found.category_meta != meta
                    ):
                        updated = found.with_summary(normalized)
                        updated = updated.with_category_meta(meta)
                        uow.register_dirty(updated)
                current = found
                current_path = next_path
                continue

            child_names = (
                source_names if index == len(segments) - 1
                else (segments[index + 1],)
            )
            raw = final_summary if index == len(segments) - 1 else (
                f"Subtree for {segment}"
            )
            meta = build_category_meta(
                raw_summary=raw,
                leaf_texts=source_texts,
                child_names=child_names,
                keywords=(
                    final_keywords
                    if index == len(segments) - 1 and final_keywords
                    else None
                ),
            )
            summary = render_category_summary(meta)
            created = Node.create_category(
                parent_id=current.id,
                parent_path=current_path,
                name=segment,
                summary=summary,
                category_meta=meta,
            )
            uow.register_new(created)
            existing_by_path[next_path] = created
            current = created
            current_path = next_path

        return current

    def _do_move(self, op: MoveOp, snapshot: Snapshot, index: dict[str, Node],
                 path_index: dict[str, Node], uow: UnitOfWork) -> Moved | None:
        """Execute move operation."""
        # Resolve source node
        source = index.get(op.leaf_id)
        if not source:
            return None

        target = path_index.get(op.target_path)
        if not target:
            return None

        # Skip no-op move: same parent already.
        if source.parent_id == target.id:
            return None

        # Register changes
        uow.register_move(source.id, target.id)

        if target.path.value == "root":
            new_path = f"root.{source.name}"
        else:
            new_path = f"{target.path.value}.{source.name}"

        return Moved(
            leaf_id=source.id,
            target_category_id=target.id,
            old_path=source.path.value,
            new_path=new_path,
            target_category=op.target_path,
        )

    def _do_rename(
        self,
        op: RenameOp,
        index: dict[str, Node],
        uow: UnitOfWork,
    ) -> None:
        """Execute rename operation as in-place update."""
        source = index.get(op.node_id)
        if not source:
            return
        if source.name == op.new_name:
            return
        uow.register_rename(source.id, op.new_name)
