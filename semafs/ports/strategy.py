"""Strategy - Reorganization strategy protocol."""

from typing import Protocol, runtime_checkable

from ..core.raw import RawPlan
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

    def fallback(self, snapshot: Snapshot) -> RawPlan:
        """
        Create fallback plan (rule-based, no LLM).

        Always returns a plan (may be empty).
        """
        ...
