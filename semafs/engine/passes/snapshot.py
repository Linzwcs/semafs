"""Snapshot-aware executable-plan validation pass."""

from __future__ import annotations

import re
from dataclasses import replace

from ...core.node import NodeType
from ...core.plan.ops import Plan, GroupOp, MergeOp, MoveOp, RenameOp
from ...core.rules import (
    CATEGORY_SEGMENT_RE,
    allocate_unique_category_segment,
    is_generic_category_name,
    is_name_locked_node,
    normalize_category_segment,
    same_semantic_family,
)
from ...core.snapshot import Snapshot
from .common import ValidationCode, ValidationReport, record_reject


class SnapshotValidationPass:
    """Drop ops violating snapshot-constrained invariants."""

    def run(
        self,
        plan: Plan,
        snapshot: Snapshot,
    ) -> tuple[Plan, ValidationReport]:
        nodes = snapshot.leaves + snapshot.pending + snapshot.subcategories
        by_id = {n.id: n for n in nodes}
        accepted = []
        rejects = []
        for op_index, op in enumerate(plan.ops):
            if isinstance(op, GroupOp):
                invalid_source = self._first_non_leaf_source(op.source_ids, by_id)
                if invalid_source is not None:
                    record_reject(
                        rejects,
                        ValidationCode.INVALID_GROUP_SOURCE_TYPE,
                        "Reject GROUP with non-leaf source node",
                        source_id=invalid_source.id,
                        source_path=invalid_source.path.value,
                        op_index=op_index,
                    )
                    continue
            if isinstance(op, MergeOp):
                invalid_source = self._first_non_leaf_source(op.source_ids, by_id)
                if invalid_source is not None:
                    record_reject(
                        rejects,
                        ValidationCode.INVALID_MERGE_SOURCE_TYPE,
                        "Reject MERGE with non-leaf source node",
                        source_id=invalid_source.id,
                        source_path=invalid_source.path.value,
                        op_index=op_index,
                    )
                    continue
            if isinstance(op, GroupOp):
                if snapshot.target.skeleton:
                    accepted.append(op)
                    continue
                all_segments = op.category_path.split(".")
                if not all_segments or all_segments[0] != "root":
                    record_reject(
                        rejects,
                        ValidationCode.INVALID_GROUP_PATH,
                        "Reject invalid GROUP category path",
                        path=op.category_path,
                        op_index=op_index,
                    )
                    continue

                segments = all_segments[1:]
                target_segments = snapshot.target.path.value.split(".")[1:]
                relative_segments = segments
                if (
                    len(segments) >= len(target_segments)
                    and segments[:len(target_segments)] == target_segments
                ):
                    relative_segments = segments[len(target_segments):]
                if (
                    not relative_segments
                    or any(
                        not CATEGORY_SEGMENT_RE.fullmatch(seg)
                        for seg in relative_segments
                    )
                ):
                    record_reject(
                        rejects,
                        ValidationCode.INVALID_GROUP_PATH,
                        "Reject invalid GROUP category path",
                        path=op.category_path,
                        op_index=op_index,
                    )
                    continue
                if self._has_adjacent_duplicates(relative_segments):
                    record_reject(
                        rejects,
                        ValidationCode.DUPLICATE_GROUP_SEGMENTS,
                        "Reject GROUP path with adjacent duplicate segments",
                        path=op.category_path,
                        op_index=op_index,
                    )
                    continue
                redundant_pair = self._find_adjacent_redundant_pair(
                    relative_segments
                )
                if redundant_pair is not None:
                    left, right = redundant_pair
                    record_reject(
                        rejects,
                        ValidationCode.REDUNDANT_GROUP_SEGMENT,
                        ("Reject GROUP path with stacked redundant parent/child "
                         "segments"),
                        path=op.category_path,
                        left_segment=left,
                        right_segment=right,
                        op_index=op_index,
                    )
                    continue
                if self._has_duplicate_segments(relative_segments):
                    record_reject(
                        rejects,
                        ValidationCode.DUPLICATE_GROUP_SEGMENTS,
                        "Reject GROUP path with repeated segments",
                        path=op.category_path,
                        op_index=op_index,
                    )
                    continue
                if relative_segments:
                    first_segment = relative_segments[0]
                    banned = self._group_forbidden_segments(snapshot)
                    matched = next(
                        (
                            token for token in banned
                            if self._is_redundant_segment(
                                first_segment, token
                            )
                        ),
                        None,
                    )
                    if matched:
                        record_reject(
                            rejects,
                            ValidationCode.REDUNDANT_GROUP_SEGMENT,
                            ("Reject GROUP path first segment in forbidden "
                             "semantic list"),
                            path=op.category_path,
                            segment=first_segment,
                            forbidden_match=matched,
                            op_index=op_index,
                        )
                        continue
                if any(is_generic_category_name(seg) for seg in segments):
                    record_reject(
                        rejects,
                        ValidationCode.GENERIC_GROUP_PATH,
                        "Reject generic GROUP category path",
                        path=op.category_path,
                        op_index=op_index,
                    )
                    continue
                accepted.append(op)
                continue

            if isinstance(op, MoveOp):
                source = by_id.get(op.leaf_id)
                if source and source.node_type != NodeType.LEAF:
                    record_reject(
                        rejects,
                        ValidationCode.INVALID_MOVE_SOURCE_TYPE,
                        "Reject MOVE with non-leaf source node",
                        source_id=source.id,
                        source_path=source.path.value,
                        op_index=op_index,
                    )
                    continue
                segments = op.target_path.split(".")[1:]
                if any(is_generic_category_name(seg) for seg in segments):
                    record_reject(
                        rejects,
                        ValidationCode.GENERIC_MOVE_TARGET,
                        "Reject MOVE target with generic category",
                        target=op.target_path,
                        op_index=op_index,
                    )
                    continue
                accepted.append(op)
                continue

            node_id = getattr(op, "node_id", None)
            if node_id is None:
                accepted.append(op)
                continue

            if isinstance(op, RenameOp):
                if not CATEGORY_SEGMENT_RE.fullmatch(op.new_name):
                    record_reject(
                        rejects,
                        ValidationCode.INVALID_RENAME_NAME,
                        "Reject invalid RENAME category name",
                        name=op.new_name,
                        op_index=op_index,
                    )
                    continue
                if is_generic_category_name(op.new_name):
                    record_reject(
                        rejects,
                        ValidationCode.GENERIC_RENAME_NAME,
                        "Reject generic RENAME category name",
                        name=op.new_name,
                        op_index=op_index,
                    )
                    continue

            target = by_id.get(node_id)
            if not target:
                continue
            if target.node_type != NodeType.CATEGORY:
                record_reject(
                    rejects,
                    ValidationCode.LEAF_RENAME_BLOCKED,
                    "Reject leaf rename op",
                    node_id=node_id,
                    op_index=op_index,
                )
                continue
            if isinstance(op, RenameOp) and is_name_locked_node(target):
                record_reject(
                    rejects,
                    ValidationCode.SKELETON_RENAME_BLOCKED,
                    "Reject rename on locked skeleton category",
                    node_id=node_id,
                    path=target.path.value,
                    op_index=op_index,
                )
                continue
            accepted.append(op)

        updated_name = self._validate_updated_name(
            plan=plan,
            snapshot=snapshot,
            accepted_ops=tuple(accepted),
            rejects=rejects,
        )

        return replace(plan, ops=tuple(accepted), updated_name=updated_name), ValidationReport(
            rejects=tuple(rejects)
        )

    @classmethod
    def _validate_updated_name(
        cls,
        *,
        plan: Plan,
        snapshot: Snapshot,
        accepted_ops: tuple[object, ...],
        rejects: list,
    ) -> str | None:
        candidate = (plan.updated_name or "").strip().lower()
        if not candidate:
            return None
        if candidate == snapshot.target.name:
            return None
        if is_name_locked_node(snapshot.target):
            record_reject(
                rejects,
                ValidationCode.SKELETON_RENAME_BLOCKED,
                "Reject updated_name on locked skeleton category",
                node_id=snapshot.target.id,
                path=snapshot.target.path.value,
            )
            return None

        conflict = cls._find_updated_name_conflict(
            updated_name=candidate,
            snapshot=snapshot,
            accepted_ops=accepted_ops,
        )
        if conflict is None:
            return candidate

        record_reject(
            rejects,
            ValidationCode.REDUNDANT_UPDATED_NAME,
            "Reject updated_name causing stacked redundant directory semantics",
            updated_name=candidate,
            conflict_kind=conflict["kind"],
            conflict_name=conflict["name"],
            path_after=conflict["path_after"],
        )
        return None

    @classmethod
    def _find_updated_name_conflict(
        cls,
        *,
        updated_name: str,
        snapshot: Snapshot,
        accepted_ops: tuple[object, ...],
    ) -> dict[str, str] | None:
        current_path = snapshot.target.path.value
        parent_path = current_path.rsplit(".", 1)[0] if current_path != "root" else ""
        path_after = (
            f"{parent_path}.{updated_name}" if parent_path else f"root.{updated_name}"
        )

        parent = snapshot.ancestors[0] if snapshot.ancestors else None
        if parent and cls._is_redundant_segment(updated_name, parent.name):
            return {
                "kind": "parent",
                "name": parent.name,
                "path_after": path_after,
            }

        for child in snapshot.subcategories:
            if cls._is_redundant_segment(updated_name, child.name):
                return {
                    "kind": "child_category",
                    "name": child.name,
                    "path_after": f"{path_after}.{child.name}",
                }

        for op in accepted_ops:
            if isinstance(op, GroupOp):
                rel = cls._relative_segments(op.category_path, current_path)
                if rel and cls._is_redundant_segment(updated_name, rel[0]):
                    return {
                        "kind": "group_child",
                        "name": rel[0],
                        "path_after": f"{path_after}.{rel[0]}",
                    }
            if isinstance(op, RenameOp):
                renamed = next(
                    (sub for sub in snapshot.subcategories if sub.id == op.node_id),
                    None,
                )
                if renamed and cls._is_redundant_segment(updated_name, op.new_name):
                    return {
                        "kind": "renamed_child",
                        "name": op.new_name,
                        "path_after": f"{path_after}.{op.new_name}",
                    }
        return None

    @staticmethod
    def _first_non_leaf_source(
        source_ids: tuple[str, ...],
        by_id: dict[str, object],
    ):
        for source_id in source_ids:
            node = by_id.get(source_id)
            if node is not None and getattr(node, "node_type", None) != NodeType.LEAF:
                return node
        return None

    @staticmethod
    def _has_adjacent_duplicates(segments: list[str]) -> bool:
        return any(
            left == right for left, right in zip(segments, segments[1:])
        )

    @staticmethod
    def _has_duplicate_segments(segments: list[str]) -> bool:
        seen: set[str] = set()
        for seg in segments:
            if seg in seen:
                return True
            seen.add(seg)
        return False

    @staticmethod
    def _relative_segments(path: str, target_path: str) -> list[str]:
        segments = path.split(".")[1:]
        target_segments = target_path.split(".")[1:]
        if (
            len(segments) >= len(target_segments)
            and segments[:len(target_segments)] == target_segments
        ):
            return segments[len(target_segments):]
        return segments

    @classmethod
    def _find_adjacent_redundant_pair(
        cls,
        segments: list[str],
    ) -> tuple[str, str] | None:
        for left, right in zip(segments, segments[1:]):
            if cls._is_redundant_segment(left, right):
                return left, right
        return None

    @staticmethod
    def _canonical_segment(value: str) -> str:
        text = re.sub(r"[^a-z]", "", (value or "").strip().lower())
        if not text:
            return ""

        for prefix in (
            "best",
            "core",
            "main",
            "general",
            "overall",
            "primary",
        ):
            if text.startswith(prefix) and len(text) - len(prefix) >= 5:
                text = text[len(prefix):]
                break

        if text.endswith("ies") and len(text) > 4:
            text = text[:-3] + "y"
        elif text.endswith(("ches", "shes", "sses", "xes", "zes")):
            text = text[:-2]
        elif text.endswith("s") and not text.endswith("ss") and len(text) > 3:
            text = text[:-1]
        return text

    @classmethod
    def _is_redundant_segment(cls, left: str, right: str) -> bool:
        a = cls._canonical_segment(left)
        b = cls._canonical_segment(right)
        if not a or not b:
            return False
        if a == b:
            return True

        shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
        if len(shorter) >= 4 and len(longer) - len(shorter) <= 2:
            if longer.startswith(shorter) or longer.endswith(shorter):
                return True
        if len(shorter) < 6:
            return same_semantic_family(a, b)
        return (
            longer.startswith(shorter)
            or longer.endswith(shorter)
            or same_semantic_family(a, b)
        )

    @classmethod
    def _group_forbidden_segments(cls, snapshot: Snapshot) -> tuple[str, ...]:
        names = (
            [snapshot.target.name]
            + [c.name for c in snapshot.subcategories]
            + [s.name for s in snapshot.siblings]
            + [a.name for a in snapshot.ancestors if a.path.value != "root"]
        )
        seen: set[str] = set()
        out: list[str] = []
        for name in names:
            lowered = (name or "").strip().lower()
            canonical = cls._canonical_segment(lowered)
            if not lowered or not canonical or canonical in seen:
                continue
            seen.add(canonical)
            out.append(lowered)
        return tuple(out)


class GroupPathRepairPass:
    """Best-effort GROUP path repair pass."""

    def run(self, plan: Plan, snapshot: Snapshot) -> Plan:
        repaired_ops = []
        forbidden = SnapshotValidationPass._group_forbidden_segments(snapshot)
        generated_first_segments: list[str] = []
        for op in plan.ops:
            if not isinstance(op, GroupOp):
                repaired_ops.append(op)
                continue
            repaired = self._repair_group_path(
                op,
                snapshot=snapshot,
                forbidden=forbidden + tuple(generated_first_segments),
            )
            rel = SnapshotValidationPass._relative_segments(
                repaired.category_path,
                snapshot.target.path.value,
            )
            if rel:
                generated_first_segments.append(rel[0])
            repaired_ops.append(repaired)
        return replace(plan, ops=tuple(repaired_ops))

    @staticmethod
    def _collapse_adjacent_duplicates(segments: list[str]) -> list[str]:
        out: list[str] = []
        for seg in segments:
            if out and out[-1] == seg:
                continue
            out.append(seg)
        return out

    @classmethod
    def _collapse_adjacent_redundant_segments(
        cls,
        segments: list[str],
    ) -> list[str]:
        out: list[str] = []
        for seg in segments:
            if out and SnapshotValidationPass._is_redundant_segment(out[-1], seg):
                continue
            out.append(seg)
        return out

    def _repair_group_path(
        self,
        op: GroupOp,
        *,
        snapshot: Snapshot,
        forbidden: tuple[str, ...],
    ) -> GroupOp:
        rel = SnapshotValidationPass._relative_segments(
            op.category_path,
            snapshot.target.path.value,
        )
        if not rel:
            rel = ["topic"]

        rel = [
            normalize_category_segment(seg, fallback="topic")
            for seg in self._collapse_adjacent_redundant_segments(
                self._collapse_adjacent_duplicates(rel)
            )
        ]
        if not rel:
            rel = ["topic"]

        first = rel[0]
        if (
            is_generic_category_name(first)
            or any(
                SnapshotValidationPass._is_redundant_segment(first, token)
                for token in forbidden
            )
        ):
            rel[0] = self._pick_replacement_segment(
                op,
                forbidden=forbidden,
            )

        rel = self._collapse_adjacent_redundant_segments(
            self._collapse_adjacent_duplicates(rel)
        ) or ["topic"]

        target_path = snapshot.target.path.value
        if target_path == "root":
            repaired_path = "root." + ".".join(rel)
        else:
            repaired_path = target_path + "." + ".".join(rel)
        return replace(op, category_path=repaired_path)

    @staticmethod
    def _pick_replacement_segment(
        op: GroupOp,
        *,
        forbidden: tuple[str, ...],
    ) -> str:
        candidates: list[str] = []
        candidates.extend(op.category_keywords)
        candidates.extend(re.findall(r"[a-z]{4,}", op.category_summary.lower()))
        candidates.extend(re.findall(r"[a-z]{4,}", op.category_path.lower()))

        for raw in candidates:
            seg = normalize_category_segment(raw, fallback="topic")
            if is_generic_category_name(seg):
                continue
            if any(
                SnapshotValidationPass._is_redundant_segment(seg, token)
                for token in forbidden
            ):
                continue
            return seg

        used = {
            normalize_category_segment(token, fallback="topic")
            for token in forbidden
            if token
        }
        return allocate_unique_category_segment(
            "topic",
            used_names=used,
            fallback="topic",
        )
