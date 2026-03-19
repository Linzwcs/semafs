"""Resolver - converts RawPlan to Plan by resolving paths."""

from uuid import uuid4

from ..core.raw import RawPlan, RawMerge, RawGroup, RawMove, RawRename
from ..core.ops import Plan, MergeOp, GroupOp, MoveOp, RenameOp
from ..core.node import NodeType
from ..core.naming import PathAllocator
from ..core.rules import (
    allocate_unique_category_segment,
    semantic_category_segment,
)
from ..core.snapshot import Snapshot


class Resolver:
    """Resolves raw LLM output into executable plans with resolved paths."""

    def __init__(self, allocator: PathAllocator | None = None):
        self._allocator = allocator or PathAllocator()

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
                    snapshot.target.path.value,
                    self._fresh_leaf_name(),
                    used,
                )
                ops.append(
                    MergeOp(
                        source_ids=raw_op.source_ids,
                        new_content=raw_op.new_content,
                        new_name=target_path.rsplit(".", 1)[-1],
                    )
                )

            elif isinstance(raw_op, RawGroup):
                cat_path = self._resolve_category_path(
                    snapshot.target.path.value,
                    raw_op.category_name,
                    used,
                    summary_hint=raw_op.category_summary,
                )
                ops.append(
                    GroupOp(
                        source_ids=raw_op.source_ids,
                        category_path=cat_path,
                        category_summary=raw_op.category_summary,
                        category_keywords=raw_op.category_keywords,
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

            elif isinstance(raw_op, RawRename):
                rename = self._resolve_rename(raw_op, snapshot, used)
                if rename:
                    ops.append(rename)

        return Plan(
            ops=tuple(ops),
            updated_summary=raw.updated_summary,
            updated_keywords=raw.updated_keywords,
            updated_name=raw.updated_name,
            reasoning=raw.reasoning,
        )

    def _resolve_rename(
        self,
        raw_op: RawRename,
        snapshot: Snapshot,
        used: set[str],
    ) -> RenameOp | None:
        target = self._find_node(snapshot, raw_op.node_id)
        if not target:
            return None
        if target.node_type != NodeType.CATEGORY:
            return None
        parent_path = target.path.parent_str
        unique_path = self._ensure_unique_category_path(
            parent_path,
            raw_op.new_name,
            used,
        )
        return RenameOp(
            node_id=target.id,
            new_name=unique_path.rsplit(".", 1)[-1],
        )

    def _find_node(self, snapshot: Snapshot, node_id: str):
        nodes = (snapshot.leaves + snapshot.pending + snapshot.subcategories)
        for node in nodes:
            if node.id == node_id or node.id[:8] == node_id[:8]:
                return node
        return None

    def _resolve_leaf_path(
        self, parent_path: str, name: str, used: set[str]
    ) -> str:
        """
        Resolve leaf path with deduplication.

        Handles dot-separated hierarchies: "tech.advice" creates
        "tech" category and returns "parent.tech.advice" path.
        """
        parts = self._normalize_relative_parts(parent_path, name)

        if len(parts) == 1:
            # Simple name - just ensure uniqueness
            return self._ensure_unique(parent_path, parts[0], used)

        # Multi-level hierarchy - create intermediate categories
        current_path = parent_path
        for i, part in enumerate(parts[:-1]):
            # Create intermediate category path
            cat_path = self._ensure_unique(current_path, part, used)
            current_path = cat_path

        # Final leaf path
        leaf_name = parts[-1]
        return self._ensure_unique(current_path, leaf_name, used)

    def _normalize_relative_parts(
        self,
        parent_path: str,
        raw_name: str,
    ) -> list[str]:
        """
        Normalize LLM-generated names into parent-relative path segments.

        Handles common hallucinations:
        - absolute-style names: "root.work.practices"
        - parent-repeated names: "work.practices", "work_practices"
        """
        text = (raw_name or "").strip().lower()
        if not text:
            return [self._fresh_leaf_name()]

        parent_tokens = (
            parent_path.split(".")[1:] if parent_path != "root" else []
        )
        parent_rel = ".".join(parent_tokens)
        parent_name = (
            parent_path.rsplit(".", 1)[-1]
            if parent_path != "root" else "root"
        )

        # Convert absolute-path style to relative expression.
        if text.startswith("root."):
            text = text[len("root."):]
        if parent_rel and text.startswith(parent_rel + "."):
            text = text[len(parent_rel) + 1:]

        raw_parts = [p for p in text.split(".") if p.strip()]
        parts = [
            self._allocator.normalize(part, fallback_prefix="node")
            for part in raw_parts
        ]
        if not parts:
            return [self._fresh_leaf_name()]

        # Remove dotted parent-prefix duplication, e.g. work.practices.
        parent_cursor = list(parent_tokens)
        while parts and parent_cursor and parts[0] == parent_cursor[0]:
            parts.pop(0)
            parent_cursor.pop(0)
        if not parts:
            parts = [self._fresh_leaf_name()]

        # Remove single-token parent-prefix duplication, e.g. work_practices.
        if len(parts) == 1 and parts[0].startswith(f"{parent_name}_"):
            trimmed = parts[0][len(parent_name) + 1:]
            parts = [
                self._allocator.normalize(trimmed, fallback_prefix="node")
            ]

        return parts

    @staticmethod
    def _fresh_leaf_name() -> str:
        """
        Generate a non-deterministic technical leaf name.

        We must avoid deterministic fallbacks such as `leaf_da39a3`, because
        canonical_path is globally unique in the SQLite schema (including
        archived rows), and deterministic reuse can trigger UNIQUE collisions.
        """
        return f"leaf_{uuid4().hex[:6]}"

    def _resolve_category_path(
        self,
        parent_path: str,
        raw_name: str,
        used: set[str],
        *,
        summary_hint: str = "",
    ) -> str:
        """Resolve GROUP category path with recursive single-word segments."""
        parts = self._normalize_category_parts(
            parent_path,
            raw_name,
            summary_hint=summary_hint,
        )
        current_path = parent_path
        for part in parts:
            current_path = self._ensure_unique_category_path(
                current_path, part, used
            )
        return current_path

    def _normalize_category_parts(
        self,
        parent_path: str,
        raw_name: str,
        *,
        summary_hint: str = "",
    ) -> list[str]:
        """
        Normalize category expression to parent-relative word segments.

        Allows dotted recursive categories (e.g. `a.b.c`) and also treats
        underscores as hierarchical separators for category intents.
        """
        text = (raw_name or "").strip().lower()
        if not text:
            return ["topic"]

        parent_tokens = (
            parent_path.split(".")[1:] if parent_path != "root" else []
        )
        parent_rel = ".".join(parent_tokens)

        if text.startswith("root."):
            text = text[len("root."):]
        if parent_rel and text.startswith(parent_rel + "."):
            text = text[len(parent_rel) + 1:]

        text = text.replace("_", ".")
        raw_parts = [p for p in text.split(".") if p.strip()]
        parts = [
            semantic_category_segment(
                part,
                context_text=summary_hint,
                fallback="topic",
            )
            for part in raw_parts
        ]
        if not parts:
            return ["topic"]

        # Remove duplicate parent prefix segments.
        cursor = list(parent_tokens)
        while parts and cursor and parts[0] == cursor[0]:
            parts.pop(0)
            cursor.pop(0)
        return parts or ["topic"]

    def _ensure_unique_category_path(
        self,
        parent_path: str,
        raw_segment: str,
        used: set[str],
    ) -> str:
        sibling_names = self._allocator.sibling_names(
            parent_path=parent_path,
            used_paths=used,
        )
        segment = allocate_unique_category_segment(
            raw_segment,
            used_names=sibling_names,
            fallback="topic",
        )
        if parent_path == "root":
            path = f"root.{segment}"
        else:
            path = f"{parent_path}.{segment}"
        used.add(path)
        return path

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
        candidate = f"{parent_path}.{target_name}"

        if candidate in snapshot.used_paths:
            return candidate

        # Target doesn't exist - skip this operation
        return None

    def _ensure_unique(
        self,
        parent_path: str,
        name: str,
        used: set[str],
    ) -> str:
        """
        Ensure path is unique by adding suffix if needed.

        Returns:
            Unique path (may have _1, _2, etc. suffix)
        """
        return self._allocator.allocate_path(
            parent_path=parent_path,
            raw_name=name,
            used_paths=used,
            fallback_prefix="node",
        )
