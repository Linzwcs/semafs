from __future__ import annotations

from ...core.plan.ops import Plan
from .common import ValidationReport


class FinalValidationPass:
    """
    Final execution-safe validation.

    Phase-2A keeps this pass intentionally light; it is the extension point
    for future strict invariants before executor staging.
    """

    def run(self, plan: Plan) -> tuple[Plan, ValidationReport]:
        return plan, ValidationReport()
