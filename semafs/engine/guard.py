"""Plan guard - centralized semantic and naming constraints."""

from __future__ import annotations

import logging
from dataclasses import replace

from ..core.node import NodeType
from ..core.ops import Plan, GroupOp, MoveOp, RenameOp
from ..core.raw import RawPlan, RawMerge
from ..core.rules import (
    CATEGORY_SEGMENT_RE,
    CATEGORY_UPDATED_NAME_RE,
    is_generic_category_name,
)
from ..core.snapshot import Snapshot

logger = logging.getLogger(__name__)


class PlanGuard:
    """Validate/sanitize raw and resolved plans before execution."""

    def validate_raw_plan(self, raw_plan: RawPlan) -> RawPlan:
        """
        Enforce raw-level constraints.

        Current rules:
        - MERGE must include non-empty evidence anchors.
        - updated_name must be a single english word, otherwise dropped.
        """
        accepted_ops = []
        for op in raw_plan.ops:
            if isinstance(op, RawMerge):
                evidence = tuple(e.strip() for e in op.evidence
                                 if isinstance(e, str) and e.strip())
                if not evidence:
                    logger.warning(
                        "Reject raw MERGE without evidence: source_ids=%s",
                        op.source_ids,
                    )
                    continue
                merged_content = (op.new_content or "").strip()
                if not merged_content:
                    logger.warning(
                        "Reject raw MERGE without content: source_ids=%s",
                        op.source_ids,
                    )
                    continue
                accepted_ops.append(
                    replace(
                        op,
                        evidence=evidence,
                        new_content=merged_content,
                    )
                )
                continue
            accepted_ops.append(op)

        return replace(
            raw_plan,
            ops=tuple(accepted_ops),
            updated_name=self._sanitize_category_name(raw_plan.updated_name),
            updated_keywords=self._sanitize_keywords(raw_plan.updated_keywords),
            updated_summary=self._sanitize_summary(raw_plan.updated_summary),
        )

    def validate_plan(self, plan: Plan) -> Plan:
        """
        Enforce resolved-plan constraints.

        Current rules:
        - updated_name must be a single english word, otherwise dropped.
        """
        return replace(
            plan,
            updated_name=self._sanitize_category_name(plan.updated_name),
            updated_keywords=self._sanitize_keywords(plan.updated_keywords),
            updated_summary=self._sanitize_summary(plan.updated_summary),
        )

    def filter_ops_for_snapshot(self, plan: Plan, snapshot: Snapshot) -> Plan:
        """
        Drop ops that violate snapshot-aware constraints.

        Current rules:
        - RENAME applies to categories only (never leaves/pending leaves).
        """
        nodes = snapshot.leaves + snapshot.pending + snapshot.subcategories
        by_id = {n.id: n for n in nodes}
        accepted = []
        for op in plan.ops:
            if isinstance(op, GroupOp):
                segments = op.category_path.split(".")[1:]
                if (
                    not segments
                    or any(
                        not CATEGORY_SEGMENT_RE.fullmatch(seg)
                        for seg in segments
                    )
                ):
                    logger.warning(
                        "Reject invalid GROUP category path: %s",
                        op.category_path,
                    )
                    continue
                if any(is_generic_category_name(seg) for seg in segments):
                    logger.warning(
                        "Reject generic GROUP category path: %s",
                        op.category_path,
                    )
                    continue
                accepted.append(op)
                continue

            if isinstance(op, MoveOp):
                segments = op.target_path.split(".")[1:]
                if any(is_generic_category_name(seg) for seg in segments):
                    logger.warning(
                        "Reject MOVE target with generic category: %s",
                        op.target_path,
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
                    logger.warning(
                        "Reject invalid RENAME category name: %s",
                        op.new_name,
                    )
                    continue
                if is_generic_category_name(op.new_name):
                    logger.warning(
                        "Reject generic RENAME category name: %s",
                        op.new_name,
                    )
                    continue
            target = by_id.get(node_id)
            if not target:
                continue
            if target.node_type != NodeType.CATEGORY:
                logger.warning("Reject leaf rename op: node_id=%s", node_id)
                continue
            accepted.append(op)
        return replace(plan, ops=tuple(accepted))

    def _sanitize_category_name(self, value: str | None) -> str | None:
        if value is None:
            return None
        candidate = value.strip().lower()
        if not candidate:
            return None
        if not CATEGORY_UPDATED_NAME_RE.fullmatch(candidate):
            logger.warning("Reject invalid updated_name: %r", value)
            return None
        return candidate

    @staticmethod
    def _sanitize_summary(value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @staticmethod
    def _sanitize_keywords(value: tuple[str, ...]) -> tuple[str, ...]:
        out = []
        seen = set()
        for item in value:
            token = item.strip().lower()
            if not token or token in seen:
                continue
            seen.add(token)
            out.append(token)
            if len(out) >= 6:
                break
        return tuple(out)
