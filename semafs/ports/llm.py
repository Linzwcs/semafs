"""LLMAdapter - LLM API call protocol."""

from typing import Any, Protocol, runtime_checkable

from ..core.plan.ops import Plan
from ..core.snapshot import Snapshot


@runtime_checkable
class LLMAdapter(Protocol):
    """LLM API call interface."""

    async def call(
            self,
            snapshot: Snapshot,
            *,
            retry_feedback: dict[str, Any] | None = None,
            frozen_ops: tuple[dict[str, Any], ...] = (),
    ) -> dict:
        """
        Call LLM with snapshot context.

        Returns raw LLM response as dict.
        """
        ...

    async def call_plan_review(self, snapshot: Snapshot, plan: Plan) -> dict:
        """Call LLM for plan structure review (pre-execution)."""
        ...

    async def call_summary(self, snapshot: Snapshot) -> dict:
        """Call LLM for category summary generation."""
        ...

    async def call_placement(
        self,
        *,
        content: str,
        current_path: str,
        current_summary: str,
        children: tuple[dict[str, Any], ...],
    ) -> dict:
        """Call LLM for one placement routing step."""
        ...
