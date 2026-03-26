"""LLM-based plan reviewer for pre-execution structure quality checks."""

from __future__ import annotations

import logging
import re
from dataclasses import replace

from ...core.capacity import Zone
from ...core.plan.ops import Plan, GroupOp
from ...core.snapshot import Snapshot
from ...ports.llm import LLMAdapter
from ...ports.reviewer import PlanReviewer

logger = logging.getLogger(__name__)
_PLACEHOLDER_SEGMENT_RE = re.compile(r"^(topic|category|cluster)[a-z]*$")


class LLMPlanReviewer(PlanReviewer):
    """Use LLM to keep/drop candidate ops based on structural quality."""

    def __init__(self, adapter: LLMAdapter):
        self._adapter = adapter

    async def review(
        self,
        *,
        snapshot: Snapshot,
        plan: Plan,
    ) -> Plan:
        if plan.is_empty():
            return plan
        # Always apply local deterministic filters first.
        candidate = self._drop_placeholder_groups(snapshot, plan)
        if candidate.is_empty():
            return candidate

        try:
            payload = await self._adapter.call_plan_review(snapshot, candidate)
        except Exception as exc:
            logger.warning("plan review call failed, keep original plan: %s", exc)
            return candidate

        keep_indices = self._parse_keep_indices(payload, len(candidate.ops))
        if keep_indices is None:
            return candidate
        if len(keep_indices) == len(candidate.ops):
            return candidate
        drop_reasons = self._parse_drop_reasons(payload, len(candidate.ops))
        dropped_indices = [
            idx for idx in range(len(candidate.ops))
            if idx not in keep_indices
        ]
        missing_reasons = [
            idx for idx in dropped_indices if idx not in drop_reasons
        ]
        if missing_reasons:
            logger.warning(
                ("plan reviewer missing drop reasons for dropped ops "
                 "indices=%s; ignore review"),
                missing_reasons,
            )
            return candidate
        for idx in dropped_indices:
            logger.info(
                "plan reviewer drop idx=%d reason=%s",
                idx,
                drop_reasons.get(idx, ""),
            )

        filtered_ops = tuple(
            op for idx, op in enumerate(candidate.ops) if idx in keep_indices
        )
        reviewed = replace(candidate, ops=filtered_ops)
        if (
            reviewed.is_empty()
            and not candidate.is_empty()
            and snapshot.zone != Zone.HEALTHY
        ):
            logger.info(
                ("plan reviewer attempted full drop under non-healthy zone; "
                 "ignore review and keep local-filtered plan")
            )
            return candidate
        return reviewed

    @staticmethod
    def _parse_keep_indices(
        payload: dict,
        total_ops: int,
    ) -> set[int] | None:
        raw_keep = payload.get("keep_op_indices")
        decision = str(payload.get("decision", "")).strip().lower()
        if not isinstance(raw_keep, list):
            if decision == "reject":
                return set()
            return None

        keep: set[int] = set()
        for item in raw_keep:
            if not isinstance(item, int):
                continue
            if 0 <= item < total_ops:
                keep.add(item)
        if not keep and decision == "accept":
            return set(range(total_ops))
        return keep

    @staticmethod
    def _parse_drop_reasons(payload: dict, total_ops: int) -> dict[int, str]:
        raw = payload.get("drop_reasons")
        if not isinstance(raw, list):
            return {}
        parsed: dict[int, str] = {}
        for item in raw:
            if not isinstance(item, dict):
                continue
            op_index = item.get("op_index")
            if not isinstance(op_index, int):
                continue
            if not (0 <= op_index < total_ops):
                continue
            reason = str(item.get("reason", "")).strip()
            if not reason:
                continue
            parsed[op_index] = reason[:240]
        return parsed

    def _drop_placeholder_groups(self, snapshot: Snapshot, plan: Plan) -> Plan:
        """Local hard filter to prevent placeholder-like group paths."""
        if snapshot.target.skeleton:
            return plan
        kept = []
        for op in plan.ops:
            if not isinstance(op, GroupOp):
                kept.append(op)
                continue
            rel = self._relative_segments(
                op.category_path,
                snapshot.target.path.value,
            )
            if not rel:
                continue
            if self._has_invalid_group_path(rel):
                logger.warning(
                    "plan reviewer dropped invalid group path: %s",
                    op.category_path,
                )
                continue
            if _PLACEHOLDER_SEGMENT_RE.fullmatch(rel[0]):
                logger.warning(
                    "plan reviewer dropped placeholder group path: %s",
                    op.category_path,
                )
                continue
            kept.append(op)
        if len(kept) == len(plan.ops):
            return plan
        return replace(plan, ops=tuple(kept))

    def _has_invalid_group_path(self, relative_segments: list[str]) -> bool:
        if not relative_segments:
            return True
        # Reject repeated segments (e.g. root.work.work / root.a.b.a).
        seen: set[str] = set()
        for seg in relative_segments:
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
