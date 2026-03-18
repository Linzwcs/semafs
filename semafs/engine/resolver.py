"""Resolver - converts RawPlan to Plan by resolving paths."""

from ..core.node import NodePath
from ..core.raw import RawPlan, RawMerge, RawGroup, RawMove
from ..core.ops import Plan, MergeOp, GroupOp, MoveOp, PersistOp
from ..core.snapshot import Snapshot


class Resolver:
    """Resolves raw LLM output into executable plans with resolved paths."""

    def compile(self, raw: RawPlan, snapshot: Snapshot) -> Plan:
        """
        Convert RawPlan to Plan by resolving paths.

        Args:
            raw: Raw plan from LLM
            snapshot: Context snapshot for path resolution

        Returns:
            Resolved Plan with full paths
        """
        ops = []
        used = set(snapshot.used_paths)

        for raw_op in raw.ops:
            if isinstance(raw_op, RawMerge):
                target_path = self._resolve_leaf_path(
                    snapshot.target.path.value, raw_op.new_name, used
                )
                ops.append(
                    MergeOp(
                        source_ids=raw_op.source_ids,
                        new_content=raw_op.new_content,
                        new_name=target_path.rsplit(".", 1)[-1],
                    )
                )

            elif isinstance(raw_op, RawGroup):
                cat_path, _ = self._resolve_group_paths(
                    snapshot.target.path.value, raw_op.category_name, used
                )
                ops.append(
                    GroupOp(
                        source_ids=raw_op.source_ids,
                        category_name=cat_path.rsplit(".", 1)[-1],
                        category_summary=raw_op.category_summary,
                    )
                )

            elif isinstance(raw_op, RawMove):
                # Resolve target category path
                target_path = self._resolve_target_path(
                    snapshot.target.path.value, raw_op.target_name, snapshot
                )
                if target_path:
                    ops.append(
                        MoveOp(leaf_id=raw_op.leaf_id, target_path=target_path)
                    )

            elif isinstance(raw_op, PersistOp):
                ops.append(raw_op)

        return Plan(
            ops=tuple(ops),
            updated_summary=raw.updated_summary,
            updated_name=raw.updated_name,
            reasoning=raw.reasoning,
        )

    def _resolve_leaf_path(
        self, parent_path: str, name: str, used: set[str]
    ) -> str:
        """
        Resolve leaf path with deduplication.

        Handles dot-separated hierarchies: "tech.advice" creates "tech" category
        and returns "parent.tech.advice" path.
        """
        # Parse dot-separated hierarchy
        parts = name.split(".")

        if len(parts) == 1:
            # Simple name - just ensure uniqueness
            return self._ensure_unique(parent_path, name, used)

        # Multi-level hierarchy - create intermediate categories
        current_path = parent_path
        for i, part in enumerate(parts[:-1]):
            # Create intermediate category path
            cat_path = self._ensure_unique(current_path, part, used)
            used.add(cat_path)
            current_path = cat_path

        # Final leaf path
        leaf_name = parts[-1]
        return self._ensure_unique(current_path, leaf_name, used)

    def _resolve_group_paths(
        self, parent_path: str, category_name: str, used: set[str]
    ) -> tuple[str, str]:
        """
        Resolve group operation paths.

        Returns:
            (category_path, leaf_path_prefix)
        """
        cat_path = self._resolve_leaf_path(parent_path, category_name, used)
        used.add(cat_path)
        return cat_path, cat_path

    def _resolve_target_path(
        self, parent_path: str, target_name: str, snapshot: Snapshot
    ) -> str | None:
        """
        Resolve target path for move operation.

        Validates that target exists in snapshot.
        Returns None if target doesn't exist (LLM hallucination).
        """
        # Check if it's an absolute path reference
        if target_name in snapshot.used_paths:
            return target_name

        # Try as relative to parent
        if parent_path == "root":
            candidate = target_name
        else:
            candidate = f"{parent_path}.{target_name}"

        if candidate in snapshot.used_paths:
            return candidate

        # Target doesn't exist - skip this operation
        return None

    def _ensure_unique(self, parent_path: str, name: str, used: set[str]) -> str:
        """
        Ensure path is unique by adding suffix if needed.

        Returns:
            Unique path (may have _1, _2, etc. suffix)
        """
        if parent_path == "root":
            base_path = name
        else:
            base_path = f"{parent_path}.{name}"

        if base_path not in used:
            used.add(base_path)
            return base_path

        # Add numeric suffix
        counter = 1
        while True:
            candidate = f"{base_path}_{counter}"
            if candidate not in used:
                used.add(candidate)
                return candidate
            counter += 1
