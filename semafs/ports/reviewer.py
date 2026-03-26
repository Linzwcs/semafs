"""Plan reviewer protocol for execution-time plan quality checks."""

from typing import Protocol, runtime_checkable

from ..core.plan.ops import Plan
from ..core.snapshot import Snapshot


@runtime_checkable
class PlanReviewer(Protocol):
    """Optional reviewer that can refine/drop plan ops before execution."""

    async def review(
        self,
        *,
        snapshot: Snapshot,
        plan: Plan,
    ) -> Plan:
        """Return reviewed plan (may be unchanged or filtered)."""
        ...
