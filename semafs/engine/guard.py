"""Plan guard - centralized semantic and naming constraints."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any

from ..core.node import Node, NodeType
from ..core.ops import Plan, GroupOp, MoveOp, RenameOp
from ..core.raw import RawPlan, RawMerge, RawGroup
from ..core.rules import (
    CATEGORY_SEGMENT_RE,
    CATEGORY_UPDATED_NAME_RE,
    is_generic_category_name,
    is_name_locked_node,
)
from ..core.snapshot import Snapshot

logger = logging.getLogger(__name__)
_SUMMARY_NOISE_TOKENS = (
    "op_type",
    "overall_reasoning",
    "updated_keywords",
    "\"ops\"",
)
_BULLET_PREFIX_RE = re.compile(r"^\s*(?:[-*•]+|\d+[.)])\s*")
_KEYWORD_NOISE_RE = re.compile(r"^(leaf|rollup)_[0-9a-z_]+$|^\d{1,2}:\d{2}$")
_STOPWORDS = {
    "and", "or", "the", "a", "an", "of", "to", "in", "on", "for",
    "with", "from", "by", "is", "are", "be", "this", "that",
}


class GuardRejectCode(str, Enum):
    RAW_MERGE_NO_EVIDENCE = "RAW_MERGE_NO_EVIDENCE"
    RAW_MERGE_NO_CONTENT = "RAW_MERGE_NO_CONTENT"
    RAW_GROUP_NO_SUMMARY = "RAW_GROUP_NO_SUMMARY"
    INVALID_GROUP_PATH = "INVALID_GROUP_PATH"
    GENERIC_GROUP_PATH = "GENERIC_GROUP_PATH"
    GENERIC_MOVE_TARGET = "GENERIC_MOVE_TARGET"
    INVALID_RENAME_NAME = "INVALID_RENAME_NAME"
    GENERIC_RENAME_NAME = "GENERIC_RENAME_NAME"
    LEAF_RENAME_BLOCKED = "LEAF_RENAME_BLOCKED"
    SKELETON_RENAME_BLOCKED = "SKELETON_RENAME_BLOCKED"
    INVALID_UPDATED_NAME = "INVALID_UPDATED_NAME"
    SUSPICIOUS_SUMMARY = "SUSPICIOUS_SUMMARY"
    JSON_LIKE_SUMMARY = "JSON_LIKE_SUMMARY"


@dataclass(frozen=True)
class GuardReject:
    """Structured record for one guard rejection."""

    code: GuardRejectCode
    message: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GuardReport:
    """Aggregate report of guard rejections in one validation pass."""

    rejects: tuple[GuardReject, ...] = ()

    @property
    def total_rejects(self) -> int:
        return len(self.rejects)

    def counts_by_code(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in self.rejects:
            key = item.code.value
            counts[key] = counts.get(key, 0) + 1
        return counts


class PlanGuard:
    """Validate/sanitize raw and resolved plans before execution."""

    def validate_raw_plan(
        self,
        raw_plan: RawPlan,
    ) -> tuple[RawPlan, GuardReport]:
        """
        Enforce raw-level constraints.

        Current rules:
        - MERGE must include non-empty evidence anchors.
        - updated_name must be a single english word, otherwise dropped.
        """
        accepted_ops = []
        rejects: list[GuardReject] = []
        for op in raw_plan.ops:
            if isinstance(op, RawMerge):
                evidence = tuple(e.strip() for e in op.evidence
                                 if isinstance(e, str) and e.strip())
                if not evidence:
                    self._record_reject(
                        rejects,
                        GuardRejectCode.RAW_MERGE_NO_EVIDENCE,
                        "Reject raw MERGE without evidence",
                        source_ids=op.source_ids,
                    )
                    continue
                merged_content = (op.new_content or "").strip()
                if not merged_content:
                    self._record_reject(
                        rejects,
                        GuardRejectCode.RAW_MERGE_NO_CONTENT,
                        "Reject raw MERGE without content",
                        source_ids=op.source_ids,
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
            if isinstance(op, RawGroup):
                group_summary = self._sanitize_summary(op.category_summary)
                if not group_summary:
                    self._record_reject(
                        rejects,
                        GuardRejectCode.RAW_GROUP_NO_SUMMARY,
                        "Reject raw GROUP without category summary",
                        source_ids=op.source_ids,
                    )
                    continue
                accepted_ops.append(
                    replace(
                        op,
                        category_summary=group_summary,
                        category_keywords=self._sanitize_keywords(
                            op.category_keywords
                        ),
                    )
                )
                continue
            accepted_ops.append(op)

        validated = replace(
            raw_plan,
            ops=tuple(accepted_ops),
            updated_name=self._sanitize_category_name(raw_plan.updated_name),
            updated_keywords=self._sanitize_keywords(
                raw_plan.updated_keywords
            ),
            updated_summary=self._sanitize_summary(raw_plan.updated_summary),
        )
        return validated, GuardReport(rejects=tuple(rejects))

    def validate_plan(
        self,
        plan: Plan,
    ) -> tuple[Plan, GuardReport]:
        """
        Enforce resolved-plan constraints.

        Current rules:
        - updated_name must be a single english word, otherwise dropped.
        """
        validated = replace(
            plan,
            updated_name=self._sanitize_category_name(plan.updated_name),
            updated_keywords=self._sanitize_keywords(plan.updated_keywords),
            updated_summary=self._sanitize_summary(plan.updated_summary),
        )
        return validated, GuardReport()

    def filter_ops_for_snapshot(
        self,
        plan: Plan,
        snapshot: Snapshot,
    ) -> tuple[Plan, GuardReport]:
        """
        Drop ops that violate snapshot-aware constraints.

        Current rules:
        - RENAME applies to categories only (never leaves/pending leaves).
        """
        nodes = snapshot.leaves + snapshot.pending + snapshot.subcategories
        by_id = {n.id: n for n in nodes}
        accepted = []
        rejects: list[GuardReject] = []
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
                    self._record_reject(
                        rejects,
                        GuardRejectCode.INVALID_GROUP_PATH,
                        "Reject invalid GROUP category path",
                        path=op.category_path,
                    )
                    continue
                if any(is_generic_category_name(seg) for seg in segments):
                    self._record_reject(
                        rejects,
                        GuardRejectCode.GENERIC_GROUP_PATH,
                        "Reject generic GROUP category path",
                        path=op.category_path,
                    )
                    continue
                accepted.append(op)
                continue

            if isinstance(op, MoveOp):
                segments = op.target_path.split(".")[1:]
                if any(is_generic_category_name(seg) for seg in segments):
                    self._record_reject(
                        rejects,
                        GuardRejectCode.GENERIC_MOVE_TARGET,
                        "Reject MOVE target with generic category",
                        target=op.target_path,
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
                    self._record_reject(
                        rejects,
                        GuardRejectCode.INVALID_RENAME_NAME,
                        "Reject invalid RENAME category name",
                        name=op.new_name,
                    )
                    continue
                if is_generic_category_name(op.new_name):
                    self._record_reject(
                        rejects,
                        GuardRejectCode.GENERIC_RENAME_NAME,
                        "Reject generic RENAME category name",
                        name=op.new_name,
                    )
                    continue
            target = by_id.get(node_id)
            if not target:
                continue
            if target.node_type != NodeType.CATEGORY:
                self._record_reject(
                    rejects,
                    GuardRejectCode.LEAF_RENAME_BLOCKED,
                    "Reject leaf rename op",
                    node_id=node_id,
                )
                continue
            if isinstance(op, RenameOp) and is_name_locked_node(target):
                self._record_reject(
                    rejects,
                    GuardRejectCode.SKELETON_RENAME_BLOCKED,
                    "Reject rename on locked skeleton category",
                    node_id=node_id,
                    path=target.path.value,
                )
                continue
            accepted.append(op)
        return replace(plan, ops=tuple(accepted)), GuardReport(
            rejects=tuple(rejects)
        )

    def _sanitize_category_name(self, value: str | None) -> str | None:
        if value is None:
            return None
        candidate = value.strip().lower()
        if not candidate:
            return None
        if not CATEGORY_UPDATED_NAME_RE.fullmatch(candidate):
            self._log_reject(
                GuardRejectCode.INVALID_UPDATED_NAME,
                "Reject invalid updated_name",
                value=repr(value),
            )
            return None
        return candidate

    @staticmethod
    def _sanitize_summary(value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not text:
            return None
        lowered = text.lower()
        if any(token in lowered for token in _SUMMARY_NOISE_TOKENS):
            PlanGuard._log_reject(
                GuardRejectCode.SUSPICIOUS_SUMMARY,
                "Reject suspicious updated_summary payload",
            )
            return None
        if "{" in text and "}" in text:
            PlanGuard._log_reject(
                GuardRejectCode.JSON_LIKE_SUMMARY,
                "Reject JSON-like updated_summary payload",
            )
            return None

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if lines:
            lines = [_BULLET_PREFIX_RE.sub("", line) for line in lines]
            text = " ".join(line for line in lines if line)

        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            return None
        return text[:500]

    @staticmethod
    def _sanitize_keywords(value: tuple[str, ...]) -> tuple[str, ...]:
        out = []
        seen = set()
        for item in value:
            token = re.sub(r"\s+", " ", item.strip().lower())
            if not token or token in seen:
                continue
            if token in _STOPWORDS:
                continue
            if _KEYWORD_NOISE_RE.fullmatch(token):
                continue
            if any(ch in token for ch in (":", "/", "\\")):
                continue
            seen.add(token)
            out.append(token)
            if len(out) >= 6:
                break
        return tuple(out)

    @staticmethod
    def _record_reject(
        rejects: list[GuardReject],
        code: GuardRejectCode,
        message: str,
        **detail: Any,
    ) -> None:
        PlanGuard._log_reject(code, message, **detail)
        rejects.append(GuardReject(code=code, message=message, detail=detail))

    @staticmethod
    def _log_reject(
        code: GuardRejectCode,
        message: str,
        **detail: Any,
    ) -> None:
        detail_text = " ".join(f"{k}={v!r}" for k, v in detail.items())
        if detail_text:
            logger.warning(
                "plan_guard_reject code=%s message=%s %s",
                code.value,
                message,
                detail_text,
            )
            return
        logger.warning(
            "plan_guard_reject code=%s message=%s",
            code.value,
            message,
        )
