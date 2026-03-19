"""LLMAdapter - LLM API call protocol."""

from typing import Protocol, runtime_checkable

from ..core.snapshot import Snapshot


@runtime_checkable
class LLMAdapter(Protocol):
    """LLM API call interface."""

    async def call(self, snapshot: Snapshot) -> dict:
        """
        Call LLM with snapshot context.

        Returns raw LLM response as dict.
        """
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
        children: tuple[dict[str, str], ...],
    ) -> dict:
        """Call LLM for one placement routing step."""
        ...
