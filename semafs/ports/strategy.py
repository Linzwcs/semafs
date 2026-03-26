"""Strategy - Reorganization strategy protocol."""

from typing import Protocol, runtime_checkable

from ..core.plan.raw import RawPlan
from ..core.snapshot import Snapshot


@runtime_checkable
class Strategy(Protocol):
    """Reorganization strategy interface."""

    async def draft(self, snapshot: Snapshot) -> RawPlan | None:
        """
        Create reorganization plan from snapshot.

        Returns None if no reorganization needed.
        """
        ...
