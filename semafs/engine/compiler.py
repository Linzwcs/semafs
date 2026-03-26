"""Compiler-style plan orchestration with structured issues."""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any

from ..core.plan.ops import Plan, GroupOp, MergeOp, MoveOp, RenameOp
from ..core.plan.pipeline import CompileResult, PlanArtifact, PlanIssue
from ..core.rules import is_name_locked_node
from ..core.snapshot import Snapshot
from ..ports.planner import PlanDraftRequest
from ..ports.reviewer import PlanReviewer
from .passes import ValidationCode, ValidationReport
from .resolver import Resolver
from .validator import PlanValidator

logger = logging.getLogger(__name__)


class DefaultPlanCompiler:
    """
    Compile snapshot into executable plan.

    Phase-1 implementation keeps existing resolver/guard logic but wraps it
    in a compiler entrypoint, enabling future pass-based decomposition.
    """

    def __init__(
        self,
        *,
        planner: Any,
        resolver: Resolver,
        validator: PlanValidator,
        reviewer: PlanReviewer | None = None,
        max_attempts: int = 2,
    ):
        self._planner = planner
        self._resolver = resolver
        self._validator = validator
        self._reviewer = reviewer
        self._max_attempts = max(1, max_attempts)

    async def compile(self, snapshot: Snapshot) -> CompileResult:
        artifact = PlanArtifact(snapshot=snapshot, attempt=1)
        all_issues: list[PlanIssue] = []
        retry_feedback: dict[str, Any] = {}
        frozen_ops: list[MergeOp | GroupOp | MoveOp | RenameOp] = []

        for attempt in range(1, self._max_attempts + 1):
            artifact.attempt = attempt
            raw_plan = await self._draft(
                snapshot,
                attempt=attempt,
                retry_feedback=retry_feedback,
                frozen_ops=tuple(self._serialize_op(op) for op in frozen_ops),
            )
            if raw_plan is None:
                empty_plan = Plan(ops=tuple(frozen_ops))
                return CompileResult(
                    plan=empty_plan,
                    issues=tuple(all_issues),
                    attempts=attempt,
                    trace=tuple(artifact.trace),
                )

            raw_plan = self._enforce_target_name_guard(raw_plan, snapshot)
            raw_plan, raw_report = self._validator.validate_raw(raw_plan)
            issues_raw = self._issues_from_report(
                stage="raw",
                report=raw_report,
            )
            all_issues.extend(issues_raw)

            plan = self._resolver.compile(raw_plan, snapshot)
            plan, resolved_report = self._validator.validate_meta(plan)
            issues_resolved = self._issues_from_report(
                stage="resolved",
                report=resolved_report,
            )
            all_issues.extend(issues_resolved)

            pre_snapshot_plan = plan
            candidate_op_count = len(pre_snapshot_plan.ops)
            plan, snapshot_report = self._validator.validate_snapshot(
                plan,
                snapshot,
            )
            issues_snapshot = self._issues_from_report(
                stage="snapshot",
                report=snapshot_report,
            )
            all_issues.extend(issues_snapshot)

            if self._should_retry_group_naming(snapshot_report):
                repaired = self._validator.repair_group_paths(
                    pre_snapshot_plan,
                    snapshot,
                )
                if repaired != pre_snapshot_plan:
                    retry_plan, retry_report = (
                        self._validator.validate_snapshot(
                            repaired,
                            snapshot,
                        )
                    )
                    all_issues.extend(
                        self._issues_from_report(
                            stage="snapshot_repair",
                            report=retry_report,
                        )
                    )
                    if len(retry_plan.ops) > len(plan.ops):
                        plan = retry_plan

            if self._reviewer is not None and not plan.is_empty():
                try:
                    reviewed = await self._reviewer.review(
                        snapshot=snapshot,
                        plan=plan,
                    )
                    if len(reviewed.ops) <= len(plan.ops):
                        plan = reviewed
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "plan reviewer failed, keep current plan: %s", exc
                    )

            plan, final_report = self._validator.validate_final(plan)
            issues_final = self._issues_from_report(
                stage="final",
                report=final_report,
            )
            all_issues.extend(issues_final)

            merged_ops = self._merge_with_frozen(tuple(frozen_ops), plan.ops)
            plan = Plan(
                ops=merged_ops,
                updated_summary=plan.updated_summary,
                updated_keywords=plan.updated_keywords,
                updated_name=plan.updated_name,
                reasoning=plan.reasoning,
            )

            attempt_issues = (
                list(issues_raw)
                + list(issues_resolved)
                + list(issues_snapshot)
                + list(issues_final)
            )

            if (
                attempt < self._max_attempts
                and self._should_retry_attempt(
                    attempt_issues=attempt_issues,
                    candidate_op_count=candidate_op_count,
                    resulting_op_count=len(plan.ops),
                )
            ):
                frozen_ops = list(plan.ops)
                retry_feedback = self._build_retry_feedback(
                    snapshot=snapshot,
                    attempt=attempt + 1,
                    issues=attempt_issues,
                    frozen_ops=tuple(frozen_ops),
                )
                continue

            artifact.plan = plan
            return CompileResult(
                plan=plan,
                issues=tuple(all_issues),
                attempts=attempt,
                trace=tuple(artifact.trace),
            )

        return CompileResult(
            plan=Plan(ops=tuple(frozen_ops)),
            issues=tuple(all_issues),
            attempts=self._max_attempts,
            trace=tuple(artifact.trace),
        )

    @staticmethod
    def _enforce_target_name_guard(raw_plan, snapshot: Snapshot):
        """Force updated_name=None when current category name is locked."""
        if not is_name_locked_node(snapshot.target):
            return raw_plan
        if raw_plan.updated_name is None:
            return raw_plan
        return replace(raw_plan, updated_name=None)

    async def _draft(
        self,
        snapshot: Snapshot,
        *,
        attempt: int,
        retry_feedback: dict[str, Any],
        frozen_ops: tuple[dict[str, Any], ...],
    ):
        # New planner-style interface
        request = PlanDraftRequest(
            snapshot=snapshot,
            attempt=attempt,
            retry_feedback=dict(retry_feedback),
            frozen_ops=frozen_ops,
        )
        try:
            return await self._planner.draft(request)
        except (TypeError, AttributeError):
            # Legacy strategy interface fallback
            return await self._planner.draft(snapshot)

    @staticmethod
    def _issues_from_report(
        *,
        stage: str,
        report: ValidationReport,
    ) -> list[PlanIssue]:
        out: list[PlanIssue] = []
        for reject in report.rejects:
            severity = "drop"
            if reject.code in {
                ValidationCode.INVALID_GROUP_PATH,
                ValidationCode.DUPLICATE_GROUP_SEGMENTS,
                ValidationCode.REDUNDANT_GROUP_SEGMENT,
                ValidationCode.REDUNDANT_UPDATED_NAME,
                ValidationCode.SEMANTIC_GROUP_OVERLAP,
                ValidationCode.GENERIC_GROUP_PATH,
            }:
                severity = "retry"
            out.append(
                PlanIssue(
                    code=reject.code.value,
                    stage=stage,
                    severity=severity,  # type: ignore[arg-type]
                    message=reject.message,
                    op_index=reject.detail.get("op_index"),
                    hint=(
                        reject.detail.get("suggestion")
                        or reject.detail.get("overlap_with")
                        or reject.detail.get("forbidden_match")
                        or reject.detail.get("path")
                        or reject.detail.get("target")
                        or reject.detail.get("name")
                        or ""
                    ),
                    meta=dict(reject.detail),
                )
            )
        return out

    @staticmethod
    def _should_retry_group_naming(report: ValidationReport) -> bool:
        retryable = {
            ValidationCode.DUPLICATE_GROUP_SEGMENTS.value,
            ValidationCode.REDUNDANT_GROUP_SEGMENT.value,
            ValidationCode.GENERIC_GROUP_PATH.value,
        }
        counts = report.counts_by_code()
        return any(counts.get(code, 0) > 0 for code in retryable)

    @staticmethod
    def _has_retryable_issues(issues: list[PlanIssue]) -> bool:
        return any(item.severity == "retry" for item in issues)

    @classmethod
    def _should_retry_attempt(
        cls,
        *,
        attempt_issues: list[PlanIssue],
        candidate_op_count: int,
        resulting_op_count: int,
    ) -> bool:
        if not cls._has_retryable_issues(attempt_issues):
            return False
        if candidate_op_count <= 0:
            return False
        return resulting_op_count < candidate_op_count

    @staticmethod
    def _merge_with_frozen(
        frozen_ops: tuple[MergeOp | GroupOp | MoveOp | RenameOp, ...],
        new_ops: tuple[MergeOp | GroupOp | MoveOp | RenameOp, ...],
    ) -> tuple[MergeOp | GroupOp | MoveOp | RenameOp, ...]:
        merged: list[MergeOp | GroupOp | MoveOp | RenameOp] = []
        seen: set[tuple] = set()
        for op in frozen_ops + new_ops:
            sig = DefaultPlanCompiler._op_signature(op)
            if sig in seen:
                continue
            seen.add(sig)
            merged.append(op)
        return tuple(merged)

    @staticmethod
    def _op_signature(op: MergeOp | GroupOp | MoveOp | RenameOp) -> tuple:
        if isinstance(op, MergeOp):
            return ("merge", tuple(sorted(op.source_ids)), op.new_name)
        if isinstance(op, GroupOp):
            return ("group", tuple(sorted(op.source_ids)), op.category_path)
        if isinstance(op, MoveOp):
            return ("move", op.leaf_id, op.target_path)
        return ("rename", op.node_id, op.new_name)

    @classmethod
    def _build_retry_feedback(
        cls,
        *,
        snapshot: Snapshot,
        attempt: int,
        issues: list[PlanIssue],
        frozen_ops: tuple[MergeOp | GroupOp | MoveOp | RenameOp, ...],
    ) -> dict[str, Any]:
        must_fix = []
        for issue in issues:
            if issue.severity != "retry":
                continue
            must_fix.append(
                {
                    "op_index": issue.op_index,
                    "code": issue.code,
                    "hint": issue.hint or issue.message,
                }
            )
            if len(must_fix) >= 12:
                break

        forbidden = [snapshot.target.name] + [
            sub.name for sub in snapshot.subcategories
        ]
        return {
            "attempt": attempt,
            "must_fix": must_fix,
            "frozen_ops": [cls._serialize_op(op) for op in frozen_ops],
            "forbidden_segments": [name for name in forbidden if name],
        }

    @staticmethod
    def _serialize_op(op: MergeOp | GroupOp | MoveOp | RenameOp) -> dict[str, Any]:
        if isinstance(op, MergeOp):
            return {
                "op_type": "MERGE",
                "source_ids": list(op.source_ids),
                "new_name": op.new_name,
            }
        if isinstance(op, GroupOp):
            return {
                "op_type": "GROUP",
                "source_ids": list(op.source_ids),
                "category_path": op.category_path,
                "keywords": list(op.category_keywords),
            }
        if isinstance(op, MoveOp):
            return {
                "op_type": "MOVE",
                "leaf_id": op.leaf_id,
                "target_path": op.target_path,
            }
        return {
            "op_type": "RENAME",
            "node_id": op.node_id,
            "new_name": op.new_name,
        }
