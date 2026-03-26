"""Plan validator facade built from compiler passes."""

from __future__ import annotations

from ..core.plan.raw import RawPlan
from ..core.plan.ops import Plan
from ..core.snapshot import Snapshot
from .passes import (
    FinalValidationPass,
    GroupPathRepairPass,
    MetaValidationPass,
    RawValidationPass,
    SnapshotValidationPass,
    ValidationCode,
    ValidationReport,
)


class PlanValidator:
    """Facade preserving simple validation API over split pass modules."""

    def __init__(self):
        self._raw = RawValidationPass()
        self._meta = MetaValidationPass()
        self._snapshot = SnapshotValidationPass()
        self._repair = GroupPathRepairPass()
        self._final = FinalValidationPass()

    def validate_raw(self, raw_plan: RawPlan) -> tuple[RawPlan, ValidationReport]:
        return self._raw.run(raw_plan)

    def validate_meta(self, plan: Plan) -> tuple[Plan, ValidationReport]:
        return self._meta.run(plan)

    def validate_snapshot(
        self,
        plan: Plan,
        snapshot: Snapshot,
    ) -> tuple[Plan, ValidationReport]:
        return self._snapshot.run(plan, snapshot)

    def repair_group_paths(self, plan: Plan, snapshot: Snapshot) -> Plan:
        return self._repair.run(plan, snapshot)

    def validate_final(self, plan: Plan) -> tuple[Plan, ValidationReport]:
        return self._final.run(plan)

    @staticmethod
    def sanitize_summary(value: str | None) -> str | None:
        return RawValidationPass.sanitize_summary(value)


__all__ = [
    "PlanValidator",
    "ValidationCode",
    "ValidationReport",
]
